from __future__ import annotations

from opensearchpy import OpenSearch, helpers

from omniai.ports.search_engine import IndexableChunk, SearchHit


def _index_name(tenant_id: str) -> str:
    return f"omniai-chunks-{tenant_id.lower()}"


class OpenSearchEngine:
    def __init__(self, *, url: str) -> None:
        self._client = OpenSearch(
            hosts=[url],
            verify_certs=False,
            ssl_show_warn=False,
        )

    def ensure_index(self, *, tenant_id: str, dim: int) -> str:
        index = _index_name(tenant_id)
        if self._client.indices.exists(index=index):
            return index
        body = {
            "settings": {"index": {"knn": True}},
            "mappings": {
                "properties": {
                    "tenant_id": {"type": "keyword"},
                    "collection_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "chunk_id": {"type": "keyword"},
                    "text": {"type": "text"},
                    "metadata": {"type": "object", "enabled": True},
                    "vector": {
                        "type": "knn_vector",
                        "dimension": dim,
                        "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"},
                    },
                }
            },
        }
        self._client.indices.create(index=index, body=body)
        return index

    def upsert_chunks(self, *, tenant_id: str, chunks: list[IndexableChunk]) -> None:
        if not chunks:
            return
        index = _index_name(tenant_id)
        actions = [
            {
                "_op_type": "index",
                "_index": index,
                "_id": chunk.chunk_id,
                "_source": {
                    "tenant_id": tenant_id,
                    "collection_id": chunk.collection_id,
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                    "vector": chunk.vector,
                },
            }
            for chunk in chunks
        ]
        helpers.bulk(self._client, actions, refresh=True)

    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None:
        index = _index_name(tenant_id)
        if not self._client.indices.exists(index=index):
            return
        self._client.delete_by_query(
            index=index,
            body={"query": {"term": {"document_id": document_id}}},
            refresh=True,
        )

    def hybrid_search(
        self,
        *,
        tenant_id: str,
        query: str,
        query_vector: list[float],
        top_k: int,
        vector_weight: float,
        collection_ids: list[str] | None = None,
    ) -> list[SearchHit]:
        index = _index_name(tenant_id)
        if not self._client.indices.exists(index=index):
            return []

        weight = max(0.0, min(1.0, vector_weight))
        filter_clauses: list[dict] = []
        if collection_ids:
            filter_clauses.append({"terms": {"collection_id": collection_ids}})

        should: list[dict] = []
        if query_vector:
            should.append(
                {
                    "function_score": {
                        "query": {
                            "knn": {"vector": {"vector": query_vector, "k": top_k * 4}},
                        },
                        "boost": weight,
                    }
                }
            )
        if query:
            should.append(
                {
                    "function_score": {
                        "query": {"match": {"text": query}},
                        "boost": 1.0 - weight,
                    }
                }
            )

        body = {
            "size": top_k,
            "query": {
                "bool": {
                    "should": should,
                    "filter": filter_clauses,
                    "minimum_should_match": 1 if should else 0,
                }
            },
            "highlight": {"fields": {"text": {"fragment_size": 220, "number_of_fragments": 1}}},
        }
        response = self._client.search(index=index, body=body)
        hits: list[SearchHit] = []
        for raw in response.get("hits", {}).get("hits", []):
            source = raw.get("_source", {})
            highlight = raw.get("highlight", {}).get("text", [])
            snippet = highlight[0] if highlight else (source.get("text") or "")[:220]
            hits.append(
                SearchHit(
                    chunk_id=source.get("chunk_id", raw.get("_id", "")),
                    document_id=source.get("document_id", ""),
                    collection_id=source.get("collection_id", ""),
                    score=float(raw.get("_score") or 0.0),
                    text=source.get("text") or "",
                    snippet=snippet,
                    metadata=source.get("metadata") or {},
                )
            )
        return hits
