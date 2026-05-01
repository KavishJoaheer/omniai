"""Weaviate search adapter — uses the Weaviate vector database.

Architecture notes:
  - One Weaviate *class* per Omni-AI installation (configurable via WEAVIATE_CLASS_NAME).
  - ``tenant_id`` and ``collection_id`` are stored as text properties and used
    for ``where`` filter queries.
  - Hybrid search uses Weaviate's built-in BM25 + vector fusion (``alpha`` = vector_weight).

Requires: ``pip install weaviate-client``
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from omniai.ports.search_engine import IndexableChunk, SearchEnginePort, SearchHit

logger = logging.getLogger(__name__)

_CLASS_SCHEMA = {
    "vectorizer": "none",  # We supply vectors ourselves
    "properties": [
        {"name": "chunk_id",      "dataType": ["text"]},
        {"name": "tenant_id",     "dataType": ["text"]},
        {"name": "document_id",   "dataType": ["text"]},
        {"name": "collection_id", "dataType": ["text"]},
        {"name": "text",          "dataType": ["text"]},
    ],
}


class WeaviateSearchEngine:
    """SearchEnginePort backed by Weaviate.

    Parameters
    ----------
    url:
        Weaviate endpoint URL (e.g. ``"http://localhost:8080"``).
    api_key:
        Optional Weaviate Cloud API key.  Pass ``None`` for self-hosted.
    class_name:
        Name of the Weaviate class used to store chunks.
    """

    kind = "weaviate"

    def __init__(self, url: str, api_key: str | None, class_name: str = "OmniAIChunk") -> None:
        try:
            import weaviate  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "weaviate-client is required for the Weaviate adapter. "
                "Install it with: pip install weaviate-client"
            ) from exc
        self._weaviate = weaviate
        self._url = url
        self._api_key = api_key
        self._class_name = class_name
        self._client: Any = None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_client(self):
        if self._client is None:
            auth = (
                self._weaviate.AuthApiKey(api_key=self._api_key)
                if self._api_key
                else None
            )
            self._client = self._weaviate.Client(url=self._url, auth_client_secret=auth)
        return self._client

    # ── SearchEnginePort ───────────────────────────────────────────────────────

    def ensure_index(self, *, tenant_id: str, dim: int) -> str:
        """Create the Weaviate class if it doesn't exist."""
        client = self._get_client()
        schema = client.schema.get()
        existing_classes = [c["class"] for c in schema.get("classes", [])]
        if self._class_name not in existing_classes:
            class_schema = {
                "class": self._class_name,
                **_CLASS_SCHEMA,
            }
            client.schema.create_class(class_schema)
            logger.info("Weaviate class %r created", self._class_name)
        else:
            logger.info("Weaviate class %r already exists", self._class_name)
        return self._class_name

    def upsert_chunks(self, *, tenant_id: str, chunks: list[IndexableChunk]) -> None:
        if not chunks:
            return
        client = self._get_client()
        with client.batch as batch:
            batch.batch_size = 100
            for c in chunks:
                # Use a deterministic UUID from chunk_id so repeated upserts work
                obj_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tenant_id}:{c.chunk_id}"))
                batch.add_data_object(
                    data_object={
                        "chunk_id":      c.chunk_id,
                        "tenant_id":     tenant_id,
                        "document_id":   c.document_id,
                        "collection_id": c.collection_id,
                        "text":          c.text,
                    },
                    class_name=self._class_name,
                    uuid=obj_uuid,
                    vector=c.vector,
                )

    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None:
        client = self._get_client()
        client.batch.delete_objects(
            class_name=self._class_name,
            where={
                "operator": "And",
                "operands": [
                    {"path": ["tenant_id"],   "operator": "Equal", "valueText": tenant_id},
                    {"path": ["document_id"], "operator": "Equal", "valueText": document_id},
                ],
            },
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
        client = self._get_client()

        # Build the where filter
        filters: list[dict] = [
            {"path": ["tenant_id"], "operator": "Equal", "valueText": tenant_id}
        ]
        if collection_ids:
            filters.append({
                "operator": "Or",
                "operands": [
                    {"path": ["collection_id"], "operator": "Equal", "valueText": cid}
                    for cid in collection_ids
                ],
            })
        if document_ids:
            filters.append({
                "operator": "Or",
                "operands": [
                    {"path": ["document_id"], "operator": "Equal", "valueText": did}
                    for did in document_ids
                ],
            })

        where_filter: dict = (
            filters[0]
            if len(filters) == 1
            else {"operator": "And", "operands": filters}
        )

        # Weaviate hybrid search: alpha=1 → pure vector, alpha=0 → pure BM25
        result = (
            client.query
            .get(self._class_name, ["chunk_id", "document_id", "collection_id", "text"])
            .with_hybrid(query=query, vector=query_vector, alpha=vector_weight)
            .with_where(where_filter)
            .with_additional(["score"])
            .with_limit(top_k)
            .do()
        )

        hits: list[SearchHit] = []
        objects = result.get("data", {}).get("Get", {}).get(self._class_name, [])
        for obj in objects:
            additional = obj.get("_additional", {})
            hits.append(
                SearchHit(
                    chunk_id=obj.get("chunk_id", ""),
                    document_id=obj.get("document_id", ""),
                    collection_id=obj.get("collection_id", ""),
                    score=float(additional.get("score", 0.0)),
                    text=obj.get("text", ""),
                    snippet=obj.get("text", "")[:280],
                    metadata={},
                )
            )
        return hits
