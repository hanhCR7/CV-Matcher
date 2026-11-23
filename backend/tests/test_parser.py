import io

import docx
import pytest

from app import parser


def _make_pdf(text: str | None) -> bytes:
    """Build a minimal one-page PDF. `text=None` yields a page with no text layer."""
    stream = b""
    if text is not None:
        stream = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _make_docx(paragraphs=(), table_cells=()) -> bytes:
    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    if table_cells:
        table = document.add_table(rows=1, cols=len(table_cells))
        for cell, value in zip(table.rows[0].cells, table_cells):
            cell.text = value
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


# ----------------------------------------------------------------- text ----

def test_txt_is_decoded_as_utf8():
    assert parser.extract_text("cv.txt", "Nguyễn Văn A".encode("utf-8")) == "Nguyễn Văn A"


def test_md_is_supported():
    assert parser.extract_text("cv.md", b"# Title") == "# Title"


def test_extension_check_is_case_insensitive():
    assert parser.extract_text("CV.TXT", b"hello") == "hello"


def test_invalid_utf8_bytes_are_ignored_not_fatal():
    assert parser.extract_text("cv.txt", b"abc\xff\xfedef") == "abcdef"


def test_unsupported_extension_raises():
    with pytest.raises(parser.UnsupportedFileType):
        parser.extract_text("cv.exe", b"data")


# ----------------------------------------------------------------- docx ----

def test_docx_extracts_paragraphs():
    text = parser.extract_text("cv.docx", _make_docx(paragraphs=["Hello", "World"]))
    assert "Hello" in text and "World" in text


def test_docx_extracts_table_cells():
    text = parser.extract_text("cv.docx", _make_docx(paragraphs=["Intro"], table_cells=["Python", "SQL"]))
    assert "Intro" in text
    assert "Python" in text and "SQL" in text


def test_empty_docx_raises_value_error():
    with pytest.raises(ValueError):
        parser.extract_text("cv.docx", _make_docx())


# ------------------------------------------------------------------ pdf ----

def test_pdf_extracts_text():
    text = parser.extract_text("cv.pdf", _make_pdf("Hello PDF"))
    assert "Hello PDF" in text


def test_pdf_without_text_layer_raises_ocr_hint():
    with pytest.raises(ValueError, match="OCR"):
        parser.extract_text("scan.pdf", _make_pdf(None))
