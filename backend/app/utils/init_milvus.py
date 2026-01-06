from __future__ import annotations

from app.services.milvus_service import MilvusService


def init_collections() -> None:
    MilvusService().ensure_collection()

