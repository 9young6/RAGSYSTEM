from __future__ import annotations

"""
chunk_service.py：chunk 生成与重建逻辑（切分器封装）。

约定：
- chunk 生成只依赖纯文本（Markdown/解析文本）
- 生成结果写入 Postgres（`DocumentChunk`），供审核/编辑/勾选 included
"""

from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.services.text_splitter import TextSplitter


class ChunkService:
    def __init__(self) -> None:
        self.splitter = TextSplitter()

    def regenerate_document_chunks(self, db: Session, document_id: int, text: str) -> int:
        # Postgres TEXT does not allow NUL (0x00). Some PDF extractors may return it.
        safe_text = (text or "").replace("\x00", "")
        chunks = self.splitter.split(safe_text)

        try:
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete(synchronize_session=False)
            db.add_all(
                [
                    DocumentChunk(document_id=document_id, chunk_index=i, content=(chunk or "").replace("\x00", ""), included=True)
                    for i, chunk in enumerate(chunks)
                    if chunk and chunk.strip()
                ]
            )
            db.commit()
            return len(chunks)
        except Exception:
            db.rollback()
            raise
