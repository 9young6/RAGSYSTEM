"""add_embedding_and_chunking_config

Revision ID: 20250109_add_emb_chunk
Revises: 6b3a9d0c2b1e
Create Date: 2026-01-09

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20250109_add_emb_chunk"
down_revision = "6b3a9d0c2b1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Embedding configuration fields
    op.add_column(
        "user_settings",
        sa.Column("embedding_provider", sa.String(length=32), nullable=False, server_default="system", comment="User's embedding provider: system | ollama | xinference | localai"),
    )
    op.add_column(
        "user_settings",
        sa.Column("embedding_model", sa.String(length=256), nullable=True, comment="User-selected embedding model name (if provider != 'system')"),
    )
    op.add_column(
        "user_settings",
        sa.Column("embedding_api_key", sa.String(length=512), nullable=True, comment="API key for external embedding providers"),
    )
    op.add_column(
        "user_settings",
        sa.Column("embedding_base_url", sa.String(length=512), nullable=True, comment="Custom base URL for embedding provider (overrides system default)"),
    )
    op.add_column(
        "user_settings",
        sa.Column("embedding_dimension", sa.Integer, nullable=True, comment="Embedding dimension override (auto-detected if null)"),
    )
    op.add_column(
        "user_settings",
        sa.Column("embedding_tested_at", sa.DateTime(timezone=True), nullable=True, comment="Last successful embedding model test timestamp"),
    )

    # Chunking configuration fields
    op.add_column(
        "user_settings",
        sa.Column("chunking_strategy", sa.String(length=32), nullable=False, server_default="character", comment="Chunking strategy: character | recursive | token | semantic"),
    )
    op.add_column(
        "user_settings",
        sa.Column("chunk_size", sa.Integer, nullable=True, comment="Target chunk size (strategy-specific)"),
    )
    op.add_column(
        "user_settings",
        sa.Column("chunk_overlap", sa.Integer, nullable=True, comment="Overlap between chunks (strategy-specific)"),
    )

    # Chunk metadata for document_chunks
    op.add_column(
        "document_chunks",
        sa.Column("chunking_strategy", sa.String(length=32), nullable=True, comment="Strategy used to create this chunk"),
    )
    op.add_column(
        "document_chunks",
        sa.Column("metadata", sa.JSON, nullable=True, comment="Chunk metadata (semantic clusters, token counts, etc.)"),
    )

    # Create index for users with custom embedding configs
    op.create_index(
        "ix_user_settings_embedding_provider",
        "user_settings",
        ["embedding_provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_settings_embedding_provider", table_name="user_settings")

    op.drop_column("document_chunks", "metadata")
    op.drop_column("document_chunks", "chunking_strategy")

    op.drop_column("user_settings", "chunk_overlap")
    op.drop_column("user_settings", "chunk_size")
    op.drop_column("user_settings", "chunking_strategy")

    op.drop_column("user_settings", "embedding_tested_at")
    op.drop_column("user_settings", "embedding_dimension")
    op.drop_column("user_settings", "embedding_base_url")
    op.drop_column("user_settings", "embedding_api_key")
    op.drop_column("user_settings", "embedding_model")
    op.drop_column("user_settings", "embedding_provider")
