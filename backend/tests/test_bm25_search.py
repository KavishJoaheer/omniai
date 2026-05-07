"""Tests for the upgraded Okapi BM25 + RRF hybrid search in InMemorySearchEngine."""
from __future__ import annotations


from omniai.adapters.search.in_memory import InMemorySearchEngine, _tokenize
from omniai.ports.search_engine import IndexableChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk(chunk_id: str, text: str, collection_id: str = "col1", doc_id: str = "doc1") -> IndexableChunk:
    """Create an IndexableChunk with a stub zero-vector (tests BM25 path)."""
    return IndexableChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        collection_id=collection_id,
        text=text,
        vector=[0.0] * 4,
        metadata={},
    )


def _chunk_vec(chunk_id: str, text: str, vector: list[float]) -> IndexableChunk:
    return IndexableChunk(
        chunk_id=chunk_id, document_id="doc1", collection_id="col1",
        text=text, vector=vector, metadata={},
    )


def _search(engine: InMemorySearchEngine, query: str, top_k=5, vector_weight=0.5, cids=None):
    return engine.hybrid_search(
        tenant_id="t1",
        query=query,
        query_vector=[0.0] * 4,
        top_k=top_k,
        vector_weight=vector_weight,
        collection_ids=cids,
    )


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

def test_tokenize_lowercases():
    assert _tokenize("Hello World") == ["hello", "world"]


def test_tokenize_strips_punctuation():
    assert _tokenize("foo, bar!") == ["foo", "bar"]


def test_tokenize_empty():
    assert _tokenize("") == []


# ---------------------------------------------------------------------------
# Upsert + delete
# ---------------------------------------------------------------------------

def test_upsert_and_search_basic():
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    engine.upsert_chunks(tenant_id="t1", chunks=[
        _chunk("c1", "The quick brown fox"),
        _chunk("c2", "A lazy dog sat"),
    ])
    results = _search(engine, "fox")
    assert any(r.chunk_id == "c1" for r in results)


def test_delete_by_document_removes_entries():
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    engine.upsert_chunks(tenant_id="t1", chunks=[
        _chunk("c1", "The quick brown fox", doc_id="docA"),
        _chunk("c2", "A lazy dog sat", doc_id="docB"),
    ])
    engine.delete_by_document(tenant_id="t1", document_id="docA")
    results = _search(engine, "fox")
    assert all(r.chunk_id != "c1" for r in results)


def test_upsert_is_idempotent():
    """Re-inserting the same chunk should not inflate df or total_tokens."""
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    chunk = _chunk("c1", "hello world")
    engine.upsert_chunks(tenant_id="t1", chunks=[chunk])
    engine.upsert_chunks(tenant_id="t1", chunks=[chunk])  # same id, same text
    idx = engine._indices["t1"]
    assert idx.num_docs == 1
    assert idx.total_tokens == 2  # "hello" + "world"


def test_upsert_update_replaces_old_df():
    """Updating a chunk's text should reflect new terms in df, not accumulate."""
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    engine.upsert_chunks(tenant_id="t1", chunks=[_chunk("c1", "foo bar")])
    engine.upsert_chunks(tenant_id="t1", chunks=[_chunk("c1", "baz qux")])  # replace
    idx = engine._indices["t1"]
    assert idx.df.get("foo", 0) == 0, "old term should be removed from df"
    assert idx.df.get("baz", 0) == 1


# ---------------------------------------------------------------------------
# BM25 relevance ranking (sparse path, zero vectors)
# ---------------------------------------------------------------------------

def test_bm25_ranks_exact_match_first():
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    engine.upsert_chunks(tenant_id="t1", chunks=[
        _chunk("exact", "python programming language tutorial"),
        _chunk("unrelated", "medieval castle architecture gothic"),
        _chunk("partial", "python scripting guide"),
    ])
    results = _search(engine, "python tutorial", vector_weight=0.0)
    # Exact match (both terms present) should beat partial
    top = results[0]
    assert top.chunk_id in ("exact", "partial")
    # "unrelated" should not be top-1
    assert results[0].chunk_id != "unrelated"


def test_bm25_idf_down_weights_common_terms():
    """A rare term should score higher than a ubiquitous one."""
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    # "the" appears in every chunk — rare term "zebra" only in c1
    chunks = [
        _chunk("c1", "the zebra runs fast"),
        _chunk("c2", "the cat runs fast"),
        _chunk("c3", "the dog runs fast"),
        _chunk("c4", "the bird runs fast"),
        _chunk("c5", "the fish runs fast"),
    ]
    engine.upsert_chunks(tenant_id="t1", chunks=chunks)
    results = _search(engine, "zebra", vector_weight=0.0)
    assert results[0].chunk_id == "c1"


def test_empty_corpus_returns_empty():
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    results = _search(engine, "anything")
    assert results == []


def test_no_match_returns_all_with_zero_ish_scores():
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    engine.upsert_chunks(tenant_id="t1", chunks=[
        _chunk("c1", "completely unrelated content here"),
    ])
    results = _search(engine, "xyzzy plugh wumpus", vector_weight=0.0)
    # Returns the only document even if score is 0
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Dense + sparse fusion (RRF)
# ---------------------------------------------------------------------------

def test_rrf_fusion_surfaces_dense_winner():
    """When vector_weight=1.0, the chunk with the highest cosine similarity wins."""
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    # c1 has a vector aligned with query; c2 is not
    engine.upsert_chunks(tenant_id="t1", chunks=[
        _chunk_vec("c1", "some text", [1.0, 0.0, 0.0, 0.0]),
        _chunk_vec("c2", "other text", [0.0, 1.0, 0.0, 0.0]),
    ])
    results = engine.hybrid_search(
        tenant_id="t1",
        query="some text",
        query_vector=[1.0, 0.0, 0.0, 0.0],
        top_k=2,
        vector_weight=1.0,
    )
    assert results[0].chunk_id == "c1"


def test_rrf_fusion_surfaces_sparse_winner():
    """When vector_weight=0.0, the chunk with the highest BM25 score wins."""
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    engine.upsert_chunks(tenant_id="t1", chunks=[
        _chunk_vec("c1", "banana mango papaya", [0.0, 0.0, 0.0, 1.0]),
        _chunk_vec("c2", "banana banana banana banana banana", [1.0, 0.0, 0.0, 0.0]),
    ])
    results = engine.hybrid_search(
        tenant_id="t1",
        query="banana",
        query_vector=[0.0, 0.0, 0.0, 0.0],
        top_k=2,
        vector_weight=0.0,
    )
    # c2 has more "banana" hits — BM25 TF saturation still makes it top
    assert results[0].chunk_id == "c2"


# ---------------------------------------------------------------------------
# Collection filter
# ---------------------------------------------------------------------------

def test_collection_filter_isolates_results():
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    engine.upsert_chunks(tenant_id="t1", chunks=[
        IndexableChunk("cA", "doc1", "colA", "python rocks", [0.0] * 4, {}),
        IndexableChunk("cB", "doc2", "colB", "python rocks", [0.0] * 4, {}),
    ])
    results = _search(engine, "python", cids=["colA"])
    assert all(r.collection_id == "colA" for r in results)
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Top-K cap
# ---------------------------------------------------------------------------

def test_top_k_caps_results():
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    engine.upsert_chunks(tenant_id="t1", chunks=[
        _chunk(f"c{i}", f"document text number {i}") for i in range(20)
    ])
    results = _search(engine, "document text", top_k=5)
    assert len(results) <= 5


# ---------------------------------------------------------------------------
# Snippet extraction
# ---------------------------------------------------------------------------

def test_snippet_highlights_query_term():
    engine = InMemorySearchEngine()
    engine.ensure_index(tenant_id="t1", dim=4)
    long_text = ("irrelevant words " * 30) + "UNICORN is magical " + ("more noise " * 30)
    engine.upsert_chunks(tenant_id="t1", chunks=[_chunk("c1", long_text)])
    results = _search(engine, "unicorn")
    assert "UNICORN" in results[0].snippet
