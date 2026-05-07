"""Tests for the in-process retrieval cache and RetrievalService cache integration."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from omniai.application.retrieval_service import RetrievalRequest, RetrievalService
from omniai.ports.search_engine import SearchHit
from omniai.utils.cache import InProcessCache, deserialize, serialize


# ── InProcessCache unit tests ─────────────────────────────────────────────


class TestInProcessCache:
    def test_miss_returns_none(self):
        cache = InProcessCache()
        assert cache.get("nonexistent") is None

    def test_set_and_get(self):
        cache = InProcessCache()
        cache.set("k", b"hello", ttl=60)
        assert cache.get("k") == b"hello"

    def test_expired_entry_returns_none(self):
        cache = InProcessCache()
        cache.set("k", b"data", ttl=1)
        # Manually expire by overwriting with past timestamp
        cache._store["k"] = (b"data", time.monotonic() - 1)
        assert cache.get("k") is None

    def test_ttl_zero_not_stored(self):
        cache = InProcessCache()
        cache.set("k", b"data", ttl=0)
        assert cache.get("k") is None

    def test_ttl_negative_not_stored(self):
        cache = InProcessCache()
        cache.set("k", b"data", ttl=-5)
        assert cache.get("k") is None

    def test_delete_removes_key(self):
        cache = InProcessCache()
        cache.set("k", b"data", ttl=60)
        cache.delete("k")
        assert cache.get("k") is None

    def test_delete_nonexistent_is_silent(self):
        cache = InProcessCache()
        cache.delete("ghost")  # should not raise

    def test_eviction_on_max_size(self):
        cache = InProcessCache(max_size=4)
        for i in range(5):
            cache.set(f"k{i}", f"v{i}".encode(), ttl=60)
        # After eviction, store should be at most max_size
        assert len(cache._store) <= cache._max_size

    def test_stats(self):
        cache = InProcessCache(max_size=100)
        cache.set("a", b"1", ttl=60)
        cache.set("b", b"2", ttl=60)
        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["max_size"] == 100


# ── Serialization ─────────────────────────────────────────────────────────


class TestSerialization:
    def test_roundtrip_bytes(self):
        assert deserialize(serialize(b"bytes")) == b"bytes"

    def test_roundtrip_list(self):
        obj = [1, "two", 3.0]
        assert deserialize(serialize(obj)) == obj

    def test_empty_bytes_returns_none(self):
        assert deserialize(b"") is None

    def test_invalid_bytes_returns_none(self):
        assert deserialize(b"not-pickle-data!!@#") is None

    def test_serialize_unserializable_returns_empty(self):
        # A generator is not picklable
        result = serialize((x for x in range(3)))
        assert result == b""


# ── RetrievalService cache integration ───────────────────────────────────


def _make_hit(text: str = "snippet") -> SearchHit:
    return SearchHit(
        chunk_id="c1",
        document_id="d1",
        collection_id="col1",
        score=0.9,
        text=text,
        snippet=text[:80],
        metadata={},
    )


@pytest.fixture
def mock_search_engine():
    engine = MagicMock()
    engine.hybrid_search.return_value = [_make_hit("hello")]
    return engine


@pytest.fixture
def mock_embedding_provider():
    provider = AsyncMock()
    provider.embed.return_value = [[0.1, 0.2, 0.3]]
    return provider


@pytest.mark.asyncio
async def test_cache_miss_then_hit(mock_search_engine, mock_embedding_provider):
    """First call should populate the cache; second call should return from cache."""
    cache = InProcessCache()
    service = RetrievalService(
        search_engine=mock_search_engine,
        embedding_provider=mock_embedding_provider,
        tenant_id="t1",
        cache=cache,
        cache_ttl=60,
    )

    req = RetrievalRequest(query="what is RAG?", top_k=3, rerank=False)

    # First call — cache miss
    r1 = await service.retrieve(req)
    assert len(r1.hits) == 1
    assert mock_search_engine.hybrid_search.call_count == 1

    # Second call — cache hit; search engine must NOT be called again
    r2 = await service.retrieve(req)
    assert mock_search_engine.hybrid_search.call_count == 1  # still 1
    assert len(r2.hits) == 1
    assert r2.hits[0].chunk_id == r1.hits[0].chunk_id


@pytest.mark.asyncio
async def test_cache_disabled_when_ttl_zero(mock_search_engine, mock_embedding_provider):
    """TTL=0 → caching disabled; every call hits the search engine."""
    cache = InProcessCache()
    service = RetrievalService(
        search_engine=mock_search_engine,
        embedding_provider=mock_embedding_provider,
        tenant_id="t1",
        cache=cache,
        cache_ttl=0,  # disabled
    )

    req = RetrievalRequest(query="test", top_k=3, rerank=False)
    await service.retrieve(req)
    await service.retrieve(req)
    assert mock_search_engine.hybrid_search.call_count == 2


@pytest.mark.asyncio
async def test_different_queries_use_different_cache_keys(mock_search_engine, mock_embedding_provider):
    cache = InProcessCache()
    service = RetrievalService(
        search_engine=mock_search_engine,
        embedding_provider=mock_embedding_provider,
        tenant_id="t1",
        cache=cache,
        cache_ttl=60,
    )

    req_a = RetrievalRequest(query="alpha", top_k=3, rerank=False)
    req_b = RetrievalRequest(query="beta", top_k=3, rerank=False)

    await service.retrieve(req_a)
    await service.retrieve(req_b)
    # Both queries miss the cache, so hybrid_search is called twice
    assert mock_search_engine.hybrid_search.call_count == 2


@pytest.mark.asyncio
async def test_empty_query_bypasses_cache(mock_search_engine, mock_embedding_provider):
    """Empty queries return immediately without touching cache or search."""
    cache = InProcessCache()
    service = RetrievalService(
        search_engine=mock_search_engine,
        embedding_provider=mock_embedding_provider,
        tenant_id="t1",
        cache=cache,
        cache_ttl=60,
    )

    result = await service.retrieve(RetrievalRequest(query="   ", top_k=3, rerank=False))
    assert result.hits == []
    assert mock_search_engine.hybrid_search.call_count == 0
    assert cache.stats()["size"] == 0


@pytest.mark.asyncio
async def test_cache_key_is_tenant_scoped(mock_search_engine, mock_embedding_provider):
    """Two services with different tenant IDs must not share cache entries."""
    cache = InProcessCache()

    service_a = RetrievalService(
        search_engine=mock_search_engine,
        embedding_provider=mock_embedding_provider,
        tenant_id="tenant_a",
        cache=cache,
        cache_ttl=60,
    )
    service_b = RetrievalService(
        search_engine=mock_search_engine,
        embedding_provider=mock_embedding_provider,
        tenant_id="tenant_b",
        cache=cache,
        cache_ttl=60,
    )

    req = RetrievalRequest(query="same question", top_k=3, rerank=False)
    await service_a.retrieve(req)
    await service_b.retrieve(req)
    # Different tenants → two distinct cache misses → two hybrid_search calls
    assert mock_search_engine.hybrid_search.call_count == 2
