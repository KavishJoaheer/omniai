from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)


@dataclass
class MetricsRegistry:
    """Holds Prometheus metrics for the application.

    Wraps a private `prometheus_client.CollectorRegistry` so we can scope
    everything cleanly and avoid global side effects in tests.
    """

    http_requests_total: int = 0
    collections_total: int = 0
    documents_total: int = 0
    _registry: CollectorRegistry = field(default_factory=CollectorRegistry)

    def __post_init__(self) -> None:
        self.requests_counter = Counter(
            "omniai_http_requests_total",
            "Total HTTP requests handled by the API.",
            ["method", "path", "status"],
            registry=self._registry,
        )
        self.request_duration = Histogram(
            "omniai_http_request_duration_seconds",
            "HTTP request duration in seconds.",
            ["method", "path"],
            registry=self._registry,
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        )
        self.collections_gauge = Gauge(
            "omniai_collections_total",
            "Total collections currently tracked.",
            registry=self._registry,
        )
        self.documents_gauge = Gauge(
            "omniai_documents_total",
            "Total documents currently tracked.",
            registry=self._registry,
        )
        self.chat_messages_counter = Counter(
            "omniai_chat_messages_total",
            "Total chat messages streamed.",
            ["status"],
            registry=self._registry,
        )
        self.retrieval_counter = Counter(
            "omniai_retrieval_total",
            "Total retrieval calls.",
            ["rerank"],
            registry=self._registry,
        )
        self.indexing_counter = Counter(
            "omniai_documents_indexed_total",
            "Total documents indexed (terminal status).",
            ["status"],
            registry=self._registry,
        )
        self.rate_limited_counter = Counter(
            "omniai_rate_limited_total",
            "Requests rejected by the rate limiter.",
            ["tenant"],
            registry=self._registry,
        )

    # ---- helpers used by middleware/handlers --------------------------------

    def observe_request(self, *, method: str, path: str, status: int, duration: float) -> None:
        self.http_requests_total += 1
        try:
            self.requests_counter.labels(method=method, path=path, status=str(status)).inc()
            self.request_duration.labels(method=method, path=path).observe(duration)
        except Exception:
            logger.debug("metrics: failed to record request", exc_info=True)

    def render_prometheus(self) -> tuple[str, str]:
        """Return (body, content_type) for the /metrics endpoint."""
        try:
            self.collections_gauge.set(self.collections_total)
            self.documents_gauge.set(self.documents_total)
        except Exception:
            pass
        return generate_latest(self._registry).decode("utf-8"), CONTENT_TYPE_LATEST


class RequestTimer:
    """Context manager that records HTTP request timing into the registry."""

    __slots__ = ("metrics", "method", "path", "_started")

    def __init__(self, metrics: MetricsRegistry, *, method: str, path: str) -> None:
        self.metrics = metrics
        self.method = method
        self.path = path
        self._started = 0.0

    def __enter__(self) -> "RequestTimer":
        self._started = time.perf_counter()
        return self

    def record(self, status: int) -> None:
        duration = time.perf_counter() - self._started
        self.metrics.observe_request(
            method=self.method, path=self.path, status=status, duration=duration
        )
