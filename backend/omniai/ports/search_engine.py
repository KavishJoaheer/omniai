from __future__ import annotations

from typing import Any, Protocol


class SearchEnginePort(Protocol):
    def ensure_index(self, *, index: str, dim: int) -> None: ...

    def upsert_chunks(self, *, index: str, chunks: list[dict[str, Any]]) -> None: ...

    def delete_by_document(self, *, index: str, document_id: str) -> None: ...

    def hybrid_search(
        self,
        *,
        index: str,
        query: str,
        query_vector: list[float],
        top_k: int,
        vector_weight: float,
        metadata_filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...
