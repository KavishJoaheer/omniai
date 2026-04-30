from __future__ import annotations

from datetime import datetime
from typing import Protocol

from omniai.domain.knowledge.models import Chunk, Collection, CollectionMembership, Document, GraphTriple


class KnowledgeStorePort(Protocol):
    def list_collections(self) -> list[Collection]: ...

    def create_collection(
        self,
        *,
        name: str,
        description: str | None,
        embedding_model: str,
        chunk_template: str,
        system_prompt: str | None = None,
        top_k: int = 8,
        vector_weight: float = 0.6,
    ) -> Collection: ...

    def get_collection(self, collection_id: str) -> Collection: ...

    def update_collection(
        self,
        *,
        collection_id: str,
        name: str | None = None,
        description: str | None = None,
        embedding_model: str | None = None,
        chunk_template: str | None = None,
        system_prompt: str | None = None,
        top_k: int | None = None,
        vector_weight: float | None = None,
    ) -> Collection: ...

    def delete_collection(self, *, collection_id: str) -> None: ...

    # ---- per-collection RBAC --------------------------------------------------

    def list_collection_members(self, *, collection_id: str) -> list[CollectionMembership]: ...

    def upsert_collection_member(
        self,
        *,
        collection_id: str,
        user_id: str,
        role: str,
    ) -> CollectionMembership: ...

    def remove_collection_member(self, *, collection_id: str, user_id: str) -> None: ...

    def collection_member_role(
        self,
        *,
        collection_id: str,
        user_id: str,
    ) -> str | None:
        """Returns the user's role in the collection, or None if they're not a member."""
        ...

    def list_collection_ids_for_user(self, *, user_id: str) -> list[str]:
        """Returns the IDs of every collection the user is a member of."""
        ...

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

    def find_document_by_name(self, collection_id: str, name: str) -> Document | None:
        """Return the first document in *collection_id* whose filename matches *name*, or ``None``."""
        ...

    def update_document_storage(
        self,
        *,
        document_id: str,
        object_key: str,
        content_sha256: str,
        size_bytes: int,
    ) -> Document:
        """Overwrite storage metadata for an existing document and reset its status to PENDING."""
        ...

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

    def replace_chunks(
        self,
        *,
        document_id: str,
        chunks: list[dict],
        template_name: str,
    ) -> list[Chunk]: ...

    def get_chunk_by_id(self, chunk_id: str) -> Chunk: ...

    def list_chunks(self, *, document_id: str) -> list[Chunk]: ...

    def mark_chunks_indexed(self, *, document_id: str, indexed_at: datetime) -> None: ...

    def delete_document(self, *, document_id: str) -> None: ...

    def set_document_tags(self, *, document_id: str, tags: list[str]) -> Document: ...

    def list_documents_by_tag(self, *, collection_id: str | None, tag: str) -> list[Document]: ...

    def replace_graph_triples(self, *, document_id: str, triples: list[dict]) -> list[GraphTriple]: ...

    def list_graph_triples(
        self,
        *,
        collection_id: str | None = None,
        document_id: str | None = None,
        entity: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GraphTriple]: ...

    def count_collections(self) -> int: ...

    def count_documents(self) -> int: ...
