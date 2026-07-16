"""Multilingual embedding model for fast semantic similarity between CV and JD.

Uses a lightweight multilingual Sentence-BERT model that works well for both
Vietnamese and English text. The model is loaded lazily and cached in memory.
If the model cannot be loaded (e.g. no internet access to download it on
first run), the app falls back to LLM-only matching so the tool still works.
"""
from __future__ import annotations

import numpy as np

_model = None
_load_failed = False

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_model():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    except Exception:
        # No internet / model not cached / torch missing, etc.
        _load_failed = True
        _model = None
    return _model


def is_available() -> bool:
    return _get_model() is not None


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-8
    return float(np.dot(a, b) / denom)


def embed(texts: list[str]) -> np.ndarray | None:
    model = _get_model()
    if model is None:
        return None
    return model.encode(texts, normalize_embeddings=True)


def semantic_similarity(text_a: str, text_b: str) -> float | None:
    """Return similarity in [0, 100], or None if the embedding model is unavailable."""
    vectors = embed([text_a, text_b])
    if vectors is None:
        return None
    sim = cosine_similarity(vectors[0], vectors[1])
    # cosine sim is roughly [-1, 1]; clip and rescale to [0, 100]
    sim = max(-1.0, min(1.0, sim))
    return round((sim + 1) / 2 * 100, 1)


def skill_overlap_score(cv_skills: list[str], jd_skills: list[str]) -> tuple[float, list[str], list[str]]:
    """Embedding-based fuzzy skill matching: for each JD skill, find best semantic
    match among CV skills. Returns (score 0-100, matched_skills, missing_skills).
    Falls back to case-insensitive exact match if embeddings are unavailable.
    """
    if not jd_skills:
        return 100.0, [], []

    model = _get_model()
    if model is None:
        cv_lower = {s.lower().strip() for s in cv_skills}
        matched = [s for s in jd_skills if s.lower().strip() in cv_lower]
        missing = [s for s in jd_skills if s.lower().strip() not in cv_lower]
        score = round(len(matched) / len(jd_skills) * 100, 1) if jd_skills else 100.0
        return score, matched, missing

    if not cv_skills:
        return 0.0, [], list(jd_skills)

    cv_vecs = embed(cv_skills)
    jd_vecs = embed(jd_skills)
    matched, missing = [], []
    threshold = 0.62  # empirical threshold for "same skill" in this embedding space
    for i, jd_skill in enumerate(jd_skills):
        sims = [cosine_similarity(jd_vecs[i], cv_vecs[j]) for j in range(len(cv_skills))]
        best = max(sims) if sims else 0.0
        if best >= threshold:
            matched.append(jd_skill)
        else:
            missing.append(jd_skill)
    score = round(len(matched) / len(jd_skills) * 100, 1)
    return score, matched, missing
