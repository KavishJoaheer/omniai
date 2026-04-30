"""connectors table

Revision ID: 0010_connectors
Revises: 0009_conv_pin_doc_tags
Create Date: 2026-10-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_connectors"
down_revision: Union[str, None] = "0009_conv_pin_doc_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("collection_id", sa.String(length=32), sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sync_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_synced_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seen_hashes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_connector_tenant_name"),
    )
    op.create_index("ix_connectors_tenant_id", "connectors", ["tenant_id"])
    op.create_index("ix_connectors_collection_id", "connectors", ["collection_id"])
    op.create_index("ix_connectors_kind", "connectors", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_connectors_kind", table_name="connectors")
    op.drop_index("ix_connectors_collection_id", table_name="connectors")
    op.drop_index("ix_connectors_tenant_id", table_name="connectors")
    op.drop_table("connectors")
