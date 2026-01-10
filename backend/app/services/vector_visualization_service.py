"""
Vector visualization service

Provides dimensionality reduction for vector visualization.
"""

import logging
from typing import TYPE_CHECKING

import numpy as np
from pymilvus import Collection

from app.services.milvus_service import MilvusService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class VectorVisualizationService:
    """
    Service for vector visualization and dimensionality reduction
    """

    def __init__(self) -> None:
        self.milvus = MilvusService()

    def get_vectors_for_visualization(
        self,
        db: "Session",
        limit: int = 500,
        user_id: int | None = None,
        document_id: int | None = None,
    ) -> tuple[list[np.ndarray], list[dict]]:
        """
        Retrieve vectors from Milvus for visualization

        Args:
            db: Database session
            limit: Maximum number of vectors to retrieve
            user_id: Filter by user ID (for multi-tenant)
            document_id: Filter by specific document

        Returns:
            Tuple of (vectors list, metadata list)
        """
        self.milvus.ensure_collection()
        collection = Collection(self.milvus.collection_name)

        # Determine partition to search
        partition_names = None
        if user_id:
            partition_names = [self.milvus.get_user_partition_name(user_id)]

        # Query to get vectors
        # Use a simple query vector to get results
        from app.services.embedding_service import EmbeddingService

        embedder = EmbeddingService()
        query_text = "测试查询获取向量"
        query_embedding = embedder.embed_text(query_text)

        # Increase limit to get more diverse samples
        search_limit = limit * 5

        search_params = {
            "metric_type": "IP",
            "params": {"nprobe": 10}
        }

        hits = collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=search_limit,
            partition_names=partition_names,
            output_fields=["document_id", "chunk_index"],
        )

        vectors = []
        metadata = []
        seen = set()

        for hit in hits[0]:
            if len(vectors) >= limit:
                break

            doc_id = hit.entity.get("document_id")
            chunk_idx = hit.entity.get("chunk_index")

            # Filter by document_id if specified
            if document_id and doc_id != document_id:
                continue

            key = (doc_id, chunk_idx)
            if key in seen:
                continue
            seen.add(key)

            # Get actual vector data
            # We need to query by id to get the vector
            expr = f"document_id == {doc_id} and chunk_index == {chunk_idx}"
            results = collection.query(
                expr=expr,
                output_fields=["document_id", "chunk_index", "embedding"],
                partition_names=partition_names,
                limit=1,
            )

            for result in results:
                vector = result.get("embedding")
                if vector:
                    vectors.append(np.array(vector, dtype=np.float32))
                    metadata.append({
                        "document_id": result.get("document_id"),
                        "chunk_index": result.get("chunk_index"),
                        "score": float(hit.score),
                    })
                    break

        return vectors, metadata

    def reduce_dimensionality_pca(
        self,
        vectors: list[np.ndarray],
        n_components: int = 2,
    ) -> list[list[float]]:
        """
        Reduce dimensionality using PCA (Principal Component Analysis)

        Args:
            vectors: List of high-dimensional vectors
            n_components: Number of components (2 for 2D, 3 for 3D)

        Returns:
            List of reduced vectors
        """
        if not vectors:
            return []

        try:
            from sklearn.decomposition import PCA

            # Convert to numpy array
            X = np.array(vectors)

            # Perform PCA
            pca = PCA(n_components=n_components)
            X_reduced = pca.fit_transform(X)

            # Convert back to list
            return X_reduced.tolist()

        except ImportError:
            logger.warning("scikit-learn not installed, using simple random projection")
            return self._simple_random_projection(vectors, n_components)

    def reduce_dimensionality_tsne(
        self,
        vectors: list[np.ndarray],
        n_components: int = 2,
        perplexity: int = 30,
    ) -> list[list[float]]:
        """
        Reduce dimensionality using t-SNE (t-Distributed Stochastic Neighbor Embedding)

        Note: t-SNE is computationally expensive, use PCA for large datasets

        Args:
            vectors: List of high-dimensional vectors
            n_components: Number of components (2 for 2D, 3 for 3D)
            perplexity: t-SNE perplexity parameter

        Returns:
            List of reduced vectors
        """
        if not vectors:
            return []

        try:
            from sklearn.manifold import TSNE

            X = np.array(vectors)

            # Perform t-SNE
            tsne = TSNE(
                n_components=n_components,
                perplexity=perplexity,
                random_state=42,
                n_iter=1000,
            )
            X_reduced = tsne.fit_transform(X)

            return X_reduced.tolist()

        except ImportError:
            logger.warning("scikit-learn not installed, falling back to PCA")
            return self.reduce_dimensionality_pca(vectors, n_components)

    def _simple_random_projection(
        self,
        vectors: list[np.ndarray],
        n_components: int = 2,
    ) -> list[list[float]]:
        """
        Simple random projection for dimensionality reduction (fallback)

        This is a very basic method that just takes the first n_components
        of each vector. Not recommended for production use.
        """
        result = []
        for vector in vectors:
            result.append(vector[:n_components].tolist())
        return result
