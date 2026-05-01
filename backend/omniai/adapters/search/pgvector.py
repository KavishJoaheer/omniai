"""pgvector search adapter — uses PostgreSQL's pgvector extension for ANN search.

This adapter stores chunk vectors in a dedicated table with an HNSW index and
falls back to exact nearest-neighbour scan when the index hasn't been built yet.

Requires:
  - PostgreSQL 14+ with pgvector extension installed (``CREATE EXTENSION vector;``)
  - ``pip install pgvector sqlalchemy[asyncio] psycopg2-binary`` (or psycopg)

The table schema is auto-created on first ``ensure_index()`` call.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from omniai.ports.search_engine import IndexableChunk, SearchEnginePort, SearchHit

logger = logging.getLogger(__name__)

_DDL_TEMPLATE = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS {table} (
    chunk_id       TEXT         NOT NULL,
    tenant_id      TEXT         NOT NULL,
    document_id    TEXT         NOT NULL,
    collection_id  TEXT         NOT NULL,
    text           TEXT         NOT NULL,
    snippet        TEXT         NOT NULL DEFAULT '',
    metadata       TEXT         NOT NULL DEFAULT '{{}}',
    embedding      vector({dim}) NOT NULL,
    PRIMARY KEY (tenant_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS {table}_hnsw_idx
    ON {table} USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS {table}_tenant_col_idx
    ON {table} (tenant_id, collection_id);
"""

_UPSERT_SQL = """
INSERT INTO {table}
    (chunk_id, tenant_id, document_id, collection_id, text, snippet, metadata, embedding)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
ON CONFLICT (tenant_id, chunk_id) DO UPDATE
    SET document_id   = EXCLUDED.document_id,
        collection_id = EXCLUDED.collection_id,
        text          = EXCLUDED.text,
        snippet       = EXCLUDED.snippet,
        metadata      = EXCLUDED.metadata,
        embedding     = EXCLUDED.embedding;
"""


class PgvectorSearchEngine:
    """SearchEnginePort backed by PostgreSQL + pgvector.

    Parameters
    ----------
    connection_string:
        A psycopg2-compatible connection string, e.g.
        ``postgresql://user:pass@host:5432/db``
    table:
        Name of the vector table (default ``omniai_vectors``).
    """

    kind = "pgvector"

    def __init__(self, connection_string: str, table: str = "omniai_vectors") -> None:
        try:
            import psycopg2  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "psycopg2-binary is required for the pgvector adapter. "
                "Install it with: pip install psycopg2-binary"
            ) from exc
        self._dsn = connection_string
        self._table = table
        self._dim: int | None = None
        self._psycopg2 = psycopg2

    # ── Connection helper ─────────────────────────────────────────────────────

    def _conn(self):
        return self._psycopg2.connect(self._dsn)

    # ── SearchEnginePort interface ─────────────────────────────────────────────

    def ensure_index(self, *, tenant_id: str, dim: int) -> str:
        """Create the pgvector table and HNSW index if they don't exist yet."""
        self._dim = dim
        ddl = _DDL_TEMPLATE.format(table=self._table, dim=dim)
        with self._conn() as conn:
            with conn.cursor() as cur:
                for stmt in ddl.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        cur.execute(stmt)
            conn.commit()
        logger.info("pgvector table %s ensured (dim=%d)", self._table, dim)
        return self._table

    def upsert_chunks(self, *, tenant_id: str, chunks: list[IndexableChunk]) -> None:
        if not chunks:
            return
        sql = _UPSERT_SQL.format(table=self._table)
        rows = [
            (
                c.chunk_id,
                tenant_id,
                c.document_id,
                c.collection_id,
                c.text,
                c.text[:280],
                json.dumps(c.metadata),
                "[" + ",".join(str(v) for v in c.vector) + "]",
            )
            for c in chunks
        ]
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()

    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None:
        sql = f"DELETE FROM {self._table} WHERE tenant_id = %s AND document_id = %s;"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tenant_id, document_id))
            conn.commit()

    def hybrid_search(
        self,
        *,
        tenant_id: str,
        query: str,
        query_vector: list[float],
        top_k: int,
        vector_weight: float,
        collection_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
    ) -> list[SearchHit]:
        """Hybrid search: combine cosine-similarity score with BM25-style keyword score.

        pgvector doesn't have native BM25, so the BM25 component is approximated
        by a PostgreSQL ``ts_rank`` full-text search (``tsvector`` query).  The
        two scores are blended with ``vector_weight``.
        """
        if not query_vector:
            return []

        vec_str = "[" + ",".join(str(v) for v in query_vector) + "]"
        params: list[Any] = [tenant_id, vec_str, query, top_k * 2]

        col_filter = ""
        if collection_ids:
            placeholders = ",".join(["%s"] * len(collection_ids))
            col_filter += f" AND collection_id IN ({placeholders})"
            params.extend(collection_ids)

        doc_filter = ""
        if document_ids:
            placeholders = ",".join(["%s"] * len(document_ids))
            doc_filter += f" AND document_id IN ({placeholders})"
            params.extend(document_ids)

        params.append(top_k)

        sql = f"""
            SELECT
                chunk_id,
                document_id,
                collection_id,
                text,
                metadata,
                1 - (embedding <=> %s::vector)               AS vec_score,
                COALESCE(
                    ts_rank(to_tsvector('english', text),
                            plainto_tsquery('english', %s)), 0.0)   AS bm25_score
            FROM {self._table}
            WHERE tenant_id = %s
            {col_filter}
            {doc_filter}
            ORDER BY
                {vector_weight} * (1 - (embedding <=> %s::vector))
                + {1.0 - vector_weight} * COALESCE(
                    ts_rank(to_tsvector('english', text),
                            plainto_tsquery('english', %s)), 0.0)
                DESC
            LIMIT %s;
        """
        # Rebuild params in the order the SQL uses them
        params = [vec_str, query, tenant_id]
        if collection_ids:
            params.extend(collection_ids)
        if document_ids:
            params.extend(document_ids)
        params += [vec_str, query, top_k]

        hits: list[SearchHit] = []
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        for row in rows:
            chunk_id, doc_id, col_id, text, metadata_json, vec_score, bm25_score = row
            blended = float(vector_weight) * float(vec_score) + (1.0 - float(vector_weight)) * float(bm25_score)
            try:
                metadata = json.loads(metadata_json or "{}")
            except Exception:
                metadata = {}
            hits.append(
                SearchHit(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    collection_id=col_id,
                    score=blended,
                    text=text,
                    snippet=text[:280],
                    metadata={**metadata, "vec_score": float(vec_score), "bm25_score": float(bm25_score)},
                )
            )
        return hits
