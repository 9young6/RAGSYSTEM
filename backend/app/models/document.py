from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
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

