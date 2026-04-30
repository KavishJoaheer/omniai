"""graph triples

Revision ID: 0006_graph_triples
Revises: 0005_parent_chunks
Create Date: 2026-06-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_graph_triples"
down_revision: Union[str, None] = "0005_parent_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "graph_triples",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("collection_id", sa.String(length=32), nullable=False),
        sa.Column("document_id", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("predicate", sa.Text(), nullable=False),
        sa.Column("object", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_graph_triples_tenant_id", "graph_triples", ["tenant_id"])
    op.create_index("ix_graph_triples_collection_id", "graph_triples", ["collection_id"])
    op.create_index("ix_graph_triples_document_id", "graph_triples", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_graph_triples_document_id", table_name="graph_triples")
    op.drop_index("ix_graph_triples_collection_id", table_name="graph_triples")
    op.drop_index("ix_graph_triples_tenant_id", table_name="graph_triples")
    op.drop_table("graph_triples")
