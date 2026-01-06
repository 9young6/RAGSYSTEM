from __future__ import annotations

import logging

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class RerankService:
    def __init__(self) -> None:
        self.base_url = (settings.XINFERENCE_BASE_URL or "").rstrip("/")
        self.api_key = settings.XINFERENCE_API_KEY

    def is_configured(self) -> bool:
        return bool(self.base_url)

    def rerank_xinference(self, query: str, documents: list[str], model: str) -> list[tuple[int, float]]:
        """
        Call Xinference rerank API.

        Expected request: POST {base_url}/v1/rerank
        Payload: {"model": model, "query": query, "documents": [..]}
        """
        if not self.base_url:
            raise RuntimeError("XINFERENCE_BASE_URL not configured")

        url = f"{self.base_url}/v1/rerank"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        r = requests.post(url, json={"model": model, "query": query, "documents": documents}, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()

        results = data.get("results") or data.get("data") or []
        pairs: list[tuple[int, float]] = []
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                idx = item.get("index")
                score = None
                for key in (
                    "score",
                    "relevance_score",  # OpenAI-compatible rerank
                    "relevanceScore",
                    "relevance",
                    "rerank_score",
                    "rerankScore",
                ):
                    if item.get(key) is not None:
                        score = item.get(key)
                        break
                if idx is None or score is None:
                    continue
                pairs.append((int(idx), float(score)))

        if not pairs and isinstance(data.get("scores"), list):
            pairs = [(i, float(s)) for i, s in enumerate(data["scores"])]

        if not pairs:
            raise ValueError("Unexpected rerank response")

        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs
