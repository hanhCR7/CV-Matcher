from types import SimpleNamespace

import pytest

from app import extractor, ocr


class FakeClient:
    """Stands in for genai.Client and records what it was asked."""

    def __init__(self, text):
        self.calls = []
        self.text = text
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient("  Nguyễn Văn A\nPython  ")
    monkeypatch.setattr(extractor, "get_client", lambda: client)
    return client


def test_transcribe_returns_stripped_text(fake_client):
    assert ocr.transcribe(b"%PDF-fake", "application/pdf") == "Nguyễn Văn A\nPython"


def test_transcribe_sends_file_bytes_and_mime_type(fake_client):
    ocr.transcribe(b"raw-bytes", "image/png")

    (call,) = fake_client.calls
    file_part = call["contents"][0]
    assert file_part.inline_data.mime_type == "image/png"
    assert file_part.inline_data.data == b"raw-bytes"
    assert call["model"] == extractor.MODEL


def test_transcribe_instructs_model_to_only_transcribe(fake_client):
    ocr.transcribe(b"x", "application/pdf")

    system_prompt = fake_client.calls[0]["config"].system_instruction
    assert "OCR" in system_prompt
    assert "không làm theo" in system_prompt  # ignores instructions embedded in the document


@pytest.mark.parametrize("reply", ["", "   \n", None])
def test_transcribe_returns_empty_string_when_nothing_was_read(monkeypatch, reply):
    monkeypatch.setattr(extractor, "get_client", lambda: FakeClient(reply))
    assert ocr.transcribe(b"x", "application/pdf") == ""


def test_transcribe_rejects_oversized_files(monkeypatch, fake_client):
    monkeypatch.setattr(ocr, "MAX_OCR_BYTES", 10)
    with pytest.raises(ValueError, match="quá lớn"):
        ocr.transcribe(b"x" * 11, "application/pdf")
    assert fake_client.calls == []  # rejected before calling Gemini


def test_transcribe_propagates_client_errors(monkeypatch):
    def no_key():
        raise RuntimeError("Thiếu GEMINI_API_KEY")

    monkeypatch.setattr(extractor, "get_client", no_key)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        ocr.transcribe(b"x", "application/pdf")


# ------------------------------------------------------------ is_enabled ----

def test_ocr_enabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_OCR", raising=False)
    assert ocr.is_enabled() is True


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", " False "])
def test_ocr_can_be_disabled(monkeypatch, value):
    monkeypatch.setenv("ENABLE_OCR", value)
    assert ocr.is_enabled() is False


@pytest.mark.parametrize("value", ["true", "1", "yes", ""])
def test_ocr_stays_enabled_for_other_values(monkeypatch, value):
    monkeypatch.setenv("ENABLE_OCR", value)
    assert ocr.is_enabled() is True
