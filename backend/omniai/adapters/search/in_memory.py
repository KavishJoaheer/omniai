from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass

from omniai.ports.search_engine import IndexableChunk, SearchHit


_TOKEN = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text)]


@dataclass
class _Entry:
    chunk_id: str
    document_id: str
    collection_id: str
    text: str
    vector: list[float]
    norm: float
    tokens: list[str]
    metadata: dict


class InMemorySearchEngine:
    """In-process hybrid search. Useful for dev and tests when OpenSearch is unavailable."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, _Entry]] = {}

    def ensure_index(self, *, tenant_id: str, dim: int) -> str:
        with self._lock:
            self._entries.setdefault(tenant_id, {})
        return f"omniai_t_{tenant_id}_in_memory"

    def upsert_chunks(self, *, tenant_id: str, chunks: list[IndexableChunk]) -> None:
        with self._lock:
            tenant_index = self._entries.setdefault(tenant_id, {})
            for chunk in chunks:
                tenant_index[chunk.chunk_id] = _Entry(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    collection_id=chunk.collection_id,
                    text=chunk.text,
                    vector=list(chunk.vector),
                    norm=_l2(chunk.vector),
                    tokens=_tokenize(chunk.text),
                    metadata=dict(chunk.metadata or {}),
                )

    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None:
        with self._lock:
            tenant_index = self._entries.get(tenant_id, {})
            doomed = [cid for cid, entry in tenant_index.items() if entry.document_id == document_id]
            for cid in doomed:
                tenant_index.pop(cid, None)

    def hybrid_search(
        self,
        *,
        tenant_id: str,
        query: str,
        query_vector: list[float],
        top_k: int,
        vector_weight: float,
        collection_ids: list[str] | None = None,
    ) -> list[SearchHit]:
        with self._lock:
            entries = list(self._entries.get(tenant_id, {}).values())

        if collection_ids:
            allowed = set(collection_ids)
            entries = [e for e in entries if e.collection_id in allowed]
        if not entries:
            return []

        query_tokens = _tokenize(query)
        query_norm = _l2(query_vector)

        # Sparse: cosine over TF vectors built from token overlap; effectively a token-overlap heuristic.
        query_token_counts = Counter(query_tokens)
        scored: list[tuple[float, float, _Entry]] = []
        for entry in entries:
            dense_score = _cosine(entry.vector, query_vector, entry.norm, query_norm) if query_vector else 0.0
            sparse_score = _bm25_lite(entry.tokens, query_token_counts)
            scored.append((dense_score, sparse_score, entry))

        max_dense = max((s[0] for s in scored), default=0.0) or 1.0
        max_sparse = max((s[1] for s in scored), default=0.0) or 1.0
        weight = max(0.0, min(1.0, vector_weight))

        ranked: list[tuple[float, _Entry]] = []
        for dense, sparse, entry in scored:
            normalized = (dense / max_dense) * weight + (sparse / max_sparse) * (1.0 - weight)
            ranked.append((normalized, entry))

        ranked.sort(key=lambda item: item[0], reverse=True)
        results: list[SearchHit] = []
        for score, entry in ranked[:top_k]:
            results.append(
                SearchHit(
                    chunk_id=entry.chunk_id,
                    document_id=entry.document_id,
                    collection_id=entry.collection_id,
                    score=float(score),
                    text=entry.text,
                    snippet=_snippet(entry.text, query_tokens),
                    metadata=dict(entry.metadata),
                )
            )
        return results


def _l2(vector: list[float]) -> float:
    return math.sqrt(sum(component * component for component in vector))


def _cosine(a: list[float], b: list[float], norm_a: float, norm_b: float) -> float:
    if not a or not b or norm_a == 0.0 or norm_b == 0.0 or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (norm_a * norm_b)


def _bm25_lite(tokens: list[str], query_counts: Counter[str]) -> float:
    if not tokens or not query_counts:
        return 0.0
    doc_counts = Counter(tokens)
    score = 0.0
    for term, qcount in query_counts.items():
        score += min(doc_counts.get(term, 0), 4) * qcount
    return score


def _snippet(text: str, query_tokens: list[str], window: int = 220) -> str:
    if not text:
        return ""
    lowered = text.lower()
    for token in query_tokens:
        idx = lowered.find(token)
        if idx >= 0:
            start = max(0, idx - window // 2)
            end = min(len(text), start + window)
            return text[start:end].strip()
    return text[:window].strip()
