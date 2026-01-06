from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def convert_to_markdown(self, document_id: int) -> dict:
    """
    异步转换文档为 Markdown

    Args:
        document_id: 文档ID

    Returns:
        dict: {"status": "success", "document_id": int} or {"status": "failed", "error": str}
    """
    from app.database import SessionLocal
    from app.models import Document
    from app.services.chunk_service import ChunkService
    from app.services.minio_service import MinioService

    db = SessionLocal()
    minio_service = MinioService()

    try:
        # 1. 获取文档信息
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document {document_id} not found")

        logger.info(f"Starting MinerU conversion for document {document_id}: {document.filename}")

        # 2. 更新状态为 processing
        document.markdown_status = "processing"
        db.commit()

        # 3. 从 MinIO 下载原始文件
        file_bytes = minio_service.download_bytes(document.minio_object)

        ext = Path(document.filename).suffix.lower()
        direct_md = {".md", ".markdown"}
        direct_text = {".txt", ".json", ".csv", ".xlsx"}

        # 4. 对常见文本/结构化文件，直接生成 Markdown，不依赖 MinerU
        if ext in direct_md | direct_text:
            from app.services.document_parser import DocumentParser

            parser = DocumentParser()
            text = parser.parse_text(file_bytes, document.content_type, document.filename).strip()
            if ext in direct_md:
                md_content = text or "# (Empty Markdown)\n"
            elif ext == ".json":
                md_content = f"# {document.filename}\n\n```json\n{text}\n```\n"
            else:
                md_content = f"# {document.filename}\n\n```text\n{text}\n```\n"

            logger.info(f"Direct markdown generation for {ext}: document={document_id}")
            temp_dir = tempfile.mkdtemp()
        else:
            # 4. 保存到临时文件（MinerU / fallback 需要）
            temp_dir = tempfile.mkdtemp()
            input_path = os.path.join(temp_dir, document.filename)

            with open(input_path, "wb") as f:
                f.write(file_bytes)

            logger.info(f"Saved temporary file: {input_path}")

            # 5. 使用 MinerU 转换
            try:
                from magic_pdf.pipe.UNIPipe import UNIPipe
                from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

                # MinerU 输出目录
                output_dir = os.path.join(temp_dir, "output")
                os.makedirs(output_dir, exist_ok=True)

                # 创建 MinerU pipeline
                reader = DiskReaderWriter(temp_dir)
                pipe = UNIPipe(input_path, reader, output_dir)

                # 执行转换
                pipe.pipe_classify()
                pipe.pipe_parse()
                md_content = pipe.pipe_mk_markdown(output_dir=output_dir, drop_mode="none")

                logger.info(f"MinerU conversion completed for document {document_id}")

            except Exception as e:
                # MinerU 不可用时的降级方案：使用简单的文本提取
                logger.warning(f"MinerU conversion failed, using fallback: {e}")

                if document.filename.lower().endswith(".pdf"):
                    import pdfplumber

                    with pdfplumber.open(input_path) as pdf:
                        md_content = "\n\n".join(
                            [f"## Page {i+1}\n\n{page.extract_text() or ''}" for i, page in enumerate(pdf.pages)]
                        )
                elif document.filename.lower().endswith(".docx"):
                    from docx import Document as DocxDocument

                    doc = DocxDocument(input_path)
                    md_content = "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                else:
                    raise ValueError(f"Unsupported file type: {document.filename}")

        # 6. 上传 Markdown 到 MinIO
        markdown_path = f"user_{document.owner_id}/markdown/{document_id}.md"
        minio_service.upload_bytes(
            markdown_path,
            md_content.encode("utf-8"),
            content_type="text/markdown"
        )

        logger.info(f"Uploaded Markdown to MinIO: {markdown_path}")

        # 7. 更新数据库
        document.markdown_path = markdown_path
        document.markdown_status = "markdown_ready"
        document.markdown_error = None
        db.commit()

        # 7.1 生成 chunks（入库前可供审核/编辑/选择部分入库）
        try:
            ChunkService().regenerate_document_chunks(db, document_id=document.id, text=md_content)
        except Exception as exc:
            logger.warning(f"Chunk generation failed for document {document_id}: {exc}")

        # 8. 清理临时文件
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

        logger.info(f"Conversion successful for document {document_id}")

        return {
            "status": "success",
            "document_id": document_id,
            "markdown_path": markdown_path
        }

    except Exception as exc:
        logger.error(f"Conversion failed for document {document_id}: {exc}", exc_info=True)

        # 更新失败状态
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                document.markdown_status = "failed"
                document.markdown_error = str(exc)
                db.commit()
        except Exception as db_exc:
            logger.error(f"Failed to update error status: {db_exc}")

        # 重试机制
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

        return {
            "status": "failed",
            "document_id": document_id,
            "error": str(exc)
        }

    finally:
        db.close()
