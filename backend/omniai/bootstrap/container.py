from __future__ import annotations

from dataclasses import dataclass

from omniai.adapters.relational.sqlalchemy.repositories import ensure_tenant
from omniai.adapters.relational.sqlalchemy.session import DatabaseManager
from omniai.application.auth_service import AuthService
from omniai.application.provider_service import ProviderService, seed_default_providers
from omniai.config.settings import Settings
from omniai.observability.metrics import MetricsRegistry
from omniai.security.secrets import SecretBox


@dataclass(slots=True)
class Container:
    settings: Settings
    database: DatabaseManager
    metrics: MetricsRegistry
    secret_box: SecretBox
    default_tenant_id: str


def build_container(settings: Settings) -> Container:
    database = DatabaseManager(settings.db_url, echo=settings.db_echo)
    if settings.auto_create_schema:
        database.create_schema()
    metrics = MetricsRegistry()
    secret_box = SecretBox(settings.encryption_key)

    with database.new_session() as session:
        tenant = ensure_tenant(
            session,
            slug=settings.bootstrap_tenant_slug,
            name=settings.bootstrap_tenant_name,
        )
        AuthService(session, settings).ensure_bootstrap_admin(tenant.id)
        seed_default_providers(
            session,
            tenant_id=tenant.id,
            ollama_base_url=settings.ollama_base_url,
        )

    return Container(
        settings=settings,
        database=database,
        metrics=metrics,
        secret_box=secret_box,
        default_tenant_id=tenant.id,
    )
