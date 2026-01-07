from __future__ import annotations

"""
rag_service.py：RAG 核心服务层（检索、重排、生成、索引）。

职责：
- `index_document()`：
  1) 从 Postgres 读取 chunks（若不存在则从 Markdown/原文生成并写回）
  2) 对 `included=true` 的 chunks 生成 embedding
  3) 写入 Milvus（按 user partition 隔离，字段：document_id + chunk_index + embedding）
  4) 更新 Document.status/indexed_at

- `query()`：
  1) 对 query 生成 embedding
  2) Milvus 检索（默认只搜用户分区；管理员可跨分区）
  3) 可选 rerank（Xinference /v1/rerank）
  4) 组装上下文 + 调用 LLM 生成回答（Ollama 或 OpenAI-compatible：vLLM/Xinference）

与“审核/可编辑”的关系：
- chunks 永远存 Postgres（便于管理员审核时编辑/删改/勾选 included）
- Milvus 只存向量；当 chunk 内容被修改或 included 变化后，需要重建向量（见 chunks/reembed 或管理员 reindex）
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.query import QueryResponse, QuerySource
from app.services.document_parser import DocumentParser
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService, LLMUnavailableError
from app.services.milvus_service import MilvusService
from app.services.minio_service import MinioService
from app.services.rerank_service import RerankService
from app.services.text_splitter import TextSplitter
from app.utils.prompt_templates import RAG_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(self) -> None:
        self.minio = MinioService()
        self.parser = DocumentParser()
        self.splitter = TextSplitter()
        self.embedder = EmbeddingService()
        self.milvus = MilvusService()
        self.llm = LLMService()

    def index_document(self, db: Session, document_id: int, user_id: int | None = None) -> int:
        """
        Index a document by extracting text, chunking, embedding, and storing in Milvus

        Args:
            db: Database session
            document_id: Document ID to index
            user_id: Optional user ID for multi-tenant partition isolation

        Returns:
            Number of chunks created
        """
        document = db.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        # Prefer pre-generated chunks (generated after Markdown conversion) so admin can select partial chunks for indexing.
        all_chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )
        included_chunks = [c for c in all_chunks if getattr(c, "included", True)]
        if not all_chunks:
            # Fallback: generate chunks from Markdown (or original content) and persist.
            if document.markdown_path and document.markdown_status == "markdown_ready":
                logger.info(f"Using Markdown content for chunk generation: document={document_id}")
                content_bytes = self.minio.download_bytes(document.markdown_path)
                text = content_bytes.decode("utf-8", errors="replace")
            else:
                logger.info(f"Parsing original file for chunk generation: document={document_id}")
                content_bytes = self.minio.download_bytes(document.minio_object)
                text = self.parser.parse_text(content_bytes, document.content_type, document.filename)

            chunks_text = self.splitter.split(text)
            db.add_all(
                [DocumentChunk(document_id=document_id, chunk_index=i, content=chunk, included=True) for i, chunk in enumerate(chunks_text)]
            )
            db.commit()
            all_chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
                .all()
            )
            included_chunks = [c for c in all_chunks if getattr(c, "included", True)]

        # Delete from Milvus (use partition if user_id provided)
        partition_name = self.milvus.get_user_partition_name(user_id) if user_id else None
        try:
            self.milvus.delete_by_document_id(document_id, partition_name=partition_name)
        except Exception as e:
            logger.warning(f"Failed to delete existing vectors for document {document_id}: {e}")

        if not included_chunks:
            logger.warning(f"No included chunks for document {document_id}; skip vector insert")
            document.status = "indexed"
            document.indexed_at = datetime.now(timezone.utc)
            db.commit()
            return 0

        chunks = [c.content for c in included_chunks]
        chunk_indices = [int(c.chunk_index) for c in included_chunks]

        # Generate embeddings and insert into Milvus
        embeddings = self.embedder.embed_texts(chunks) if chunks else []
        if embeddings:
            partition_name = self.milvus.get_user_partition_name(user_id) if user_id else None
            self.milvus.insert(
                document_id=document_id,
                chunk_indices=chunk_indices,
                embeddings=embeddings,
                partition_name=partition_name,
            )
            logger.info(f"Indexed {len(chunks)} chunks for document {document_id} in partition {partition_name or 'default'}")

        document.status = "indexed"
        document.indexed_at = datetime.now(timezone.utc)
        db.commit()
        return len(chunks)

    def query(
        self,
        db: Session,
        query_text: str,
        top_k: int,
        llm_provider: str,
        model: str,
        temperature: float,
        user_id: int | None = None,
        partition_names: list[str] | None = None,
        rerank: bool | None = None,
        rerank_provider: str | None = None,
        rerank_model: str | None = None,
    ) -> QueryResponse:
        """
        Query the knowledge base using RAG

        Args:
            db: Database session
            query_text: User query
            top_k: Number of top results to retrieve
            model: LLM model name
            temperature: LLM temperature
            user_id: Optional user ID for multi-tenant filtering (will be converted to partition name)
            partition_names: Optional explicit list of partition names to search (overrides user_id)

        Returns:
            QueryResponse with answer and sources
        """
        query_embedding = self.embedder.embed_text(query_text)

        # Determine which partitions to search
        search_partitions = partition_names
        if search_partitions is None and user_id is not None:
            search_partitions = [self.milvus.get_user_partition_name(user_id)]
            logger.info(f"Searching in user partition: {search_partitions}")

        hits = self.milvus.search(query_embedding=query_embedding, top_k=top_k, partition_names=search_partitions)
        if not hits:
            return QueryResponse(query=query_text, answer="未检索到相关内容。", sources=[], confidence=0.0)

        scores: list[float] = []
        candidates: list[tuple[QuerySource, str, float]] = []
        for hit in hits:
            doc_id = hit["document_id"]
            chunk_index = hit["chunk_index"]
            score = float(hit["score"])
            scores.append(score)

            document = db.get(Document, doc_id)
            chunk = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == doc_id, DocumentChunk.chunk_index == chunk_index)
                .one_or_none()
            )
            if document is None or chunk is None:
                continue

            candidates.append(
                (
                    QuerySource(
                        document_id=doc_id,
                        document_name=document.filename,
                        chunk_index=chunk_index,
                        relevance=score,
                    ),
                    chunk.content,
                    score,
                )
            )

        # Optional rerank (after retrieval, before LLM)
        try:
            if rerank and (rerank_provider or "").lower() == "xinference" and rerank_model and candidates:
                reranker = RerankService()
                if reranker.is_configured():
                    texts = [c[1] for c in candidates]
                    pairs = reranker.rerank_xinference(query=query_text, documents=texts, model=rerank_model)
                    order = [idx for idx, _ in pairs if 0 <= idx < len(candidates)]
                    if order:
                        candidates = [candidates[i] for i in order]
        except Exception as exc:
            logger.warning(f"Rerank skipped due to error: {exc}")

        context_parts: list[str] = []
        sources: list[QuerySource] = []
        for src, content, _score in candidates[:top_k]:
            context_parts.append(f"[{src.document_id}:{src.chunk_index}] {content}")
            sources.append(src)

        context = "\n\n".join(context_parts)
        prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=query_text)

        try:
            answer = self.llm.generate(prompt, provider=llm_provider, model=model, temperature=temperature).strip()
        except LLMUnavailableError as exc:
            provider_norm = (llm_provider or "").lower()
            if provider_norm == "ollama":
                hint = (
                    f"LLM 模型不可用：{exc}\n"
                    f"请先执行：ollama pull {model}\n"
                    "或把请求中的 model 改为 `ollama list` 里已安装的模型。\n\n"
                    "相关片段：\n"
                )
            else:
                hint = (
                    f"LLM 不可用（{provider_norm}）：{exc}\n"
                    "请在“设置”页检查推理后端配置并执行连通性测试。\n\n"
                    "相关片段：\n"
                )
            answer = hint + (context_parts[0][:400] if context_parts else "（无可用片段）")
        except Exception:
            answer = (context_parts[0][:400] if context_parts else "") or "检索成功，但生成失败。"

        confidence = 0.0
        if scores:
            # IP/cosine similarity roughly in [-1, 1]; map to [0, 1]
            confidence = max(0.0, min(1.0, (max(scores) + 1.0) / 2.0))

        return QueryResponse(query=query_text, answer=answer, sources=sources, confidence=confidence)
