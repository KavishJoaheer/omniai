from __future__ import annotations

import time

from omniai.observability.rate_limit import TokenBucketLimiter


def test_initial_burst_allowed():
    limiter = TokenBucketLimiter(capacity=5, refill_per_second=1.0)
    for _ in range(5):
        allowed, _ = limiter.acquire("tenant-a")
        assert allowed
    allowed, retry_after = limiter.acquire("tenant-a")
    assert not allowed
    assert retry_after > 0


def test_buckets_are_per_key():
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=1.0)
    assert limiter.acquire("a")[0]
    assert limiter.acquire("a")[0]
    assert not limiter.acquire("a")[0]
    # b has its own bucket
    assert limiter.acquire("b")[0]


def test_bucket_refills_over_time():
    limiter = TokenBucketLimiter(capacity=1, refill_per_second=100.0)
    assert limiter.acquire("k")[0]
    assert not limiter.acquire("k")[0]
    time.sleep(0.05)  # 5 tokens worth of refill, capped at 1
    assert limiter.acquire("k")[0]
