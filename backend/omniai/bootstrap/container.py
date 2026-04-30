from __future__ import annotations

from dataclasses import dataclass

from omniai.adapters.object_store import build_object_store
from omniai.adapters.queue import build_job_queue
from omniai.adapters.queue.inline import InlineJobQueue
from omniai.adapters.relational.sqlalchemy.repositories import ensure_tenant
from omniai.adapters.relational.sqlalchemy.session import DatabaseManager
from omniai.adapters.search.factory import build_search_engine
from omniai.application.auth_service import AuthService
from omniai.application.connector_service import ConnectorScheduler
from omniai.application.ingestion_service import PARSE_JOB_NAME
from omniai.application.provider_service import seed_default_providers
from omniai.config.settings import Settings
from omniai.observability.metrics import MetricsRegistry
from omniai.plugins.chunk_templates.registry import ChunkTemplateRegistry, build_default_registry as build_chunk_registry
from omniai.plugins.embedding_providers.ollama import OllamaEmbeddingProvider
from omniai.plugins.ocr.factory import build_ocr_backend
from omniai.plugins.parsers import ParserRegistry, build_default_registry
from omniai.plugins.rerankers.factory import build_reranker
from omniai.plugins.sandbox.factory import build_sandbox
from omniai.ports.object_store import ObjectStorePort
from omniai.ports.queue import JobQueuePort
from omniai.ports.reranker import RerankerPort
from omniai.ports.sandbox import SandboxPort
from omniai.ports.search_engine import SearchEnginePort
from omniai.security.secrets import SecretBox
from omniai.utils.cache import RetrievalCachePort, build_retrieval_cache
from omniai.workers.graph_extraction import GRAPH_JOB_NAME
from omniai.workers.graph_extraction import extract_graph as extract_graph_handler
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
    reranker: RerankerPort
    sandbox: SandboxPort | None
    retrieval_cache: RetrievalCachePort | None
    connector_scheduler: ConnectorScheduler
    default_tenant_id: str


def build_container(settings: Settings) -> Container:
    database = DatabaseManager(settings.db_url, echo=settings.db_echo)
    if settings.auto_create_schema:
        database.create_schema()
    metrics = MetricsRegistry()
    secret_box = SecretBox(settings.encryption_key)
    object_store = build_object_store(settings)
    ocr_backend = build_ocr_backend(settings)
    parsers = build_default_registry(
        ocr_backend=ocr_backend,
        ocr_min_chars_per_page=settings.ocr_min_chars_per_page,
        ocr_image_dpi=settings.ocr_image_dpi,
    )
    chunk_templates = build_chunk_registry()
    search_engine = build_search_engine(settings)
    job_queue = build_job_queue(settings)
    reranker = build_reranker(
        settings=settings,
        embedding_provider=OllamaEmbeddingProvider(base_url=settings.ollama_base_url),
        embedding_model="nomic-embed-text",
    )
    sandbox = build_sandbox(settings)
    retrieval_cache = build_retrieval_cache(
        redis_url=settings.redis_url,
        ttl_seconds=settings.retrieval_cache_ttl_seconds,
    )

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
                queue=job_queue,
                tenant_id=tenant_id,
                document_id=document_id,
            )

        async def _run_graph(tenant_id: str, document_id: str) -> None:
            await extract_graph_handler(
                settings=settings,
                database=database,
                object_store=object_store,
                search_engine=search_engine,
                secret_box=secret_box,
                tenant_id=tenant_id,
                document_id=document_id,
            )

        job_queue.register(PARSE_JOB_NAME, _run_parse)
        job_queue.register(INDEX_JOB_NAME, _run_index)
        job_queue.register(GRAPH_JOB_NAME, _run_graph)

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

    connector_scheduler = ConnectorScheduler(
        database=database,
        object_store=object_store,
        queue=job_queue,
        parsers=parsers,
        upload_max_bytes=settings.upload_max_bytes,
        tick_seconds=30.0,
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
        reranker=reranker,
        sandbox=sandbox,
        retrieval_cache=retrieval_cache,
        connector_scheduler=connector_scheduler,
        default_tenant_id=tenant.id,
    )
