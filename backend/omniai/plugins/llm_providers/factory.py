from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import ProviderRecord
from omniai.config.settings import Settings
from omniai.plugins.llm_providers.anthropic import AnthropicLlmProvider
from omniai.plugins.llm_providers.gemini import GeminiLlmProvider
from omniai.plugins.llm_providers.ollama import OllamaLlmProvider
from omniai.plugins.llm_providers.openai import OpenAILlmProvider
from omniai.ports.llm_provider import LlmProviderPort
from omniai.security.secrets import SecretBox


def build_llm_provider(
    *,
    session: Session,
    settings: Settings,
    secret_box: SecretBox,
    tenant_id: str,
    requested_model: str | None = None,
    requested_provider: str | None = None,
) -> tuple[LlmProviderPort, str]:
    """Resolve a chat-capable LLM provider for a tenant. Returns (provider, model_name)."""
    statement = select(ProviderRecord).where(
        ProviderRecord.tenant_id == tenant_id,
        ProviderRecord.kind == "llm",
        ProviderRecord.enabled == 1,
    )
    records = list(session.scalars(statement))

    if requested_provider:
        records = [r for r in records if r.name.lower() == requested_provider.lower()]

    for record in records:
        provider = _instantiate(record, secret_box, settings)
        if provider is None:
            continue
        model = requested_model or record.default_model or _safe_json(record.options_json).get("default_model")
        if not model:
            # fall back to provider's first known model
            model = _fallback_model(record.name)
        return provider, model

    # Last-resort fallback to local Ollama
    return (
        OllamaLlmProvider(base_url=settings.ollama_base_url),
        requested_model or "llama3",
    )


def _instantiate(record: ProviderRecord, secret_box: SecretBox, settings: Settings) -> LlmProviderPort | None:
    name = record.name.lower()
    options = _safe_json(record.options_json)
    base_url = record.base_url
    default_model = record.default_model or options.get("default_model")

    if name == "ollama":
        return OllamaLlmProvider(
            base_url=base_url or settings.ollama_base_url,
            default_model=default_model,
        )

    if not record.has_credentials or not record.encrypted_credentials:
        return None
    try:
        decrypted = secret_box.decrypt(record.encrypted_credentials)
        creds = json.loads(decrypted)
    except Exception:
        return None
    api_key = creds.get("api_key")
    if not api_key:
        return None

    if name == "anthropic":
        return AnthropicLlmProvider(
            api_key=api_key,
            base_url=base_url or "https://api.anthropic.com",
            default_model=default_model,
        )
    if name == "openai":
        return OpenAILlmProvider(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
            default_model=default_model,
        )
    if name == "gemini":
        return GeminiLlmProvider(
            api_key=api_key,
            base_url=base_url or "https://generativelanguage.googleapis.com/v1beta",
            default_model=default_model,
        )
    return None


def _fallback_model(provider_name: str) -> str:
    name = provider_name.lower()
    if name == "anthropic":
        return AnthropicLlmProvider.DEFAULT_MODELS[1]
    if name == "openai":
        return OpenAILlmProvider.DEFAULT_MODELS[0]
    if name == "gemini":
        return GeminiLlmProvider.DEFAULT_MODELS[0]
    return "llama3"


def _safe_json(value: str) -> dict:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
