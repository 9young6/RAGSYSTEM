from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.schemas.chunks import (
    ChunkCreateRequest,
    ChunkCreateResponse,
    ChunkDeleteResponse,
    ChunkItem,
    ChunkListResponse,
    ChunkReembedRequest,
    ChunkReembedResponse,
    ChunkUpdateRequest,
    ChunkUpdateResponse,
)
from app.schemas.documents import (
    BatchDeleteRequest,
    BatchDeleteResponse,
    DocumentConfirmResponse,
    DocumentDetail,
    DocumentListItem,
    DocumentListResponse,
    DocumentUploadResponse,
)
from app.services.document_parser import DocumentParser
from app.services.minio_service import MinioService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def _build_content_disposition(filename: str) -> str:
    ascii_fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "").strip("._") or "download"
    utf8_name = filename or "download"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(utf8_name)}"


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    """
    Upload a document. Sets owner_id and triggers MinerU conversion.

    Multi-tenant: Document belongs to the uploading user (owner_id).
    MinerU: Triggers async Markdown conversion task.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "document"

    sha256 = hashlib.sha256(content).hexdigest()

    # Multi-tenant: Use user-specific path in MinIO
    minio = MinioService()
    minio.ensure_bucket()
    object_name = minio.get_user_path(user.id, "documents", f"{uuid.uuid4().hex}_{filename}")
    minio.upload_bytes(object_name=object_name, content=content, content_type=content_type)

    parser = DocumentParser()
    preview_text: str | None
    try:
        preview_text = parser.parse_preview(content, content_type, filename)
    except Exception:
        preview_text = None

    normalized_name = (filename or "").lower()
    ext = "." + (normalized_name.split(".")[-1] if "." in normalized_name else "")
    direct_md_exts = {".md", ".markdown"}
    direct_text_exts = {".txt", ".json", ".csv", ".xlsx"}
    is_direct_markdown = ext in (direct_md_exts | direct_text_exts)

    # Create document with owner_id and markdown_status
    document = Document(
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256=sha256,
        status="uploaded",
        preview_text=preview_text,
        minio_bucket=minio.bucket,
        minio_object=object_name,
        owner_id=user.id,  # Multi-tenant: Set owner
        uploader_id=user.id,
        markdown_status="processing",  # set immediately to avoid confusing "pending" state
        created_at=datetime.now(timezone.utc),
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    if is_direct_markdown:
        # For common text/structured files, generate Markdown immediately (no celery dependency).
        try:
            text = parser.parse_text(content, content_type, filename).strip()
            if ext in direct_md_exts:
                md_content = text or "# (Empty Markdown)\n"
            elif ext == ".json":
                md_content = f"# {filename}\n\n```json\n{text}\n```\n"
            else:
                md_content = f"# {filename}\n\n```text\n{text}\n```\n"

            markdown_path = minio.get_user_path(user.id, "markdown", f"{document.id}.md")
            minio.upload_bytes(markdown_path, md_content.encode("utf-8"), content_type="text/markdown")
            document.markdown_path = markdown_path
            document.markdown_status = "markdown_ready"
            document.markdown_error = None
            db.commit()

            try:
                from app.services.chunk_service import ChunkService

                ChunkService().regenerate_document_chunks(db, document_id=document.id, text=md_content)
            except Exception as exc:
                logger.warning(f"Chunk generation failed for document {document.id}: {exc}")
        except Exception as e:
            logger.error(f"Direct markdown generation failed: {e}")
            document.markdown_status = "failed"
            document.markdown_error = str(e)
            db.commit()
    else:
        # Trigger MinerU conversion task asynchronously
        try:
            from tasks.celery_app import celery_app

            task = celery_app.send_task("tasks.mineru_tasks.convert_to_markdown", args=[document.id])
            logger.info(f"Triggered MinerU conversion task {task.id} for document {document.id}")
        except Exception as e:
            logger.error(f"Failed to trigger MinerU conversion: {e}")
            document.markdown_status = "failed"
            document.markdown_error = str(e)
            db.commit()

    return DocumentUploadResponse(
        document_id=document.id,
        document_name=document.filename,
        preview=document.preview_text,
        status=document.status,
    )


@router.post("/confirm/{document_id}", response_model=DocumentConfirmResponse)
def confirm_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentConfirmResponse:
    """Confirm a document after reviewing its Markdown conversion"""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Multi-tenant: Users can only confirm their own documents, admins can confirm any
    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    if document.status not in {"uploaded"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status for confirm")

    # Only allow confirm after Markdown is ready (admin review should never see "waiting conversion").
    if document.markdown_status != "markdown_ready":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Markdown not ready. Please wait for conversion or upload Markdown, then confirm.",
        )

    document.status = "confirmed"
    document.confirmed_at = datetime.now(timezone.utc)
    db.commit()
    return DocumentConfirmResponse(document_id=document.id, status=document.status)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    """Get document details"""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Multi-tenant: Users can only view their own documents, admins can view any
    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    return DocumentDetail(
        id=document.id,
        document_name=document.filename,
        status=document.status,
        preview=document.preview_text,
    )


@router.get("/{document_id}/markdown/status")
def get_markdown_status(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get MinerU Markdown conversion status

    Returns:
        dict: {"markdown_status": str, "markdown_error": str|None}
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    return {
        "document_id": document.id,
        "markdown_status": document.markdown_status,
        "markdown_error": document.markdown_error,
        "markdown_path": document.markdown_path,
    }


@router.get("/{document_id}/markdown/download")
def download_markdown(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """
    Download converted Markdown file for editing

    Returns:
        Response: Markdown file content as text/markdown
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    if document.markdown_status != "markdown_ready":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Markdown not ready. Status: {document.markdown_status}",
        )

    if not document.markdown_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Markdown path not found")

    # Download Markdown from MinIO
    minio = MinioService()
    try:
        markdown_bytes = minio.download_bytes(document.markdown_path)
        return Response(
            content=markdown_bytes,
            media_type="text/markdown",
            headers={"Content-Disposition": _build_content_disposition(f"{document.id}_{document.filename}.md")},
        )
    except Exception as e:
        logger.error(f"Failed to download Markdown for document {document_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to download Markdown")


@router.post("/{document_id}/markdown/upload")
async def upload_markdown(
    document_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Upload edited Markdown file to replace the auto-generated one

    This allows users to edit the Markdown before it gets indexed.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    # Read uploaded Markdown content
    markdown_content = await file.read()
    if not markdown_content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    # Upload to MinIO (overwrite existing or create new path)
    minio = MinioService()
    markdown_path = document.markdown_path or minio.get_user_path(user.id, "markdown", f"{document_id}.md")

    try:
        minio.upload_bytes(markdown_path, markdown_content, content_type="text/markdown")
        logger.info(f"Uploaded edited Markdown for document {document_id} to {markdown_path}")
    except Exception as e:
        logger.error(f"Failed to upload Markdown: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload Markdown")

    # Update document record
    document.markdown_path = markdown_path
    document.markdown_status = "markdown_ready"
    document.markdown_error = None
    db.commit()

    try:
        from app.services.chunk_service import ChunkService

        ChunkService().regenerate_document_chunks(
            db,
            document_id=document.id,
            text=markdown_content.decode("utf-8", errors="replace"),
        )
    except Exception as exc:
        logger.warning(f"Chunk regeneration failed for document {document.id}: {exc}")

    return {
        "document_id": document.id,
        "markdown_path": markdown_path,
        "markdown_status": document.markdown_status,
        "message": "Markdown uploaded successfully",
    }


@router.post("/{document_id}/markdown/convert")
def trigger_markdown_convert(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Trigger (or retry) Markdown conversion for a document.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    document.markdown_status = "processing"
    document.markdown_error = None
    db.commit()

    try:
        from tasks.celery_app import celery_app

        task = celery_app.send_task("tasks.mineru_tasks.convert_to_markdown", args=[document.id])
        logger.info(f"Triggered MinerU conversion task {task.id} for document {document.id}")
        return {"document_id": document.id, "markdown_status": document.markdown_status, "task_id": task.id}
    except Exception as e:
        document.markdown_status = "failed"
        document.markdown_error = str(e)
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to trigger conversion")


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    owner_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    """
    List user's documents with pagination and filtering

    Args:
        page: Page number (starts from 1)
        page_size: Number of documents per page (max 100)
        status_filter: Optional status filter (uploaded, confirmed, approved, indexed, rejected)
        user: Current user
        db: Database session

    Returns:
        DocumentListResponse with paginated documents
    """
    # Validate pagination parameters
    page = max(1, page)
    page_size = min(100, max(1, page_size))

    # Base query: users see their own documents, admins see all
    query = db.query(Document)
    if user.role != "admin":
        query = query.filter(Document.owner_id == user.id)
        if owner_id is not None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner_id filter requires admin")
    else:
        if owner_id is not None:
            query = query.filter(Document.owner_id == owner_id)

    # Apply status filter if provided
    if status_filter:
        query = query.filter(Document.status == status_filter)
    else:
        # Hide rejected documents by default for non-admin users.
        if user.role != "admin":
            query = query.filter(Document.status != "rejected")

    # Get total count
    total = query.count()

    # Get paginated documents
    documents = (
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return DocumentListResponse(
        documents=[
            DocumentListItem(
                id=d.id,
                document_name=d.filename,
                status=d.status,
                markdown_status=d.markdown_status,
                created_at=d.created_at,
                confirmed_at=d.confirmed_at,
                reviewed_at=d.reviewed_at,
                indexed_at=d.indexed_at,
                owner_id=d.owner_id,
                size_bytes=d.size_bytes,
                content_type=d.content_type,
            )
            for d in documents
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}/chunks", response_model=ChunkListResponse)
def list_document_chunks(
    document_id: int,
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChunkListResponse:
    page = max(1, page)
    page_size = min(200, max(1, page_size))

    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    # Chunks should be viewable even if Markdown conversion is still processing.
    # If chunks are missing, generate them once from the best available source:
    # - Prefer Markdown if ready
    # - Otherwise fall back to parsing the original file
    try:
        has_any = (
            db.query(DocumentChunk.id)
            .filter(DocumentChunk.document_id == document_id)
            .limit(1)
            .first()
            is not None
        )
    except Exception:
        has_any = False

    if not has_any:
        try:
            minio = MinioService()
            text = ""
            if document.markdown_path and document.markdown_status == "markdown_ready":
                md_bytes = minio.download_bytes(document.markdown_path)
                text = md_bytes.decode("utf-8", errors="replace")
            else:
                raw = minio.download_bytes(document.minio_object)
                text = DocumentParser().parse_text(raw, document.content_type, document.filename)

            from app.services.chunk_service import ChunkService

            ChunkService().regenerate_document_chunks(db, document_id=document_id, text=text)
        except Exception as exc:
            logger.warning(f"Chunks auto-generation skipped for document {document_id}: {exc}")

    q = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id)
    total = q.count()
    chunks = (
        q.order_by(DocumentChunk.chunk_index.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ChunkListResponse(
        document_id=document_id,
        chunks=[
            ChunkItem(
                id=c.id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                content=c.content,
                included=bool(getattr(c, "included", True)),
            )
            for c in chunks
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{document_id}/chunks", response_model=ChunkCreateResponse)
def create_document_chunk(
    document_id: int,
    payload: ChunkCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChunkCreateResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    max_idx = (
        db.query(func.max(DocumentChunk.chunk_index))
        .filter(DocumentChunk.document_id == document_id)
        .scalar()
    )
    next_idx = int(max_idx) + 1 if max_idx is not None else 0

    chunk = DocumentChunk(document_id=document_id, chunk_index=next_idx, content=payload.content, included=True)
    db.add(chunk)
    db.commit()
    db.refresh(chunk)

    vector_synced = False
    if document.status == "indexed":
        from app.services.embedding_service import EmbeddingService
        from app.services.milvus_service import MilvusService

        milvus = MilvusService()
        partition_name = milvus.get_user_partition_name(document.owner_id)
        milvus.create_partition(partition_name)
        embedding = EmbeddingService().embed_text(payload.content)
        milvus.insert(
            document_id=document_id,
            chunk_indices=[next_idx],
            embeddings=[embedding],
            partition_name=partition_name,
        )
        vector_synced = True

    return ChunkCreateResponse(
        document_id=document_id,
        chunk=ChunkItem(
            id=chunk.id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            included=bool(getattr(chunk, "included", True)),
        ),
        vector_synced=vector_synced,
    )


@router.patch("/{document_id}/chunks/{chunk_id}", response_model=ChunkUpdateResponse)
def update_document_chunk(
    document_id: int,
    chunk_id: int,
    payload: ChunkUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChunkUpdateResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    chunk = db.get(DocumentChunk, chunk_id)
    if chunk is None or chunk.document_id != document_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")

    if payload.content is None and payload.included is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update")

    old_included = bool(getattr(chunk, "included", True))
    if payload.content is not None:
        chunk.content = payload.content
    if payload.included is not None and hasattr(chunk, "included"):
        chunk.included = bool(payload.included)
    db.commit()
    db.refresh(chunk)

    vector_synced = False
    if document.status == "indexed":
        from app.services.embedding_service import EmbeddingService
        from app.services.milvus_service import MilvusService

        milvus = MilvusService()
        partition_name = milvus.get_user_partition_name(document.owner_id)
        milvus.create_partition(partition_name)

        new_included = bool(getattr(chunk, "included", True))
        if old_included and not new_included:
            milvus.delete_by_document_chunk(
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                partition_name=partition_name,
            )
            vector_synced = True
        elif (not old_included) and new_included:
            embedding = EmbeddingService().embed_text(chunk.content)
            milvus.insert(
                document_id=document_id,
                chunk_indices=[chunk.chunk_index],
                embeddings=[embedding],
                partition_name=partition_name,
            )
            vector_synced = True
        elif payload.sync_vector and new_included and payload.content is not None:
            embedding = EmbeddingService().embed_text(chunk.content)
            milvus.delete_by_document_chunk(
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                partition_name=partition_name,
            )
            milvus.insert(
                document_id=document_id,
                chunk_indices=[chunk.chunk_index],
                embeddings=[embedding],
                partition_name=partition_name,
            )
            vector_synced = True

    return ChunkUpdateResponse(
        document_id=document_id,
        chunk=ChunkItem(
            id=chunk.id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            included=bool(getattr(chunk, "included", True)),
        ),
        vector_synced=vector_synced,
    )


@router.delete("/{document_id}/chunks/{chunk_id}", response_model=ChunkDeleteResponse)
def delete_document_chunk(
    document_id: int,
    chunk_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChunkDeleteResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    chunk = db.get(DocumentChunk, chunk_id)
    if chunk is None or chunk.document_id != document_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")

    deleted_index = int(chunk.chunk_index)
    db.delete(chunk)
    db.commit()

    vector_deleted = False
    if document.status == "indexed":
        from app.services.milvus_service import MilvusService

        milvus = MilvusService()
        partition_name = milvus.get_user_partition_name(document.owner_id)
        try:
            milvus.delete_by_document_chunk(
                document_id=document_id,
                chunk_index=deleted_index,
                partition_name=partition_name,
            )
            vector_deleted = True
        except Exception as exc:
            logger.warning(f"Failed to delete chunk vector: {exc}")

    return ChunkDeleteResponse(
        document_id=document_id,
        deleted_chunk_id=chunk_id,
        deleted_chunk_index=deleted_index,
        vector_deleted=vector_deleted,
    )


@router.post("/{document_id}/chunks/reembed", response_model=ChunkReembedResponse)
def reembed_document_chunks(
    document_id: int,
    payload: ChunkReembedRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChunkReembedResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    if document.status != "indexed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document not indexed")

    from app.services.embedding_service import EmbeddingService
    from app.services.milvus_service import MilvusService

    milvus = MilvusService()
    partition_name = milvus.get_user_partition_name(document.owner_id)
    milvus.create_partition(partition_name)

    q = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id)
    if payload.chunk_ids:
        q = q.filter(DocumentChunk.id.in_(payload.chunk_ids))
    chunks = q.order_by(DocumentChunk.chunk_index.asc()).all()
    if not chunks:
        return ChunkReembedResponse(document_id=document_id, reembedded_chunks=0)

    if payload.chunk_ids:
        # targeted reembed: delete only specified chunk vectors
        for c in chunks:
            milvus.delete_by_document_chunk(document_id=document_id, chunk_index=c.chunk_index, partition_name=partition_name)
    else:
        # full rebuild: delete all doc vectors
        milvus.delete_by_document_id(document_id=document_id, partition_name=partition_name)

    embedder = EmbeddingService()
    texts = [c.content for c in chunks]
    embeddings = embedder.embed_texts(texts)
    milvus.insert(
        document_id=document_id,
        chunk_indices=[c.chunk_index for c in chunks],
        embeddings=embeddings,
        partition_name=partition_name,
    )

    return ChunkReembedResponse(document_id=document_id, reembedded_chunks=len(chunks))


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Delete a document (with permission check)

    Args:
        document_id: Document ID to delete
        user: Current user
        db: Database session

    Returns:
        Success message
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Permission check: users can delete their own documents, admins can delete any
    if document.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete this document")

    # Delete from Milvus if indexed
    if document.status == "indexed":
        try:
            from app.services.milvus_service import MilvusService

            milvus = MilvusService()
            partition_name = milvus.get_user_partition_name(document.owner_id) if document.owner_id else None
            milvus.delete_by_document_id(document_id, partition_name=partition_name)
            logger.info(f"Deleted vectors for document {document_id} from Milvus partition {partition_name}")
        except Exception as e:
            logger.warning(f"Failed to delete vectors from Milvus: {e}")

    # Delete files from MinIO
    try:
        minio = MinioService()
        if document.minio_object:
            minio.delete_object(document.minio_object)
        if document.markdown_path:
            minio.delete_object(document.markdown_path)
        logger.info(f"Deleted MinIO objects for document {document_id}")
    except Exception as e:
        logger.warning(f"Failed to delete MinIO objects: {e}")

    # Delete chunks (cascade handled by SQLAlchemy relationship)
    from app.models.document_chunk import DocumentChunk

    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete(synchronize_session=False)

    # Delete review actions to avoid FK constraint failures
    try:
        from app.models.review_action import ReviewAction

        db.query(ReviewAction).filter(ReviewAction.document_id == document_id).delete(synchronize_session=False)
    except Exception as e:
        logger.warning(f"Failed to delete review actions for document {document_id}: {e}")

    # Delete document record
    db.delete(document)
    db.commit()

    return {"message": f"Document {document_id} deleted successfully"}


@router.post("/batch-delete", response_model=BatchDeleteResponse)
def batch_delete_documents(
    payload: BatchDeleteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BatchDeleteResponse:
    """
    Batch delete multiple documents

    Args:
        payload: List of document IDs to delete
        user: Current user
        db: Database session

    Returns:
        BatchDeleteResponse with count and failed IDs
    """
    if not payload.document_ids:
        return BatchDeleteResponse(deleted_count=0, failed_ids=[], message="No documents specified")

    deleted_count = 0
    failed_ids: list[int] = []

    for doc_id in payload.document_ids:
        try:
            document = db.get(Document, doc_id)
            if document is None:
                failed_ids.append(doc_id)
                continue

            # Permission check
            if document.owner_id != user.id and user.role != "admin":
                failed_ids.append(doc_id)
                continue

            # Delete from Milvus if indexed
            if document.status == "indexed":
                try:
                    from app.services.milvus_service import MilvusService

                    milvus = MilvusService()
                    partition_name = milvus.get_user_partition_name(document.owner_id) if document.owner_id else None
                    milvus.delete_by_document_id(doc_id, partition_name=partition_name)
                except Exception as e:
                    logger.warning(f"Failed to delete vectors for document {doc_id}: {e}")

            # Delete files from MinIO
            try:
                minio = MinioService()
                if document.minio_object:
                    minio.delete_object(document.minio_object)
                if document.markdown_path:
                    minio.delete_object(document.markdown_path)
            except Exception as e:
                logger.warning(f"Failed to delete MinIO objects for document {doc_id}: {e}")

            # Delete chunks
            from app.models.document_chunk import DocumentChunk

            db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete(synchronize_session=False)

            # Delete review actions (FK)
            try:
                from app.models.review_action import ReviewAction

                db.query(ReviewAction).filter(ReviewAction.document_id == doc_id).delete(synchronize_session=False)
            except Exception as e:
                logger.warning(f"Failed to delete review actions for document {doc_id}: {e}")

            # Delete document record
            db.delete(document)
            deleted_count += 1

        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            failed_ids.append(doc_id)

    db.commit()

    message = f"Successfully deleted {deleted_count} document(s)"
    if failed_ids:
        message += f", failed to delete {len(failed_ids)} document(s)"

    return BatchDeleteResponse(deleted_count=deleted_count, failed_ids=failed_ids, message=message)
