from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReviewAction(Base):
    """
    审核操作流水（审计日志）。

    目前记录：
    - approve：审核通过（随后会触发索引）
    - reject：审核拒绝（会写入 reason，并把 Document.status 置为 rejected）

    典型定制点（内网场景）：
    - 接入外部审批系统：可在写入 ReviewAction 后，额外调用 Webhook / MQ
    - 增加更多动作：如 "request_changes" / "escalate" 等
    """
    __tablename__ = "review_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    reviewer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # approve | reject
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    document = relationship("Document")
    reviewer = relationship("User")
