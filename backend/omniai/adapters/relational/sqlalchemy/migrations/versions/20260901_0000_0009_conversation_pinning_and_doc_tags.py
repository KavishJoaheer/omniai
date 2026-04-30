"""conversation pinning and document tags

Revision ID: 0009_conv_pin_doc_tags
Revises: 0008_agents
Create Date: 2026-09-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_conv_pin_doc_tags"
down_revision: Union[str, None] = "0008_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(sa.Column("pinned", sa.Integer(), nullable=False, server_default="0"))

    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("tags_json")
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("pinned")
