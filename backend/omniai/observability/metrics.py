from dataclasses import dataclass


@dataclass
class MetricsRegistry:
    http_requests_total: int = 0
    collections_total: int = 0
    documents_total: int = 0

    def render_prometheus(self) -> str:
        return "\n".join(
            [
                "# HELP omniai_http_requests_total Total HTTP requests handled by the API.",
                "# TYPE omniai_http_requests_total counter",
                f"omniai_http_requests_total {self.http_requests_total}",
                "# HELP omniai_collections_total Total collections currently tracked.",
                "# TYPE omniai_collections_total gauge",
                f"omniai_collections_total {self.collections_total}",
                "# HELP omniai_documents_total Total documents currently tracked.",
                "# TYPE omniai_documents_total gauge",
                f"omniai_documents_total {self.documents_total}",
                "",
            ]
        )

