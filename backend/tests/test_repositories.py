from __future__ import annotations

import pytest


def test_create_collection_rejects_duplicate_name(store):
    store.create_collection(
        name="Duplicate Test",
        description=None,
        embedding_model="nomic-embed-text",
        chunk_template="general",
    )
    with pytest.raises(ValueError):
        store.create_collection(
            name="duplicate test",  # case-insensitive uniqueness
            description=None,
            embedding_model="nomic-embed-text",
            chunk_template="general",
        )


def test_create_collection_persists_config_fields(store):
    col = store.create_collection(
        name="Configured Collection",
        description="desc",
        embedding_model="nomic-embed-text",
        chunk_template="general",
        system_prompt="You are a tax assistant.",
        top_k=12,
        vector_weight=0.8,
    )
    fetched = store.get_collection(col.id)
    assert fetched.system_prompt == "You are a tax assistant."
    assert fetched.top_k == 12
    assert fetched.vector_weight == pytest.approx(0.8)


def test_set_document_tags_normalizes_and_persists(store):
    col = store.create_collection(
        name="Tag Test",
        description=None,
        embedding_model="nomic-embed-text",
        chunk_template="general",
    )
    doc = store.create_document_with_storage(
        collection_id=col.id,
        name="x.txt",
        mime_type="text/plain",
        size_bytes=10,
        object_key="k",
        content_sha256="sha",
    )
    store.set_document_tags(document_id=doc.id, tags=["  Paris ", "monument", "monument", ""])
    fetched = store.get_document(doc.id)
    assert sorted(fetched.tags) == ["Paris", "monument"]


def test_list_documents_by_tag_filters(store):
    col = store.create_collection(
        name="Tag List Test",
        description=None,
        embedding_model="nomic-embed-text",
        chunk_template="general",
    )
    a = store.create_document_with_storage(
        collection_id=col.id, name="a.txt", mime_type="text/plain",
        size_bytes=1, object_key="a", content_sha256="a",
    )
    b = store.create_document_with_storage(
        collection_id=col.id, name="b.txt", mime_type="text/plain",
        size_bytes=1, object_key="b", content_sha256="b",
    )
    store.set_document_tags(document_id=a.id, tags=["foo"])
    store.set_document_tags(document_id=b.id, tags=["bar"])
    foo_docs = store.list_documents_by_tag(collection_id=col.id, tag="foo")
    assert {d.id for d in foo_docs} == {a.id}
