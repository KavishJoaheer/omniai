from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from omniai.application.ingestion_service import IngestionService
from omniai.connectors.base import ConnectorAdapter, hash_content
from omniai.connectors.confluence import ConfluenceConnector
from omniai.connectors.database import DatabaseConnector
from omniai.connectors.google_drive import GoogleDriveConnector
from omniai.connectors.local_folder import LocalFolderConnector
from omniai.connectors.notion import NotionConnector
from omniai.connectors.s3 import S3Connector
from omniai.connectors.sharepoint import SharePointConnector
from omniai.connectors.slack import SlackConnector
from omniai.connectors.webcrawler import WebCrawlerConnector
from omniai.domain.connectors.models import Connector, ConnectorSyncReport
from omniai.ports.connectors import ConnectorStorePort

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Distributed / in-process sync lock
# ---------------------------------------------------------------------------

class _InProcessSyncLock:
    """Per-connector asyncio.Lock that prevents double-sync within a single
    process.  Thread-safe because asyncio runs in one event loop."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def acquire(self, connector_id: str, *, ttl_seconds: int = 300) -> AsyncIterator[bool]:
        """Yield ``True`` if the lock was acquired, ``False`` if already held."""
        lock = self._locks.setdefault(connector_id, asyncio.Lock())
        if lock.locked():
            yield False
            return
        async with lock:
            yield True


class _RedisSyncLock:
    """Distributed connector lock backed by Redis SETNX.

    Uses a single SET key=1 NX EX <ttl> call.  If the key already exists
    (another replica holds the lock) we skip the connector.  The key expires
    automatically so a crashed worker never blocks indefinitely.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis = None  # lazy-init

    def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis  # type: ignore[import-untyped]
                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            except ImportError:
                raise RuntimeError(
                    "redis package is required for distributed connector locking. "
                    "Install it with: pip install redis"
                )
        return self._redis

    @asynccontextmanager
    async def acquire(self, connector_id: str, *, ttl_seconds: int = 300) -> AsyncIterator[bool]:
        key = f"omniai:connector_lock:{connector_id}"
        redis = self._get_redis()
        acquired: bool = await redis.set(key, "1", nx=True, ex=ttl_seconds)
        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            try:
                await redis.delete(key)
            except Exception:
                pass  # TTL will clean it up


def build_sync_lock(redis_url: str | None):
    """Return a _RedisSyncLock if Redis is configured, else in-process lock."""
    if redis_url:
        return _RedisSyncLock(redis_url)
    return _InProcessSyncLock()


_ADAPTER_REGISTRY: dict[str, type] = {
    "local_folder": LocalFolderConnector,
    "s3": S3Connector,
    "web_crawler": WebCrawlerConnector,
    # M17 — extended connector library
    "google_drive": GoogleDriveConnector,
    "sharepoint": SharePointConnector,
    "notion": NotionConnector,
    "confluence": ConfluenceConnector,
    "slack": SlackConnector,
    "database": DatabaseConnector,
}

#: Sorted list of all supported connector kind strings (used in route validation).
SUPPORTED_KINDS: list[str] = sorted(_ADAPTER_REGISTRY.keys())


def _build_adapter(kind: str) -> ConnectorAdapter:
    cls = _ADAPTER_REGISTRY.get(kind)
    if cls is None:
        raise ValueError(f"Unknown connector kind: {kind!r}. Supported: {SUPPORTED_KINDS}")
    return cls()


def _validate_config(kind: str, config: dict) -> None:
    cls = _ADAPTER_REGISTRY.get(kind)
    if cls is None:
        raise ValueError(f"Unknown connector kind: {kind!r}. Supported: {SUPPORTED_KINDS}")
    cls.validate_config(config)


async def preview_connector(kind: str, config: dict, max_items: int = 5) -> list[dict]:
    """Dry-run a connector: return a sample of what *would* be ingested.

    Returns a list of dicts with keys: source_id, filename, mime_type,
    size_bytes, content_preview (first 500 chars decoded as UTF-8).
    Never writes anything to the database or object store.
    """
    _validate_config(kind, config)
    adapter = _build_adapter(kind)
    results: list[dict] = []

    async for discovered in adapter.discover(config):
        preview_text = ""
        try:
            preview_text = discovered.content[:2000].decode("utf-8", errors="replace")
        except Exception:
            pass

        results.append({
            "source_id": discovered.source_id,
            "filename": discovered.filename,
            "mime_type": discovered.mime_type,
            "size_bytes": len(discovered.content),
            "content_preview": preview_text[:500],
        })
        if len(results) >= max_items:
            break

    return results


class ConnectorService:
    """Per-tenant CRUD + sync orchestration for ingestion connectors."""

    def __init__(
        self,
        *,
        store: ConnectorStorePort,
        ingestion: IngestionService,
        tenant_id: str,
    ) -> None:
        self._store = store
        self._ingestion = ingestion
        self._tenant_id = tenant_id

    def list(self, *, collection_id: str | None = None) -> list[Connector]:
        return self._store.list_connectors(collection_id=collection_id)

    def get(self, connector_id: str) -> Connector:
        return self._store.get_connector(connector_id)

    def create(
        self,
        *,
        collection_id: str,
        name: str,
        kind: str,
        config: dict,
        sync_interval_seconds: int = 300,
    ) -> Connector:
        _validate_config(kind, config)
        return self._store.create_connector(
            collection_id=collection_id,
            name=name,
            kind=kind,
            config=config,
            sync_interval_seconds=sync_interval_seconds,
        )

    def update(
        self,
        connector_id: str,
        *,
        name: str | None = None,
        config: dict | None = None,
        enabled: bool | None = None,
        sync_interval_seconds: int | None = None,
    ) -> Connector:
        if config is not None:
            existing = self._store.get_connector(connector_id)
            _validate_config(existing.kind, config)
        return self._store.update_connector(
            connector_id=connector_id,
            name=name,
            config=config,
            enabled=enabled,
            sync_interval_seconds=sync_interval_seconds,
        )

    def delete(self, connector_id: str) -> None:
        self._store.delete_connector(connector_id)

    async def sync(self, connector_id: str) -> ConnectorSyncReport:
        connector = self._store.get_connector(connector_id)
        return await self._sync_connector(connector)

    async def _sync_connector(self, connector: Connector) -> ConnectorSyncReport:
        adapter = _build_adapter(connector.kind)
        report = ConnectorSyncReport(connector_id=connector.id)
        seen = set(connector.seen_hashes)
        last_error: str | None = None

        try:
            async for discovered in adapter.discover(connector.config):
                report.discovered += 1
                digest = hash_content(discovered.content)
                if digest in seen:
                    report.skipped_duplicate += 1
                    continue
                try:
                    await self._ingestion.upload_document(
                        collection_id=connector.collection_id,
                        filename=discovered.filename,
                        mime_type=discovered.mime_type,
                        data=discovered.content,
                    )
                    seen.add(digest)
                    report.ingested += 1
                except ValueError as exc:
                    msg = f"{discovered.source_id}: {exc}"
                    report.errors.append(msg[:500])
                except Exception as exc:
                    logger.exception("connector %s: ingest failed for %s", connector.id, discovered.source_id)
                    report.errors.append(f"{discovered.source_id}: {exc}"[:500])
        except Exception as exc:
            logger.exception("connector %s: discover failed", connector.id)
            last_error = str(exc)[:500]

        if not last_error and report.errors:
            last_error = report.errors[0]

        self._store.record_sync(
            connector_id=connector.id,
            last_sync_at=datetime.now(timezone.utc),
            last_error=last_error,
            last_synced_count=report.ingested,
            seen_hashes=list(seen),
        )
        return report


class ConnectorScheduler:
    """Background task that polls every enabled connector on its own interval.

    Uses a separate database session per tick; never holds a request-scoped
    session. Safe to start at app boot and stop at shutdown.

    With ``sync_lock`` (a ``_RedisSyncLock`` or ``_InProcessSyncLock``), two
    API replicas that both run the scheduler will not double-sync the same
    connector: only the replica that acquires the lock will sync; the other
    skips that connector and tries again on the next tick.
    """

    def __init__(
        self,
        *,
        database,  # DatabaseManager
        object_store,
        queue,
        parsers,
        upload_max_bytes: int,
        tick_seconds: float = 30.0,
        sync_lock=None,  # _InProcessSyncLock | _RedisSyncLock | None
    ) -> None:
        self._database = database
        self._object_store = object_store
        self._queue = queue
        self._parsers = parsers
        self._upload_max_bytes = upload_max_bytes
        self._tick_seconds = tick_seconds
        self._sync_lock = sync_lock or _InProcessSyncLock()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        # Lazy imports to avoid circular deps at module load time
        from omniai.adapters.relational.sqlalchemy.repositories import (
            SqlAlchemyConnectorStore,
            SqlAlchemyKnowledgeStore,
        )

        while not self._stop.is_set():
            try:
                await self._tick(SqlAlchemyConnectorStore, SqlAlchemyKnowledgeStore)
            except Exception:
                logger.exception("connector scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_seconds)
            except asyncio.TimeoutError:
                pass

    async def _tick(self, ConnectorStore, KnowledgeStore) -> None:
        # First, snapshot enabled connectors across all tenants in a quick session
        with self._database.new_session() as session:
            store = ConnectorStore(session, "_unused")  # tenant_id ignored for cross-tenant query
            entries = store.list_enabled_connectors_across_tenants()

        now = datetime.now(timezone.utc)
        for tenant_id, connector in entries:
            if connector.last_sync_at is not None:
                elapsed = (now - connector.last_sync_at.replace(tzinfo=timezone.utc)).total_seconds()
                if elapsed < connector.sync_interval_seconds:
                    continue
            # Acquire a distributed lock so multi-replica deployments don't
            # double-sync the same connector at the same time.
            async with self._sync_lock.acquire(
                connector.id,
                ttl_seconds=max(int(connector.sync_interval_seconds), 60),
            ) as acquired:
                if not acquired:
                    logger.debug("connector %s: lock held by another replica, skipping", connector.id)
                    continue
                try:
                    with self._database.new_session() as session:
                        knowledge_store = KnowledgeStore(session, tenant_id)
                        ingestion = IngestionService(
                            store=knowledge_store,
                            object_store=self._object_store,
                            queue=self._queue,
                            parsers=self._parsers,
                            tenant_id=tenant_id,
                            max_bytes=self._upload_max_bytes,
                        )
                        connector_store = ConnectorStore(session, tenant_id)
                        service = ConnectorService(
                            store=connector_store,
                            ingestion=ingestion,
                            tenant_id=tenant_id,
                        )
                        report = await service.sync(connector.id)
                        logger.info(
                            "connector %s synced: ingested=%d skipped=%d errors=%d",
                            connector.id, report.ingested, report.skipped_duplicate, len(report.errors),
                        )
                except Exception:
                    logger.exception("connector %s scheduler error", connector.id)
