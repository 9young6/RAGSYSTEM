from __future__ import annotations

from pydantic import BaseModel, Field


class ServerDefaults(BaseModel):
    api_base: str
    ollama_base_url: str
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    ollama_embedding_model: str


class UserSettingsResponse(BaseModel):
    default_llm_provider: str
    default_llm_model: str
    default_top_k: int
    default_temperature: float
    enable_rerank: bool
    rerank_provider: str
    rerank_model: str | None = None
    server: ServerDefaults


class UserSettingsUpdateRequest(BaseModel):
    default_llm_provider: str = Field(default="ollama", min_length=1, max_length=32)
    default_llm_model: str = Field(min_length=1, max_length=128)
    default_top_k: int = Field(default=5, ge=1, le=20)
    default_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    enable_rerank: bool = False
    rerank_provider: str = Field(default="none", min_length=1, max_length=32)
    rerank_model: str | None = Field(default=None, max_length=128)
