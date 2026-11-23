import pytest

from app import extractor, matcher
from app.models import ParsedCV, ParsedJob

from .conftest import make_match


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    """Replace every Gemini-backed call with a deterministic fake."""
    monkeypatch.setattr(
        extractor,
        "extract_job",
        lambda text: ParsedJob(title="Parsed Title", required_skills=["Python"]),
    )
    # The CV "name" is the file's text, so tests control it via file content.
    monkeypatch.setattr(extractor, "extract_cv", lambda text: ParsedCV(full_name=text.strip()))
    # Score = length of the name, so "bbb" outranks "cc" outranks "a".
    monkeypatch.setattr(
        matcher,
        "match_cv_to_job",
        lambda cv, job: make_match(final_score=float(len(cv.full_name))),
    )


def _files(*items):
    """items: (filename, content_str) -> multipart `files` field."""
    return [("files", (name, content.encode(), "text/plain")) for name, content in items]


def _create_job(client, **payload):
    payload.setdefault("raw_text", "Need a Python dev")
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------- health ----

def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "embedding_model_available": False}


# ------------------------------------------------------------------ jobs ----

def test_create_job_uses_parsed_title_by_default(client):
    job = _create_job(client)
    assert job["title"] == "Parsed Title"
    assert job["parsed"]["required_skills"] == ["Python"]
    assert job["candidate_count"] == 0


def test_create_job_explicit_title_wins(client):
    assert _create_job(client, title="My Title")["title"] == "My Title"


@pytest.mark.parametrize("raw", ["", "   \n "])
def test_create_job_rejects_blank_text(client, raw):
    assert client.post("/api/jobs", json={"raw_text": raw}).status_code == 400


def test_create_job_returns_502_when_extraction_fails(client, monkeypatch):
    def boom(text):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(extractor, "extract_job", boom)
    resp = client.post("/api/jobs", json={"raw_text": "something"})
    assert resp.status_code == 502
    assert "gemini down" in resp.json()["detail"]


def test_create_job_from_uploaded_file(client):
    resp = client.post("/api/jobs/upload", files={"file": ("jd.txt", b"Need a dev", "text/plain")})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Parsed Title"
    assert resp.json()["raw_text"] == "Need a dev"


def test_upload_job_rejects_unsupported_extension(client):
    resp = client.post("/api/jobs/upload", files={"file": ("jd.exe", b"x", "application/octet-stream")})
    assert resp.status_code == 400


def test_list_and_get_job(client):
    created = _create_job(client)
    assert [j["id"] for j in client.get("/api/jobs").json()] == [created["id"]]
    assert client.get(f"/api/jobs/{created['id']}").json()["id"] == created["id"]


def test_get_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_delete_job(client):
    created = _create_job(client)
    assert client.delete(f"/api/jobs/{created['id']}").json() == {"ok": True}
    assert client.get(f"/api/jobs/{created['id']}").status_code == 404


def test_delete_unknown_job_is_404(client):
    assert client.delete("/api/jobs/nope").status_code == 404


# ------------------------------------------------------------ candidates ----

def test_upload_candidates_for_unknown_job_is_404(client):
    assert client.post("/api/jobs/nope/candidates", files=_files(("a.txt", "a"))).status_code == 404


def test_upload_candidates_returns_one_result_per_file(client):
    job = _create_job(client)
    resp = client.post(f"/api/jobs/{job['id']}/candidates", files=_files(("a.txt", "a"), ("b.txt", "bbb")))
    assert resp.status_code == 200
    body = resp.json()
    assert sorted(c["filename"] for c in body["candidates"]) == ["a.txt", "b.txt"]
    assert body["errors"] == []
    assert client.get(f"/api/jobs/{job['id']}").json()["candidate_count"] == 2


def test_upload_candidates_422_when_every_file_fails(client):
    job = _create_job(client)
    resp = client.post(f"/api/jobs/{job['id']}/candidates", files=_files(("bad.exe", "x")))
    assert resp.status_code == 422
    assert "bad.exe" in resp.json()["detail"]


def test_upload_candidates_keeps_good_files_and_reports_failed_ones(client):
    job = _create_job(client)
    resp = client.post(
        f"/api/jobs/{job['id']}/candidates", files=_files(("ok.txt", "a"), ("bad.exe", "x"))
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [c["filename"] for c in body["candidates"]] == ["ok.txt"]
    assert [e["filename"] for e in body["errors"]] == ["bad.exe"]
    assert body["errors"][0]["detail"]  # human-readable reason is included


def test_list_candidates_is_ranked_by_score(client):
    job = _create_job(client)
    client.post(
        f"/api/jobs/{job['id']}/candidates",
        files=_files(("a.txt", "a"), ("b.txt", "bbb"), ("c.txt", "cc")),
    )
    ranked = client.get(f"/api/jobs/{job['id']}/candidates").json()
    assert [c["parsed"]["full_name"] for c in ranked] == ["bbb", "cc", "a"]
    assert [c["match"]["final_score"] for c in ranked] == [3.0, 2.0, 1.0]


def test_list_candidates_for_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope/candidates").status_code == 404


def test_delete_candidate(client):
    job = _create_job(client)
    (cand,) = client.post(
        f"/api/jobs/{job['id']}/candidates", files=_files(("a.txt", "a"))
    ).json()["candidates"]
    assert client.delete(f"/api/candidates/{cand['id']}").json() == {"ok": True}
    assert client.get(f"/api/jobs/{job['id']}/candidates").json() == []


def test_delete_unknown_candidate_is_404(client):
    assert client.delete("/api/candidates/nope").status_code == 404


# ---------------------------------------------------------- concurrency ----

def test_upload_handlers_are_sync_so_they_run_in_the_threadpool():
    """`async def` handlers calling blocking Gemini/SQLite code would freeze the
    whole server during an upload; plain `def` handlers run in FastAPI's threadpool."""
    import inspect

    from app import main

    assert not inspect.iscoroutinefunction(main.upload_candidates)
    assert not inspect.iscoroutinefunction(main.create_job_from_file)
