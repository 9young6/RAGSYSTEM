"""
libraries.py：文档库管理接口。

每个用户可以创建多个文档库，用于分类管理不同项目/类型的文档。

功能：
- 创建文档库
- 查看我的文档库列表
- 更新文档库信息
- 删除文档库
- 查看库的文档统计
"""
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.document import Document
from app.models.document_library import DocumentLibrary
from app.models.user import User
from app.schemas.libraries import (
    LibraryCreate,
    LibraryListResponse,
    LibraryResponse,
    LibraryUpdate,
)

if TYPE_CHECKING:
    from app.models.user_settings import UserSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("", response_model=LibraryListResponse)
def list_libraries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取当前用户的文档库列表。

    普通用户只能看到自己的库。
    管理员可以看到所有用户的库。
    """
    if current_user.role == "admin":
        # 管理员查看所有库
        libraries = db.query(DocumentLibrary).all()
    else:
        # 普通用户只查看自己的库
        libraries = db.query(DocumentLibrary).filter(DocumentLibrary.owner_id == current_user.id).all()

    # 统计每个库的文档数量
    result = []
    for lib in libraries:
        doc_count = db.query(func.count(Document.id)).filter(Document.library_id == lib.id).scalar()
        lib_response = LibraryResponse(
            id=lib.id,
            owner_id=lib.owner_id,
            name=lib.name,
            description=lib.description,
            embedding_strategy=lib.embedding_strategy,
            chunking_strategy=lib.chunking_strategy,
            created_at=lib.created_at,
            document_count=doc_count or 0,
        )
        result.append(lib_response)

    return LibraryListResponse(libraries=result, total=len(result))


@router.get("/{library_id}", response_model=LibraryResponse)
def get_library(
    library_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个文档库的详细信息"""
    library = db.query(DocumentLibrary).filter(DocumentLibrary.id == library_id).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    # 权限检查
    if library.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # 统计文档数量
    doc_count = db.query(func.count(Document.id)).filter(Document.library_id == library.id).scalar()

    return LibraryResponse(
        id=library.id,
        owner_id=library.owner_id,
        name=library.name,
        description=library.description,
        embedding_strategy=library.embedding_strategy,
        chunking_strategy=library.chunking_strategy,
        created_at=library.created_at,
        document_count=doc_count or 0,
    )


@router.post("", response_model=LibraryResponse, status_code=201)
def create_library(
    payload: LibraryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新文档库"""
    # 检查同名库
    existing = db.query(DocumentLibrary).filter(
        DocumentLibrary.owner_id == current_user.id,
        DocumentLibrary.name == payload.name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Library with this name already exists")

    # 创建新库
    library = DocumentLibrary(
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
        embedding_strategy=payload.embedding_strategy,
        chunking_strategy=payload.chunking_strategy,
    )
    db.add(library)
    db.commit()
    db.refresh(library)

    logger.info(f"User {current_user.id} created library {library.id}: {library.name}")

    return LibraryResponse(
        id=library.id,
        owner_id=library.owner_id,
        name=library.name,
        description=library.description,
        embedding_strategy=library.embedding_strategy,
        chunking_strategy=library.chunking_strategy,
        created_at=library.created_at,
        document_count=0,
    )


@router.put("/{library_id}", response_model=LibraryResponse)
def update_library(
    library_id: int,
    payload: LibraryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新文档库信息"""
    library = db.query(DocumentLibrary).filter(DocumentLibrary.id == library_id).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    # 权限检查
    if library.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # 更新字段
    if payload.name is not None:
        library.name = payload.name
    if payload.description is not None:
        library.description = payload.description
    if payload.embedding_strategy is not None:
        library.embedding_strategy = payload.embedding_strategy
    if payload.chunking_strategy is not None:
        library.chunking_strategy = payload.chunking_strategy

    db.commit()
    db.refresh(library)

    # 统计文档数量
    doc_count = db.query(func.count(Document.id)).filter(Document.library_id == library.id).scalar()

    logger.info(f"User {current_user.id} updated library {library_id}")

    return LibraryResponse(
        id=library.id,
        owner_id=library.owner_id,
        name=library.name,
        description=library.description,
        embedding_strategy=library.embedding_strategy,
        chunking_strategy=library.chunking_strategy,
        created_at=library.created_at,
        document_count=doc_count or 0,
    )


@router.delete("/{library_id}", status_code=204)
def delete_library(
    library_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除文档库。

    注意：删除库会同时删除库中的所有文档（级联删除）。
    """
    library = db.query(DocumentLibrary).filter(DocumentLibrary.id == library_id).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    # 权限检查
    if library.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # 检查是否有文档
    doc_count = db.query(func.count(Document.id)).filter(Document.library_id == library_id).scalar()
    if doc_count and doc_count > 0:
        logger.warning(f"User {current_user.id} deleting library {library_id} with {doc_count} documents")

    # 删除库（级联删除文档）
    db.delete(library)
    db.commit()

    logger.info(f"User {current_user.id} deleted library {library_id}")
