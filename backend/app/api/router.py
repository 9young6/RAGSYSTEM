from __future__ import annotations

from fastapi import APIRouter

from app.api import acceptance, admin, auth, diagnostics, documents, health, query, review, settings


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(review.router)
api_router.include_router(query.router)
api_router.include_router(health.router)
api_router.include_router(admin.router)
api_router.include_router(settings.router)
api_router.include_router(diagnostics.router)
api_router.include_router(acceptance.router)
