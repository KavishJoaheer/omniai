from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import ProviderRecord
from omniai.config.settings import Settings
from omniai.plugins.embedding_providers.ollama import OllamaEmbeddingProvider
from omniai.ports.embedding_provider import EmbeddingProviderPort


def build_embedding_provider(
    *,
    session: Session,
    settings: Settings,
    tenant_id: str,
    requested_model: str,
) -> tuple[EmbeddingProviderPort, str]:
    """Resolve the embedding provider for a tenant. Returns (provider, model_name)."""
    candidate = _select_provider(session=session, tenant_id=tenant_id, requested_model=requested_model)
    if candidate is not None:
        provider, model = candidate
        return provider, model
    return (
        OllamaEmbeddingProvider(base_url=settings.ollama_base_url),
        requested_model or "nomic-embed-text",
    )


def _select_provider(
    *, session: Session, tenant_id: str, requested_model: str
) -> tuple[EmbeddingProviderPort, str] | None:
    statement = select(ProviderRecord).where(
        ProviderRecord.tenant_id == tenant_id,
        ProviderRecord.kind == "embedding",
        ProviderRecord.enabled == 1,
    )
    for record in session.scalars(statement):
        if record.name.lower() == "ollama":
            options = _safe_json(record.options_json)
            base_url = record.base_url or "http://localhost:11434"
            model = requested_model or record.default_model or options.get("default_model") or "nomic-embed-text"
            return OllamaEmbeddingProvider(base_url=base_url, default_model=model), model
    return None


def _safe_json(value: str) -> dict:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
