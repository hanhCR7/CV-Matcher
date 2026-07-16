"""Lightweight SQLite persistence for jobs and matched candidates.

Sized for internal-company usage (dozens to hundreds of CVs/month) - no
external DB needed. Swap for Postgres later by replacing this module if
usage grows.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from .models import CandidateOut, JobOut, MatchResult, ParsedCV, ParsedJob

DB_PATH = os.environ.get("CV_MATCHER_DB", "cv_matcher.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    parsed_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    filename TEXT NOT NULL,
    parsed_json TEXT NOT NULL,
    match_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enforce SQLite foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(title: str, raw_text: str, parsed: ParsedJob) -> JobOut:
    job_id = str(uuid.uuid4())
    created_at = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (id, title, raw_text, parsed_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, title, raw_text, parsed.model_dump_json(), created_at),
        )
    return JobOut(
        id=job_id,
        title=title,
        raw_text=raw_text,
        parsed=parsed,
        created_at=datetime.fromisoformat(created_at),
        candidate_count=0,
    )


def list_jobs() -> list[JobOut]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT j.*, (SELECT COUNT(*) FROM candidates c WHERE c.job_id = j.id) AS candidate_count
               FROM jobs j ORDER BY j.created_at DESC"""
        ).fetchall()
    return [_row_to_job(r) for r in rows]


def get_job(job_id: str) -> JobOut | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT j.*, (SELECT COUNT(*) FROM candidates c WHERE c.job_id = j.id) AS candidate_count
               FROM jobs j WHERE j.id = ?""",
            (job_id,),
        ).fetchone()
    return _row_to_job(row) if row else None


def delete_job(job_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM candidates WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def add_candidate(job_id: str, filename: str, parsed: ParsedCV, match: MatchResult) -> CandidateOut:
    cand_id = str(uuid.uuid4())
    created_at = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO candidates (id, job_id, filename, parsed_json, match_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cand_id, job_id, filename, parsed.model_dump_json(), match.model_dump_json(), created_at),
        )
    return CandidateOut(
        id=cand_id,
        job_id=job_id,
        filename=filename,
        parsed=parsed,
        match=match,
        created_at=datetime.fromisoformat(created_at),
    )


def list_candidates(job_id: str) -> list[CandidateOut]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM candidates WHERE job_id = ? ORDER BY created_at DESC", (job_id,)
        ).fetchall()
    candidates = [_row_to_candidate(r) for r in rows]
    # Rank by final_score, descending
    candidates.sort(key=lambda c: c.match.final_score, reverse=True)
    return candidates


def delete_candidate(candidate_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))


def _row_to_job(row: sqlite3.Row) -> JobOut:
    return JobOut(
        id=row["id"],
        title=row["title"],
        raw_text=row["raw_text"],
        parsed=ParsedJob.model_validate(json.loads(row["parsed_json"])),
        created_at=datetime.fromisoformat(row["created_at"]),
        candidate_count=row["candidate_count"],
    )


def _row_to_candidate(row: sqlite3.Row) -> CandidateOut:
    return CandidateOut(
        id=row["id"],
        job_id=row["job_id"],
        filename=row["filename"],
        parsed=ParsedCV.model_validate(json.loads(row["parsed_json"])),
        match=MatchResult.model_validate(json.loads(row["match_json"])),
        created_at=datetime.fromisoformat(row["created_at"]),
    )
