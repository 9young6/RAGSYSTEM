from __future__ import annotations

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
        enable_rerank = False
        rerank_provider = "none"
        rerank_model = None
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
            embedding_provider=settings.EMBEDDING_PROVIDER,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dimension=int(settings.EMBEDDING_DIMENSION),
            ollama_embedding_model=settings.OLLAMA_EMBEDDING_MODEL,
        ),
    )
