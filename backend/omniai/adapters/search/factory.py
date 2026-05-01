from __future__ import annotations

from omniai.adapters.search.in_memory import InMemorySearchEngine
from omniai.adapters.search.opensearch import OpenSearchEngine
from omniai.config.settings import Settings
from omniai.ports.search_engine import SearchEnginePort


def build_search_engine(settings: Settings) -> SearchEnginePort:
    kind = settings.search_kind.lower()
    if kind in {"memory", "in_memory", "none", ""}:
        engine = InMemorySearchEngine(snapshot_path=settings.search_snapshot_path)
        engine.load_snapshot()
        return engine
    if kind == "opensearch":
        url = settings.search_url or "http://localhost:9200"
        return OpenSearchEngine(url=url)
    if kind == "pgvector":
        from omniai.adapters.search.pgvector import PgvectorSearchEngine
        connection_string = settings.db_url.replace("sqlite:///", "postgresql://", 1) if "sqlite" in settings.db_url else settings.db_url
        return PgvectorSearchEngine(connection_string=connection_string, table=settings.pgvector_table)
    if kind == "pinecone":
        from omniai.adapters.search.pinecone import PineconeSearchEngine
        if not settings.pinecone_api_key:
            raise ValueError("PINECONE_API_KEY must be set when SEARCH_KIND=pinecone")
        return PineconeSearchEngine(
            api_key=settings.pinecone_api_key,
            environment=settings.pinecone_environment,
            index_name=settings.pinecone_index_name,
        )
    if kind == "weaviate":
        from omniai.adapters.search.weaviate import WeaviateSearchEngine
        return WeaviateSearchEngine(
            url=settings.weaviate_url,
            api_key=settings.weaviate_api_key,
            class_name=settings.weaviate_class_name,
        )
    raise ValueError(f"Unsupported SEARCH_KIND={kind!r}. Valid options: memory, opensearch, pgvector, pinecone, weaviate")
