from __future__ import annotations

from dataclasses import dataclass

from omniai.ports.embedding_provider import EmbeddingProviderPort
from omniai.ports.search_engine import SearchEnginePort, SearchHit


@dataclass(slots=True)
class RetrievalRequest:
    query: str
    top_k: int = 8
    vector_weight: float = 0.6
    collection_ids: list[str] | None = None
    embedding_model: str = "nomic-embed-text"


@dataclass(slots=True)
class RetrievalResponse:
    hits: list[SearchHit]
    embedding_model: str
    vector_weight: float


class RetrievalService:
    def __init__(
        self,
        *,
        search_engine: SearchEnginePort,
        embedding_provider: EmbeddingProviderPort,
        tenant_id: str,
    ) -> None:
        self._search = search_engine
        self._embeddings = embedding_provider
        self._tenant_id = tenant_id

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        if not request.query.strip():
            return RetrievalResponse(hits=[], embedding_model=request.embedding_model, vector_weight=request.vector_weight)

        try:
            vectors = await self._embeddings.embed(model=request.embedding_model, inputs=[request.query])
            query_vector = vectors[0]
        except Exception:
            query_vector = []

        hits = self._search.hybrid_search(
            tenant_id=self._tenant_id,
            query=request.query,
            query_vector=query_vector,
            top_k=request.top_k,
            vector_weight=request.vector_weight,
            collection_ids=request.collection_ids,
        )
        return RetrievalResponse(
            hits=hits,
            embedding_model=request.embedding_model,
            vector_weight=request.vector_weight,
        )
