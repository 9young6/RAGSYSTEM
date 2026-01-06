from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    provider: str | None = None  # ollama | vllm | xinference (optional; fallback to user settings)
    model: str = "qwen2.5:32b"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    user_id: int | None = Field(default=None, ge=1)
    rerank: bool | None = None
    rerank_provider: str | None = None
    rerank_model: str | None = None


class QuerySource(BaseModel):
    document_id: int
    document_name: str
    chunk_index: int
    relevance: float


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[QuerySource]
    confidence: float
