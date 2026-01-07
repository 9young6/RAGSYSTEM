from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    """
    文档主表（元数据 + 流程状态）。

    关键字段：
    - `status`：业务流程状态（影响“审核/索引/可见性”等）
      - uploaded：已上传（等待 Markdown 转换完成后由用户确认提交）
      - confirmed：用户已确认提交（管理员可在审核列表看到）
      - rejected：管理员拒绝（用户可看到拒绝原因并重新提交）
      - indexed：已入库（Milvus 已写入向量，可检索）
      - approved：审批中间态（approve 时短暂设置，索引完成后会被置为 indexed）
    - `markdown_status`：转换状态（异步 Celery 或直转）
      - processing：转换中
      - markdown_ready：已生成 Markdown（并通常已生成 chunks）
      - failed：转换失败（可重试或手动上传 Markdown）
      - pending：仅历史/兼容字段默认值，上传接口会立即设为 processing，避免“待转换”误导

    MinIO 路径：
    - `minio_object`：原始文件（user_{id}/documents/...）
    - `markdown_path`：Markdown 文件（user_{id}/markdown/{document_id}.md）
    """
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    preview_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    minio_bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    minio_object: Mapped[str] = mapped_column(String(512), nullable=False)

    # Multi-tenant fields
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    uploader_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    # MinerU Markdown conversion fields
    markdown_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    markdown_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending/processing/markdown_ready/failed
    markdown_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", foreign_keys=[owner_id])
    uploader = relationship("User", foreign_keys=[uploader_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
