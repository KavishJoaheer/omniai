"""baseline schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-01-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("primary_tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_primary_tenant_id", "users", ["primary_tenant_id"])

    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="MEMBER"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])

    op.create_table(
        "teams",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_team_tenant_name"),
    )
    op.create_index("ix_teams_tenant_id", "teams", ["tenant_id"])

    op.create_table(
        "team_memberships",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("team_id", sa.String(length=32), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="MEMBER"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_membership"),
    )
    op.create_index("ix_team_memberships_team_id", "team_memberships", ["team_id"])
    op.create_index("ix_team_memberships_user_id", "team_memberships", ["user_id"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("prefix", sa.String(length=32), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"])
    op.create_index("ix_api_keys_created_by_user_id", "api_keys", ["created_by_user_id"])

    op.create_table(
        "collections",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=False, server_default="text-embedding-default"),
        sa.Column("chunk_template", sa.String(length=64), nullable=False, server_default="general"),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_collection_tenant_name"),
    )
    op.create_index("ix_collections_tenant_id", "collections", ["tenant_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("collection_id", sa.String(length=32), sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_collection_id", "documents", ["collection_id"])

    op.create_table(
        "providers",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("default_model", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_credentials", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("encrypted_credentials", sa.Text(), nullable=True),
        sa.Column("options_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "kind", "name", name="uq_provider_tenant_kind_name"),
    )
    op.create_index("ix_providers_tenant_id", "providers", ["tenant_id"])
    op.create_index("ix_providers_kind", "providers", ["kind"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("providers")
    op.drop_table("documents")
    op.drop_table("collections")
    op.drop_table("api_keys")
    op.drop_table("team_memberships")
    op.drop_table("teams")
    op.drop_table("tenant_memberships")
    op.drop_table("users")
    op.drop_table("tenants")
