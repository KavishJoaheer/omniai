"""Account lockout: failed_login_attempts + locked_until on users

Revision ID: 0014_account_lockout
Revises: 0013_auth_hardening
Create Date: 2027-02-01 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_account_lockout"
down_revision: Union[str, None] = "0013_auth_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Track consecutive failed logins so we can lock accounts automatically.
    op.add_column(
        "users",
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    # Index for the common "is this account locked?" check by email.
    op.create_index("ix_users_locked_until", "users", ["locked_until"])


def downgrade() -> None:
    op.drop_index("ix_users_locked_until", "users")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
