import io

import docx
import pytest

from app import ocr, parser


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


def test_pdf_with_text_layer_does_not_use_ocr(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("OCR must not run for PDFs that already have text")

    monkeypatch.setattr(ocr, "transcribe", fail)
    assert "Hello PDF" in parser.extract_text("cv.pdf", _make_pdf("Hello PDF"))


# ------------------------------------------------------------------ OCR ----

@pytest.fixture
def ocr_calls(monkeypatch):
    """Fake OCR that records (content, mime_type) and returns canned text."""
    calls = []

    def fake_transcribe(content, mime_type):
        calls.append((content, mime_type))
        return "Văn bản từ OCR"

    monkeypatch.setattr(ocr, "transcribe", fake_transcribe)
    monkeypatch.delenv("ENABLE_OCR", raising=False)
    return calls


def test_scanned_pdf_falls_back_to_ocr(ocr_calls):
    pdf = _make_pdf(None)
    assert parser.extract_text("scan.pdf", pdf) == "Văn bản từ OCR"
    assert ocr_calls == [(pdf, "application/pdf")]


@pytest.mark.parametrize(
    "filename, mime_type",
    [
        ("cv.png", "image/png"),
        ("cv.JPG", "image/jpeg"),
        ("cv.jpeg", "image/jpeg"),
        ("cv.webp", "image/webp"),
    ],
)
def test_image_files_are_read_with_ocr(ocr_calls, filename, mime_type):
    assert parser.extract_text(filename, b"image-bytes") == "Văn bản từ OCR"
    assert ocr_calls == [(b"image-bytes", mime_type)]


def test_scanned_pdf_with_ocr_disabled_explains_why(ocr_calls, monkeypatch):
    monkeypatch.setenv("ENABLE_OCR", "false")
    with pytest.raises(ValueError, match="ENABLE_OCR"):
        parser.extract_text("scan.pdf", _make_pdf(None))
    assert ocr_calls == []


def test_image_with_ocr_disabled_explains_why(ocr_calls, monkeypatch):
    monkeypatch.setenv("ENABLE_OCR", "false")
    with pytest.raises(ValueError, match="ENABLE_OCR"):
        parser.extract_text("cv.png", b"x")
    assert ocr_calls == []


def test_ocr_that_reads_nothing_raises(monkeypatch):
    monkeypatch.setattr(ocr, "transcribe", lambda content, mime_type: "")
    with pytest.raises(ValueError, match="không đọc được chữ nào"):
        parser.extract_text("blank.png", b"x")


def test_ocr_failure_becomes_value_error_with_reason(monkeypatch):
    def boom(content, mime_type):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(ocr, "transcribe", boom)
    with pytest.raises(ValueError, match="OCR thất bại: quota exceeded"):
        parser.extract_text("scan.pdf", _make_pdf(None))


def test_scanned_pdf_without_gemini_configured_raises_ocr_error():
    # conftest blocks the real Gemini client, so this exercises the "no usable key" path.
    with pytest.raises(ValueError, match="OCR"):
        parser.extract_text("scan.pdf", _make_pdf(None))


def test_unsupported_error_lists_image_formats():
    with pytest.raises(parser.UnsupportedFileType, match=r"\.png"):
        parser.extract_text("cv.exe", b"x")
