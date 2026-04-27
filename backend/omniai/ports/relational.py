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

    def create_document_with_storage(
        self,
        *,
        collection_id: str,
        name: str,
        mime_type: str,
        size_bytes: int,
        object_key: str,
        content_sha256: str,
    ) -> Document: ...

    def list_documents(self, collection_id: str) -> list[Document]: ...

    def get_document(self, document_id: str) -> Document: ...

    def update_status(
        self,
        *,
        document_id: str,
        status: str,
        error_message: str | None = None,
        parsed_text_key: str | None = None,
        page_count: int | None = None,
        parser_name: str | None = None,
    ) -> Document: ...

    def count_collections(self) -> int: ...

    def count_documents(self) -> int: ...
