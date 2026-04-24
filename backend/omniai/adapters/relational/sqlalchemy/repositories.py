from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import CollectionRecord, DocumentRecord, TenantRecord
from omniai.application.store import KnowledgeStore
from omniai.domain.knowledge.models import Collection, Document, utc_now


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
    def _to_document(record: DocumentRecord) -> Document:
        return Document(
            id=record.id,
            tenant_id=record.tenant_id,
            collection_id=record.collection_id,
            name=record.name,
            mime_type=record.mime_type,
            size_bytes=record.size_bytes,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

