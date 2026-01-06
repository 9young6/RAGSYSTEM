"""add_user_settings

Revision ID: 0a9f5b6f2a17
Revises: 023e2c73bbf7
Create Date: 2026-01-05

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0a9f5b6f2a17"
down_revision = "023e2c73bbf7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("default_llm_model", sa.String(length=128), nullable=False, server_default="qwen2.5:32b"),
        sa.Column("default_top_k", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("default_temperature", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_settings_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_settings_user_id"),
    )
    op.create_index(op.f("ix_user_settings_id"), "user_settings", ["id"], unique=False)
    op.create_index(op.f("ix_user_settings_user_id"), "user_settings", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_settings_user_id"), table_name="user_settings")
    op.drop_index(op.f("ix_user_settings_id"), table_name="user_settings")
    op.drop_table("user_settings")

