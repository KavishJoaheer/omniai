"""document storage columns

Revision ID: 0002_document_storage
Revises: 0001_baseline
Create Date: 2026-02-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_document_storage"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("object_key", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("parsed_text_key", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("content_sha256", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("parser_name", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch.add_column(sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_documents_content_sha256", "documents", ["content_sha256"])


def downgrade() -> None:
    op.drop_index("ix_documents_content_sha256", table_name="documents")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("parsed_at")
        batch.drop_column("error_message")
        batch.drop_column("parser_name")
        batch.drop_column("page_count")
        batch.drop_column("content_sha256")
        batch.drop_column("parsed_text_key")
        batch.drop_column("object_key")
