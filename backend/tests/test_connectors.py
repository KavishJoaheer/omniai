from __future__ import annotations

import pathlib
import tempfile

import pytest

from omniai.connectors.local_folder import LocalFolderConnector


@pytest.fixture
def folder_with_files() -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp(prefix="connector-test-"))
    (root / "a.txt").write_text("hello world")
    (root / "b.md").write_text("# Hello")
    (root / "ignore.bin").write_bytes(b"\x00\x01\x02")
    sub = root / "nested"
    sub.mkdir()
    (sub / "c.txt").write_text("nested content")
    return root


async def _collect(connector: LocalFolderConnector, config: dict) -> list:
    out = []
    async for f in connector.discover(config):
        out.append(f)
    return out


@pytest.mark.asyncio
async def test_local_folder_recursive_finds_supported_files(folder_with_files):
    connector = LocalFolderConnector()
    files = await _collect(connector, {"path": str(folder_with_files)})
    names = sorted(f.filename for f in files)
    # ignore.bin is excluded (extension not allowed)
    assert names == ["a.txt", "b.md", "c.txt"]


@pytest.mark.asyncio
async def test_local_folder_respects_recursive_flag(folder_with_files):
    connector = LocalFolderConnector()
    files = await _collect(connector, {"path": str(folder_with_files), "recursive": False})
    names = sorted(f.filename for f in files)
    assert names == ["a.txt", "b.md"]


@pytest.mark.asyncio
async def test_local_folder_extension_filter(folder_with_files):
    connector = LocalFolderConnector()
    files = await _collect(connector, {"path": str(folder_with_files), "extensions": [".md"]})
    names = sorted(f.filename for f in files)
    assert names == ["b.md"]


@pytest.mark.asyncio
async def test_local_folder_missing_path_yields_nothing():
    connector = LocalFolderConnector()
    files = await _collect(connector, {"path": "/nonexistent/path/12345"})
    assert files == []


def test_local_folder_validate_config_requires_path():
    with pytest.raises(ValueError):
        LocalFolderConnector.validate_config({})


def test_local_folder_validate_config_accepts_valid_path(folder_with_files):
    LocalFolderConnector.validate_config({"path": str(folder_with_files)})


def test_connector_store_crud(store, container, tenant_id):
    """Round-trip a connector through the SQLAlchemy store."""
    from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyConnectorStore

    col = store.create_collection(
        name="Connector Smoke",
        description=None,
        embedding_model="nomic-embed-text",
        chunk_template="general",
    )

    session = container.database.new_session()
    try:
        c_store = SqlAlchemyConnectorStore(session, tenant_id)
        connector = c_store.create_connector(
            collection_id=col.id,
            name="my folder",
            kind="local_folder",
            config={"path": "/tmp/x"},
            sync_interval_seconds=120,
        )
        assert connector.id.startswith("cnt_")
        assert connector.collection_id == col.id

        listed = c_store.list_connectors(collection_id=col.id)
        assert any(c.id == connector.id for c in listed)

        updated = c_store.update_connector(
            connector_id=connector.id,
            sync_interval_seconds=600,
            enabled=False,
        )
        assert updated.sync_interval_seconds == 600
        assert updated.enabled is False

        c_store.delete_connector(connector.id)
        with pytest.raises(KeyError):
            c_store.get_connector(connector.id)
    finally:
        session.close()


@pytest.mark.asyncio
async def test_connector_service_sync_dedups_by_content_hash(container, tenant_id, store, folder_with_files):
    """End-to-end: sync runs, ingests new files, second sync skips duplicates."""
    from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyConnectorStore
    from omniai.application.connector_service import ConnectorService
    from omniai.application.ingestion_service import IngestionService

    col = store.create_collection(
        name="Connector Sync Smoke",
        description=None,
        embedding_model="nomic-embed-text",
        chunk_template="general",
    )

    session = container.database.new_session()
    try:
        c_store = SqlAlchemyConnectorStore(session, tenant_id)
        connector = c_store.create_connector(
            collection_id=col.id,
            name="folder-watcher",
            kind="local_folder",
            config={"path": str(folder_with_files)},
        )

        ingestion = IngestionService(
            store=store,
            object_store=container.object_store,
            queue=container.job_queue,
            parsers=container.parsers,
            tenant_id=tenant_id,
            max_bytes=10_000_000,
        )
        service = ConnectorService(store=c_store, ingestion=ingestion, tenant_id=tenant_id)

        report = await service.sync(connector.id)
        assert report.discovered == 3
        assert report.ingested == 3
        assert report.skipped_duplicate == 0

        # Second sync — same content, same hashes, all dedup'd
        report2 = await service.sync(connector.id)
        assert report2.skipped_duplicate == 3
        assert report2.ingested == 0
    finally:
        session.close()
