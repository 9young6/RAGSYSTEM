from __future__ import annotations

import requests
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas.health import HealthResponse
from app.services.milvus_service import MilvusService
from app.services.minio_service import MinioService


router = APIRouter(prefix="", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    details: dict = {}
    ok = True

    # DB
    try:
        db.execute(text("SELECT 1"))
        details["postgres"] = "ok"
    except Exception as exc:
        ok = False
        details["postgres"] = f"error: {exc}"

    # Milvus
    try:
        MilvusService().ensure_collection()
        details["milvus"] = "ok"
    except Exception as exc:
        ok = False
        details["milvus"] = f"error: {exc}"

    # MinIO
    try:
        MinioService().ensure_bucket()
        details["minio"] = "ok"
    except Exception as exc:
        ok = False
        details["minio"] = f"error: {exc}"

    # Ollama
    try:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        models = [m.get("name") for m in (data.get("models") or []) if isinstance(m, dict) and m.get("name")]
        details["ollama"] = "ok"
        details["ollama_models"] = models
    except Exception as exc:
        ok = False
        details["ollama"] = f"error: {exc}"

    return HealthResponse(status="ok" if ok else "degraded", details=details)
