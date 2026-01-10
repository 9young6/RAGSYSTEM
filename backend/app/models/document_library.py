"""
Document Library model.

每个用户可以创建多个文档库，用于分类管理不同项目/类型的文档。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentLibrary(Base):
    """
    文档库模型。

    用途：
    - 用户可以创建多个文档库
    - 每个库管理一类文档（如：项目A、项目B、技术文档、产品手册等）
    - 文档上传时选择所属库
    - 查询时选择库进行检索

    隔离性：
    - 用户只能看到自己的库
    - 库与库之间完全隔离（Milvus 也使用不同的 collection）
    """

    __tablename__ = "document_libraries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(index=True, nullable=False)  # 所属用户
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # 库名称
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # 描述
    embedding_strategy: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="该库使用的 embedding 策略"
    )
    chunking_strategy: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="该库使用的切分策略"
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    # 关系
    documents = relationship("Document", back_populates="library", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<DocumentLibrary(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"
