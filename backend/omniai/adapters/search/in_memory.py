from __future__ import annotations

import logging
import math
import pickle
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from omniai.ports.search_engine import IndexableChunk, SearchHit

logger = logging.getLogger(__name__)


_TOKEN = re.compile(r"[A-Za-z0-9]+")

# Okapi BM25 hyperparameters — industry-standard defaults
_K1 = 1.2   # term-frequency saturation
_B = 0.75   # length normalisation


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


@dataclass
class _TenantIndex:
    """Per-tenant in-memory index that supports both dense (cosine) and
    sparse (Okapi BM25) retrieval, fused with Reciprocal Rank Fusion (RRF).
    """
    entries: dict[str, _Entry] = field(default_factory=dict)
    # document-frequency: term -> number of entries containing it
    df: Counter[str] = field(default_factory=Counter)
    # running sum of entry lengths for average-document-length computation
    total_tokens: int = 0

    @property
    def num_docs(self) -> int:
        return len(self.entries)

    @property
    def avg_dl(self) -> float:
        return self.total_tokens / max(1, self.num_docs)

    def add(self, entry: _Entry) -> None:
        old = self.entries.get(entry.chunk_id)
        if old is not None:
            # Remove old contribution from df / total_tokens
            self.total_tokens -= len(old.tokens)
            old_terms = set(old.tokens)
            for term in old_terms:
                self.df[term] -= 1
                if self.df[term] <= 0:
                    del self.df[term]

        self.entries[entry.chunk_id] = entry
        self.total_tokens += len(entry.tokens)
        for term in set(entry.tokens):
            self.df[term] += 1

    def remove_by_document(self, document_id: str) -> None:
        doomed = [cid for cid, e in self.entries.items() if e.document_id == document_id]
        for cid in doomed:
            entry = self.entries.pop(cid)
            self.total_tokens -= len(entry.tokens)
            for term in set(entry.tokens):
                self.df[term] -= 1
                if self.df[term] <= 0:
                    del self.df[term]

    def bm25_score(self, entry: _Entry, query_counts: Counter[str]) -> float:
        """Okapi BM25 score for a single entry against pre-counted query terms."""
        if not entry.tokens or not query_counts:
            return 0.0
        doc_len = len(entry.tokens)
        avg = self.avg_dl
        doc_counts = Counter(entry.tokens)
        score = 0.0
        n = self.num_docs
        for term, _qf in query_counts.items():
            df_t = self.df.get(term, 0)
            if df_t == 0:
                continue
            tf = doc_counts.get(term, 0)
            if tf == 0:
                continue
            # Robertson–Sparck Jones IDF (smoothed, always positive)
            idf = math.log((n - df_t + 0.5) / (df_t + 0.5) + 1.0)
            tf_norm = (tf * (_K1 + 1.0)) / (tf + _K1 * (1.0 - _B + _B * doc_len / avg))
            score += idf * tf_norm
        return score


class InMemorySearchEngine:
    """In-process hybrid search (dense cosine + Okapi BM25), fused via RRF.

    Suitable for development and tests when OpenSearch is unavailable.

    Persistence
    -----------
    Pass ``snapshot_path`` to save the full index to a pickle file on
    ``save_snapshot()`` and restore it on construction.  This survives
    backend restarts without requiring OpenSearch.

        engine = InMemorySearchEngine(snapshot_path=Path(".omniai-index.pkl"))
        engine.load_snapshot()          # call once at startup
        ...
        engine.save_snapshot()          # call at shutdown / on each upsert batch
    """

    _RRF_K = 60  # standard RRF constant

    def __init__(self, snapshot_path: Path | str | None = None) -> None:
        self._lock = threading.Lock()
        self._indices: dict[str, _TenantIndex] = {}
        self._snapshot_path: Path | None = Path(snapshot_path) if snapshot_path else None

    def _get_index(self, tenant_id: str) -> _TenantIndex:
        """Return (and lazily create) the tenant-scoped index. Must hold lock."""
        if tenant_id not in self._indices:
            self._indices[tenant_id] = _TenantIndex()
        return self._indices[tenant_id]

    # ------------------------------------------------------------------
    # Snapshot persistence
    # ------------------------------------------------------------------

    def load_snapshot(self) -> None:
        """Restore the index from a previously saved snapshot file.

        Safe to call even if the file does not exist yet (first run).
        Any pickle errors are logged and silently swallowed so the
        application can still start with a fresh empty index.
        """
        if self._snapshot_path is None or not self._snapshot_path.exists():
            return
        try:
            with open(self._snapshot_path, "rb") as fh:
                data = pickle.load(fh)
            if isinstance(data, dict):
                with self._lock:
                    self._indices = data
                chunk_total = sum(len(idx.entries) for idx in self._indices.values())
                logger.info(
                    "in_memory_search: restored %d tenant index(es), %d chunk(s) from %s",
                    len(self._indices), chunk_total, self._snapshot_path,
                )
        except Exception as exc:
            logger.warning("in_memory_search: snapshot load failed (%s) — starting fresh", exc)

    def save_snapshot(self) -> None:
        """Persist the current index to disk atomically.

        Writes to a ``<path>.tmp`` file first then renames so a crash mid-write
        never corrupts the previous good snapshot.
        """
        if self._snapshot_path is None:
            return
        try:
            self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._snapshot_path.with_suffix(".tmp")
            with self._lock:
                data = dict(self._indices)
            with open(tmp, "wb") as fh:
                pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(self._snapshot_path)
            logger.debug("in_memory_search: snapshot saved to %s", self._snapshot_path)
        except Exception as exc:
            logger.warning("in_memory_search: snapshot save failed: %s", exc)

    def ensure_index(self, *, tenant_id: str, dim: int) -> str:
        with self._lock:
            self._get_index(tenant_id)
        return f"omniai_t_{tenant_id}_in_memory"

    def upsert_chunks(self, *, tenant_id: str, chunks: list[IndexableChunk]) -> None:
        with self._lock:
            idx = self._get_index(tenant_id)
            for chunk in chunks:
                idx.add(_Entry(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    collection_id=chunk.collection_id,
                    text=chunk.text,
                    vector=list(chunk.vector),
                    norm=_l2(chunk.vector),
                    tokens=_tokenize(chunk.text),
                    metadata=dict(chunk.metadata or {}),
                ))
        # Persist asynchronously after each batch so restarts don't lose data.
        # This is a best-effort background operation; failures are logged not raised.
        self.save_snapshot()

    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None:
        with self._lock:
            if tenant_id in self._indices:
                self._indices[tenant_id].remove_by_document(document_id)

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
    ) -> list[SearchHit]:
        with self._lock:
            idx = self._get_index(tenant_id)
            entries = list(idx.entries.values())
            # Capture BM25 corpus state for scoring
            bm25_fn = idx.bm25_score

        # Apply filters
        if collection_ids:
            allowed = set(collection_ids)
            entries = [e for e in entries if e.collection_id in allowed]
        if document_ids:
            allowed_docs = set(document_ids)
            entries = [e for e in entries if e.document_id in allowed_docs]
        if not entries:
            return []

        query_tokens = _tokenize(query)
        query_counts = Counter(query_tokens)
        query_norm = _l2(query_vector)
        weight = max(0.0, min(1.0, vector_weight))

        # --- Dense pass (cosine similarity) ---
        dense_scored: list[tuple[float, _Entry]] = []
        for entry in entries:
            score = _cosine(entry.vector, query_vector, entry.norm, query_norm) if query_vector else 0.0
            dense_scored.append((score, entry))
        dense_scored.sort(key=lambda x: x[0], reverse=True)
        dense_rank: dict[str, int] = {e.chunk_id: rank for rank, (_, e) in enumerate(dense_scored, start=1)}

        # --- Sparse pass (Okapi BM25) ---
        sparse_scored: list[tuple[float, _Entry]] = []
        for entry in entries:
            score = bm25_fn(entry, query_counts) if query_tokens else 0.0
            sparse_scored.append((score, entry))
        sparse_scored.sort(key=lambda x: x[0], reverse=True)
        sparse_rank: dict[str, int] = {e.chunk_id: rank for rank, (_, e) in enumerate(sparse_scored, start=1)}

        k = self._RRF_K
        # --- Reciprocal Rank Fusion ---
        rrf: dict[str, float] = {}
        for entry in entries:
            cid = entry.chunk_id
            dr = dense_rank.get(cid, len(entries) + 1)
            sr = sparse_rank.get(cid, len(entries) + 1)
            rrf[cid] = weight * (1.0 / (k + dr)) + (1.0 - weight) * (1.0 / (k + sr))

        entry_map = {e.chunk_id: e for e in entries}
        ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]

        # Normalise RRF scores to [0, 1] for consistent downstream comparisons
        max_rrf = ranked[0][1] if ranked else 1.0

        results: list[SearchHit] = []
        for cid, score in ranked:
            entry = entry_map[cid]
            results.append(
                SearchHit(
                    chunk_id=entry.chunk_id,
                    document_id=entry.document_id,
                    collection_id=entry.collection_id,
                    score=score / (max_rrf or 1.0),
                    text=entry.text,
                    snippet=_snippet(entry.text, query_tokens),
                    metadata=dict(entry.metadata),
                )
            )
        return results


def _l2(vector: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vector))


def _cosine(a: list[float], b: list[float], norm_a: float, norm_b: float) -> float:
    if not a or not b or norm_a == 0.0 or norm_b == 0.0 or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (norm_a * norm_b)


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
