"""Auth hardening: revoked_tokens table + password-reset columns on users

Revision ID: 0013_auth_hardening
Revises: 0012_deployments
Create Date: 2027-01-01 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_auth_hardening"
down_revision: Union[str, None] = "0012_deployments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── revoked_tokens ──────────────────────────────────────────────────────
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_revoked_tokens_jti", "revoked_tokens", ["jti"])
    op.create_index("ix_revoked_tokens_user_id", "revoked_tokens", ["user_id"])

    # ── users: password reset columns ───────────────────────────────────────
    op.add_column("users", sa.Column("reset_token_hash", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("reset_token_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_reset_token_hash", "users", ["reset_token_hash"])


def downgrade() -> None:
    op.drop_index("ix_users_reset_token_hash", "users")
    op.drop_column("users", "reset_token_expires_at")
    op.drop_column("users", "reset_token_hash")

    op.drop_index("ix_revoked_tokens_user_id", "revoked_tokens")
    op.drop_index("ix_revoked_tokens_jti", "revoked_tokens")
    op.drop_table("revoked_tokens")
