from __future__ import annotations

from pydantic import BaseModel, Field


class ChunkItem(BaseModel):
    id: int
    document_id: int
    chunk_index: int
    content: str
    included: bool


class ChunkListResponse(BaseModel):
    document_id: int
    chunks: list[ChunkItem]
    total: int
    page: int
    page_size: int


class ChunkCreateRequest(BaseModel):
    content: str = Field(min_length=1)


class ChunkCreateResponse(BaseModel):
    document_id: int
    chunk: ChunkItem
    vector_synced: bool


class ChunkUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    sync_vector: bool = True
    included: bool | None = None


class ChunkUpdateResponse(BaseModel):
    document_id: int
    chunk: ChunkItem
    vector_synced: bool


class ChunkDeleteResponse(BaseModel):
    document_id: int
    deleted_chunk_id: int
    deleted_chunk_index: int
    vector_deleted: bool


class ChunkReembedRequest(BaseModel):
    chunk_ids: list[int] | None = None


class ChunkReembedResponse(BaseModel):
    document_id: int
    reembedded_chunks: int
