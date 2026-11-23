import sqlite3

import pytest

from app import storage

from .conftest import make_match


def test_create_and_get_job(tmp_db, sample_job):
    created = storage.create_job("Backend Dev", "raw jd", sample_job)
    fetched = storage.get_job(created.id)

    assert fetched is not None
    assert fetched.title == "Backend Dev"
    assert fetched.raw_text == "raw jd"
    assert fetched.parsed.required_skills == ["Python", "Docker"]
    assert fetched.candidate_count == 0


def test_get_unknown_job_returns_none(tmp_db):
    assert storage.get_job("does-not-exist") is None


def test_list_jobs_newest_first(tmp_db, sample_job):
    first = storage.create_job("first", "x", sample_job)
    second = storage.create_job("second", "x", sample_job)
    ids = [j.id for j in storage.list_jobs()]
    assert ids == [second.id, first.id]


def test_candidate_count_is_reported(tmp_db, sample_job, sample_cv):
    job = storage.create_job("j", "x", sample_job)
    storage.add_candidate(job.id, "a.txt", sample_cv, make_match())
    storage.add_candidate(job.id, "b.txt", sample_cv, make_match())

    assert storage.get_job(job.id).candidate_count == 2
    assert storage.list_jobs()[0].candidate_count == 2


def test_add_and_list_candidate_roundtrip(tmp_db, sample_job, sample_cv):
    job = storage.create_job("j", "x", sample_job)
    added = storage.add_candidate(job.id, "cv.pdf", sample_cv, make_match(77.5, strengths=["Python"]))

    (listed,) = storage.list_candidates(job.id)
    assert listed.id == added.id
    assert listed.filename == "cv.pdf"
    assert listed.parsed.full_name == "Nguyen Van A"
    assert listed.match.final_score == 77.5
    assert listed.match.strengths == ["Python"]


def test_candidates_ranked_by_final_score_descending(tmp_db, sample_job, sample_cv):
    job = storage.create_job("j", "x", sample_job)
    for name, score in [("low.txt", 10.0), ("high.txt", 90.0), ("mid.txt", 50.0)]:
        storage.add_candidate(job.id, name, sample_cv, make_match(score))

    assert [c.filename for c in storage.list_candidates(job.id)] == ["high.txt", "mid.txt", "low.txt"]


def test_candidates_are_scoped_to_their_job(tmp_db, sample_job, sample_cv):
    job_a = storage.create_job("a", "x", sample_job)
    job_b = storage.create_job("b", "x", sample_job)
    storage.add_candidate(job_a.id, "a.txt", sample_cv, make_match())

    assert len(storage.list_candidates(job_a.id)) == 1
    assert storage.list_candidates(job_b.id) == []


def test_delete_candidate(tmp_db, sample_job, sample_cv):
    job = storage.create_job("j", "x", sample_job)
    cand = storage.add_candidate(job.id, "a.txt", sample_cv, make_match())
    assert storage.delete_candidate(cand.id) is True
    assert storage.list_candidates(job.id) == []


def test_delete_unknown_candidate_returns_false(tmp_db):
    assert storage.delete_candidate("no-such-candidate") is False


def test_delete_job_also_deletes_its_candidates(tmp_db, sample_job, sample_cv):
    job = storage.create_job("j", "x", sample_job)
    other = storage.create_job("other", "x", sample_job)
    storage.add_candidate(job.id, "a.txt", sample_cv, make_match())
    storage.add_candidate(other.id, "b.txt", sample_cv, make_match())

    storage.delete_job(job.id)

    assert storage.get_job(job.id) is None
    assert storage.list_candidates(job.id) == []
    assert len(storage.list_candidates(other.id)) == 1  # other job untouched


def test_foreign_key_is_enforced(tmp_db, sample_cv):
    with pytest.raises(sqlite3.IntegrityError):
        storage.add_candidate("no-such-job", "a.txt", sample_cv, make_match())
