from __future__ import annotations

"""
embedding_service.py：统一的 embedding 生成封装。

当前支持的 provider（通过 `.env` 的 `EMBEDDING_PROVIDER` 控制）：
- `ollama`：调用 `POST {OLLAMA_BASE_URL}/api/embeddings`（模型名使用 `OLLAMA_EMBEDDING_MODEL`）
- `sentence_transformers`：容器内本地推理（`EMBEDDING_MODEL` 指向本地/HF 模型名）
- `hash`：兜底方案（纯哈希向量，只用于演示/开发，无法提供真实语义检索）

注意：
- `EMBEDDING_DIMENSION` 必须与所用 embedding 模型输出维度一致，否则 Milvus collection 会不匹配。
- Ollama embeddings 可能对输入长度有限制；这里做了自动截断重试，避免因超长 chunk 导致整体索引失败。
"""

import logging
import math
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self.provider = (settings.EMBEDDING_PROVIDER or "hash").lower()
        self.dimension = int(settings.EMBEDDING_DIMENSION)
        self._st_model: Any | None = None

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.provider == "sentence_transformers":
            return self._embed_sentence_transformers(texts)
        if self.provider == "ollama":
            return [self._embed_ollama(t) for t in texts]
        if self.provider == "hash":
            return [self._embed_hash(t) for t in texts]
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {self.provider}")

    def _embed_sentence_transformers(self, texts: list[str]) -> list[list[float]]:
        from sentence_transformers import SentenceTransformer

        if self._st_model is None:
            self._st_model = SentenceTransformer(settings.EMBEDDING_MODEL)
        vectors = self._st_model.encode(texts, normalize_embeddings=True)
        vectors_list: list[list[float]] = vectors.tolist()
        for vector in vectors_list:
            if len(vector) != self.dimension:
                raise ValueError(
                    f"Embedding dimension mismatch (expected {self.dimension}, got {len(vector)}). "
                    "Check EMBEDDING_MODEL / EMBEDDING_DIMENSION."
                )
        return vectors_list

    def _embed_ollama(self, text: str) -> list[float]:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embeddings"
        prompt = text or ""

        # Some embedding models (e.g. bge-large) enforce relatively small context length.
        # If Ollama returns "input length exceeds the context length", retry with a shorter prompt.
        for attempt in range(5):
            payload = {"model": settings.OLLAMA_EMBEDDING_MODEL, "prompt": prompt}
            response = requests.post(url, json=payload, timeout=60)
            if response.status_code >= 400:
                err_text = ""
                try:
                    err_text = str((response.json() or {}).get("error") or "")
                except Exception:
                    err_text = ""
                if not err_text:
                    err_text = response.text or ""

                if "context length" in err_text.lower() and attempt < 4 and len(prompt) > 128:
                    new_len = max(128, int(len(prompt) * 0.75))
                    logger.info("Ollama embeddings prompt too long; retry with %s chars (was %s)", new_len, len(prompt))
                    prompt = prompt[:new_len]
                    continue

                response.raise_for_status()

            data = response.json()
            vector = data.get("embedding")
            if not isinstance(vector, list):
                raise ValueError("Unexpected Ollama embeddings response")
            if self.dimension and len(vector) != self.dimension:
                raise ValueError(
                    f"Embedding dimension mismatch (expected {self.dimension}, got {len(vector)}). "
                    "Check OLLAMA_EMBEDDING_MODEL / EMBEDDING_DIMENSION."
                )
            return [float(v) for v in vector]

        raise ValueError("Ollama embeddings failed after retries")

    def _embed_hash(self, text: str) -> list[float]:
        import hashlib

        digest = hashlib.sha256((text or "").encode("utf-8")).digest()
        vector = [((digest[i % len(digest)] / 255.0) * 2.0 - 1.0) for i in range(self.dimension)]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]
