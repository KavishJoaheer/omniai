from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import (
    ChunkRecord,
    CollectionRecord,
    DocumentRecord,
    TenantRecord,
)
from omniai.application.store import KnowledgeStore
from omniai.domain.knowledge.models import Chunk, Collection, Document, utc_now


def ensure_tenant(session: Session, *, slug: str, name: str) -> TenantRecord:
    tenant = session.scalar(select(TenantRecord).where(TenantRecord.slug == slug))
    if tenant is not None:
        return tenant

    tenant = TenantRecord(slug=slug, name=name)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return tenant


class SqlAlchemyKnowledgeStore(KnowledgeStore):
    def __init__(self, session: Session, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def list_collections(self) -> list[Collection]:
        statement = (
            select(CollectionRecord)
            .where(CollectionRecord.tenant_id == self._tenant_id)
            .order_by(CollectionRecord.created_at.asc())
        )
        return [self._to_collection(record) for record in self._session.scalars(statement)]

    def create_collection(
        self,
        *,
        name: str,
        description: str | None,
        embedding_model: str,
        chunk_template: str,
    ) -> Collection:
        duplicate = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.tenant_id == self._tenant_id,
                func.lower(CollectionRecord.name) == name.lower(),
            )
        )
        if duplicate is not None:
            raise ValueError("A collection with that name already exists.")

        record = CollectionRecord(
            tenant_id=self._tenant_id,
            name=name,
            description=description,
            embedding_model=embedding_model,
            chunk_template=chunk_template,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_collection(record)

    def get_collection(self, collection_id: str) -> Collection:
        record = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Collection not found.")
        return self._to_collection(record)

    def create_document(
        self,
        *,
        collection_id: str,
        name: str,
        mime_type: str,
        size_bytes: int,
    ) -> Document:
        collection = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if collection is None:
            raise KeyError("Collection not found.")

        record = DocumentRecord(
            tenant_id=self._tenant_id,
            collection_id=collection_id,
            name=name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            status="PENDING",
        )
        collection.document_count += 1
        collection.updated_at = utc_now()
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_document(record)

    def list_documents(self, collection_id: str) -> list[Document]:
        collection = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if collection is None:
            raise KeyError("Collection not found.")

        statement = (
            select(DocumentRecord)
            .where(
                DocumentRecord.collection_id == collection_id,
                DocumentRecord.tenant_id == self._tenant_id,
            )
            .order_by(DocumentRecord.created_at.asc())
        )
        return [self._to_document(record) for record in self._session.scalars(statement)]

    def get_document(self, document_id: str) -> Document:
        record = self._get_document_record(document_id)
        return self._to_document(record)

    def create_document_with_storage(
        self,
        *,
        collection_id: str,
        name: str,
        mime_type: str,
        size_bytes: int,
        object_key: str,
        content_sha256: str,
    ) -> Document:
        collection = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if collection is None:
            raise KeyError("Collection not found.")

        record = DocumentRecord(
            tenant_id=self._tenant_id,
            collection_id=collection_id,
            name=name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            status="PENDING",
            object_key=object_key,
            content_sha256=content_sha256,
        )
        collection.document_count += 1
        collection.updated_at = utc_now()
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_document(record)

    def update_status(
        self,
        *,
        document_id: str,
        status: str,
        error_message: str | None = None,
        parsed_text_key: str | None = None,
        page_count: int | None = None,
        parser_name: str | None = None,
    ) -> Document:
        record = self._get_document_record(document_id)
        record.status = status
        if status == "FAILED":
            record.error_message = error_message
        elif status in ("PARSED", "READY"):
            record.error_message = None
            if status == "PARSED":
                record.parsed_at = utc_now()
            if parsed_text_key is not None:
                record.parsed_text_key = parsed_text_key
            if page_count is not None:
                record.page_count = page_count
            if parser_name is not None:
                record.parser_name = parser_name
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_document(record)

    def replace_chunks(
        self,
        *,
        document_id: str,
        chunks: list[dict],
        template_name: str,
    ) -> list[Chunk]:
        document = self._get_document_record(document_id)
        self._session.execute(delete(ChunkRecord).where(ChunkRecord.document_id == document_id))
        records: list[ChunkRecord] = []
        for ordinal, chunk in enumerate(chunks):
            text = chunk["text"]
            metadata = chunk.get("metadata") or {}
            record = ChunkRecord(
                tenant_id=self._tenant_id,
                collection_id=document.collection_id,
                document_id=document_id,
                ordinal=ordinal,
                text=text,
                char_count=len(text),
                token_count=max(1, len(text.split())),
                template_name=template_name,
                metadata_json=json.dumps(metadata, separators=(",", ":"), sort_keys=True),
            )
            self._session.add(record)
            records.append(record)
        self._session.commit()
        for record in records:
            self._session.refresh(record)
        return [self._to_chunk(r) for r in records]

    def list_chunks(self, *, document_id: str) -> list[Chunk]:
        statement = (
            select(ChunkRecord)
            .where(
                ChunkRecord.document_id == document_id,
                ChunkRecord.tenant_id == self._tenant_id,
            )
            .order_by(ChunkRecord.ordinal.asc())
        )
        return [self._to_chunk(r) for r in self._session.scalars(statement)]

    def mark_chunks_indexed(self, *, document_id: str, indexed_at: datetime) -> None:
        records = self._session.scalars(
            select(ChunkRecord).where(
                ChunkRecord.document_id == document_id,
                ChunkRecord.tenant_id == self._tenant_id,
            )
        )
        for record in records:
            record.indexed_at = indexed_at
        self._session.commit()

    def _get_document_record(self, document_id: str) -> DocumentRecord:
        record = self._session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == document_id,
                DocumentRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Document not found.")
        return record

    def count_collections(self) -> int:
        statement = select(func.count(CollectionRecord.id)).where(CollectionRecord.tenant_id == self._tenant_id)
        return int(self._session.scalar(statement) or 0)

    def count_documents(self) -> int:
        statement = select(func.count(DocumentRecord.id)).where(DocumentRecord.tenant_id == self._tenant_id)
        return int(self._session.scalar(statement) or 0)

    @staticmethod
    def _to_collection(record: CollectionRecord) -> Collection:
        return Collection(
            id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            description=record.description,
            embedding_model=record.embedding_model,
            chunk_template=record.chunk_template,
            created_at=record.created_at,
            updated_at=record.updated_at,
            document_count=record.document_count,
        )

    @staticmethod
    def _to_chunk(record: ChunkRecord) -> Chunk:
        try:
            metadata = json.loads(record.metadata_json) if record.metadata_json else {}
        except json.JSONDecodeError:
            metadata = {}
        return Chunk(
            id=record.id,
            tenant_id=record.tenant_id,
            collection_id=record.collection_id,
            document_id=record.document_id,
            ordinal=record.ordinal,
            text=record.text,
            char_count=record.char_count,
            token_count=record.token_count,
            template_name=record.template_name,
            metadata=metadata,
            indexed_at=record.indexed_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _to_document(record: DocumentRecord) -> Document:
        return Document(
            id=record.id,
            tenant_id=record.tenant_id,
            collection_id=record.collection_id,
            name=record.name,
            mime_type=record.mime_type,
            size_bytes=record.size_bytes,
            status=record.status,
            object_key=record.object_key,
            parsed_text_key=record.parsed_text_key,
            content_sha256=record.content_sha256,
            page_count=record.page_count,
            parser_name=record.parser_name,
            error_message=record.error_message,
            parsed_at=record.parsed_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

