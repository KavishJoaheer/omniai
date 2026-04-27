from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import ProviderRecord
from omniai.security.permissions import Perm, assert_permission
from omniai.security.secrets import SecretBox


PROVIDER_KINDS: frozenset[str] = frozenset({"llm", "embedding", "reranker", "asr", "tts"})


@dataclass(slots=True)
class ProviderActor:
    user_id: str
    tenant_id: str
    role: str


class CreateProviderInput(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=512)
    default_model: str | None = Field(default=None, max_length=128)
    enabled: bool = False
    api_key: str | None = Field(default=None, max_length=2048)
    options: dict | None = None


class UpdateProviderInput(BaseModel):
    base_url: str | None = Field(default=None, max_length=512)
    default_model: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None
    api_key: str | None = Field(default=None, max_length=2048)
    options: dict | None = None


def seed_default_providers(session: Session, *, tenant_id: str, ollama_base_url: str) -> None:
    seeds = [
        {
            "kind": "llm",
            "name": "ollama",
            "base_url": ollama_base_url,
            "default_model": None,
            "enabled": 1,
            "options": {"detect_models": True},
        },
        {"kind": "llm", "name": "anthropic", "base_url": "https://api.anthropic.com", "enabled": 0},
        {"kind": "llm", "name": "openai", "base_url": "https://api.openai.com/v1", "enabled": 0},
        {"kind": "llm", "name": "gemini", "base_url": "https://generativelanguage.googleapis.com", "enabled": 0},
        {
            "kind": "embedding",
            "name": "ollama",
            "base_url": ollama_base_url,
            "enabled": 1,
            "options": {"detect_models": True},
        },
        {"kind": "embedding", "name": "openai", "base_url": "https://api.openai.com/v1", "enabled": 0},
    ]
    for seed in seeds:
        existing = session.scalar(
            select(ProviderRecord).where(
                ProviderRecord.tenant_id == tenant_id,
                ProviderRecord.kind == seed["kind"],
                func.lower(ProviderRecord.name) == seed["name"].lower(),
            )
        )
        if existing is not None:
            continue
        session.add(
            ProviderRecord(
                tenant_id=tenant_id,
                kind=seed["kind"],
                name=seed["name"],
                base_url=seed.get("base_url"),
                default_model=seed.get("default_model"),
                enabled=int(seed.get("enabled", 0)),
                options_json=json.dumps(seed.get("options", {}), separators=(",", ":"), sort_keys=True),
            )
        )
    session.commit()


class ProviderService:
    def __init__(self, session: Session, secret_box: SecretBox) -> None:
        self._session = session
        self._secrets = secret_box

    def list_providers(self, actor: ProviderActor) -> list[dict]:
        assert_permission(actor.role, Perm.PROVIDERS_READ)
        statement = (
            select(ProviderRecord)
            .where(ProviderRecord.tenant_id == actor.tenant_id)
            .order_by(ProviderRecord.kind.asc(), ProviderRecord.name.asc())
        )
        return [self._to_payload(record) for record in self._session.scalars(statement)]

    def create_provider(self, actor: ProviderActor, payload: CreateProviderInput) -> dict:
        assert_permission(actor.role, Perm.PROVIDERS_WRITE)
        kind = payload.kind.lower().strip()
        if kind not in PROVIDER_KINDS:
            raise ValueError(f"Unsupported provider kind: {kind}")

        duplicate = self._session.scalar(
            select(ProviderRecord).where(
                ProviderRecord.tenant_id == actor.tenant_id,
                ProviderRecord.kind == kind,
                func.lower(ProviderRecord.name) == payload.name.lower(),
            )
        )
        if duplicate is not None:
            raise ValueError("A provider with that kind and name already exists.")

        encrypted = self._secrets.encrypt(payload.api_key) if payload.api_key else ""
        record = ProviderRecord(
            tenant_id=actor.tenant_id,
            kind=kind,
            name=payload.name.strip(),
            base_url=payload.base_url,
            default_model=payload.default_model,
            enabled=int(bool(payload.enabled)),
            has_credentials=int(bool(payload.api_key)),
            encrypted_credentials=encrypted,
            options_json=json.dumps(payload.options or {}, separators=(",", ":"), sort_keys=True),
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_payload(record)

    def update_provider(self, actor: ProviderActor, provider_id: str, payload: UpdateProviderInput) -> dict:
        assert_permission(actor.role, Perm.PROVIDERS_WRITE)
        record = self._get_record(actor, provider_id)

        if payload.base_url is not None:
            record.base_url = payload.base_url
        if payload.default_model is not None:
            record.default_model = payload.default_model
        if payload.enabled is not None:
            record.enabled = int(bool(payload.enabled))
        if payload.options is not None:
            record.options_json = json.dumps(payload.options, separators=(",", ":"), sort_keys=True)
        if payload.api_key is not None:
            if payload.api_key == "":
                record.encrypted_credentials = ""
                record.has_credentials = 0
            else:
                record.encrypted_credentials = self._secrets.encrypt(payload.api_key)
                record.has_credentials = 1
        self._session.commit()
        self._session.refresh(record)
        return self._to_payload(record)

    def delete_provider(self, actor: ProviderActor, provider_id: str) -> None:
        assert_permission(actor.role, Perm.PROVIDERS_WRITE)
        record = self._get_record(actor, provider_id)
        self._session.delete(record)
        self._session.commit()

    def list_models(self, actor: ProviderActor, provider_id: str) -> list[str]:
        assert_permission(actor.role, Perm.PROVIDERS_READ)
        record = self._get_record(actor, provider_id)
        if record.kind not in {"llm", "embedding"}:
            return []
        if record.name.lower() == "ollama":
            return self._fetch_ollama_models(record.base_url or "http://localhost:11434")
        if not bool(record.has_credentials):
            return []
        return []

    def _get_record(self, actor: ProviderActor, provider_id: str) -> ProviderRecord:
        record = self._session.scalar(
            select(ProviderRecord).where(
                ProviderRecord.id == provider_id,
                ProviderRecord.tenant_id == actor.tenant_id,
            )
        )
        if record is None:
            raise KeyError("Provider not found.")
        return record

    @staticmethod
    def _fetch_ollama_models(base_url: str) -> list[str]:
        url = base_url.rstrip("/") + "/api/tags"
        try:
            response = httpx.get(url, timeout=3.0)
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TransportError):
            return []
        data = response.json()
        models = data.get("models") or []
        names: list[str] = []
        for entry in models:
            name = entry.get("name") if isinstance(entry, dict) else None
            if isinstance(name, str):
                names.append(name)
        return names

    @staticmethod
    def _to_payload(record: ProviderRecord) -> dict:
        try:
            options = json.loads(record.options_json) if record.options_json else {}
        except json.JSONDecodeError:
            options = {}
        return {
            "id": record.id,
            "kind": record.kind,
            "name": record.name,
            "baseUrl": record.base_url,
            "defaultModel": record.default_model,
            "enabled": bool(record.enabled),
            "hasCredentials": bool(record.has_credentials),
            "options": options,
            "createdAt": record.created_at.isoformat(),
            "updatedAt": record.updated_at.isoformat(),
        }
