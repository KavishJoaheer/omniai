from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass

from omniai.domain.knowledge.models import Document
from omniai.plugins.parsers import ParserRegistry
from omniai.ports.object_store import ObjectStorePort
from omniai.ports.queue import JobQueuePort
from omniai.ports.relational import KnowledgeStorePort


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
    ) -> None:
        self._store = store
        self._object_store = object_store
        self._queue = queue
        self._parsers = parsers
        self._tenant_id = tenant_id
        self._max_bytes = max_bytes

    async def upload_document(
        self,
        *,
        collection_id: str,
        filename: str,
        mime_type: str,
        data: bytes,
    ) -> Document:
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
