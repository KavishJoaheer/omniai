from __future__ import annotations

from pydantic import BaseModel, Field

from omniai.application.store import KnowledgeStore
from omniai.domain.knowledge.models import Collection, Document


class CreateCollectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    embedding_model: str = "text-embedding-default"
    chunk_template: str = "general"


class CreateDocumentInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    mime_type: str = "application/octet-stream"
    size_bytes: int = Field(default=0, ge=0)


class KnowledgeService:
    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    def list_collections(self) -> list[Collection]:
        return self._store.list_collections()

    def create_collection(self, payload: CreateCollectionInput) -> Collection:
        return self._store.create_collection(
            name=payload.name,
            description=payload.description,
            embedding_model=payload.embedding_model,
            chunk_template=payload.chunk_template,
        )

    def get_collection(self, collection_id: str) -> Collection:
        return self._store.get_collection(collection_id)

    def list_documents(self, collection_id: str) -> list[Document]:
        return self._store.list_documents(collection_id)

    def create_document(self, collection_id: str, payload: CreateDocumentInput) -> Document:
        return self._store.create_document(
            collection_id=collection_id,
            name=payload.name,
            mime_type=payload.mime_type,
            size_bytes=payload.size_bytes,
        )

    def count_collections(self) -> int:
        return self._store.count_collections()

    def count_documents(self) -> int:
        return self._store.count_documents()
