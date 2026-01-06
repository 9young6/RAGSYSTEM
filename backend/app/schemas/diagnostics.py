from __future__ import annotations

from pydantic import BaseModel, Field


class OllamaDiagnosticsRequest(BaseModel):
    llm_model: str = Field(min_length=1, max_length=128)
    embedding_model: str = Field(min_length=1, max_length=128)
    prompt: str = Field(default="ping", min_length=1, max_length=2000)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)


class OllamaDiagnosticsResponse(BaseModel):
    ok: bool
    ollama_base_url: str
    models_found: list[str]
    llm_ok: bool
    llm_error: str | None = None
    llm_preview: str | None = None
    embedding_ok: bool
    embedding_error: str | None = None
    embedding_dimension: int | None = None


class InferenceProviderDiagnosticsRequest(BaseModel):
    provider: str = Field(default="ollama", min_length=1, max_length=32)  # ollama | vllm | xinference
    model: str = Field(min_length=1, max_length=128)
    prompt: str = Field(default="ping", min_length=1, max_length=2000)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)


class InferenceProviderDiagnosticsResponse(BaseModel):
    ok: bool
    provider: str
    base_url: str
    model: str
    preview: str | None = None
    error: str | None = None


class RerankDiagnosticsRequest(BaseModel):
    provider: str = Field(default="xinference", min_length=1, max_length=32)  # xinference
    model: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=2000)
    documents: list[str] = Field(min_length=1)


class RerankDiagnosticsResponse(BaseModel):
    ok: bool
    provider: str
    base_url: str
    model: str
    scores: list[float] | None = None
    error: str | None = None
