import json
from types import SimpleNamespace

import pytest

from app import extractor


class FakeClient:
    """Stands in for genai.Client: returns a canned text for any request."""

    def __init__(self, text):
        self.models = SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text=text))


# ---------------------------------------------------------- repair_json ----

def test_repair_json_empty_returns_empty_object():
    assert extractor.repair_json("") == "{}"
    assert extractor.repair_json("   ") == "{}"


def test_repair_json_leaves_valid_json_parseable():
    src = '{"a": [1, 2, {"b": "c"}]}'
    assert json.loads(extractor.repair_json(src)) == {"a": [1, 2, {"b": "c"}]}


def test_repair_json_closes_truncated_brackets():
    assert json.loads(extractor.repair_json('{"a": [1, 2')) == {"a": [1, 2]}


def test_repair_json_closes_open_string():
    assert json.loads(extractor.repair_json('{"a": "hel')) == {"a": "hel"}


def test_repair_json_escapes_literal_newline_inside_string():
    assert json.loads(extractor.repair_json('{"a": "x\ny"}')) == {"a": "x\ny"}


def test_repair_json_keeps_escaped_quote():
    assert json.loads(extractor.repair_json(r'{"a": "he said \"hi\""}')) == {"a": 'he said "hi"'}


# ------------------------------------------------------------ _call_json ----

def test_call_json_parses_plain_json(monkeypatch):
    monkeypatch.setattr(extractor, "get_client", lambda: FakeClient('{"x": 1}'))
    assert extractor._call_json("sys", "user") == {"x": 1}


def test_call_json_recovers_from_code_fence(monkeypatch):
    fenced = '```json\n{"x": 1}\n```'
    monkeypatch.setattr(extractor, "get_client", lambda: FakeClient(fenced))
    assert extractor._call_json("sys", "user") == {"x": 1}


def test_call_json_recovers_from_truncated_reply(monkeypatch):
    monkeypatch.setattr(extractor, "get_client", lambda: FakeClient('{"skills": ["a", "b"'))
    assert extractor._call_json("sys", "user") == {"skills": ["a", "b"]}


def test_call_json_raises_value_error_on_garbage(monkeypatch):
    monkeypatch.setattr(extractor, "get_client", lambda: FakeClient("not json at all"))
    with pytest.raises(ValueError):
        extractor._call_json("sys", "user")


def test_call_json_handles_none_text(monkeypatch):
    monkeypatch.setattr(extractor, "get_client", lambda: FakeClient(None))
    assert extractor._call_json("sys", "user") == {}


# ------------------------------------------------- extract_cv / extract_job ----

def test_extract_cv_builds_parsed_cv(monkeypatch):
    reply = json.dumps({"full_name": "An", "skills": ["Python"], "total_years_experience": 2})
    monkeypatch.setattr(extractor, "get_client", lambda: FakeClient(reply))
    cv = extractor.extract_cv("raw cv text")
    assert cv.full_name == "An"
    assert cv.skills == ["Python"]
    assert cv.total_years_experience == 2


def test_extract_job_builds_parsed_job(monkeypatch):
    reply = json.dumps({"title": "Dev", "required_skills": ["Go"], "min_years_experience": 3})
    monkeypatch.setattr(extractor, "get_client", lambda: FakeClient(reply))
    job = extractor.extract_job("raw jd text")
    assert job.title == "Dev"
    assert job.required_skills == ["Go"]
    assert job.min_years_experience == 3


def test_extract_cv_fills_defaults_for_missing_fields(monkeypatch):
    monkeypatch.setattr(extractor, "get_client", lambda: FakeClient("{}"))
    cv = extractor.extract_cv("x")
    assert cv.skills == []
    assert cv.work_experience == []


# ------------------------------------------------------------ get_client ----

def test_get_client_requires_api_key(monkeypatch):
    monkeypatch.setattr(extractor, "_client", None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        extractor.get_client()
