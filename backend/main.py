from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.services.minio_service import MinioService
from app.utils.init_db import create_admin
from app.utils.init_milvus import init_collections


logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "alembic_version" not in tables and ({"users", "documents"} & tables):
        command.stamp(cfg, "head")
        return

    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("%s starting...", settings.APP_NAME)
    try:
        _run_migrations()
    except Exception as exc:
        logger.warning("DB init failed: %s", exc)
    try:
        MinioService().ensure_bucket()
    except Exception as exc:
        logger.warning("MinIO init failed: %s", exc)
    try:
        init_collections()
    except Exception as exc:
        logger.warning("Milvus init failed: %s", exc)
    try:
        create_admin()
    except Exception as exc:
        logger.warning("Admin init skipped: %s", exc)
    yield
    logger.info("%s shutting down...", settings.APP_NAME)


app = FastAPI(title=settings.APP_NAME, version="1.0.0", debug=settings.DEBUG, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
def root():
    return {"status": "ok", "message": f"{settings.APP_NAME} API"}
