"""Extract raw text from uploaded CV/JD files (PDF, DOCX, TXT)."""
from __future__ import annotations

import io

import docx
import pdfplumber


class UnsupportedFileType(Exception):
    pass


def extract_text(filename: str, content: bytes) -> str:
    """Dispatch to the right extractor based on file extension."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf(content)
    if lower.endswith(".docx"):
        return _extract_docx(content)
    if lower.endswith(".txt") or lower.endswith(".md"):
        return content.decode("utf-8", errors="ignore")
    raise UnsupportedFileType(
        f"Không hỗ trợ định dạng file: {filename}. Chỉ hỗ trợ .pdf, .docx, .txt"
    )


def _extract_pdf(content: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    text = "\n".join(text_parts).strip()
    if not text:
        raise ValueError(
            "Không trích xuất được text từ PDF này (có thể là ảnh scan, cần OCR)."
        )
    return text


def _extract_docx(content: bytes) -> str:
    document = docx.Document(io.BytesIO(content))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    # Also pull text out of tables (many CVs use table layouts)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text.strip())
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("File DOCX không có nội dung text.")
    return text
