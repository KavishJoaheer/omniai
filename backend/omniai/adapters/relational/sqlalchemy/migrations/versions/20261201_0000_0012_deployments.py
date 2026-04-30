"""deployments table for the in-app deploy manager

Revision ID: 0012_deployments
Revises: 0011_collection_memberships
Create Date: 2026-12-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_deployments"
down_revision: Union[str, None] = "0011_collection_memberships"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deployments",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),  # public_chat | webhook
        sa.Column("target_kind", sa.String(length=32), nullable=False),  # collection | agent
        sa.Column("target_id", sa.String(length=32), nullable=False),
        sa.Column("system_prompt_override", sa.Text(), nullable=True),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("anonymous_allowed", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("daily_message_quota", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("branding_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("definition_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),  # ACTIVE | PAUSED | DELETED
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("today_message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("today_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_deployment_slug"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_deployment_tenant_name"),
    )
    op.create_index("ix_deployments_tenant_id", "deployments", ["tenant_id"])
    op.create_index("ix_deployments_slug", "deployments", ["slug"])
    op.create_index("ix_deployments_status", "deployments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_deployments_status", table_name="deployments")
    op.drop_index("ix_deployments_slug", table_name="deployments")
    op.drop_index("ix_deployments_tenant_id", table_name="deployments")
    op.drop_table("deployments")
