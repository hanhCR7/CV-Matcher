"""CV-JD Matcher API.

Run with:
    GEMINI_API_KEY=... uvicorn app.main:app --reload --port 8000

Endpoints:
    POST   /api/jobs                     Create a job from pasted JD text
    POST   /api/jobs/upload              Create a job from an uploaded JD file
    GET    /api/jobs                     List all jobs
    GET    /api/jobs/{job_id}            Get one job
    DELETE /api/jobs/{job_id}            Delete a job and its candidates
    POST   /api/jobs/{job_id}/candidates Upload one or more CVs, parse + match them against the job
                                         (returns {"candidates": [...], "errors": [...]})
    GET    /api/jobs/{job_id}/candidates List candidates for a job, ranked by fit score
    DELETE /api/candidates/{candidate_id} Delete a candidate
"""
from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
# Load .env variables before other imports/app initialization
load_dotenv()

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import extractor, matcher, parser, storage
from .models import CandidateOut, CreateJobRequest, JobOut, UploadError, UploadResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cv-jd-matcher")

app = FastAPI(title="CV-JD Matcher", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    storage.init_db()


# ---------------------------------------------------------------- jobs ----

@app.post("/api/jobs", response_model=JobOut)
def create_job(payload: CreateJobRequest):
    if not payload.raw_text.strip():
        raise HTTPException(400, "Nội dung JD không được để trống.")
    try:
        parsed = extractor.extract_job(payload.raw_text)
    except Exception as exc:
        logger.exception("JD extraction failed")
        raise HTTPException(502, f"Lỗi khi trích xuất JD: {exc}") from exc
    title = payload.title or parsed.title or "Untitled position"
    return storage.create_job(title, payload.raw_text, parsed)


# NOTE: the upload handlers below are plain `def`, not `async def`, on purpose.
# They call blocking code (Gemini, embeddings, SQLite). FastAPI runs sync
# handlers in a threadpool, so a slow upload doesn't stall every other request.
@app.post("/api/jobs/upload", response_model=JobOut)
def create_job_from_file(file: UploadFile = File(...)):
    content = file.file.read()
    try:
        raw_text = parser.extract_text(file.filename, content)
    except (parser.UnsupportedFileType, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        parsed = extractor.extract_job(raw_text)
    except Exception as exc:
        logger.exception("JD extraction failed")
        raise HTTPException(502, f"Lỗi khi trích xuất JD: {exc}") from exc
    return storage.create_job(parsed.title or file.filename, raw_text, parsed)


@app.get("/api/jobs", response_model=list[JobOut])
def get_jobs():
    return storage.list_jobs()


@app.get("/api/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str):
    job = storage.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy job.")
    return job


@app.delete("/api/jobs/{job_id}")
def remove_job(job_id: str):
    if storage.get_job(job_id) is None:
        raise HTTPException(404, "Không tìm thấy job.")
    storage.delete_job(job_id)
    return {"ok": True}


# --------------------------------------------------------- candidates ----

@app.post("/api/jobs/{job_id}/candidates", response_model=UploadResponse)
def upload_candidates(job_id: str, files: list[UploadFile] = File(...)):
    job = storage.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy job.")

    candidates = []
    errors: list[UploadError] = []

    for file in files:
        name = file.filename or "(không tên)"
        try:
            content = file.file.read()
            raw_text = parser.extract_text(name, content)
            parsed_cv = extractor.extract_cv(raw_text)
            match_result = matcher.match_cv_to_job(parsed_cv, job.parsed)
            candidates.append(storage.add_candidate(job_id, name, parsed_cv, match_result))
        except Exception as exc:  # noqa: BLE001 - report per-file, keep processing rest
            logger.exception("Failed to process %s", name)
            errors.append(UploadError(filename=name, detail=str(exc)))

    if errors and not candidates:
        details = "\n".join(f"{e.filename}: {e.detail}" for e in errors)
        raise HTTPException(422, "Không xử lý được file nào.\n" + details)

    return UploadResponse(candidates=candidates, errors=errors)


@app.get("/api/jobs/{job_id}/candidates", response_model=list[CandidateOut])
def get_candidates(job_id: str):
    if storage.get_job(job_id) is None:
        raise HTTPException(404, "Không tìm thấy job.")
    return storage.list_candidates(job_id)


@app.delete("/api/candidates/{candidate_id}")
def remove_candidate(candidate_id: str):
    if not storage.delete_candidate(candidate_id):
        raise HTTPException(404, "Không tìm thấy ứng viên.")
    return {"ok": True}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "embedding_model_available": _embedding_status(),
    }


def _embedding_status() -> bool:
    try:
        from . import embeddings

        return embeddings.is_available()
    except Exception:
        return False


# ------------------------------------------------------------ frontend ----
# Serve the static frontend (if present) so the whole tool runs from one
# `uvicorn` process: web app + API on the same origin, no CORS headaches.
_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
