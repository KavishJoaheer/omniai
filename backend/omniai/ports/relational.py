from __future__ import annotations

from typing import Protocol

from omniai.domain.knowledge.models import Collection, Document


class KnowledgeStorePort(Protocol):
    def list_collections(self) -> list[Collection]: ...

    def create_collection(
        self,
        *,
        name: str,
        description: str | None,
        embedding_model: str,
        chunk_template: str,
    ) -> Collection: ...

    def get_collection(self, collection_id: str) -> Collection: ...

    def create_document(
        self,
        *,
        collection_id: str,
        name: str,
        mime_type: str,
        size_bytes: int,
    ) -> Document: ...

    def list_documents(self, collection_id: str) -> list[Document]: ...

    def count_collections(self) -> int: ...

    def count_documents(self) -> int: ...
