from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    document_id: int
    document_name: str
    preview: str | None = None
    status: str


class DocumentConfirmResponse(BaseModel):
    document_id: int
    status: str


class DocumentSummary(BaseModel):
    id: int
    document_name: str
    status: str
    preview: str | None = None
    created_at: datetime
    markdown_status: str | None = None
    owner_id: int | None = None
    size_bytes: int | None = None
    chunk_count: int | None = None


class DocumentListItem(BaseModel):
    """Extended document list item with more details"""
    id: int
    document_name: str
    status: str
    markdown_status: str | None = None
    created_at: datetime
    confirmed_at: datetime | None = None
    reviewed_at: datetime | None = None
    indexed_at: datetime | None = None
    owner_id: int
    size_bytes: int
    content_type: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]
    total: int
    page: int
    page_size: int


class PendingReviewsResponse(BaseModel):
    documents: list[DocumentSummary]


class DocumentDetail(BaseModel):
    id: int
    document_name: str
    status: str
    preview: str | None = None


class BatchDeleteRequest(BaseModel):
    document_ids: list[int]


class BatchDeleteResponse(BaseModel):
    deleted_count: int
    failed_ids: list[int] = []
    message: str
