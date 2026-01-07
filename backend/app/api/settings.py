from __future__ import annotations

"""
settings.py：用户侧“默认查询设置”接口（FastAPI）。

这个模块只存储“每个用户的默认值”（UserSettings）：
- 默认 LLM provider/model/top_k/temperature
- 是否启用 rerank，以及 rerank provider/model

同时返回一份“服务端默认配置”（来自 `.env`），用于前端展示与一键诊断：
- Ollama/vLLM/Xinference 的 base_url（服务地址）
- embedding provider/model/dimension

说明：
- 服务地址/端口本身不写入数据库，统一由部署侧环境变量控制（`.env` / 容器环境变量）。
- 前端如果需要“可编辑的推理地址”，建议做成“环境覆盖”或“多环境配置”，并配合 `/diagnostics/*` 做连通性测试。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.query import QueryRequest
from app.schemas.settings import ServerDefaults, UserSettingsResponse, UserSettingsUpdateRequest


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/me", response_model=UserSettingsResponse)
def get_my_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSettingsResponse:
    record = db.query(UserSettings).filter(UserSettings.user_id == user.id).one_or_none()
    if record is None:
        defaults = QueryRequest(query="x")
        default_llm_provider = "ollama"
        default_llm_model = defaults.model
        default_top_k = defaults.top_k
        default_temperature = defaults.temperature
        enable_rerank = bool(settings.XINFERENCE_BASE_URL)
        rerank_provider = "xinference" if enable_rerank else "none"
        rerank_model = "bge-reranker-large" if enable_rerank else None
    else:
        default_llm_provider = record.default_llm_provider
        default_llm_model = record.default_llm_model
        default_top_k = int(record.default_top_k)
        default_temperature = float(record.default_temperature)
        enable_rerank = bool(record.enable_rerank)
        rerank_provider = record.rerank_provider
        rerank_model = record.rerank_model

    api_base = "/api/v1"
    return UserSettingsResponse(
        default_llm_provider=default_llm_provider,
        default_llm_model=default_llm_model,
        default_top_k=default_top_k,
        default_temperature=default_temperature,
        enable_rerank=enable_rerank,
        rerank_provider=rerank_provider,
        rerank_model=rerank_model,
        server=ServerDefaults(
            api_base=api_base,
            ollama_base_url=settings.OLLAMA_BASE_URL,
            vllm_base_url=settings.VLLM_BASE_URL,
            xinference_base_url=settings.XINFERENCE_BASE_URL,
            embedding_provider=settings.EMBEDDING_PROVIDER,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dimension=int(settings.EMBEDDING_DIMENSION),
            ollama_embedding_model=settings.OLLAMA_EMBEDDING_MODEL,
        ),
    )


@router.put("/me", response_model=UserSettingsResponse)
def update_my_settings(
    payload: UserSettingsUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSettingsResponse:
    record = db.query(UserSettings).filter(UserSettings.user_id == user.id).one_or_none()
    if record is None:
        record = UserSettings(user_id=user.id)
        db.add(record)

    record.default_llm_provider = payload.default_llm_provider
    record.default_llm_model = payload.default_llm_model
    record.default_top_k = int(payload.default_top_k)
    record.default_temperature = float(payload.default_temperature)
    record.enable_rerank = bool(payload.enable_rerank)
    record.rerank_provider = payload.rerank_provider
    record.rerank_model = payload.rerank_model
    record.updated_at = datetime.now(timezone.utc)
    db.commit()

    api_base = "/api/v1"
    return UserSettingsResponse(
        default_llm_provider=record.default_llm_provider,
        default_llm_model=record.default_llm_model,
        default_top_k=int(record.default_top_k),
        default_temperature=float(record.default_temperature),
        enable_rerank=bool(record.enable_rerank),
        rerank_provider=record.rerank_provider,
        rerank_model=record.rerank_model,
        server=ServerDefaults(
            api_base=api_base,
            ollama_base_url=settings.OLLAMA_BASE_URL,
            vllm_base_url=settings.VLLM_BASE_URL,
            xinference_base_url=settings.XINFERENCE_BASE_URL,
            embedding_provider=settings.EMBEDDING_PROVIDER,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dimension=int(settings.EMBEDDING_DIMENSION),
            ollama_embedding_model=settings.OLLAMA_EMBEDDING_MODEL,
        ),
    )
