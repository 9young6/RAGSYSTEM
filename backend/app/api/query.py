from __future__ import annotations

"""
query.py：检索问答接口（FastAPI）。

接口分两类：
- `POST /query`：普通用户查询，只检索自己的知识库（Milvus 用户分区隔离）
- `POST /query/admin`：管理员跨库查询，可选择指定 user_id 或全库

查询参数来源：
- 请求体 `QueryRequest` 可覆盖单次查询的 provider/model/top_k/temperature/rerank 等
- 若未提供，则使用 `UserSettings` 中的默认值（见 `backend/app/api/settings.py`）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.query import QueryRequest, QueryResponse
from app.services.rag_service import RAGService


router = APIRouter(prefix="", tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query_knowledge_base(
    payload: QueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QueryResponse:
    """
    Query knowledge base (multi-tenant: searches only user's own partition)

    Regular users can only query their own knowledge base.
    For admin cross-library queries, use /query/admin endpoint.
    """
    us = db.query(UserSettings).filter(UserSettings.user_id == user.id).one_or_none()
    llm_provider = (payload.provider or (us.default_llm_provider if us else "ollama") or "ollama") or "ollama"
    llm_model = payload.model or (us.default_llm_model if us else None) or payload.model
    llm_temperature = payload.temperature if payload.temperature is not None else (us.default_temperature if us else 0.7)
    effective_top_k = payload.top_k if payload.top_k is not None else (us.default_top_k if us else 5)

    effective_rerank = payload.rerank if payload.rerank is not None else (bool(us.enable_rerank) if us else False)
    effective_rerank_provider = payload.rerank_provider or (us.rerank_provider if us else None)
    effective_rerank_model = payload.rerank_model or (us.rerank_model if us else None)

    return RAGService().query(
        db,
        query_text=payload.query,
        top_k=effective_top_k,
        llm_provider=llm_provider,
        model=llm_model,
        temperature=llm_temperature,
        user_id=user.id,  # Multi-tenant: Filter by user partition
        rerank=effective_rerank,
        rerank_provider=effective_rerank_provider,
        rerank_model=effective_rerank_model,
    )


@router.post("/query/admin", response_model=QueryResponse)
def admin_query_knowledge_base(
    payload: QueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QueryResponse:
    """
    Admin cross-library query (searches across all user partitions or specific users)

    Only admins can use this endpoint.
    Optional: Add user_ids list in payload to search specific users' libraries.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for cross-library queries",
        )

    # Admin queries all partitions by default; can restrict to a specific user partition via user_id.
    partition_names = None
    if payload.user_id:
        partition_names = [f"user_{payload.user_id}"]

    us = db.query(UserSettings).filter(UserSettings.user_id == user.id).one_or_none()
    llm_provider = (payload.provider or (us.default_llm_provider if us else "ollama") or "ollama") or "ollama"
    llm_model = payload.model or (us.default_llm_model if us else None) or payload.model
    llm_temperature = payload.temperature if payload.temperature is not None else (us.default_temperature if us else 0.7)
    effective_top_k = payload.top_k if payload.top_k is not None else (us.default_top_k if us else 5)

    effective_rerank = payload.rerank if payload.rerank is not None else (bool(us.enable_rerank) if us else False)
    effective_rerank_provider = payload.rerank_provider or (us.rerank_provider if us else None)
    effective_rerank_model = payload.rerank_model or (us.rerank_model if us else None)

    return RAGService().query(
        db,
        query_text=payload.query,
        top_k=effective_top_k,
        llm_provider=llm_provider,
        model=llm_model,
        temperature=llm_temperature,
        user_id=None,  # No filtering - searches all partitions
        partition_names=partition_names,
        rerank=effective_rerank,
        rerank_provider=effective_rerank_provider,
        rerank_model=effective_rerank_model,
    )
