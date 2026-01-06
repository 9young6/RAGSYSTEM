from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Database
    DATABASE_URL: str = "postgresql://admin:secure_password_2024@postgres:5432/knowledge_base"

    # Milvus
    MILVUS_HOST: str = "milvus"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "knowledge_base"

    # Redis
    REDIS_URL: str = "redis://redis:6379"

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    # Ollama
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen2.5:32b"
    OLLAMA_TEMPERATURE: float = 0.7
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # Optional inference backends (OpenAI-compatible)
    VLLM_BASE_URL: str | None = None
    VLLM_API_KEY: str | None = None
    XINFERENCE_BASE_URL: str | None = None
    XINFERENCE_API_KEY: str | None = None

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "knowledge-base"
    MINIO_USE_SSL: bool = False

    # App
    APP_NAME: str = "Knowledge Base Management System"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])

    # Document processing
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    MAX_FILE_SIZE: int = 50 * 1024 * 1024

    # Embeddings
    EMBEDDING_PROVIDER: str = "hash"  # sentence_transformers | ollama | hash
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384

    # Auth
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"


settings = Settings()
