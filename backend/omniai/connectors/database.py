"""M17 — Database (JDBC / SQLAlchemy) connector.

Reads rows from any SQLAlchemy-compatible database and turns each row (or
batches of rows) into a plain-text document for ingestion.  The only
requirement is that an appropriate driver is installed alongside the project
(e.g. ``psycopg2`` for PostgreSQL, ``pymysql`` for MySQL, the built-in
``sqlite3`` for SQLite, etc.).

Config schema
-------------
{
  "connection_string": "postgresql+psycopg2://user:pass@host/db",  # required
  "table":             "documents",          # required
  "columns":           ["title", "body"],    # optional; all TEXT/VARCHAR if omitted
  "id_column":         "id",                # optional; used as source_id
  "batch_size":        500,                 # optional rows per SELECT
  "max_rows":          50000,               # optional safety cap
  "where_clause":      "status = 'active'", # optional SQL WHERE fragment (no WHERE keyword)
  "document_template": "{title}\\n\\n{body}" # optional Python str.format_map template
}

Security note: ``connection_string`` and ``where_clause`` come from trusted
admin-configured connector records, not from user-supplied request bodies.
The WHERE clause is included verbatim — do not expose this connector kind to
untrusted input.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from omniai.connectors.base import DiscoveredFile

logger = logging.getLogger(__name__)

_MAX_ROWS = 50_000
_BATCH_SIZE = 500

# Column type names (lowercased) we include by default when ``columns`` is omitted
_TEXT_AFFINITY = {
    "text", "varchar", "character varying", "char", "nvarchar", "nchar",
    "clob", "mediumtext", "longtext", "string", "str",
}


class DatabaseConnector:
    """Ingest rows from a SQL table as plain-text documents.

    Config keys:
    - ``connection_string`` (str): SQLAlchemy URL (required)
    - ``table`` (str): table name (required)
    - ``columns`` (list[str]): columns to include as document text (optional)
    - ``id_column`` (str): column used as stable source_id (optional)
    - ``batch_size`` (int): rows fetched per round-trip (default 500)
    - ``max_rows`` (int): hard cap on total rows (default 50 000)
    - ``where_clause`` (str): SQL WHERE fragment appended to the query (optional)
    - ``document_template`` (str): Python ``str.format_map`` template (optional)
    """

    kind = "database"

    async def discover(self, config: dict) -> AsyncIterator[DiscoveredFile]:
        import asyncio

        try:
            import sqlalchemy as sa  # type: ignore[import-untyped]
        except ImportError as exc:
            logger.error("database connector: sqlalchemy not installed: %s", exc)
            return

        connection_string: str = config["connection_string"]
        table_name: str = config["table"]
        user_columns: list[str] | None = config.get("columns") or None
        id_column: str | None = config.get("id_column")
        batch_size = int(config.get("batch_size") or _BATCH_SIZE)
        max_rows = int(config.get("max_rows") or _MAX_ROWS)
        where_clause: str | None = config.get("where_clause")
        template: str | None = config.get("document_template")

        try:
            engine = await asyncio.to_thread(
                lambda: sa.create_engine(connection_string, pool_pre_ping=True)
            )
        except Exception as exc:
            logger.error("database connector: failed to create engine: %s", exc)
            return

        try:
            columns, id_col = await asyncio.to_thread(
                _resolve_columns, engine, table_name, user_columns, id_column
            )
        except Exception as exc:
            logger.error("database connector: failed to inspect table '%s': %s", table_name, exc)
            return

        logger.debug(
            "database connector: syncing table=%s columns=%s id_col=%s",
            table_name, columns, id_col,
        )

        offset = 0
        seen = 0

        while seen < max_rows:
            batch_limit = min(batch_size, max_rows - seen)
            try:
                rows = await asyncio.to_thread(
                    _fetch_batch, engine, table_name, columns + ([id_col] if id_col else []),
                    where_clause, offset, batch_limit
                )
            except Exception as exc:
                logger.error("database connector: fetch failed (offset=%d): %s", offset, exc)
                break

            if not rows:
                break

            for row in rows:
                row_dict = dict(zip(columns + ([id_col] if id_col else []), row))
                source_id = str(row_dict.get(id_col, f"{table_name}:{offset + seen}")) if id_col else f"{table_name}:{offset + seen}"

                # Build document text
                if template:
                    try:
                        text = template.format_map({k: (v or "") for k, v in row_dict.items()})
                    except KeyError as exc:
                        logger.warning("database connector: template key error %s — using default", exc)
                        text = _default_text(table_name, row_dict, columns)
                else:
                    text = _default_text(table_name, row_dict, columns)

                if not text.strip():
                    continue

                content = text.encode("utf-8")
                yield DiscoveredFile(
                    source_id=f"db:{table_name}:{source_id}",
                    filename=f"{table_name}_{source_id}.txt",
                    mime_type="text/plain",
                    content=content,
                )
                seen += 1

            offset += len(rows)
            if len(rows) < batch_limit:
                break  # last page

        try:
            await asyncio.to_thread(engine.dispose)
        except Exception:
            pass

    @staticmethod
    def validate_config(config: dict) -> None:
        if not config.get("connection_string"):
            raise ValueError("database config requires 'connection_string'.")
        if not config.get("table"):
            raise ValueError("database config requires 'table'.")
        # Validate the connection_string looks like a SQLAlchemy URL
        cs = config["connection_string"]
        if "://" not in cs:
            raise ValueError(
                "database config: 'connection_string' must be a SQLAlchemy URL "
                "(e.g. postgresql+psycopg2://user:pass@host/db)."
            )


def _resolve_columns(
    engine,
    table_name: str,
    user_columns: list[str] | None,
    id_column: str | None,
) -> tuple[list[str], str | None]:
    """Return (text_columns, id_column) using DB inspection."""
    import sqlalchemy as sa

    inspector = sa.inspect(engine)
    col_infos = inspector.get_columns(table_name)
    all_cols = [c["name"] for c in col_infos]

    if user_columns:
        # Validate requested columns exist
        missing = set(user_columns) - set(all_cols)
        if missing:
            raise ValueError(
                f"database connector: columns not found in '{table_name}': {missing}"
            )
        text_cols = [c for c in user_columns if c != id_column]
    else:
        # Auto-detect text-affinity columns
        text_cols = [
            c["name"] for c in col_infos
            if str(c["type"]).lower().split("(")[0] in _TEXT_AFFINITY
        ]
        if not text_cols:
            # Fall back to all columns
            text_cols = [c for c in all_cols if c != id_column]

    # Auto-detect id column if not specified
    resolved_id = id_column
    if resolved_id is None:
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_cols = pk_constraint.get("constrained_columns") or []
        if pk_cols:
            resolved_id = pk_cols[0]
        elif all_cols:
            resolved_id = all_cols[0]

    # Remove id column from text columns to avoid duplication
    text_cols = [c for c in text_cols if c != resolved_id]

    return text_cols, resolved_id


def _fetch_batch(
    engine,
    table_name: str,
    columns: list[str],
    where_clause: str | None,
    offset: int,
    limit: int,
) -> list[tuple]:
    import sqlalchemy as sa

    quoted_cols = ", ".join(f'"{c}"' for c in columns)
    query = f'SELECT {quoted_cols} FROM "{table_name}"'
    if where_clause:
        query += f" WHERE {where_clause}"
    query += f" LIMIT {limit} OFFSET {offset}"

    with engine.connect() as conn:
        result = conn.execute(sa.text(query))
        return list(result.fetchall())


def _default_text(table_name: str, row: dict, text_cols: list[str]) -> str:
    parts = [f"Table: {table_name}"]
    for col in text_cols:
        val = row.get(col)
        if val is not None:
            parts.append(f"{col}: {val}")
    return "\n".join(parts)
