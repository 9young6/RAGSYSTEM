"""Document library schemas."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class LibraryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    embedding_strategy: str | None = Field(None, max_length=50)
    chunking_strategy: str | None = Field(None, max_length=50)


class LibraryCreate(LibraryBase):
    """创建文档库请求"""
    pass


class LibraryUpdate(BaseModel):
    """更新文档库请求"""
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    embedding_strategy: str | None = Field(None, max_length=50)
    chunking_strategy: str | None = Field(None, max_length=50)


class LibraryResponse(LibraryBase):
    """文档库响应"""
    id: int
    owner_id: int
    document_count: int = 0  # 该库的文档数量
    created_at: datetime

    class Config:
        from_attributes = True


class LibraryListResponse(BaseModel):
    """文档库列表响应"""
    libraries: list[LibraryResponse]
    total: int
