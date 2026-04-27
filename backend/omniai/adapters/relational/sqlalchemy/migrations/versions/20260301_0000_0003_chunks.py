"""chunks table

Revision ID: 0003_chunks
Revises: 0002_document_storage
Create Date: 2026-03-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_chunks"
down_revision: Union[str, None] = "0002_document_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("collection_id", sa.String(length=32), sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("document_id", sa.String(length=32), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("template_name", sa.String(length=64), nullable=False, server_default="general"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_chunk_document_ordinal"),
    )
    op.create_index("ix_chunks_tenant_id", "chunks", ["tenant_id"])
    op.create_index("ix_chunks_collection_id", "chunks", ["collection_id"])
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_index("ix_chunks_collection_id", table_name="chunks")
    op.drop_index("ix_chunks_tenant_id", table_name="chunks")
    op.drop_table("chunks")
