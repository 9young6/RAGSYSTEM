from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.acceptance import AcceptanceRunRequest, AcceptanceRunResponse, AcceptanceSource
from app.services.document_parser import DocumentParser
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService, LLMUnavailableError
from app.services.milvus_service import MilvusService
from app.services.minio_service import MinioService


router = APIRouter(prefix="/acceptance", tags=["acceptance"])


def _extract_title(filename: str) -> str:
    name = (filename or "").strip()
    if not name:
        return "未命名报告"
    return re.sub(r"\.[a-zA-Z0-9]{1,6}$", "", name)


def _parse_passed(markdown: str) -> tuple[bool | None, str | None]:
    if not markdown:
        return None, None
    m = re.search(r"是否合格\s*[:：]?\s*(合格|不合格|需补充材料)", markdown)
    if not m:
        return None, None
    verdict = m.group(1)
    if verdict == "合格":
        return True, verdict
    if verdict == "不合格":
        return False, verdict
    return None, verdict


@router.post("/run", response_model=AcceptanceRunResponse)
def run_acceptance_review(
    payload: AcceptanceRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AcceptanceRunResponse:
    report = db.get(Document, payload.report_document_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report document not found")

    # Report must be owned by the requester (admin can access any)
    if report.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    # Determine knowledge base scope
    scope = (payload.scope or "self").lower()
    partition_names: list[str] | None = None
    if scope == "self":
        partition_names = [f"user_{user.id}"]
    elif scope == "user":
        if user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required for scope=user")
        if not payload.scope_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_user_id required for scope=user")
        partition_names = [f"user_{payload.scope_user_id}"]
    elif scope == "all":
        if user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required for scope=all")
        partition_names = None
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope")

    us = db.query(UserSettings).filter(UserSettings.user_id == user.id).one_or_none()
    llm_provider = (payload.provider or (us.default_llm_provider if us else "ollama") or "ollama") or "ollama"
    llm_model = payload.model or (us.default_llm_model if us else None) or payload.model
    llm_temperature = payload.temperature if payload.temperature is not None else (us.default_temperature if us else 0.2)

    # Load report content (prefer Markdown if ready)
    minio = MinioService()
    if report.markdown_path and report.markdown_status == "markdown_ready":
        report_text = minio.download_bytes(report.markdown_path).decode("utf-8", errors="replace")
    else:
        raw = minio.download_bytes(report.minio_object)
        try:
            report_text = DocumentParser().parse_text(raw, report.content_type, report.filename)
        except Exception:
            report_text = raw.decode("utf-8", errors="replace")

    title = _extract_title(report.filename)
    query_hint = f"{title} 验收 要求 标准 条款"

    embedder = EmbeddingService()
    milvus = MilvusService()
    query_embedding = embedder.embed_text(query_hint)
    hits = milvus.search(query_embedding=query_embedding, top_k=payload.top_k, partition_names=partition_names)

    sources: list[AcceptanceSource] = []
    requirement_lines: list[str] = []
    for hit in hits:
        doc_id = int(hit["document_id"])
        chunk_index = int(hit["chunk_index"])
        score = float(hit["score"])

        doc = db.get(Document, doc_id)
        chunk = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc_id, DocumentChunk.chunk_index == chunk_index)
            .one_or_none()
        )
        if doc is None or chunk is None:
            continue
        if hasattr(chunk, "included") and not chunk.included:
            continue

        sources.append(
            AcceptanceSource(document_id=doc_id, document_name=doc.filename, chunk_index=chunk_index, relevance=score)
        )
        requirement_lines.append(f"[{doc_id}:{chunk_index}] {chunk.content}")

    requirements_block = "\n\n".join(requirement_lines[: payload.top_k]) or "（未检索到相关要求条款）"
    report_excerpt = (report_text or "").strip()
    if len(report_excerpt) > 6000:
        report_excerpt = report_excerpt[:6000] + "\n\n...(省略)..."

    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    scope_desc = "本人知识库" if scope == "self" else (f"指定用户 user_{payload.scope_user_id}" if scope == "user" else "全库")

    prompt = f"""你是企业知识库的验收审查助手。请严格按固定模板输出“验收审查报告”，不要输出模板之外的无关内容。

【报告信息】
- 报告名称：{title}
- 报告文档ID：{report.id}
- 审查时间：{now}
- 审查范围：{scope_desc}
- 使用模型：{llm_provider}/{llm_model}

【依据条款（来自知识库检索的 chunks）】
{requirements_block}

【待审查报告内容（节选）】
{report_excerpt}

输出模板如下（必须保持结构与字段名一致）：

# 验收审查报告

## 基本信息
- 报告名称：
- 报告文档ID：
- 审查时间：
- 审查范围：
- 使用模型：

## 结论
- 是否合格：合格 / 不合格 / 需补充材料
- 结论摘要：

## 发现的问题（如有）
1. 问题描述：
   - 依据条款（引用 chunk，使用 [document_id:chunk_index]）：
   - 报告证据（引用报告原文）：
   - 风险/影响：
   - 建议整改：

## 依据条款（TopN）
- [document_id:chunk_index] ...
"""

    llm = LLMService()
    try:
        md = llm.generate(prompt, provider=llm_provider, model=llm_model, temperature=llm_temperature).strip()
    except LLMUnavailableError as exc:
        md = f"# 验收审查报告\n\n## 结论\n- 是否合格：需补充材料\n- 结论摘要：LLM 不可用：{exc}\n"
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Acceptance review failed: {exc}")

    passed, verdict = _parse_passed(md)
    return AcceptanceRunResponse(
        report_document_id=report.id,
        passed=passed,
        verdict=verdict,
        report_markdown=md,
        sources=sources,
    )
