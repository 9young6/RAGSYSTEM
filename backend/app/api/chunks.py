"""
chunks.py：Chunk 切分预览和管理接口。

提供以下功能：
1. 切分预览：在入库前预览文档切分效果
2. Chunk 管理：增删改查 chunks
3. Chunk 重新 embedding
"""

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.chunks import (
    ChunkPreviewRequest,
    ChunkPreviewResponse,
    ChunkPreviewItem,
)
from app.services.text_splitter import (
    TextSplitter,
    num_tokens_from_string,
)

if TYPE_CHECKING:
    from app.models.user_settings import UserSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chunks", tags=["chunks"])


@router.post("/preview", response_model=ChunkPreviewResponse)
def preview_chunks(
    payload: ChunkPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    预览文档切分效果。

    支持两种模式：
    1. 提供 document_id：从数据库读取文档的 Markdown 内容
    2. 提供文本：直接切分提供的文本（用于快速测试）

    切分参数优先级：
    - 明确提供的参数（chunk_size, overlap 等）
    - 用户设置中的参数
    - 系统默认值
    """
    # 获取要切分的文本
    if payload.document_id:
        # 从数据库读取文档
        doc = db.query(Document).filter(Document.id == payload.document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # 权限检查
        if doc.owner_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Not authorized")

        # 从 MinIO 读取 Markdown 内容
        from app.services.minio_service import MinioService

        try:
            content_bytes = MinioService().download_bytes(doc.markdown_path)
            text = content_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to download markdown: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to load document content: {str(e)}")

    elif payload.text:
        text = payload.text
    else:
        raise HTTPException(
            status_code=400, detail="Must provide either document_id or text"
        )

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Text is empty")

    # 获取切分参数
    # TODO: 从用户设置中获取默认参数
    strategy = payload.strategy or "recursive"

    # 根据 overlap_percent 计算 overlap
    chunk_size = payload.chunk_size or 1000
    overlap_percent = payload.overlap_percent or 20

    if payload.overlap is not None:
        overlap = payload.overlap
    else:
        # 使用百分比计算 overlap
        overlap = max(0, min(int(chunk_size * overlap_percent / 100), chunk_size // 2))

    try:
        # 创建 splitter
        splitter = TextSplitter(
            strategy=strategy,
            chunk_size=chunk_size,
            overlap=overlap,
            delimiters=payload.delimiters,
        )

        # 执行切分
        chunks_text = splitter.split(text)

        if not chunks_text:
            raise HTTPException(status_code=500, detail="Splitting failed: no chunks generated")

        # 统计信息
        total_chars = sum(len(c) for c in chunks_text)
        avg_chunk_size = total_chars / len(chunks_text) if chunks_text else 0
        min_chunk_size = min((len(c) for c in chunks_text), default=0)
        max_chunk_size = max((len(c) for c in chunks_text), default=0)

        # 如果是 token 策略，统计 token 数
        total_tokens = None
        if strategy == "token":
            total_tokens = sum(num_tokens_from_string(c) for c in chunks_text)

        # 构建预览项
        preview_items = []
        for i, chunk_text in enumerate(chunks_text):
            item = ChunkPreviewItem(
                chunk_index=i,
                content=chunk_text,
                char_count=len(chunk_text),
                token_count=num_tokens_from_string(chunk_text) if strategy == "token" else None,
            )
            preview_items.append(item)

        return ChunkPreviewResponse(
            strategy=strategy,
            total_chunks=len(preview_items),
            total_chars=total_chars,
            total_tokens=total_tokens,
            chunks=preview_items,
            avg_chunk_size=round(avg_chunk_size, 2),
            min_chunk_size=min_chunk_size,
            max_chunk_size=max_chunk_size,
        )

    except Exception as e:
        logger.error(f"Chunk preview failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Splitting failed: {str(e)}")
