from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass

import logging

from omniai.domain.knowledge.models import Document
from omniai.plugins.parsers import ParserRegistry
from omniai.ports.object_store import ObjectStorePort
from omniai.ports.queue import JobQueuePort
from omniai.ports.relational import KnowledgeStorePort
from omniai.ports.search_engine import SearchEnginePort

logger = logging.getLogger(__name__)


PARSE_JOB_NAME = "parse_document"


@dataclass(slots=True)
class StoredUpload:
    object_key: str
    sha256: str
    size_bytes: int
    mime_type: str


def build_object_key(*, tenant_id: str, collection_id: str, sha256: str, ext: str) -> str:
    return f"tenants/{tenant_id}/collections/{collection_id}/sources/{sha256}{ext}"


def build_parsed_text_key(*, tenant_id: str, collection_id: str, document_id: str) -> str:
    return f"tenants/{tenant_id}/collections/{collection_id}/parsed/{document_id}.txt"


class IngestionService:
    def __init__(
        self,
        *,
        store: KnowledgeStorePort,
        object_store: ObjectStorePort,
        queue: JobQueuePort,
        parsers: ParserRegistry,
        tenant_id: str,
        max_bytes: int,
        tenant_max_documents: int = 0,
        tenant_max_storage_bytes: int = 0,
    ) -> None:
        self._store = store
        self._object_store = object_store
        self._queue = queue
        self._parsers = parsers
        self._tenant_id = tenant_id
        self._max_bytes = max_bytes
        self._tenant_max_documents = tenant_max_documents
        self._tenant_max_storage_bytes = tenant_max_storage_bytes

    async def upload_document(
        self,
        *,
        collection_id: str,
        filename: str,
        mime_type: str,
        data: bytes,
        search_engine: SearchEnginePort | None = None,
    ) -> Document:
        """Upload or re-upload a document.

        Document versioning behaviour:
        - **New document**: standard create + enqueue flow.
        - **Same filename, identical content** (sha256 match): returns the
          existing document unchanged.  No re-processing, no duplicate stored.
        - **Same filename, changed content**: updates the existing document
          record in-place (new object key, new sha256, status reset to PENDING),
          clears the old search index for that document, and re-enqueues parsing.
        """
        if len(data) == 0:
            raise ValueError("Uploaded file is empty.")
        if len(data) > self._max_bytes:
            raise ValueError(
                f"File exceeds upload limit of {self._max_bytes} bytes "
                f"(received {len(data)})."
            )
        if self._parsers.resolve(mime_type=mime_type, filename=filename) is None:
            raise ValueError(
                f"Unsupported file type: mime={mime_type!r}, filename={filename!r}."
            )

        sha256 = hashlib.sha256(data).hexdigest()
        ext = os.path.splitext(filename)[1].lower() or ".bin"
        object_key = build_object_key(
            tenant_id=self._tenant_id,
            collection_id=collection_id,
            sha256=sha256,
            ext=ext,
        )

        # ── Document versioning check ──────────────────────────────────────
        existing = self._store.find_document_by_name(collection_id, filename)
        if existing is not None:
            if existing.content_sha256 == sha256:
                # Bit-identical re-upload → deduplicate silently
                logger.debug(
                    "Skipping re-upload of unchanged document %s in collection %s",
                    filename,
                    collection_id,
                )
                return existing

            # Content changed → update in-place
            logger.info(
                "Updating document %s (id=%s) in collection %s with new content",
                filename,
                existing.id,
                collection_id,
            )
            # Store the new binary first so the object exists before we commit
            self._object_store.put_object(
                key=object_key,
                data=io.BytesIO(data),
                content_type=mime_type,
                size=len(data),
            )
            # Clear stale search index entries for the old version
            if search_engine is not None:
                try:
                    search_engine.delete_by_document(
                        tenant_id=self._tenant_id,
                        document_id=existing.id,
                    )
                except Exception:
                    pass  # non-fatal; indexing worker will overwrite them
            # Update DB record
            document = self._store.update_document_storage(
                document_id=existing.id,
                object_key=object_key,
                content_sha256=sha256,
                size_bytes=len(data),
            )
            await self._queue.enqueue(
                job_name=PARSE_JOB_NAME,
                payload={
                    "tenant_id": self._tenant_id,
                    "document_id": document.id,
                },
            )
            return document

        # ── Normal (new) document creation ────────────────────────────────

        # Tenant-level quota enforcement
        if self._tenant_max_documents > 0:
            current = self._store.count_documents()
            if current >= self._tenant_max_documents:
                raise ValueError(
                    f"Tenant document quota reached ({current}/{self._tenant_max_documents})."
                )
        if self._tenant_max_storage_bytes > 0:
            used = sum(d.size_bytes for d in self._store_all_documents())
            if used + len(data) > self._tenant_max_storage_bytes:
                raise ValueError(
                    f"Tenant storage quota exceeded "
                    f"({(used + len(data)) // (1024 * 1024)} MiB > "
                    f"{self._tenant_max_storage_bytes // (1024 * 1024)} MiB)."
                )

        self._object_store.put_object(
            key=object_key,
            data=io.BytesIO(data),
            content_type=mime_type,
            size=len(data),
        )

        document = self._store.create_document_with_storage(
            collection_id=collection_id,
            name=filename,
            mime_type=mime_type,
            size_bytes=len(data),
            object_key=object_key,
            content_sha256=sha256,
        )

        await self._queue.enqueue(
            job_name=PARSE_JOB_NAME,
            payload={
                "tenant_id": self._tenant_id,
                "document_id": document.id,
            },
        )
        return document

    def _store_all_documents(self):
        # Collect documents across all collections to compute storage usage.
        all_docs = []
        for collection in self._store.list_collections():
            try:
                all_docs.extend(self._store.list_documents(collection.id))
            except KeyError:
                continue
        return all_docs

    def get_download_url(self, *, document_id: str, expires_seconds: int = 600) -> str:
        document = self._store.get_document(document_id)
        if document.object_key is None:
            raise FileNotFoundError("Document has no stored object.")
        return self._object_store.presigned_get_url(
            key=document.object_key,
            expires_seconds=expires_seconds,
        )

    def get_parsed_text(self, *, document_id: str) -> str:
        document = self._store.get_document(document_id)
        if document.parsed_text_key is None:
            raise FileNotFoundError("Document has no parsed text yet.")
        return self._object_store.get_object(key=document.parsed_text_key).decode("utf-8")

    def delete_document(self, *, document_id: str, search_engine: SearchEnginePort | None = None) -> None:
        document = self._store.get_document(document_id)

        if search_engine is not None:
            try:
                search_engine.delete_by_document(tenant_id=self._tenant_id, document_id=document_id)
            except Exception:
                logger.debug("delete_document: search index cleanup failed", exc_info=True)

        # Remove stored objects
        for key in (document.object_key, document.parsed_text_key):
            if key:
                try:
                    self._object_store.delete_object(key=key)
                except Exception:
                    pass

        self._store.delete_document(document_id=document_id)

    def delete_collection(
        self,
        *,
        collection_id: str,
        search_engine: SearchEnginePort | None = None,
    ) -> None:
        documents = list(self._store.list_documents(collection_id))
        for document in documents:
            self.delete_document(document_id=document.id, search_engine=search_engine)
        self._store.delete_collection(collection_id=collection_id)
