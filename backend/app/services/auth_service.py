from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User


_PBKDF2_ITERATIONS = 120_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    """
    使用 PBKDF2-SHA256 对密码进行哈希。

    返回格式：`pbkdf2_sha256$iterations$salt$derived`（salt/derived 为 base64）。
    """
    if salt is None:
        salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return "pbkdf2_sha256$%d$%s$%s" % (
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("utf-8"),
        base64.b64encode(derived).decode("utf-8"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    """
    验证明文密码是否与存储的 PBKDF2 哈希匹配。
    """
    try:
        # 解析哈希格式：scheme$iterations$salt$hash
        scheme, iterations_raw, salt_b64, derived_b64 = password_hash.split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    try:
        # 将迭代次数转换为整数
        iterations = int(iterations_raw)
    except ValueError:
        return False
    # 解码base64编码的盐值和派生值
    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(derived_b64)
    # 使用相同的参数重新计算哈希值
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    # 比较计算出的哈希值与期望的哈希值
    return hmac.compare_digest(derived, expected)


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """
    根据用户名与密码验证用户；成功返回 User，否则返回 None。
    """
    user = db.query(User).filter(User.username == username).one_or_none()
    # 检查用户是否存在且处于激活状态
    if not user or not user.is_active:
        return None
    # 验证用户提供的密码是否与存储的密码哈希匹配
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(username: str, role: str) -> str:
    """
    创建 JWT 访问令牌（包含 sub/role/iat/exp）。
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": username, "role": role, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    解码 JWT 访问令牌并返回 payload。
    """
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def get_user_by_username(db: Session, username: str) -> User | None:
    """
    根据用户名查询用户；不存在返回 None。
    """
    return db.query(User).filter(User.username == username).one_or_none()


def register_user(db: Session, username: str, password: str) -> User:
    """注册新用户（用户名冲突时抛出 ValueError）。"""
    # 检查用户名是否已存在
    existing = db.query(User).filter(User.username == username).one_or_none()
    if existing is not None:
        raise ValueError("Username already exists")
    # 创建新用户并保存到数据库
    user = User(username=username, password_hash=hash_password(password), role="user", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
