from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_settings_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    default_llm_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="ollama")  # ollama | vllm | xinference
    default_llm_model: Mapped[str] = mapped_column(String(128), nullable=False, default="qwen2.5:32b")
    default_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    default_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)

    enable_rerank: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rerank_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="none")  # none | xinference
    rerank_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
