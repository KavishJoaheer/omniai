from __future__ import annotations

import threading
import time
from collections import defaultdict


class TokenBucketLimiter:
    """Per-key token bucket rate limiter with steady refill.

    Each key (tenant id, IP, etc.) gets its own bucket of capacity `capacity`,
    refilling at `refill_per_second` tokens. Threadsafe — uses a single lock
    around all bucket state. Adequate for single-process FastAPI; for
    multi-process deployments, swap in a Redis-backed implementation.
    """

    __slots__ = ("_capacity", "_refill_per_second", "_buckets", "_lock")

    def __init__(self, *, capacity: int, refill_per_second: float) -> None:
        self._capacity = max(1, capacity)
        self._refill_per_second = max(0.001, refill_per_second)
        self._buckets: dict[str, tuple[float, float]] = defaultdict(
            lambda: (float(self._capacity), time.monotonic())
        )
        self._lock = threading.Lock()

    def acquire(self, key: str, *, cost: float = 1.0) -> tuple[bool, float]:
        """Attempt to consume `cost` tokens from `key`'s bucket.

        Returns (allowed, retry_after_seconds). retry_after_seconds is 0 when
        allowed=True and otherwise the seconds the caller should wait before
        retrying for the bucket to refill `cost` tokens.
        """
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets[key]
            elapsed = max(0.0, now - last)
            tokens = min(self._capacity, tokens + elapsed * self._refill_per_second)
            if tokens >= cost:
                self._buckets[key] = (tokens - cost, now)
                return True, 0.0
            shortfall = cost - tokens
            retry_after = shortfall / self._refill_per_second
            self._buckets[key] = (tokens, now)
            return False, retry_after

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)
