from __future__ import annotations

import logging
from typing import Any

from arq.connections import RedisSettings

from omniai.adapters.object_store import build_object_store
from omniai.adapters.queue.arq_queue import ArqJobQueue
from omniai.adapters.relational.sqlalchemy.session import DatabaseManager
from omniai.adapters.search.factory import build_search_engine
from omniai.config.settings import get_settings
from omniai.plugins.chunk_templates.registry import build_default_registry as build_chunk_registry
from omniai.plugins.parsers import build_default_registry
from omniai.security.secrets import SecretBox
from omniai.workers.graph_extraction import extract_graph as run_extract_graph
from omniai.workers.indexing import index_document as run_index_document
from omniai.workers.parsing import parse_document as run_parse_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
logger = logging.getLogger("omniai.worker")


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    ctx["settings"] = settings
    ctx["database"] = DatabaseManager(settings.db_url, echo=settings.db_echo)
    ctx["object_store"] = build_object_store(settings)
    ctx["parsers"] = build_default_registry()
    ctx["chunk_templates"] = build_chunk_registry()
    ctx["search_engine"] = build_search_engine(settings)
    ctx["secret_box"] = SecretBox(settings.encryption_key)
    # give parse worker a minimal queue so it can chain into index
    ctx["queue"] = ArqJobQueue(redis_url=settings.redis_url)
    logger.info("worker started against db=%s object_store=%s", settings.db_url, settings.object_store_kind)


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("worker shutting down")


async def parse_document(ctx: dict[str, Any], tenant_id: str, document_id: str) -> None:
    await run_parse_document(
        database=ctx["database"],
        object_store=ctx["object_store"],
        parsers=ctx["parsers"],
        queue=ctx["queue"],
        tenant_id=tenant_id,
        document_id=document_id,
    )


async def index_document(ctx: dict[str, Any], tenant_id: str, document_id: str) -> None:
    await run_index_document(
        settings=ctx["settings"],
        database=ctx["database"],
        object_store=ctx["object_store"],
        search_engine=ctx["search_engine"],
        chunk_templates=ctx["chunk_templates"],
        queue=ctx["queue"],
        tenant_id=tenant_id,
        document_id=document_id,
    )


async def extract_graph(ctx: dict[str, Any], tenant_id: str, document_id: str) -> None:
    await run_extract_graph(
        settings=ctx["settings"],
        database=ctx["database"],
        object_store=ctx["object_store"],
        search_engine=ctx["search_engine"],
        secret_box=ctx["secret_box"],
        tenant_id=tenant_id,
        document_id=document_id,
    )


class WorkerSettings:
    functions = [parse_document, index_document, extract_graph]
    on_startup = startup
    on_shutdown = shutdown

    @classmethod
    def redis_settings(cls) -> RedisSettings:
        settings = get_settings()
        if not settings.redis_url:
            raise RuntimeError("REDIS_URL must be set to run the arq worker.")
        return RedisSettings.from_dsn(settings.redis_url)
