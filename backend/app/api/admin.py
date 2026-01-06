from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.admin import AdminUserItem, AdminUserListResponse


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

