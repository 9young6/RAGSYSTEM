from __future__ import annotations

from pydantic import BaseModel, Field


class AcceptanceRunRequest(BaseModel):
    report_document_id: int = Field(ge=1)
    provider: str | None = Field(default=None, min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=128)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_k: int = Field(default=12, ge=1, le=30)

    # scope: self (user partition), user (specific user), all (all partitions; admin only)
    scope: str = Field(default="self", min_length=1, max_length=16)
    scope_user_id: int | None = Field(default=None, ge=1)


class AcceptanceSource(BaseModel):
    document_id: int
    document_name: str
    chunk_index: int
    relevance: float


class AcceptanceRunResponse(BaseModel):
    report_document_id: int
    passed: bool | None = None
    verdict: str | None = None
    report_markdown: str
    sources: list[AcceptanceSource] = []
