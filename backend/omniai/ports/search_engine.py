from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class SearchHit:
    chunk_id: str
    document_id: str
    collection_id: str
    score: float
    text: str
    snippet: str
    metadata: dict


@dataclass(slots=True)
class IndexableChunk:
    chunk_id: str
    document_id: str
    collection_id: str
    text: str
    vector: list[float]
    metadata: dict


class SearchEnginePort(Protocol):
    def ensure_index(self, *, tenant_id: str, dim: int) -> str: ...

    def upsert_chunks(self, *, tenant_id: str, chunks: list[IndexableChunk]) -> None: ...

    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None: ...

    def hybrid_search(
        self,
        *,
        tenant_id: str,
        query: str,
        query_vector: list[float],
        top_k: int,
        vector_weight: float,
        collection_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
    ) -> list[SearchHit]: ...
