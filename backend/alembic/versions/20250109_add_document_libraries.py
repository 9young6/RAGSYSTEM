"""add document libraries

Revision ID: 20250109_add_doc_lib
Revises: 20250109_add_emb_chunk
Create Date: 2025-01-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250109_add_doc_lib'
down_revision = '20250109_add_emb_chunk'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 document_libraries 表
    op.create_table(
        'document_libraries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('embedding_strategy', sa.String(length=50), nullable=True),
        sa.Column('chunking_strategy', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_libraries_id'), 'document_libraries', ['id'], unique=False)
    op.create_index(op.f('ix_document_libraries_owner_id'), 'document_libraries', ['owner_id'], unique=False)

    # 为 documents 表添加 library_id 外键
    op.add_column('documents', sa.Column('library_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_documents_library_id',
        'documents', 'document_libraries',
        ['library_id'], ['id']
    )
    op.create_index('ix_documents_library_id', 'documents', ['library_id'])


def downgrade() -> None:
    # 删除 documents 表的 library_id 外键和索引
    op.drop_index('ix_documents_library_id', table_name='documents')
    op.drop_constraint('fk_documents_library_id', 'documents', type_='foreignkey')
    op.drop_column('documents', 'library_id')

    # 删除 document_libraries 表
    op.drop_index(op.f('ix_document_libraries_owner_id'), table_name='document_libraries')
    op.drop_index(op.f('ix_document_libraries_id'), table_name='document_libraries')
    op.drop_table('document_libraries')
