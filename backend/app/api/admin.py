from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.models.document import Document
from app.schemas.admin import AdminReindexItem, AdminReindexRequest, AdminReindexResponse, AdminUserItem, AdminUserListResponse
from app.services.rag_service import RAGService


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=AdminUserListResponse)
def list_users(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    users = db.query(User).order_by(User.id.asc()).all()
    return AdminUserListResponse(
        users=[
            AdminUserItem(id=u.id, username=u.username, role=u.role, is_active=bool(u.is_active))
            for u in users
        ]
    )


@router.post("/reindex", response_model=AdminReindexResponse)
def reindex_documents(
    payload: AdminReindexRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminReindexResponse:
    """
    Rebuild Milvus vectors for documents.

    - Default: reindex all documents with status == 'indexed'
    - Optional: restrict by document_ids / owner_id / status_in
    """
    q = db.query(Document)

    if payload.document_ids:
        q = q.filter(Document.id.in_([int(i) for i in payload.document_ids]))
    else:
        status_in = payload.status_in or ["indexed"]
        q = q.filter(Document.status.in_(status_in))
        if payload.owner_id is not None:
            q = q.filter(Document.owner_id == int(payload.owner_id))

    docs = q.order_by(Document.id.asc()).all()
    rag = RAGService()

    results: list[AdminReindexItem] = []
    succeeded = 0
    failed = 0

    for d in docs:
        try:
            chunks_indexed = rag.index_document(db, document_id=int(d.id), user_id=int(d.owner_id) if d.owner_id else None)
            results.append(AdminReindexItem(document_id=int(d.id), owner_id=int(d.owner_id) if d.owner_id else None, chunks_indexed=chunks_indexed, ok=True))
            succeeded += 1
        except Exception as exc:
            db.rollback()
            results.append(AdminReindexItem(document_id=int(d.id), owner_id=int(d.owner_id) if d.owner_id else None, ok=False, error=str(exc)))
            failed += 1

    return AdminReindexResponse(requested=len(docs), succeeded=succeeded, failed=failed, results=results)
