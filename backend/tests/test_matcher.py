import pytest

from app import embeddings, matcher
from app.models import ParsedCV, ParsedJob, WorkExperienceItem


def _fake_llm(response, captured=None):
    def _call(system_prompt, user_content, max_tokens=2000):
        if captured is not None:
            captured["payload"] = user_content
        return response

    return _call


# --------------------------------------------------------- score maths ----

def test_fallback_mode_uses_exact_skill_overlap(no_embedding_model, monkeypatch, sample_cv, sample_job):
    # CV has Python but not Docker -> skill overlap 50, no semantic score available.
    monkeypatch.setattr(matcher, "_call_json", _fake_llm({"llm_score": 80}))
    result = matcher.match_cv_to_job(sample_cv, sample_job)

    assert result.embedding_score == 50.0
    assert result.llm_score == 80.0
    assert result.final_score == 68.0  # 0.4*50 + 0.6*80
    assert result.matched_skills == ["Python"]
    assert result.missing_required_skills == ["Docker"]


def test_hybrid_mode_blends_skill_and_profile_similarity(monkeypatch, sample_cv, sample_job):
    monkeypatch.setattr(embeddings, "skill_overlap_score", lambda cv, jd: (100.0, ["Python", "Docker"], []))
    monkeypatch.setattr(embeddings, "semantic_similarity", lambda a, b: 80.0)
    monkeypatch.setattr(matcher, "_call_json", _fake_llm({"llm_score": 50}))
    result = matcher.match_cv_to_job(sample_cv, sample_job)

    assert result.embedding_score == 92.0  # 0.6*100 + 0.4*80
    assert result.final_score == 66.8  # 0.4*92 + 0.6*50


def test_missing_llm_fields_fall_back_to_defaults(no_embedding_model, monkeypatch, sample_cv, sample_job):
    monkeypatch.setattr(matcher, "_call_json", _fake_llm({}))
    result = matcher.match_cv_to_job(sample_cv, sample_job)

    assert result.llm_score == 0.0
    assert result.final_score == 20.0  # only the embedding part: 0.4*50
    assert result.strengths == [] and result.concerns == []
    assert result.explanation == "" and result.recommendation == ""


def test_llm_text_fields_are_passed_through(no_embedding_model, monkeypatch, sample_cv, sample_job):
    reply = {
        "llm_score": 70,
        "experience_fit": "Đáp ứng",
        "strengths": ["Python tốt"],
        "concerns": ["Thiếu Docker"],
        "explanation": "Ổn.",
        "recommendation": "Phù hợp - nên phỏng vấn",
    }
    monkeypatch.setattr(matcher, "_call_json", _fake_llm(reply))
    result = matcher.match_cv_to_job(sample_cv, sample_job)

    assert result.experience_fit == "Đáp ứng"
    assert result.strengths == ["Python tốt"]
    assert result.concerns == ["Thiếu Docker"]
    assert result.recommendation == "Phù hợp - nên phỏng vấn"


def test_llm_receives_precomputed_skill_match(no_embedding_model, monkeypatch, sample_cv, sample_job):
    captured = {}
    monkeypatch.setattr(matcher, "_call_json", _fake_llm({"llm_score": 60}, captured))
    matcher.match_cv_to_job(sample_cv, sample_job)

    assert "Nguyen Van A" in captured["payload"]
    assert "Backend Developer" in captured["payload"]
    assert "['Python']" in captured["payload"]  # matched
    assert "['Docker']" in captured["payload"]  # missing


# ----------------------------------------------------------- text helpers ----

def test_profile_text_includes_summary_skills_and_experience():
    cv = ParsedCV(
        summary="Dev",
        skills=["Python", "SQL"],
        work_experience=[WorkExperienceItem(title="Engineer", company="ACME", description="Built APIs")],
    )
    text = matcher._profile_text(cv)
    for part in ("Dev", "Python SQL", "Engineer", "ACME", "Built APIs"):
        assert part in text


def test_job_text_skips_empty_parts():
    job = ParsedJob(title="Dev", required_skills=["Go"], responsibilities=["Ship code"])
    text = matcher._job_text(job)
    assert "Dev" in text and "Go" in text and "Ship code" in text
    assert "\n\n" not in text


# ----------------------------------------------------------- score sanity ----

@pytest.mark.parametrize(
    "raw, expected",
    [(72, 72.0), ("85", 85.0), (250, 100.0), (-5, 0.0), ("N/A", 0.0), (None, 0.0), (float("nan"), 0.0)],
)
def test_to_score_coerces_and_clamps(raw, expected):
    assert matcher._to_score(raw) == expected


def test_llm_score_is_clamped_to_valid_range(no_embedding_model, monkeypatch, sample_cv, sample_job):
    monkeypatch.setattr(matcher, "_call_json", _fake_llm({"llm_score": 250}))
    result = matcher.match_cv_to_job(sample_cv, sample_job)
    assert 0 <= result.llm_score <= 100
    assert 0 <= result.final_score <= 100


def test_non_numeric_llm_score_does_not_crash(no_embedding_model, monkeypatch, sample_cv, sample_job):
    monkeypatch.setattr(matcher, "_call_json", _fake_llm({"llm_score": "N/A"}))
    result = matcher.match_cv_to_job(sample_cv, sample_job)
    assert result.llm_score == 0.0
