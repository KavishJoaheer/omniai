from __future__ import annotations

import logging
from typing import Any

from omniai.adapters.search.lightrag_client import RagServiceClient
from omniai.config.settings import Settings
from omniai.ports.search_engine import IndexableChunk, SearchHit

logger = logging.getLogger(__name__)


class RagServiceSearchEngine:
    """SearchEnginePort adapter for an external model1-style rag-service.

    This adapter is intentionally query-focused. Ingestion into the external
    rag-service should be run by that service's own upload/ingest path or a
    dedicated importer. Native OmniAI indexing remains the default in model2.
    """

    kind = "rag_service"

    def __init__(self, settings: Settings) -> None:
        self._client = RagServiceClient(settings)

    def ensure_index(self, *, tenant_id: str, dim: int) -> str:
        del dim
        return f"omniai_{tenant_id}_rag_service"

    def upsert_chunks(self, *, tenant_id: str, chunks: list[IndexableChunk]) -> None:
        del tenant_id, chunks
        logger.debug("rag-service search adapter does not upsert chunks from model2")

    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None:
        self._client.delete_document_index(tenant_id=tenant_id, document_id=document_id)

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
        del query_vector, vector_weight
        filters: dict[str, Any] = {}
        if collection_ids:
            filters["collection_ids"] = collection_ids
        if document_ids:
            filters["document_ids"] = document_ids

        raw = self._client.query_knowledge_base(
            tenant_id=tenant_id,
            query=query,
            top_k=top_k,
            filters=filters,
        )
        hits = [_chunk_to_hit(chunk, index) for index, chunk in enumerate(raw.get("chunks") or []) if isinstance(chunk, dict)]

        graph_context = _graph_context(raw)
        if graph_context and hits:
            hits[0].metadata["graph_context"] = graph_context

        return hits[:top_k]


def _chunk_to_hit(chunk: dict[str, Any], index: int) -> SearchHit:
    text = str(chunk.get("content") or chunk.get("text") or "")
    document_id = str(chunk.get("document_id") or chunk.get("doc_id") or "unknown_doc")
    collection_id = str(chunk.get("collection_id") or chunk.get("workspace_id") or "rag_service")
    metadata = {
        "filename": chunk.get("file_path") or chunk.get("source") or "",
        "document_name": chunk.get("file_path") or chunk.get("source") or "",
        "page_number": chunk.get("page_number"),
        "raw_rag_service": chunk,
    }
    return SearchHit(
        chunk_id=str(chunk.get("chunk_id") or chunk.get("id") or f"rag_chunk_{index}"),
        document_id=document_id,
        collection_id=collection_id,
        score=float(chunk.get("score") or 0.0),
        text=text,
        snippet=text[:280],
        metadata=metadata,
    )


def _graph_context(raw: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for relationship in raw.get("relationships") or []:
        if not isinstance(relationship, dict):
            continue
        source = relationship.get("source_entity") or relationship.get("source") or ""
        target = relationship.get("target_entity") or relationship.get("target") or ""
        description = relationship.get("description") or relationship.get("predicate") or ""
        if source and target:
            lines.append(f"{source} -> {target} ({description})")
    return lines
