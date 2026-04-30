"""collection rag config

Revision ID: 0007_collection_config
Revises: 0006_graph_triples
Create Date: 2026-07-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_collection_config"
down_revision: Union[str, None] = "0006_graph_triples"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("collections") as batch_op:
        batch_op.add_column(sa.Column("system_prompt", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("top_k", sa.Integer(), nullable=False, server_default="8"))
        batch_op.add_column(sa.Column("vector_weight", sa.Float(), nullable=False, server_default="0.6"))


def downgrade() -> None:
    with op.batch_alter_table("collections") as batch_op:
        batch_op.drop_column("vector_weight")
        batch_op.drop_column("top_k")
        batch_op.drop_column("system_prompt")
