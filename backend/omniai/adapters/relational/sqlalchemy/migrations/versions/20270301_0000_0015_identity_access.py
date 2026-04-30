"""Identity & Access: TOTP MFA, invitations, OIDC state

Revision ID: 0015_identity_access
Revises: 0014_account_lockout
Create Date: 2027-03-01 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_identity_access"
down_revision: Union[str, None] = "0014_account_lockout"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── TOTP / MFA columns on users ─────────────────────────────────────────
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("mfa_recovery_codes_json", sa.Text(), nullable=True))

    # ── invitations table ────────────────────────────────────────────────────
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("tenant_id", sa.String(32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("invited_by_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="MEMBER"),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_invitations_tenant_id", "invitations", ["tenant_id"])
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"])
    op.create_index("ix_invitations_email", "invitations", ["email"])

    # ── oidc_state table (CSRF nonce for OAuth2 callbacks) ───────────────────
    op.create_table(
        "oidc_states",
        sa.Column("state", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("redirect_uri", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_oidc_states_expires_at", "oidc_states", ["expires_at"])

    # ── token_usage table (M16 cost tracking) ───────────────────────────────
    # Stored here in migration 0015 so M16 code can reference it without
    # an out-of-order migration.
    op.create_table(
        "token_usage",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("tenant_id", sa.String(32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("conversation_id", sa.String(32), nullable=True),
        sa.Column("model_provider", sa.String(64), nullable=True),
        sa.Column("model_name", sa.String(128), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_token_usage_tenant_id", "token_usage", ["tenant_id"])
    op.create_index("ix_token_usage_created_at", "token_usage", ["created_at"])
    op.create_index("ix_token_usage_user_id", "token_usage", ["user_id"])

    # ── retrieval_feedback table (M16 quality metrics) ───────────────────────
    op.create_table(
        "retrieval_feedback",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("tenant_id", sa.String(32), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("chunk_id", sa.String(32), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("relevant", sa.Integer(), nullable=False),  # 1=relevant, 0=not
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_retrieval_feedback_tenant_id", "retrieval_feedback", ["tenant_id"])
    op.create_index("ix_retrieval_feedback_query_hash", "retrieval_feedback", ["query_hash"])


def downgrade() -> None:
    op.drop_index("ix_retrieval_feedback_query_hash", "retrieval_feedback")
    op.drop_index("ix_retrieval_feedback_tenant_id", "retrieval_feedback")
    op.drop_table("retrieval_feedback")

    op.drop_index("ix_token_usage_user_id", "token_usage")
    op.drop_index("ix_token_usage_created_at", "token_usage")
    op.drop_index("ix_token_usage_tenant_id", "token_usage")
    op.drop_table("token_usage")

    op.drop_index("ix_oidc_states_expires_at", "oidc_states")
    op.drop_table("oidc_states")

    op.drop_index("ix_invitations_email", "invitations")
    op.drop_index("ix_invitations_token_hash", "invitations")
    op.drop_index("ix_invitations_tenant_id", "invitations")
    op.drop_table("invitations")

    op.drop_column("users", "mfa_recovery_codes_json")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "totp_secret")
