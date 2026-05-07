from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from omniai.config.settings import Settings

logger = logging.getLogger(__name__)


class RagServiceClient:
    """Client for the model1-style rag-service HTTP API.

    The service is not the LightRAG server itself. It is the orchestration layer
    that exposes /ingest, /query, and related routes while talking to LightRAG
    internally. The old LightRAGClient name is kept below as a compatibility
    alias for local code that imported it during the first integration pass.
    """

    def __init__(self, settings: Settings, *, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.effective_rag_service_url).rstrip("/")

    def ingest_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        file_path: str,
        mime_type: str,
        metadata: dict[str, Any] | None = None,
        ingestion_mode: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "file_path": file_path,
            "mime_type": mime_type,
            "metadata": {
                **(metadata or {}),
                "tenant_id": tenant_id,
                "document_id": document_id,
            },
        }
        if ingestion_mode:
            payload["ingestion_mode"] = ingestion_mode

        with httpx.Client(timeout=httpx.Timeout(120.0)) as client:
            try:
                response = client.post(f"{self._base_url}/ingest", json=payload)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                logger.error("rag-service ingest failed: %s", exc)
                raise RuntimeError(f"rag-service ingest failed: {exc}") from exc

    def query_knowledge_base(
        self,
        *,
        tenant_id: str,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "query": query,
            "top_k": top_k,
            "filters": {
                **(filters or {}),
                "tenant_id": tenant_id,
            },
        }

        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
                    response = client.post(f"{self._base_url}/query", json=payload)
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    time.sleep(2 ** (attempt - 1))

        raise RuntimeError(f"rag-service query failed after retries: {last_exc}") from last_exc

    def delete_document_index(
        self,
        *,
        tenant_id: str,
        document_id: str,
        lightrag_doc_id: str = "",
    ) -> None:
        payload = {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "lightrag_doc_id": lightrag_doc_id,
        }
        with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
            try:
                response = client.post(f"{self._base_url}/delete", json=payload)
                response.raise_for_status()
            except Exception as exc:
                logger.warning("rag-service delete failed: %s", exc)


LightRAGClient = RagServiceClient
