"""M20 Agent Platform: parallel branches, human-in-the-loop, replay, cost tracking

Revision ID: 0016_agent_platform
Revises: 0015_identity_access
Create Date: 2027-04-01 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_agent_platform"
down_revision: Union[str, None] = "0015_identity_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── agents: marketplace template tracking ────────────────────────────────
    op.add_column("agents", sa.Column("template_id", sa.String(128), nullable=True))

    # ── agent_runs: human-in-the-loop, replay, cost ─────────────────────────
    op.add_column("agent_runs", sa.Column("paused_at_node", sa.String(128), nullable=True))
    op.add_column("agent_runs", sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"))
    op.add_column("agent_runs", sa.Column("replay_of_run_id", sa.String(32), nullable=True))
    op.add_column("agent_runs", sa.Column("replay_from_event", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("resumed_with_json", sa.Text(), nullable=True, server_default="{}"))


def downgrade() -> None:
    op.drop_column("agent_runs", "resumed_with_json")
    op.drop_column("agent_runs", "replay_from_event")
    op.drop_column("agent_runs", "replay_of_run_id")
    op.drop_column("agent_runs", "cost_usd")
    op.drop_column("agent_runs", "paused_at_node")
    op.drop_column("agents", "template_id")
