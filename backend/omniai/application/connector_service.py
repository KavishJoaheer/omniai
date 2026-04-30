from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from omniai.application.ingestion_service import IngestionService
from omniai.connectors.base import ConnectorAdapter, hash_content
from omniai.connectors.local_folder import LocalFolderConnector
from omniai.connectors.s3 import S3Connector
from omniai.connectors.webcrawler import WebCrawlerConnector
from omniai.domain.connectors.models import Connector, ConnectorSyncReport
from omniai.ports.connectors import ConnectorStorePort

logger = logging.getLogger(__name__)


def _build_adapter(kind: str) -> ConnectorAdapter:
    if kind == "local_folder":
        return LocalFolderConnector()
    if kind == "s3":
        return S3Connector()
    if kind == "web_crawler":
        return WebCrawlerConnector()
    raise ValueError(f"Unknown connector kind: {kind!r}")


def _validate_config(kind: str, config: dict) -> None:
    if kind == "local_folder":
        LocalFolderConnector.validate_config(config)
    elif kind == "s3":
        S3Connector.validate_config(config)
    elif kind == "web_crawler":
        WebCrawlerConnector.validate_config(config)
    else:
        raise ValueError(f"Unknown connector kind: {kind!r}")


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
    ) -> None:
        self._database = database
        self._object_store = object_store
        self._queue = queue
        self._parsers = parsers
        self._upload_max_bytes = upload_max_bytes
        self._tick_seconds = tick_seconds
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
