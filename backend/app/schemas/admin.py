from __future__ import annotations

from pydantic import BaseModel


class AdminUserItem(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool


class AdminUserListResponse(BaseModel):
    users: list[AdminUserItem]


class AdminReindexRequest(BaseModel):
    """Admin-only: rebuild Milvus vectors from DB chunks/Markdown/original file."""

    document_ids: list[int] | None = None
    owner_id: int | None = None
    status_in: list[str] | None = None  # default: ["indexed"]


class AdminReindexItem(BaseModel):
    document_id: int
    owner_id: int | None = None
    chunks_indexed: int | None = None
    ok: bool
    error: str | None = None


class AdminReindexResponse(BaseModel):
    requested: int
    succeeded: int
    failed: int
    results: list[AdminReindexItem]
