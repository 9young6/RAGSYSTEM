from __future__ import annotations

"""
review.py：管理员审核接口（FastAPI）。

审核链路（简化）：
1) 用户上传文档 -> 后端生成 Markdown + chunks（PDF 走 Celery/MinerU）
2) 用户确认提交（Document.status=confirmed，且 markdown_status=markdown_ready）
3) 管理员审核：
   - `GET /review/pending`：只展示“已确认提交 + Markdown 就绪”的文档
   - `POST /review/approve/{id}`：记录审核动作 + 触发索引（写入 Milvus）
   - `POST /review/reject/{id}`：记录审核动作 + 写入拒绝原因（用户可见并可重新提交）

内网常见定制点：
- 待审核队列的筛选规则（`get_pending_reviews()`：哪些状态/哪些用户可见）
- approve/reject 后的动作（是否自动索引、是否需要二次确认、是否接入外部审批系统）
- 审计字段与动作类型扩展（`ReviewAction.action` 的枚举扩展）
"""

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
    # 只展示“用户已确认提交 + Markdown 已就绪”的文档：
    # - 避免管理员看到“待转换/processing”的文档
    # - 避免审核内容与最终入库内容不一致
    documents = (
        db.query(Document)
        .filter(Document.status == "confirmed")
        .filter(Document.markdown_status == "markdown_ready")
        .order_by(Document.created_at.desc())
        .all()
    )

    owner_map: dict[int, str] = {}
    try:
        owner_ids = sorted({int(d.owner_id) for d in documents if d.owner_id})
        if owner_ids:
            rows = db.query(User).filter(User.id.in_(owner_ids)).all()
            owner_map = {int(u.id): str(u.username) for u in rows}
    except Exception:
        owner_map = {}
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
                owner_username=owner_map.get(int(d.owner_id)) if d.owner_id else None,
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
