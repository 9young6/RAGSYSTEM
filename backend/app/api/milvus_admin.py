from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pymilvus import Collection
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.database import get_db
from app.models.user import User
from app.services.milvus_service import MilvusService
from app.services.vector_visualization_service import VectorVisualizationService
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

router = APIRouter(prefix="/milvus", tags=["milvus-admin"])


@router.get("/stats")
def get_milvus_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get Milvus collection statistics

    Returns:
        - collection info (name, schema, indexes)
        - partitions list
        - vector count per partition
        - documents/chunks per partition
    """
    milvus = MilvusService()
    milvus.ensure_collection()

    collection = Collection(milvus.collection_name)

    # Get basic collection info
    stats = {
        "collection": {
            "name": collection.name,
            "description": collection.description,
            "num_entities": collection.num_entities,
        },
        "partitions": [],
    }

    # Get partition information
    partitions = collection.partitions
    for partition in partitions:
        partition_name = partition.name

        # Skip _default partition
        if partition_name == "_default":
            continue

        # Parse user_id from partition name (format: user_{id})
        user_id = None
        if partition_name.startswith("user_"):
            try:
                user_id = int(partition_name.split("_")[1])
            except (IndexError, ValueError):
                pass

        # Get partition statistics
        partition_stats = {
            "name": partition_name,
            "user_id": user_id,
            "num_entities": partition.num_entities,
            "loaded": True,  # pymilvus 2.4.0 doesn't have is_loaded attribute
        }

        # Get document/chunk count from database for this user
        if user_id:
            doc_count = db.query(Document).filter(Document.owner_id == user_id).count()
            chunk_count = db.query(DocumentChunk).join(Document).filter(
                Document.owner_id == user_id
            ).count()

            partition_stats["document_count"] = doc_count
            partition_stats["chunk_count"] = chunk_count

        stats["partitions"].append(partition_stats)

    # Get overall statistics
    stats["summary"] = {
        "total_partitions": len(partitions) - 1,  # Exclude _default
        "total_vectors": collection.num_entities,
        "loaded": True,  # pymilvus 2.4.0 doesn't have is_loaded attribute
    }

    # Get index information
    indexes = collection.indexes
    stats["indexes"] = [
        {
            "field": idx.field_name,
            "type": idx.index_type,
            "metric": idx.metric_type,
            "params": idx.params,
        }
        for idx in indexes
    ]

    return stats


@router.get("/partitions")
def list_partitions(
    current_user: User = Depends(get_current_user),
):
    """
    List all partitions in the Milvus collection

    Regular users can only see their own partition.
    Admins can see all partitions.
    """
    milvus = MilvusService()
    milvus.ensure_collection()

    collection = Collection(milvus.collection_name)
    partitions = collection.partitions

    result = []
    for partition in partitions:
        partition_name = partition.name

        if partition_name == "_default":
            continue

        user_id = None
        if partition_name.startswith("user_"):
            try:
                user_id = int(partition_name.split("_")[1])
            except (IndexError, ValueError):
                pass

        # Non-admin users can only see their own partition
        if current_user.role != "admin" and user_id != current_user.id:
            continue

        result.append({
            "name": partition_name,
            "user_id": user_id,
            "num_entities": partition.num_entities,
            "loaded": True,  # pymilvus 2.4.0 doesn't have is_loaded attribute
        })

    return {"partitions": result}


@router.post("/partitions/{partition_name}")
def create_partition(
    partition_name: str,
    current_user: User = Depends(require_admin),
):
    """
    Create a new partition in the Milvus collection

    Only admins can create partitions.
    """
    milvus = MilvusService()
    milvus.ensure_collection()

    try:
        milvus.create_partition(partition_name)
        return {"message": f"Partition '{partition_name}' created successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create partition: {str(e)}",
        )


@router.delete("/partitions/{partition_name}")
def delete_partition(
    partition_name: str,
    current_user: User = Depends(require_admin),
):
    """
    Delete a partition from the Milvus collection

    Only admins can delete partitions.
    """
    milvus = MilvusService()
    milvus.ensure_collection()

    if partition_name == "_default":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete _default partition",
        )

    try:
        collection = Collection(milvus.collection_name)
        collection.drop_partition(partition_name)
        return {"message": f"Partition '{partition_name}' deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete partition: {str(e)}",
        )


@router.get("/vectors/sample")
def get_sample_vectors(
    limit: int = 100,
    partition_name: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get sample vectors from the collection for visualization

    Parameters:
    - limit: number of vectors to retrieve (default 100, max 1000)
    - partition_name: filter by partition name (optional)
    - For regular users, only their own partition is accessible

    Returns:
        - vectors with metadata (document_id, chunk_index, content snippet)
    """
    if limit > 1000:
        limit = 1000

    milvus = MilvusService()
    milvus.ensure_collection()

    # Determine which partitions to search
    search_partitions = None
    if partition_name:
        if current_user.role != "admin":
            # Non-admin can only access their own partition
            user_partition = milvus.get_user_partition_name(current_user.id)
            if partition_name != user_partition:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only access your own partition",
                )
        search_partitions = [partition_name]
    else:
        if current_user.role != "admin":
            search_partitions = [milvus.get_user_partition_name(current_user.id)]

    # Generate a random query vector to retrieve sample vectors
    import random
    from app.services.embedding_service import EmbeddingService

    embedder = EmbeddingService()

    # Use random queries to get diverse samples
    sample_queries = [
        "测试",
        "文档",
        "数据",
        "系统",
        "管理",
    ]

    results = []
    seen = set()

    for query_text in sample_queries:
        if len(results) >= limit:
            break

        query_embedding = embedder.embed_text(query_text)

        hits = Collection(milvus.collection_name).search(
            data=[query_embedding],
            anns_field="embedding",
            partition_names=search_partitions,
            limit=limit,
        )

        for hit in hits[0]:  # First (and only) query
            doc_id = hit.entity.get("document_id")
            chunk_index = hit.entity.get("chunk_index")

            # Avoid duplicates
            key = (doc_id, chunk_index)
            if key in seen:
                continue
            seen.add(key)

            # Get chunk content from database
            chunk = (
                db.query(DocumentChunk)
                .filter(
                    DocumentChunk.document_id == doc_id,
                    DocumentChunk.chunk_index == chunk_index,
                )
                .first()
            )

            results.append(
                {
                    "document_id": doc_id,
                    "chunk_index": chunk_index,
                    "content": chunk.content[:200] if chunk else "",
                    "score": float(hit.score),
                }
            )

            if len(results) >= limit:
                break

    return {
        "total": len(results),
        "limit": limit,
        "vectors": results[:limit],
    }


@router.get("/visualization/embeddings")
def get_embedding_visualization(
    limit: int = 500,
    method: str = "pca",
    user_id: int | None = None,
    dimensions: int = 3,  # Support 2D or 3D visualization
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get 2D/3D coordinates for vector visualization

    Parameters:
    - limit: number of vectors to visualize (default 500, max 1000)
    - method: dimensionality reduction method ('pca' or 'tsne')
    - user_id: filter by user (admin only, others see only their own)
    - dimensions: 2 for 2D plot, 3 for 3D plot (default 3)

    Returns:
        - vectors_2d: 2D/3D coordinates for scatter plot
        - metadata: document_id, chunk_index for each point
        - method_used: actual method used
    """
    if limit > 1000:
        limit = 1000

    # Non-admin users can only visualize their own data
    if current_user.role != "admin":
        user_id = current_user.id

    # Get vectors and metadata
    viz_service = VectorVisualizationService()
    vectors, metadata = viz_service.get_vectors_for_visualization(
        db=db,
        limit=limit,
        user_id=user_id,
    )

    if not vectors:
        return {
            "vectors_2d": [],
            "metadata": [],
            "method_used": method,
            "total": 0,
        }

    # Reduce dimensionality to 3D
    if method == "tsne":
        coords = viz_service.reduce_dimensionality_tsne(vectors, n_components=dimensions)
    else:
        coords = viz_service.reduce_dimensionality_pca(vectors, n_components=dimensions)

    # Combine coordinates with metadata
    if dimensions == 3:
        result = {
            "vectors_2d": [
                {"x": float(coord[0]), "y": float(coord[1]), "z": float(coord[2]), "metadata": meta}
                for coord, meta in zip(coords, metadata)
            ],
            "method_used": method,
            "total": len(coords),
        }
    else:
        result = {
            "vectors_2d": [
                {"x": float(coord[0]), "y": float(coord[1]), "metadata": meta}
                for coord, meta in zip(coords, metadata)
            ],
            "method_used": method,
            "total": len(coords),
        }

    return result


@router.get("/visualization/stats")
def get_visualization_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get statistics for visualization dashboard

    Returns:
        - Total vectors
        - Vectors per partition
        - Document/chunk counts
        - Embedding dimension
    """
    milvus = MilvusService()
    milvus.ensure_collection()

    collection = Collection(milvus.collection_name)

    # Get overall stats
    stats = {
        "collection_name": collection.name,
        "total_vectors": collection.num_entities,
        "embedding_dimension": milvus.dimension,
        "loaded": True,  # pymilvus 2.4.0 doesn't have is_loaded attribute
        "partitions": [],
    }

    # Get per-partition stats
    for partition in collection.partitions:
        if partition.name == "_default":
            continue

        user_id = None
        if partition.name.startswith("user_"):
            try:
                user_id = int(partition.name.split("_")[1])
            except (IndexError, ValueError):
                pass

        # Non-admin users only see their own partition
        if current_user.role != "admin" and user_id != current_user.id:
            continue

        partition_stats = {
            "name": partition.name,
            "user_id": user_id,
            "num_vectors": partition.num_entities,
        }

        # Add document/chunk counts from database
        if user_id:
            doc_count = db.query(Document).filter(Document.owner_id == user_id).count()
            chunk_count = (
                db.query(DocumentChunk)
                .join(Document)
                .filter(Document.owner_id == user_id)
                .count()
            )

            partition_stats["document_count"] = doc_count
            partition_stats["chunk_count"] = chunk_count

        stats["partitions"].append(partition_stats)

    return stats

