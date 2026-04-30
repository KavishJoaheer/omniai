from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass

from omniai.ports.embedding_provider import EmbeddingProviderPort
from omniai.ports.relational import KnowledgeStorePort
from omniai.ports.reranker import RerankCandidate, RerankerPort
from omniai.ports.search_engine import SearchEnginePort, SearchHit
from omniai.utils.cache import RetrievalCachePort, deserialize, serialize

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievalRequest:
    query: str
    top_k: int = 8
    vector_weight: float = 0.6
    collection_ids: list[str] | None = None
    document_ids: list[str] | None = None
    embedding_model: str = "nomic-embed-text"
    rerank: bool = True


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
        reranker: RerankerPort | None = None,
        cache: RetrievalCachePort | None = None,
        cache_ttl: int = 0,
    ) -> None:
        self._search = search_engine
        self._embeddings = embedding_provider
        self._tenant_id = tenant_id
        self._store = store
        self._reranker = reranker
        self._cache = cache
        self._cache_ttl = cache_ttl

    # ------------------------------------------------------------------
    # Cache key helpers
    # ------------------------------------------------------------------

    def _cache_key(self, request: RetrievalRequest) -> str:
        """Stable SHA-256 key over all parameters that affect the result."""
        payload = {
            "tenant": self._tenant_id,
            "q": request.query.strip(),
            "cols": sorted(request.collection_ids or []),
            "docs": sorted(request.document_ids or []),
            "k": request.top_k,
            "vw": round(request.vector_weight, 4),
            "model": request.embedding_model,
            "rerank": request.rerank,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "ret:" + hashlib.sha256(raw.encode()).hexdigest()

    # ------------------------------------------------------------------

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        if not request.query.strip():
            return RetrievalResponse(hits=[], embedding_model=request.embedding_model, vector_weight=request.vector_weight)

        # ── Cache read ────────────────────────────────────────────────
        cache_key: str | None = None
        if self._cache is not None and self._cache_ttl > 0:
            cache_key = self._cache_key(request)
            cached = self._cache.get(cache_key)
            if cached:
                result = deserialize(cached)
                if isinstance(result, RetrievalResponse):
                    logger.debug("Retrieval cache HIT key=%s", cache_key)
                    return result

        try:
            vectors = await self._embeddings.embed(model=request.embedding_model, inputs=[request.query])
            query_vector = vectors[0]
        except Exception:
            query_vector = []

        # Over-fetch when re-ranking is enabled so we have headroom to reorder
        fetch_k = request.top_k * 3 if request.rerank else request.top_k

        hits = self._search.hybrid_search(
            tenant_id=self._tenant_id,
            query=request.query,
            query_vector=query_vector,
            top_k=fetch_k,
            vector_weight=request.vector_weight,
            collection_ids=request.collection_ids,
            document_ids=request.document_ids,
        )

        # Re-rank: re-embed each candidate with the query and recompute cosine.
        # The first-stage hybrid search uses chunk-time embeddings only; this stage
        # has the embedding model "see" the query alongside the candidate text.
        if request.rerank and len(hits) > 1 and query_vector:
            hits = await self._rerank(request.query, hits, request.embedding_model)

        # Trim to requested top_k after re-ranking
        hits = hits[: request.top_k]

        # Apply MMR diversification when we have more hits than needed
        if len(hits) > 1:
            hits = _mmr(hits, query_vector, top_k=request.top_k)

        # Expand child hits to parent text for small-to-big templates
        if self._store is not None:
            hits = _expand_to_parents(hits, self._store)
            hits = _augment_with_graph(
                query=request.query,
                hits=hits,
                store=self._store,
                collection_ids=request.collection_ids,
                top_k=request.top_k,
            )

        response = RetrievalResponse(
            hits=hits,
            embedding_model=request.embedding_model,
            vector_weight=request.vector_weight,
        )

        # ── Cache write ───────────────────────────────────────────────
        if cache_key is not None and self._cache is not None:
            blob = serialize(response)
            if blob:
                self._cache.set(cache_key, blob, self._cache_ttl)
                logger.debug("Retrieval cache SET key=%s ttl=%ds", cache_key, self._cache_ttl)

        return response

    async def _rerank(
        self,
        query: str,
        hits: list[SearchHit],
        embedding_model: str,
    ) -> list[SearchHit]:
        """Second-stage re-rank.

        Delegates to the configured RerankerPort if available; otherwise falls
        back to paired-embedding scoring. Final score is a 0.7/0.3 blend of
        (rerank_score, first_stage_score).
        """
        if not hits:
            return hits

        rerank_scores: list[float] = []
        if self._reranker is not None:
            try:
                rerank_scores = await self._reranker.rerank(
                    query=query,
                    candidates=[RerankCandidate(chunk_id=h.chunk_id, text=h.text) for h in hits],
                )
            except Exception:
                rerank_scores = []

        # Fallback: paired-embedding scoring using the embedding provider directly
        if not rerank_scores or len(rerank_scores) != len(hits):
            try:
                anchor = await self._embeddings.embed(model=embedding_model, inputs=[f"query: {query}"])
                paired = await self._embeddings.embed(
                    model=embedding_model,
                    inputs=[f"query: {query} passage: {h.text[:1500]}" for h in hits],
                )
                if anchor and len(paired) == len(hits):
                    anchor_vec = anchor[0]
                    rerank_scores = [_cosine(anchor_vec, v) for v in paired]
            except Exception:
                return hits

        if not rerank_scores or len(rerank_scores) != len(hits):
            return hits

        # Normalize rerank_scores to [0,1] so blending is meaningful regardless
        # of which scorer produced them (cross-encoder logits vs. cosine sims).
        max_score = max(rerank_scores)
        min_score = min(rerank_scores)
        spread = (max_score - min_score) or 1.0
        normed = [(s - min_score) / spread for s in rerank_scores]

        rescored: list[tuple[float, SearchHit]] = []
        for hit, raw_score, norm_score in zip(hits, rerank_scores, normed):
            blended = 0.7 * norm_score + 0.3 * hit.score
            rescored.append((blended, SearchHit(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                collection_id=hit.collection_id,
                score=blended,
                text=hit.text,
                snippet=hit.snippet,
                metadata={
                    **hit.metadata,
                    "first_stage_score": hit.score,
                    "rerank_score": float(raw_score),
                },
            )))
        rescored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in rescored]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


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


_ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,4}\b")


def _augment_with_graph(
    *,
    query: str,
    hits: list[SearchHit],
    store: KnowledgeStorePort,
    collection_ids: list[str] | None,
    top_k: int,
) -> list[SearchHit]:
    entities = _extract_entities(query)
    if not entities:
        return hits

    triples = []
    seen_ids: set[str] = set()
    for entity in entities[:6]:
        if collection_ids:
            for collection_id in collection_ids:
                results = store.list_graph_triples(collection_id=collection_id, entity=entity, limit=20)
                for triple in results:
                    if triple.id not in seen_ids:
                        seen_ids.add(triple.id)
                        triples.append(triple)
        else:
            results = store.list_graph_triples(entity=entity, limit=20)
            for triple in results:
                if triple.id not in seen_ids:
                    seen_ids.add(triple.id)
                    triples.append(triple)

    if not triples:
        return hits

    graph_lines_by_document: dict[str, list[str]] = {}
    graph_lines_by_collection: dict[str, list[str]] = {}
    for triple in triples:
        line = _triple_line(triple)
        graph_lines_by_document.setdefault(triple.document_id, []).append(line)
        graph_lines_by_collection.setdefault(triple.collection_id, []).append(line)

    augmented: list[SearchHit] = []
    for hit in hits:
        lines = graph_lines_by_document.get(hit.document_id) or graph_lines_by_collection.get(hit.collection_id) or []
        metadata = dict(hit.metadata or {})
        if lines:
            metadata["graph_context"] = lines[:5]
        augmented.append(
            SearchHit(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                collection_id=hit.collection_id,
                score=hit.score,
                text=hit.text,
                snippet=hit.snippet,
                metadata=metadata,
            )
        )

    synthetic_slots = max(0, top_k - len(augmented))
    for triple in triples[:synthetic_slots]:
        line = _triple_line(triple)
        augmented.append(
            SearchHit(
                chunk_id=f"graph:{triple.id}",
                document_id=triple.document_id,
                collection_id=triple.collection_id,
                score=0.35 * triple.confidence,
                text=line,
                snippet=line,
                metadata={
                    "kind": "graph_triple",
                    "graph_context": [line],
                    "confidence": triple.confidence,
                },
            )
        )
    return augmented


def _extract_entities(query: str) -> list[str]:
    seen: set[str] = set()
    entities: list[str] = []
    for match in _ENTITY_RE.findall(query):
        entity = " ".join(match.split())
        if len(entity) < 2 or entity.lower() in {"i", "the", "what", "who", "where", "when", "how"}:
            continue
        key = entity.lower()
        if key not in seen:
            seen.add(key)
            entities.append(entity)
    return entities


def _triple_line(triple) -> str:
    return f"{triple.subject} {triple.predicate} {triple.object} (confidence {triple.confidence:.2f})"
