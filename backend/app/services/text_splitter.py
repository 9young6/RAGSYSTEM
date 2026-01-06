from __future__ import annotations

from app.config import settings


class TextSplitter:
    def __init__(self, chunk_size: int | None = None, overlap: int | None = None) -> None:
        self.chunk_size = chunk_size if chunk_size is not None else settings.CHUNK_SIZE
        self.overlap = overlap if overlap is not None else settings.CHUNK_OVERLAP

    def split(self, text: str) -> list[str]:
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return []
        if self.chunk_size <= 0:
            return [cleaned]

        chunks: list[str] = []
        start = 0
        while start < len(cleaned):
            end = min(len(cleaned), start + self.chunk_size)
            chunk = cleaned[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(cleaned):
                break
            start = max(0, end - max(0, self.overlap))
        return chunks

