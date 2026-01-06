from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.review_action import ReviewAction
from app.models.user import User
from app.schemas.documents import DocumentSummary, PendingReviewsResponse
from app.schemas.review import RejectRequest, ReviewActionResponse
from app.services.rag_service import RAGService


router = APIRouter(prefix="/review", tags=["review"])


@router.get("/pending", response_model=PendingReviewsResponse)
def get_pending_reviews(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PendingReviewsResponse:
    # Show both 'uploaded' and 'confirmed' documents for review
    documents = (
        db.query(Document)
        .filter(Document.status.in_(["uploaded", "confirmed"]))
        .order_by(Document.created_at.desc())
        .all()
    )
    chunk_counts: dict[int, int] = {}
    try:
        ids = [int(d.id) for d in documents]
        if ids:
            rows = (
                db.query(DocumentChunk.document_id, func.count(DocumentChunk.id))
                .filter(DocumentChunk.document_id.in_(ids))
                .group_by(DocumentChunk.document_id)
                .all()
            )
            chunk_counts = {int(doc_id): int(cnt) for doc_id, cnt in rows}
    except Exception:
        chunk_counts = {}
    return PendingReviewsResponse(
        documents=[
            DocumentSummary(
                id=d.id,
                document_name=d.filename,
                status=d.status,
                preview=d.preview_text,
                created_at=d.created_at,
                markdown_status=d.markdown_status,
                owner_id=d.owner_id,
                size_bytes=d.size_bytes,
                chunk_count=chunk_counts.get(int(d.id), 0),
            )
            for d in documents
        ]
    )


@router.post("/approve/{document_id}", response_model=ReviewActionResponse)
def approve_document(
    document_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReviewActionResponse:
    """
    Approve a document and index it to the owner's partition

    Multi-tenant: Document is indexed to the owner's Milvus partition.
    MinerU: Uses Markdown content if available, otherwise parses original file.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    # Allow approve for both 'uploaded' and 'confirmed' status
    if document.status not in {"uploaded", "confirmed"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status for approve: {document.status}. Must be 'uploaded' or 'confirmed'."
        )
    if document.markdown_status != "markdown_ready":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Markdown not ready for approval")

    document.status = "approved"
    document.reviewer_id = admin.id
    document.reviewed_at = datetime.now(timezone.utc)
    document.reject_reason = None
    db.add(ReviewAction(document_id=document.id, reviewer_id=admin.id, action="approve"))
    db.commit()

    try:
        # Multi-tenant: Index to owner's partition
        RAGService().index_document(db, document_id=document.id, user_id=document.owner_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Indexing failed: {exc}")

    return ReviewActionResponse(document_id=document.id, status="indexed")


@router.post("/reject/{document_id}", response_model=ReviewActionResponse)
def reject_document(
    document_id: int,
    payload: RejectRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReviewActionResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    # Allow reject for both 'uploaded' and 'confirmed' status
    if document.status not in {"uploaded", "confirmed"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status for reject: {document.status}. Must be 'uploaded' or 'confirmed'."
        )

    document.status = "rejected"
    document.reviewer_id = admin.id
    document.reviewed_at = datetime.now(timezone.utc)
    document.reject_reason = payload.reason
    db.add(ReviewAction(document_id=document.id, reviewer_id=admin.id, action="reject", reason=payload.reason))
    db.commit()
    return ReviewActionResponse(document_id=document.id, status=document.status)
