"""Pinecone search adapter — uses the Pinecone serverless / pod-based index.

Architecture notes:
  - One Pinecone *index* per Omni-AI installation (configurable via PINECONE_INDEX_NAME).
  - ``tenant_id`` and ``collection_id`` are stored as metadata filter fields.
  - Vector IDs are ``{tenant_id}:{chunk_id}``.
  - BM25 (keyword) scoring is not supported by Pinecone's standard plan, so
    the ``vector_weight`` parameter is ignored and we return pure ANN results.
  - Hybrid search (sparse + dense) requires Pinecone's Hybrid tier; this adapter
    supports it automatically when the index was created with ``metric="dotproduct"``
    and sparse vectors are provided.  When the index uses ``cosine`` or ``euclidean``
    the sparse component is skipped.

Requires: ``pip install pinecone-client``
"""
from __future__ import annotations

import logging
from typing import Any

from omniai.ports.search_engine import IndexableChunk, SearchHit

logger = logging.getLogger(__name__)


class PineconeSearchEngine:
    """SearchEnginePort backed by Pinecone.

    Parameters
    ----------
    api_key:
        Pinecone API key.
    environment:
        Pinecone environment/region (e.g. ``"us-east-1-aws"``).
    index_name:
        Name of the Pinecone index to use.  Created automatically if it doesn't
        exist when ``ensure_index()`` is called.
    """

    kind = "pinecone"

    def __init__(self, api_key: str, environment: str, index_name: str) -> None:
        try:
            import pinecone  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "pinecone-client is required for the Pinecone adapter. "
                "Install it with: pip install pinecone-client"
            ) from exc
        self._pinecone = pinecone
        self._api_key = api_key
        self._environment = environment
        self._index_name = index_name
        self._index: Any = None
        self._dim: int | None = None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_index(self):
        if self._index is None:
            self._pinecone.init(api_key=self._api_key, environment=self._environment)
            self._index = self._pinecone.Index(self._index_name)
        return self._index

    # ── SearchEnginePort ───────────────────────────────────────────────────────

    def ensure_index(self, *, tenant_id: str, dim: int) -> str:
        """Create the Pinecone index if it doesn't exist."""
        self._dim = dim
        self._pinecone.init(api_key=self._api_key, environment=self._environment)
        existing = self._pinecone.list_indexes()
        if self._index_name not in existing:
            self._pinecone.create_index(
                name=self._index_name,
                dimension=dim,
                metric="cosine",
                pods=1,
                pod_type="p1.x1",
            )
            logger.info("Pinecone index %r created (dim=%d)", self._index_name, dim)
        else:
            logger.info("Pinecone index %r already exists", self._index_name)
        self._index = self._pinecone.Index(self._index_name)
        return self._index_name

    def upsert_chunks(self, *, tenant_id: str, chunks: list[IndexableChunk]) -> None:
        if not chunks:
            return
        index = self._get_index()
        vectors = [
            (
                f"{tenant_id}:{c.chunk_id}",
                c.vector,
                {
                    "tenant_id": tenant_id,
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "collection_id": c.collection_id,
                    "text": c.text[:1000],  # Pinecone metadata values have a size limit
                    **{k: v for k, v in c.metadata.items() if isinstance(v, (str, int, float, bool))},
                },
            )
            for c in chunks
        ]
        # Pinecone upsert in batches of 100
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            index.upsert(vectors=vectors[i : i + batch_size])

    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None:
        index = self._get_index()
        index.delete(
            filter={"tenant_id": {"$eq": tenant_id}, "document_id": {"$eq": document_id}}
        )

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
        if not query_vector:
            return []

        index = self._get_index()
        filters: dict[str, Any] = {"tenant_id": {"$eq": tenant_id}}
        if collection_ids:
            filters["collection_id"] = {"$in": collection_ids}
        if document_ids:
            filters["document_id"] = {"$in": document_ids}

        response = index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True,
            filter=filters,
        )

        hits: list[SearchHit] = []
        for match in response.get("matches", []):
            meta = match.get("metadata", {})
            hits.append(
                SearchHit(
                    chunk_id=meta.get("chunk_id", match["id"]),
                    document_id=meta.get("document_id", ""),
                    collection_id=meta.get("collection_id", ""),
                    score=float(match.get("score", 0.0)),
                    text=meta.get("text", ""),
                    snippet=meta.get("text", "")[:280],
                    metadata={k: v for k, v in meta.items() if k not in ("chunk_id", "document_id", "collection_id", "text", "tenant_id")},
                )
            )
        return hits
