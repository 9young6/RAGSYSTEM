from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.services.auth_service import hash_password


def create_admin(username: str | None = None, password: str | None = None) -> User:
    username = username or settings.ADMIN_USERNAME
    password = password or settings.ADMIN_PASSWORD

    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).one_or_none()
        if existing:
            return existing
        user = User(username=username, password_hash=hash_password(password), role="admin", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def create_user(username: str, password: str) -> User:
    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).one_or_none()
        if existing:
            return existing
        user = User(username=username, password_hash=hash_password(password), role="user", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()

