"""Extract raw text from uploaded CV/JD files (PDF, DOCX, TXT, images).

Scanned PDFs (no text layer) and image files are read with OCR (see ocr.py).
"""
from __future__ import annotations

import io
import logging

import docx
import pdfplumber

from . import ocr

logger = logging.getLogger("cv-jd-matcher")

IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


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
    for ext, mime_type in IMAGE_MIME_TYPES.items():
        if lower.endswith(ext):
            return _ocr(content, mime_type, f"{filename} là file ảnh")
    raise UnsupportedFileType(
        f"Không hỗ trợ định dạng file: {filename}. "
        "Chỉ hỗ trợ .pdf, .docx, .txt, .md hoặc ảnh (.png, .jpg, .jpeg, .webp)"
    )


def _ocr(content: bytes, mime_type: str, reason: str) -> str:
    """Read text out of a scan/image with OCR, raising ValueError with a clear reason."""
    if not ocr.is_enabled():
        raise ValueError(f"{reason}, cần OCR nhưng tính năng OCR đang tắt (ENABLE_OCR=false).")
    logger.info("Running OCR (%s): %s", mime_type, reason)
    try:
        text = ocr.transcribe(content, mime_type)
    except Exception as exc:  # noqa: BLE001 - API/key/size errors all mean "could not OCR"
        raise ValueError(f"{reason}, OCR thất bại: {exc}") from exc
    if not text:
        raise ValueError(f"{reason}, OCR không đọc được chữ nào.")
    return text


def _extract_pdf(content: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    text = "\n".join(text_parts).strip()
    if not text:
        # No text layer: most likely a scanned/photographed CV, so fall back to OCR.
        return _ocr(content, "application/pdf", "PDF không có lớp text (có thể là ảnh scan)")
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
