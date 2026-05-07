"""Tests for document versioning (upsert-by-name) in IngestionService."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from omniai.application.ingestion_service import IngestionService
from omniai.domain.knowledge.models import Document


def _make_document(doc_id: str = "doc1", sha256: str = "abc123", name: str = "test.txt") -> Document:
    return Document(
        id=doc_id,
        collection_id="col1",
        tenant_id="t1",
        name=name,
        mime_type="text/plain",
        size_bytes=100,
        status="READY",
        content_sha256=sha256,
        object_key="tenants/t1/collections/col1/sources/abc123.txt",
    )


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.count_documents.return_value = 0
    store.list_collections.return_value = []
    store.find_document_by_name.return_value = None  # new document by default
    return store


@pytest.fixture
def mock_object_store():
    obj_store = MagicMock()
    obj_store.put_object.return_value = None
    return obj_store


@pytest.fixture
def mock_queue():
    queue = AsyncMock()
    queue.enqueue.return_value = None
    return queue


@pytest.fixture
def mock_parsers():
    parsers = MagicMock()
    parsers.resolve.return_value = MagicMock()  # non-None means supported
    return parsers


@pytest.fixture
def ingestion(mock_store, mock_object_store, mock_queue, mock_parsers):
    return IngestionService(
        store=mock_store,
        object_store=mock_object_store,
        queue=mock_queue,
        parsers=mock_parsers,
        tenant_id="t1",
        max_bytes=10 * 1024 * 1024,
    )


# ── New document (no prior version) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_new_document_creates_and_enqueues(ingestion, mock_store, mock_queue):
    """Uploading a file with no prior version should create a new document."""
    new_doc = _make_document(sha256="sha256ofcontent")
    mock_store.create_document_with_storage.return_value = new_doc

    data = b"Hello world content"
    doc = await ingestion.upload_document(
        collection_id="col1",
        filename="test.txt",
        mime_type="text/plain",
        data=data,
    )

    assert doc.id == new_doc.id
    mock_store.create_document_with_storage.assert_called_once()
    mock_queue.enqueue.assert_awaited_once()


# ── Identical re-upload (same SHA-256) ────────────────────────────────────


@pytest.mark.asyncio
async def test_identical_reupload_returns_existing_without_create(ingestion, mock_store, mock_queue):
    """Re-uploading a file with the same content should return the existing document."""
    data = b"Identical content"
    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    existing = _make_document(sha256=sha)
    mock_store.find_document_by_name.return_value = existing

    doc = await ingestion.upload_document(
        collection_id="col1",
        filename="test.txt",
        mime_type="text/plain",
        data=data,
    )

    assert doc.id == existing.id
    # Must NOT create a new document record
    mock_store.create_document_with_storage.assert_not_called()
    # Must NOT enqueue a parse job
    mock_queue.enqueue.assert_not_awaited()


# ── Changed content (different SHA-256) ───────────────────────────────────


@pytest.mark.asyncio
async def test_updated_content_updates_existing_document(ingestion, mock_store, mock_object_store, mock_queue):
    """Re-uploading with different content should update the existing document in-place."""
    old_sha = "aaaaaaaabbbbbbbbcccccccc"
    existing = _make_document(sha256=old_sha)
    mock_store.find_document_by_name.return_value = existing

    new_data = b"Brand new content that differs from the old version"
    import hashlib
    new_sha = hashlib.sha256(new_data).hexdigest()

    updated_doc = _make_document(sha256=new_sha)
    mock_store.update_document_storage.return_value = updated_doc

    await ingestion.upload_document(
        collection_id="col1",
        filename="test.txt",
        mime_type="text/plain",
        data=new_data,
    )

    # Must update, not create
    mock_store.update_document_storage.assert_called_once()
    mock_store.create_document_with_storage.assert_not_called()

    # Must enqueue re-parsing
    mock_queue.enqueue.assert_awaited_once()
    call_kwargs = mock_queue.enqueue.call_args.kwargs
    assert call_kwargs["payload"]["document_id"] == updated_doc.id

    # New object must have been stored
    mock_object_store.put_object.assert_called_once()


@pytest.mark.asyncio
async def test_updated_content_clears_search_index(ingestion, mock_store, mock_queue):
    """When content changes the old search index should be cleared."""
    old_sha = "old_sha_hex"
    existing = _make_document(doc_id="old_doc", sha256=old_sha)
    mock_store.find_document_by_name.return_value = existing

    new_data = b"Updated content for versioning test"
    updated_doc = _make_document(doc_id="old_doc", sha256="new_sha")
    mock_store.update_document_storage.return_value = updated_doc

    search_engine = MagicMock()
    search_engine.delete_by_document.return_value = None

    await ingestion.upload_document(
        collection_id="col1",
        filename="test.txt",
        mime_type="text/plain",
        data=new_data,
        search_engine=search_engine,
    )

    search_engine.delete_by_document.assert_called_once_with(
        tenant_id="t1", document_id="old_doc"
    )


@pytest.mark.asyncio
async def test_update_search_index_failure_is_non_fatal(ingestion, mock_store, mock_queue):
    """A failure to clear the old search index should not abort the upload."""
    old_sha = "stale_sha"
    existing = _make_document(sha256=old_sha)
    mock_store.find_document_by_name.return_value = existing

    new_data = b"Changed content"
    updated_doc = _make_document(sha256="new_sha")
    mock_store.update_document_storage.return_value = updated_doc

    search_engine = MagicMock()
    search_engine.delete_by_document.side_effect = RuntimeError("search is down")

    # Should not raise
    doc = await ingestion.upload_document(
        collection_id="col1",
        filename="test.txt",
        mime_type="text/plain",
        data=new_data,
        search_engine=search_engine,
    )
    assert doc.id == updated_doc.id


# ── Validation guards still apply ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_file_raises(ingestion):
    with pytest.raises(ValueError, match="empty"):
        await ingestion.upload_document(
            collection_id="col1",
            filename="empty.txt",
            mime_type="text/plain",
            data=b"",
        )


@pytest.mark.asyncio
async def test_file_too_large_raises(ingestion):
    with pytest.raises(ValueError, match="exceeds upload limit"):
        await ingestion.upload_document(
            collection_id="col1",
            filename="big.bin",
            mime_type="application/octet-stream",
            data=b"x" * (11 * 1024 * 1024),  # 11 MiB > 10 MiB limit
        )


@pytest.mark.asyncio
async def test_unsupported_mime_raises(ingestion, mock_parsers):
    mock_parsers.resolve.return_value = None  # unsupported
    with pytest.raises(ValueError, match="Unsupported"):
        await ingestion.upload_document(
            collection_id="col1",
            filename="file.xyz",
            mime_type="application/x-unknown",
            data=b"some data",
        )


# ── update_document_storage method on store ──────────────────────────────


@pytest.mark.asyncio
async def test_update_document_storage_args(ingestion, mock_store, mock_queue):
    """Ensure update_document_storage is called with the new sha256 and object_key."""
    import hashlib

    old_sha = "OLD_SHA_HEX_PLACEHOLDER_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    existing = _make_document(sha256=old_sha)
    mock_store.find_document_by_name.return_value = existing

    new_data = b"Totally different file content here for versioning"
    new_sha = hashlib.sha256(new_data).hexdigest()
    updated = _make_document(sha256=new_sha)
    mock_store.update_document_storage.return_value = updated

    await ingestion.upload_document(
        collection_id="col1",
        filename="report.txt",
        mime_type="text/plain",
        data=new_data,
    )

    call_kwargs = mock_store.update_document_storage.call_args.kwargs
    assert call_kwargs["document_id"] == existing.id
    assert call_kwargs["content_sha256"] == new_sha
    assert call_kwargs["size_bytes"] == len(new_data)
    assert new_sha in call_kwargs["object_key"]
