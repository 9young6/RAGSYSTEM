from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.services.text_splitter import TextSplitter


class ChunkService:
    def __init__(self) -> None:
        self.splitter = TextSplitter()

    def regenerate_document_chunks(self, db: Session, document_id: int, text: str) -> int:
        chunks = self.splitter.split(text or "")

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete(synchronize_session=False)
        db.add_all(
            [
                DocumentChunk(document_id=document_id, chunk_index=i, content=chunk, included=True)
                for i, chunk in enumerate(chunks)
                if chunk and chunk.strip()
            ]
        )
        db.commit()
        return len(chunks)

