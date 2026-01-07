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
    from app.models import Document, DocumentChunk
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
                if document.filename.lower().endswith(".pdf"):
                    # Default-enable magic-pdf (MinerU). If it fails (missing deps/models), we automatically fall back.
                    use_magic_pdf = str(os.getenv("MINERU_USE_MAGIC_PDF", "true")).lower() in {"1", "true", "yes", "y"}
                    if not use_magic_pdf:
                        raise ValueError("magic-pdf disabled (MINERU_USE_MAGIC_PDF=false)")

                    # MinerU / magic-pdf: 支持文本 PDF + OCR PDF
                    from magic_pdf.libs.MakeContentConfig import DropMode
                    from magic_pdf.pipe.UNIPipe import UNIPipe
                    from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

                    img_bucket_path = "imgs"
                    img_dir = os.path.join(temp_dir, img_bucket_path)
                    os.makedirs(img_dir, exist_ok=True)

                    # UNIPipe 期望输入 pdf_bytes + jso_useful_key(dict) + image_writer
                    jso_useful_key = {"_pdf_type": "", "model_list": []}
                    pipe = UNIPipe(file_bytes, jso_useful_key, DiskReaderWriter(img_dir))

                    # 执行转换（分类 -> 分析(含 OCR) -> 解析 -> 生成 Markdown）
                    pipe.pipe_classify()
                    pipe.pipe_analyze()
                    pipe.pipe_parse()
                    md_content = pipe.pipe_mk_markdown(img_parent_path=img_bucket_path, drop_mode=DropMode.NONE)

                    logger.info(f"MinerU conversion completed for document {document_id}")
                else:
                    raise ValueError("MinerU only supports PDF in current pipeline")

            # NOTE: magic-pdf 在缺失重依赖时可能会触发 SystemExit（内部 exit(1)），
            # 这里必须兜住，避免 Celery worker 进程被直接退出。
            except BaseException as e:
                # MinerU 不可用时的降级方案：使用简单的文本提取
                if isinstance(e, Exception) and str(e).startswith("magic-pdf disabled"):
                    logger.info(f"MinerU conversion skipped, using fallback: {e}")
                else:
                    logger.warning(f"MinerU conversion failed, using fallback: {e}")

                if document.filename.lower().endswith(".pdf"):
                    import pdfplumber

                    page_texts: list[str] = []
                    with pdfplumber.open(input_path) as pdf:
                        for page in pdf.pages:
                            page_texts.append((page.extract_text() or "").strip())

                    md_content = "\n\n".join([f"## Page {i+1}\n\n{t}" for i, t in enumerate(page_texts)])

                    # 如果文本几乎提取不到，尝试 OCR（可通过环境变量开关）
                    try:
                        ocr_enabled = str(os.getenv("OCR_ENABLED", "true")).lower() in {"1", "true", "yes", "y"}
                        min_chars = int(os.getenv("OCR_MIN_CHARS", "50"))
                        total_chars = sum(len(t) for t in page_texts)
                        if ocr_enabled and total_chars < min_chars:
                            import fitz  # PyMuPDF
                            import pytesseract
                            from PIL import Image

                            ocr_lang = os.getenv("OCR_LANG", "chi_sim+eng")
                            ocr_dpi = int(os.getenv("OCR_DPI", "200"))
                            max_pages = int(os.getenv("OCR_MAX_PAGES", "0"))  # 0 表示不限制

                            logger.info(f"PDF seems image-based; running OCR: document={document_id}, lang={ocr_lang}")
                            doc = fitz.open(stream=file_bytes, filetype="pdf")
                            ocr_parts: list[str] = []
                            for i, page in enumerate(doc):
                                if max_pages and i >= max_pages:
                                    break
                                pix = page.get_pixmap(dpi=ocr_dpi)
                                mode = "RGB" if pix.alpha == 0 else "RGBA"
                                img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                                text = (pytesseract.image_to_string(img, lang=ocr_lang) or "").strip()
                                ocr_parts.append(f"## Page {i+1}\n\n{text}")
                            md_content = "\n\n".join(ocr_parts) if ocr_parts else md_content
                    except Exception as ocr_exc:
                        logger.warning(f"OCR skipped/failed for document {document_id}: {ocr_exc}")
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
        # 如果 chunks 已存在（例如用户已提前进入 chunks 页面并做了编辑/勾选），则不自动覆盖。
        try:
            has_chunks = (
                db.query(DocumentChunk.id)
                .filter(DocumentChunk.document_id == document.id)
                .limit(1)
                .first()
                is not None
            )
            if document.status == "indexed":
                logger.info(f"Skip chunk generation for indexed document {document_id}")
            elif has_chunks:
                logger.info(f"Skip chunk regeneration because chunks already exist: document={document_id}")
            else:
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
