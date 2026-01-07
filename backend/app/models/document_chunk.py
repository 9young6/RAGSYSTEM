from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentChunk(Base):
    """
    文档分块（chunk）表。

    设计目的：
    - 让“管理员/用户”在入库前就可以查看/编辑/删除/新增 chunk
    - 通过 `included` 控制该 chunk 是否参与“最终入库”（索引到 Milvus）
      - 管理员审核时可在前端勾选 included
      - `RAGService.index_document()` 只会写入 included=true 的 chunks
    """
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    document = relationship("Document", back_populates="chunks")
