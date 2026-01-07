from __future__ import annotations

"""
milvus_service.py：Milvus 向量库封装（collection/partition/insert/search/delete）。

设计要点：
- 使用单个 collection（`MILVUS_COLLECTION`），通过 partition 做多租户隔离（`user_{id}`）。
- 向量字段：`embedding`；同时存储 `document_id` + `chunk_index` 以便回表读取 chunk 文本。
- 删除策略：按 document_id 删除，或按 (document_id, chunk_index) 删除单个 chunk。

注意：
- `EMBEDDING_DIMENSION` 一旦用于创建 collection 后，不建议随意修改（需要重建 collection 并全量 reindex）。
"""

import logging

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, Partition, connections, utility

from app.config import settings

logger = logging.getLogger(__name__)


class MilvusService:
    def __init__(self) -> None:
        self.collection_name = settings.MILVUS_COLLECTION
        self.dimension = int(settings.EMBEDDING_DIMENSION)

    def connect(self) -> None:
        connections.connect(alias="default", host=settings.MILVUS_HOST, port=str(settings.MILVUS_PORT))

    def ensure_collection(self) -> None:
        self.connect()
        if not utility.has_collection(self.collection_name):
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="document_id", dtype=DataType.INT64, is_primary=False),
                FieldSchema(name="chunk_index", dtype=DataType.INT64, is_primary=False),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.dimension),
            ]
            schema = CollectionSchema(fields, description="Knowledge base document chunks")
            collection = Collection(self.collection_name, schema)
            collection.create_index(
                field_name="embedding",
                index_params={"index_type": "IVF_FLAT", "metric_type": "IP", "params": {"nlist": 1024}},
            )
        collection = Collection(self.collection_name)
        collection.load()

    def create_partition(self, partition_name: str) -> None:
        """
        Create a partition for a user if it doesn't exist

        Args:
            partition_name: Partition name (e.g., 'user_1', 'user_2')
        """
        self.ensure_collection()
        collection = Collection(self.collection_name)

        if not collection.has_partition(partition_name):
            collection.create_partition(partition_name)
            logger.info(f"Created partition: {partition_name}")
        else:
            logger.debug(f"Partition already exists: {partition_name}")

    def get_user_partition_name(self, user_id: int) -> str:
        """
        Generate partition name for a user

        Args:
            user_id: User ID

        Returns:
            str: Partition name like 'user_1'
        """
        return f"user_{user_id}"

    def list_partitions(self) -> list[str]:
        """List all partitions in the collection"""
        self.ensure_collection()
        collection = Collection(self.collection_name)
        return [p.name for p in collection.partitions]

    def insert(self, document_id: int, chunk_indices: list[int], embeddings: list[list[float]], partition_name: str | None = None) -> None:
        """
        Insert embeddings into collection

        Args:
            document_id: Document ID
            chunk_indices: List of chunk indices
            embeddings: List of embedding vectors
            partition_name: Optional partition name for multi-tenant isolation
        """
        if len(chunk_indices) != len(embeddings):
            raise ValueError("chunk_indices and embeddings length mismatch")

        self.ensure_collection()
        collection = Collection(self.collection_name)

        # Create partition if specified and doesn't exist
        if partition_name:
            if not collection.has_partition(partition_name):
                collection.create_partition(partition_name)
                logger.info(f"Created partition during insert: {partition_name}")

        doc_ids = [int(document_id) for _ in chunk_indices]

        if partition_name:
            partition = Partition(collection, partition_name)
            partition.insert([doc_ids, [int(i) for i in chunk_indices], embeddings])
            logger.info(f"Inserted {len(embeddings)} vectors into partition {partition_name}")
        else:
            collection.insert([doc_ids, [int(i) for i in chunk_indices], embeddings])
            logger.info(f"Inserted {len(embeddings)} vectors into default partition")

        collection.flush()

    def search(self, query_embedding: list[float], top_k: int, partition_names: list[str] | None = None) -> list[dict]:
        """
        Search for similar embeddings

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            partition_names: Optional list of partition names to search in (for multi-tenant isolation)

        Returns:
            List of search results with document_id, chunk_index, and score
        """
        self.ensure_collection()
        collection = Collection(self.collection_name)

        search_params = {
            "data": [query_embedding],
            "anns_field": "embedding",
            "param": {"metric_type": "IP", "params": {"nprobe": 10}},
            "limit": top_k,
            "output_fields": ["document_id", "chunk_index"],
        }

        # Add partition filtering if specified (ignore non-existing partitions)
        if partition_names:
            try:
                existing = {p.name for p in collection.partitions}
            except Exception:
                existing = set()
            filtered = [p for p in partition_names if p in existing]
            if not filtered:
                logger.info("No existing partitions matched %s; returning empty hits", partition_names)
                return []
            search_params["partition_names"] = filtered
            logger.debug(f"Searching in partitions: {filtered}")

        try:
            results = collection.search(**search_params)
        except Exception as exc:
            # Common case: partition not found / not loaded.
            logger.warning("Milvus search failed: %s", exc)
            return []
        hits = results[0] if results else []
        items: list[dict] = []
        for hit in hits:
            entity = hit.entity
            items.append(
                {
                    "document_id": int(entity.get("document_id")),
                    "chunk_index": int(entity.get("chunk_index")),
                    "score": float(hit.score),
                }
            )
        return items

    def delete_by_document_id(self, document_id: int, partition_name: str | None = None) -> None:
        """
        Delete all vectors for a document

        Args:
            document_id: Document ID to delete
            partition_name: Optional partition name
        """
        self.ensure_collection()
        collection = Collection(self.collection_name)

        expr = f"document_id == {document_id}"

        if partition_name:
            partition = Partition(collection, partition_name)
            partition.delete(expr)
            logger.info(f"Deleted vectors for document {document_id} from partition {partition_name}")
        else:
            collection.delete(expr)
            logger.info(f"Deleted vectors for document {document_id}")

        collection.flush()

    def delete_by_document_chunk(
        self,
        document_id: int,
        chunk_index: int,
        partition_name: str | None = None,
    ) -> None:
        """
        Delete vectors for a single chunk (document_id + chunk_index)

        Args:
            document_id: Document ID
            chunk_index: Chunk index within the document
            partition_name: Optional partition name
        """
        self.ensure_collection()
        collection = Collection(self.collection_name)

        expr = f"document_id == {int(document_id)} && chunk_index == {int(chunk_index)}"

        if partition_name:
            partition = Partition(collection, partition_name)
            partition.delete(expr)
            logger.info(f"Deleted vectors for document {document_id} chunk {chunk_index} from partition {partition_name}")
        else:
            collection.delete(expr)
            logger.info(f"Deleted vectors for document {document_id} chunk {chunk_index}")

        collection.flush()
