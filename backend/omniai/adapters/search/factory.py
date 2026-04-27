from __future__ import annotations

from omniai.adapters.search.in_memory import InMemorySearchEngine
from omniai.adapters.search.opensearch import OpenSearchEngine
from omniai.config.settings import Settings
from omniai.ports.search_engine import SearchEnginePort


def build_search_engine(settings: Settings) -> SearchEnginePort:
    kind = settings.search_kind.lower()
    if kind in {"memory", "in_memory", "none", ""}:
        return InMemorySearchEngine()
    if kind == "opensearch":
        url = settings.search_url or "http://localhost:9200"
        return OpenSearchEngine(url=url)
    raise ValueError(f"Unsupported SEARCH_KIND={kind!r}")
