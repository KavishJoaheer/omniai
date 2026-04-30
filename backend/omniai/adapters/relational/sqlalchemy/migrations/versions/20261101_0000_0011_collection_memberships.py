"""collection memberships for per-collection RBAC

Revision ID: 0011_collection_memberships
Revises: 0010_connectors
Create Date: 2026-11-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_collection_memberships"
down_revision: Union[str, None] = "0010_connectors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collection_memberships",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("collection_id", sa.String(length=32), sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="VIEWER"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("collection_id", "user_id", name="uq_collection_membership"),
    )
    op.create_index("ix_collection_memberships_tenant_id", "collection_memberships", ["tenant_id"])
    op.create_index("ix_collection_memberships_collection_id", "collection_memberships", ["collection_id"])
    op.create_index("ix_collection_memberships_user_id", "collection_memberships", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_collection_memberships_user_id", table_name="collection_memberships")
    op.drop_index("ix_collection_memberships_collection_id", table_name="collection_memberships")
    op.drop_index("ix_collection_memberships_tenant_id", table_name="collection_memberships")
    op.drop_table("collection_memberships")
