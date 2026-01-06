from __future__ import annotations

from pydantic import BaseModel, Field


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ReviewActionResponse(BaseModel):
    document_id: int
    status: str

