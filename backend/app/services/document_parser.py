from __future__ import annotations

import io
import json
import zipfile
from xml.etree import ElementTree as ET

import pdfplumber
from docx import Document as DocxDocument


class DocumentParser:
    def parse_text(self, content: bytes, content_type: str, filename: str) -> str:
        normalized_name = (filename or "").lower()
        normalized_type = (content_type or "").lower()

        if normalized_name.endswith(".pdf") or normalized_type == "application/pdf":
            return self._parse_pdf(content)
        if normalized_name.endswith(".docx") or "wordprocessingml" in normalized_type or normalized_type.endswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            return self._parse_docx(content)
        if normalized_name.endswith((".md", ".markdown")) or normalized_type in {"text/markdown"}:
            return self._parse_text_utf8(content)
        if normalized_name.endswith(".txt") or normalized_type.startswith("text/plain"):
            return self._parse_text_utf8(content)
        if normalized_name.endswith(".json") or normalized_type in {"application/json"}:
            return self._parse_json(content)
        if normalized_name.endswith(".csv") or normalized_type in {"text/csv"}:
            return self._parse_csv(content)
        if normalized_name.endswith(".xlsx") or "spreadsheetml" in normalized_type:
            return self._parse_xlsx(content)

        raise ValueError("Unsupported file type")

    def parse_preview(self, content: bytes, content_type: str, filename: str, max_chars: int = 2000) -> str:
        text = self.parse_text(content, content_type, filename)
        text = " ".join(text.split())
        if not text:
            return "（未提取到可搜索文本：可能是扫描件/图片PDF、加密PDF或内容为空）"
        return text[:max_chars]

    def _parse_pdf(self, content: bytes) -> str:
        parts: list[str] = []

        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        parts.append(page_text)
        except Exception:
            parts = []

        text = "\n".join(parts).strip()
        if text:
            return text

        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(io.BytesIO(content))
            parts = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    parts.append(page_text)
            return "\n".join(parts).strip()
        except Exception:
            return ""

    def _parse_docx(self, content: bytes) -> str:
        doc = DocxDocument(io.BytesIO(content))
        parts: list[str] = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                parts.append(paragraph.text)
        return "\n".join(parts)

    def _parse_text_utf8(self, content: bytes) -> str:
        # Best effort: try utf-8, then gb18030 (common in CN), then replace.
        for enc in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return content.decode(enc)
            except Exception:
                continue
        return content.decode("utf-8", errors="replace")

    def _parse_json(self, content: bytes) -> str:
        text = self._parse_text_utf8(content)
        try:
            data = json.loads(text)
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            return text

    def _parse_csv(self, content: bytes) -> str:
        import csv

        text = self._parse_text_utf8(content)
        reader = csv.reader(io.StringIO(text))
        lines: list[str] = []
        for row in reader:
            if not row:
                continue
            lines.append("\t".join(cell.strip() for cell in row))
        return "\n".join(lines)

    def _parse_xlsx(self, content: bytes) -> str:
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        parts: list[str] = []

        with zipfile.ZipFile(io.BytesIO(content)) as z:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in root.findall(f".//{ns}si"):
                    texts = [t.text or "" for t in si.findall(f".//{ns}t")]
                    shared.append("".join(texts))

            sheets = sorted(
                [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
            )
            for sheet_path in sheets:
                parts.append(f"## {sheet_path.split('/')[-1]}\n")
                root = ET.fromstring(z.read(sheet_path))
                for row in root.findall(f".//{ns}row"):
                    cells: list[str] = []
                    for c in row.findall(f"{ns}c"):
                        t = c.get("t")
                        v = c.find(f"{ns}v")
                        if v is None or v.text is None:
                            cells.append("")
                            continue
                        raw = v.text
                        if t == "s":
                            try:
                                idx = int(raw)
                                cells.append(shared[idx] if 0 <= idx < len(shared) else raw)
                            except Exception:
                                cells.append(raw)
                        else:
                            cells.append(raw)
                    if any(cell.strip() for cell in cells):
                        parts.append("\t".join(cell.strip() for cell in cells).rstrip() + "\n")
                parts.append("\n")

        return "".join(parts).strip()
