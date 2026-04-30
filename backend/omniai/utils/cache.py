"""Lightweight retrieval-result cache.

Two implementations are provided:
- ``InProcessCache`` — thread-safe, in-memory TTL dict.  Zero extra deps,
  works in single-process deployments.
- ``RedisCache`` — Redis-backed, shares state across processes/replicas.
  Only instantiated when ``redis`` is installed and ``REDIS_URL`` is set.

``build_retrieval_cache(settings)`` picks the best available backend and
returns ``None`` when caching is disabled (``RETRIEVAL_CACHE_TTL_SECONDS=0``).
"""
from __future__ import annotations

import logging
import pickle
import threading
import time
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

_SENTINEL = object()


@runtime_checkable
class RetrievalCachePort(Protocol):
    """Minimal key-value cache contract for retrieval results."""

    def get(self, key: str) -> bytes | None:
        """Return cached bytes or ``None`` on miss / error."""
        ...

    def set(self, key: str, value: bytes, ttl: int) -> None:
        """Store *value* with a TTL in seconds.  Silently swallows errors."""
        ...

    def delete(self, key: str) -> None:
        """Invalidate a single key (best-effort)."""
        ...


# ── In-process implementation ──────────────────────────────────────────────


class InProcessCache:
    """Thread-safe LRU+TTL cache backed by an ordinary ``dict``.

    When the store reaches *max_size* entries the oldest half is evicted
    to avoid unbounded memory growth.
    """

    def __init__(self, max_size: int = 2048) -> None:
        self._store: dict[str, tuple[bytes, float]] = {}  # key → (data, expires_at)
        self._lock = threading.Lock()
        self._max_size = max_size

    # -- RetrievalCachePort ---------------------------------------------------

    def get(self, key: str) -> bytes | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            data, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return data

    def set(self, key: str, value: bytes, ttl: int) -> None:
        if ttl <= 0:
            return
        with self._lock:
            if len(self._store) >= self._max_size:
                self._evict()
            self._store[key] = (value, time.monotonic() + ttl)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    # -- helpers --------------------------------------------------------------

    def _evict(self) -> None:
        """Remove expired entries first; if still full remove oldest half."""
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        if len(self._store) >= self._max_size:
            # Remove oldest half by insertion order
            keys = list(self._store.keys())
            for k in keys[: len(keys) // 2]:
                del self._store[k]

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"size": len(self._store), "max_size": self._max_size}


# ── Redis implementation (optional) ───────────────────────────────────────


class RedisCache:
    """Redis-backed cache.  Instantiated only when *redis-py* is available."""

    def __init__(self, redis_client) -> None:  # type: ignore[type-arg]
        self._r = redis_client

    def get(self, key: str) -> bytes | None:
        try:
            return self._r.get(key)
        except Exception as exc:
            logger.debug("Redis cache GET error: %s", exc)
            return None

    def set(self, key: str, value: bytes, ttl: int) -> None:
        try:
            self._r.setex(key, ttl, value)
        except Exception as exc:
            logger.debug("Redis cache SET error: %s", exc)

    def delete(self, key: str) -> None:
        try:
            self._r.delete(key)
        except Exception as exc:
            logger.debug("Redis cache DELETE error: %s", exc)


# ── Serialization helpers ─────────────────────────────────────────────────


def serialize(obj: object) -> bytes:
    """Pickle *obj* to bytes.  Never raises (returns empty bytes on error)."""
    try:
        return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        return b""


def deserialize(data: bytes) -> object | None:
    """Unpickle *data*.  Returns ``None`` on any error."""
    if not data:
        return None
    try:
        return pickle.loads(data)  # noqa: S301 — internal cache, not user input
    except Exception:
        return None


# ── Factory ──────────────────────────────────────────────────────────────


def build_retrieval_cache(
    *,
    redis_url: str | None,
    ttl_seconds: int,
) -> RetrievalCachePort | None:
    """Return the best cache backend or ``None`` when caching is disabled.

    Args:
        redis_url: ``REDIS_URL`` setting value.
        ttl_seconds: ``RETRIEVAL_CACHE_TTL_SECONDS`` setting value.
            Zero or negative → caching disabled.
    """
    if ttl_seconds <= 0:
        return None

    if redis_url:
        try:
            import redis  # type: ignore[import]

            client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()  # fail-fast if Redis is unreachable
            logger.info("Retrieval cache: using Redis at %s (TTL=%ds)", redis_url, ttl_seconds)
            return RedisCache(client)
        except Exception as exc:
            logger.warning(
                "Redis unreachable (%s); falling back to in-process cache (TTL=%ds).",
                exc,
                ttl_seconds,
            )

    logger.info("Retrieval cache: using in-process cache (TTL=%ds)", ttl_seconds)
    return InProcessCache()
