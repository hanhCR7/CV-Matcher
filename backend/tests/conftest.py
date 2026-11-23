"""Shared fixtures. No test here touches the network, Gemini, or the real
sentence-transformers model: everything external is replaced with fakes."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import embeddings, extractor, storage
from app.models import MatchResult, ParsedCV, ParsedJob


@pytest.fixture(autouse=True)
def _block_real_gemini(monkeypatch):
    """Safety net: no test may reach the real Gemini API, even if GEMINI_API_KEY
    is set on the developer's machine (app.main loads backend/.env on import)."""

    def _blocked(*args, **kwargs):
        raise RuntimeError("Real Gemini client is blocked in tests; fake it instead.")

    monkeypatch.setattr(extractor, "_client", None)
    monkeypatch.setattr(extractor.genai, "Client", _blocked)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point storage at a fresh SQLite file for the duration of one test."""
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "test.db"))
    storage.init_db()
    return storage.DB_PATH


@pytest.fixture
def no_embedding_model(monkeypatch):
    """Force the offline fallback path (embedding model unavailable)."""
    monkeypatch.setattr(embeddings, "_get_model", lambda: None)


@pytest.fixture
def sample_job() -> ParsedJob:
    return ParsedJob(
        title="Backend Developer",
        seniority_level="Mid",
        required_skills=["Python", "Docker"],
        preferred_skills=["Kubernetes"],
        min_years_experience=3,
        summary="Build APIs.",
    )


@pytest.fixture
def sample_cv() -> ParsedCV:
    return ParsedCV(
        full_name="Nguyen Van A",
        email="a@example.com",
        total_years_experience=4,
        skills=["Python", "SQL"],
        summary="Backend engineer.",
    )


def make_match(final_score: float = 50.0, **overrides) -> MatchResult:
    data = dict(embedding_score=50.0, llm_score=50.0, final_score=final_score)
    data.update(overrides)
    return MatchResult(**data)


@pytest.fixture
def client(tmp_db, monkeypatch):
    """FastAPI test client with a temp DB and the embedding health check stubbed."""
    from app.main import app

    monkeypatch.setattr(embeddings, "is_available", lambda: False)
    with TestClient(app) as c:
        yield c
