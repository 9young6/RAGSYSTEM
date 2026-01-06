"""add_document_chunk_included

Revision ID: 6b3a9d0c2b1e
Revises: 5d2c0adff7d2
Create Date: 2026-01-05

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "6b3a9d0c2b1e"
down_revision = "5d2c0adff7d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "included")

