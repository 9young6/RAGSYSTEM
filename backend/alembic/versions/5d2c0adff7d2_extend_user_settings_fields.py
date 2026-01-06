"""extend_user_settings_fields

Revision ID: 5d2c0adff7d2
Revises: 0a9f5b6f2a17
Create Date: 2026-01-05

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "5d2c0adff7d2"
down_revision = "0a9f5b6f2a17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("default_llm_provider", sa.String(length=32), nullable=False, server_default="ollama"),
    )
    op.add_column(
        "user_settings",
        sa.Column("enable_rerank", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "user_settings",
        sa.Column("rerank_provider", sa.String(length=32), nullable=False, server_default="none"),
    )
    op.add_column("user_settings", sa.Column("rerank_model", sa.String(length=128), nullable=True))

    # Backfill updated_at if any rows exist with NULL (defensive)
    op.execute("UPDATE user_settings SET updated_at = NOW() WHERE updated_at IS NULL")


def downgrade() -> None:
    op.drop_column("user_settings", "rerank_model")
    op.drop_column("user_settings", "rerank_provider")
    op.drop_column("user_settings", "enable_rerank")
    op.drop_column("user_settings", "default_llm_provider")

