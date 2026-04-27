"""parent chunk relationship

Revision ID: 0005_parent_chunks
Revises: 0004_conversations
Create Date: 2026-05-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from alembic.operations import BatchOperations

revision: str = "0005_parent_chunks"
down_revision: Union[str, None] = "0004_conversations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chunks") as batch_op:
        batch_op.add_column(
            sa.Column("parent_chunk_id", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("is_indexable", sa.Integer(), nullable=False, server_default="1")
        )
    op.create_index("ix_chunks_parent_chunk_id", "chunks", ["parent_chunk_id"])


def downgrade() -> None:
    op.drop_index("ix_chunks_parent_chunk_id", table_name="chunks")
    with op.batch_alter_table("chunks") as batch_op:
        batch_op.drop_column("is_indexable")
        batch_op.drop_column("parent_chunk_id")
