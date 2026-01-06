from __future__ import annotations

import math
from typing import Any

import requests

from app.config import settings


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
        payload = {"model": settings.OLLAMA_EMBEDDING_MODEL, "prompt": text}
        response = requests.post(url, json=payload, timeout=60)
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

    def _embed_hash(self, text: str) -> list[float]:
        import hashlib

        digest = hashlib.sha256((text or "").encode("utf-8")).digest()
        vector = [((digest[i % len(digest)] / 255.0) * 2.0 - 1.0) for i in range(self.dimension)]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

