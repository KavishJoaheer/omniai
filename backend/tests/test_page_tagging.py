"""End-to-end tests for PDF citation page numbers.

We don't generate real PDFs here — instead we verify the indexing-worker page
tagging logic directly, since it's the piece that scans for [OMNI_PAGE_N]
markers and writes page_number into chunk metadata. This isolates the unit
under test from the (heavy) PDF parsing path.
"""
from __future__ import annotations

import json


from omniai.adapters.relational.sqlalchemy.models import ChunkRecord
from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore
from omniai.plugins.parsers.pdf import PAGE_MARKER_RE, page_marker
from omniai.workers.indexing import _tag_chunk_pages


def test_page_marker_format_round_trips():
    text = page_marker(7)
    match = PAGE_MARKER_RE.search(text)
    assert match is not None
    assert int(match.group(1)) == 7


def test_tag_chunk_pages_assigns_pages_and_strips_markers(container, tenant_id):
    store = SqlAlchemyKnowledgeStore(container.database.new_session(), tenant_id)
    col = store.create_collection(
        name="Page Tagging Test",
        description=None,
        embedding_model="nomic-embed-text",
        chunk_template="general",
    )
    doc = store.create_document_with_storage(
        collection_id=col.id,
        name="paper.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        object_key="k",
        content_sha256="sha-pages",
    )

    chunks = [
        {"text": page_marker(1) + "Intro paragraph about the topic.", "metadata": {}},
        {"text": "Continuation of page 1 content here.", "metadata": {}},
        {"text": page_marker(2) + "Page two starts here. Important fact A.", "metadata": {}},
        {"text": page_marker(2) + "Still on page 2. " + page_marker(3) + "Now on page 3.", "metadata": {}},
        {"text": "Trailing chunk with no marker.", "metadata": {}},
    ]
    store.replace_chunks(document_id=doc.id, chunks=chunks, template_name="general")

    session = container.database.new_session()
    try:
        live = list(
            session.query(ChunkRecord)
            .filter(ChunkRecord.document_id == doc.id)
            .order_by(ChunkRecord.ordinal.asc())
        )
        # Sanity: tag fn assumes the in-memory chunk objects mirror DB rows
        from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore as _S

        domain_chunks = [_S._to_chunk(r) for r in live]
        _tag_chunk_pages(session, domain_chunks)

        refreshed = list(
            session.query(ChunkRecord)
            .filter(ChunkRecord.document_id == doc.id)
            .order_by(ChunkRecord.ordinal.asc())
        )
    finally:
        session.close()

    metas = [json.loads(r.metadata_json) for r in refreshed]
    pages = [m.get("page_number") for m in metas]

    # Chunk 0 starts on page 1, chunk 1 inherits page 1 (no marker),
    # chunk 2 starts page 2, chunk 3 has BOTH page 2 and page 3 markers,
    # chunk 4 inherits page 3.
    assert pages[0] == 1
    assert pages[1] == 1
    assert pages[2] == 2
    assert pages[3] == 2  # start_page
    assert metas[3].get("start_page") == 2
    assert metas[3].get("end_page") == 3
    assert pages[4] == 3

    # Markers must be stripped from stored text
    for r in refreshed:
        assert "[OMNI_PAGE_" not in r.text


def test_tag_chunk_pages_skips_non_pdf_chunks(container, tenant_id):
    """If no chunk has any marker (e.g. a plain TXT doc) the tagger is a no-op."""
    store = SqlAlchemyKnowledgeStore(container.database.new_session(), tenant_id)
    col = store.create_collection(
        name="No Markers",
        description=None,
        embedding_model="nomic-embed-text",
        chunk_template="general",
    )
    doc = store.create_document_with_storage(
        collection_id=col.id, name="x.txt", mime_type="text/plain",
        size_bytes=1, object_key="k2", content_sha256="sha-nomark",
    )
    store.replace_chunks(
        document_id=doc.id,
        chunks=[{"text": "Plain content with no markers.", "metadata": {}}],
        template_name="general",
    )

    session = container.database.new_session()
    try:
        live = list(
            session.query(ChunkRecord)
            .filter(ChunkRecord.document_id == doc.id)
            .order_by(ChunkRecord.ordinal.asc())
        )
        domain_chunks = [SqlAlchemyKnowledgeStore._to_chunk(r) for r in live]
        _tag_chunk_pages(session, domain_chunks)
        refreshed = list(
            session.query(ChunkRecord)
            .filter(ChunkRecord.document_id == doc.id)
            .order_by(ChunkRecord.ordinal.asc())
        )
    finally:
        session.close()

    meta = json.loads(refreshed[0].metadata_json)
    assert "page_number" not in meta
    assert refreshed[0].text == "Plain content with no markers."
