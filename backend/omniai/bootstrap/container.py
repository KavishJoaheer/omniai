from __future__ import annotations

from dataclasses import dataclass

from omniai.adapters.object_store import build_object_store
from omniai.adapters.queue import build_job_queue
from omniai.adapters.queue.inline import InlineJobQueue
from omniai.adapters.relational.sqlalchemy.repositories import ensure_tenant
from omniai.adapters.relational.sqlalchemy.session import DatabaseManager
from omniai.adapters.search.factory import build_search_engine
from omniai.application.auth_service import AuthService
from omniai.application.ingestion_service import PARSE_JOB_NAME
from omniai.application.provider_service import seed_default_providers
from omniai.config.settings import Settings
from omniai.observability.metrics import MetricsRegistry
from omniai.plugins.chunk_templates.registry import ChunkTemplateRegistry, build_default_registry as build_chunk_registry
from omniai.plugins.parsers import ParserRegistry, build_default_registry
from omniai.ports.object_store import ObjectStorePort
from omniai.ports.queue import JobQueuePort
from omniai.ports.search_engine import SearchEnginePort
from omniai.security.secrets import SecretBox
from omniai.workers.indexing import INDEX_JOB_NAME
from omniai.workers.indexing import index_document as index_document_handler
from omniai.workers.parsing import parse_document as parse_document_handler


@dataclass(slots=True)
class Container:
    settings: Settings
    database: DatabaseManager
    metrics: MetricsRegistry
    secret_box: SecretBox
    object_store: ObjectStorePort
    job_queue: JobQueuePort
    parsers: ParserRegistry
    chunk_templates: ChunkTemplateRegistry
    search_engine: SearchEnginePort
    default_tenant_id: str


def build_container(settings: Settings) -> Container:
    database = DatabaseManager(settings.db_url, echo=settings.db_echo)
    if settings.auto_create_schema:
        database.create_schema()
    metrics = MetricsRegistry()
    secret_box = SecretBox(settings.encryption_key)
    object_store = build_object_store(settings)
    parsers = build_default_registry()
    chunk_templates = build_chunk_registry()
    search_engine = build_search_engine(settings)
    job_queue = build_job_queue(settings)

    if isinstance(job_queue, InlineJobQueue):
        async def _run_parse(tenant_id: str, document_id: str) -> None:
            await parse_document_handler(
                database=database,
                object_store=object_store,
                parsers=parsers,
                queue=job_queue,
                tenant_id=tenant_id,
                document_id=document_id,
            )

        async def _run_index(tenant_id: str, document_id: str) -> None:
            await index_document_handler(
                settings=settings,
                database=database,
                object_store=object_store,
                search_engine=search_engine,
                chunk_templates=chunk_templates,
                tenant_id=tenant_id,
                document_id=document_id,
            )

        job_queue.register(PARSE_JOB_NAME, _run_parse)
        job_queue.register(INDEX_JOB_NAME, _run_index)

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
        object_store=object_store,
        job_queue=job_queue,
        parsers=parsers,
        chunk_templates=chunk_templates,
        search_engine=search_engine,
        default_tenant_id=tenant.id,
    )
