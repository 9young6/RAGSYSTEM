from __future__ import annotations

from pydantic import BaseModel


class AdminUserItem(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool


class AdminUserListResponse(BaseModel):
    users: list[AdminUserItem]

