"""Repair an older local SQLite dev database in place.

This is intentionally conservative:
- only works for SQLite URLs
- creates a timestamped backup first
- only adds missing columns/indexes
- keeps legacy columns so existing local data is not destroyed
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from omniai.config.settings import get_settings


HEAD_REVISION = "0016_agent_platform"


def main() -> None:
    db_path = sqlite_path_from_settings()
    if not db_path.exists():
        print(f"No SQLite database found at {db_path}. Nothing to repair.")
        return

    backup = db_path.with_name(f"{db_path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(db_path, backup)
    print(f"Backup written: {backup}")

    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        repair(cursor)
        connection.commit()
    finally:
        connection.close()

    print("SQLite dev schema repair complete.")


def sqlite_path_from_settings() -> Path:
    url = make_url(get_settings().db_url)
    if not url.drivername.startswith("sqlite"):
        raise SystemExit(f"DB_URL is not SQLite: {url.drivername}")
    if not url.database or url.database == ":memory:":
        raise SystemExit("DB_URL points to an in-memory SQLite database; nothing to repair.")
    path = Path(url.database)
    return path if path.is_absolute() else Path.cwd() / path


def repair(cursor: sqlite3.Cursor) -> None:
    add_columns(
        cursor,
        "users",
        {
            "reset_token_hash": "VARCHAR(128)",
            "reset_token_expires_at": "DATETIME",
            "failed_login_attempts": "INTEGER NOT NULL DEFAULT 0",
            "locked_until": "DATETIME",
            "totp_secret": "VARCHAR(64)",
            "mfa_enabled": "INTEGER NOT NULL DEFAULT 0",
            "mfa_recovery_codes_json": "TEXT",
        },
    )
    create_index(cursor, "ix_users_reset_token_hash", "users", "reset_token_hash")
    create_index(cursor, "ix_users_locked_until", "users", "locked_until")

    add_columns(
        cursor,
        "collections",
        {
            "system_prompt": "TEXT",
            "top_k": "INTEGER NOT NULL DEFAULT 8",
            "vector_weight": "FLOAT NOT NULL DEFAULT 0.6",
        },
    )

    add_columns(
        cursor,
        "documents",
        {
            "object_key": "VARCHAR(512)",
            "parsed_text_key": "VARCHAR(512)",
            "content_sha256": "VARCHAR(64)",
            "page_count": "INTEGER NOT NULL DEFAULT 0",
            "parser_name": "VARCHAR(64)",
            "error_message": "TEXT",
            "parsed_at": "DATETIME",
            "tags_json": "TEXT NOT NULL DEFAULT '[]'",
        },
    )
    copy_if_possible(cursor, "documents", "storage_key", "object_key")
    copy_if_possible(cursor, "documents", "content_hash", "content_sha256")
    copy_if_possible(cursor, "documents", "parser_kind", "parser_name")
    copy_if_possible(cursor, "documents", "parse_error", "error_message")
    copy_if_possible(cursor, "documents", "parse_completed_at", "parsed_at")
    create_index(cursor, "ix_documents_content_sha256", "documents", "content_sha256")

    add_columns(
        cursor,
        "chunks",
        {
            "char_count": "INTEGER NOT NULL DEFAULT 0",
            "template_name": "VARCHAR(64) NOT NULL DEFAULT 'general'",
            "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
            "indexed_at": "DATETIME",
            "parent_chunk_id": "VARCHAR(32)",
            "is_indexable": "INTEGER NOT NULL DEFAULT 1",
        },
    )
    if table_has_columns(cursor, "chunks", {"text", "char_count"}):
        cursor.execute("UPDATE chunks SET char_count = length(text) WHERE char_count = 0 OR char_count IS NULL")
    create_index(cursor, "ix_chunks_parent_chunk_id", "chunks", "parent_chunk_id")

    add_columns(cursor, "conversations", {"pinned": "INTEGER NOT NULL DEFAULT 0"})
    add_columns(cursor, "agents", {"template_id": "VARCHAR(128)"})
    add_columns(
        cursor,
        "agent_runs",
        {
            "paused_at_node": "VARCHAR(128)",
            "cost_usd": "FLOAT NOT NULL DEFAULT 0",
            "replay_of_run_id": "VARCHAR(32)",
            "replay_from_event": "INTEGER",
            "resumed_with_json": "TEXT NOT NULL DEFAULT '{}'",
        },
    )

    cursor.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
    cursor.execute("DELETE FROM alembic_version")
    cursor.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (HEAD_REVISION,))
    print(f"Stamped alembic_version={HEAD_REVISION}")


def add_columns(cursor: sqlite3.Cursor, table: str, definitions: dict[str, str]) -> None:
    if not table_exists(cursor, table):
        print(f"Skipped missing table: {table}")
        return
    existing = columns(cursor, table)
    for name, definition in definitions.items():
        if name in existing:
            continue
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        print(f"Added {table}.{name}")


def create_index(cursor: sqlite3.Cursor, name: str, table: str, column: str) -> None:
    if not table_has_columns(cursor, table, {column}):
        return
    cursor.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})")


def copy_if_possible(cursor: sqlite3.Cursor, table: str, source: str, target: str) -> None:
    if not table_has_columns(cursor, table, {source, target}):
        return
    cursor.execute(f"UPDATE {table} SET {target} = COALESCE({target}, {source})")


def table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def columns(cursor: sqlite3.Cursor, table: str) -> set[str]:
    return {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}


def table_has_columns(cursor: sqlite3.Cursor, table: str, names: set[str]) -> bool:
    return table_exists(cursor, table) and names.issubset(columns(cursor, table))


if __name__ == "__main__":
    main()
