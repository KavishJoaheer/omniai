from __future__ import annotations

from dataclasses import dataclass

from omniai.ports.embedding_provider import EmbeddingProviderPort
from omniai.ports.relational import KnowledgeStorePort
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
        store: KnowledgeStorePort | None = None,
    ) -> None:
        self._search = search_engine
        self._embeddings = embedding_provider
        self._tenant_id = tenant_id
        self._store = store

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

        # Apply MMR diversification when we have more hits than needed
        if len(hits) > 1:
            hits = _mmr(hits, query_vector, top_k=request.top_k)

        # Expand child hits to parent text for small-to-big templates
        if self._store is not None:
            hits = _expand_to_parents(hits, self._store)

        return RetrievalResponse(
            hits=hits,
            embedding_model=request.embedding_model,
            vector_weight=request.vector_weight,
        )


def _mmr(
    hits: list[SearchHit],
    query_vector: list[float],
    top_k: int,
    diversity: float = 0.3,
) -> list[SearchHit]:
    """Maximal Marginal Relevance re-ranking for diversity.

    diversity=0 → pure relevance, diversity=1 → pure diversity.
    """
    if not hits or not query_vector:
        return hits[:top_k]

    selected: list[SearchHit] = []
    remaining = list(hits)

    while remaining and len(selected) < top_k:
        if not selected:
            # First pick: highest relevance score
            best = max(remaining, key=lambda h: h.score)
        else:
            # MMR: balance relevance vs. redundancy with already-selected hits
            def mmr_score(candidate: SearchHit) -> float:
                rel = candidate.score
                # Redundancy = max cosine similarity to any selected hit
                redundancy = max(
                    _text_overlap(candidate.text, sel.text)
                    for sel in selected
                )
                return (1.0 - diversity) * rel - diversity * redundancy

            best = max(remaining, key=mmr_score)

        selected.append(best)
        remaining.remove(best)

    return selected


def _text_overlap(a: str, b: str) -> float:
    """Quick token-overlap similarity as a proxy for semantic similarity."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _expand_to_parents(hits: list[SearchHit], store: KnowledgeStorePort) -> list[SearchHit]:
    """Replace child hit text with parent chunk text for small-to-big retrieval.

    The parent_chunk_id is stored in the hit metadata (set during indexing).
    Deduplicate so that multiple children from the same parent only appear once.
    """
    seen_parent_ids: set[str] = set()
    expanded: list[SearchHit] = []
    for hit in hits:
        parent_id = hit.metadata.get("parent_chunk_id")
        if not parent_id:
            expanded.append(hit)
            continue
        if parent_id in seen_parent_ids:
            continue
        seen_parent_ids.add(parent_id)
        try:
            parent = store.get_chunk_by_id(parent_id)
            expanded.append(
                SearchHit(
                    chunk_id=parent.id,
                    document_id=hit.document_id,
                    collection_id=hit.collection_id,
                    score=hit.score,
                    text=parent.text,
                    snippet=parent.text[:280],
                    metadata={**hit.metadata, "expanded_from_child": hit.chunk_id},
                )
            )
        except KeyError:
            expanded.append(hit)
    return expanded
