import numpy as np
import pytest

from app import embeddings

# Tiny fake "embedding space": synonyms share a vector, unrelated skills are orthogonal.
VECTORS = {
    "react": [1.0, 0.0, 0.0],
    "reactjs": [1.0, 0.0, 0.0],
    "python": [0.0, 1.0, 0.0],
    "java": [0.0, 0.0, 1.0],
}


class FakeModel:
    def encode(self, texts, normalize_embeddings=True):
        return np.array([VECTORS.get(t.lower().strip(), [0.0, 0.0, 0.0]) for t in texts])


@pytest.fixture
def fake_model(monkeypatch):
    monkeypatch.setattr(embeddings, "_get_model", lambda: FakeModel())


# ------------------------------------------------------- model loading ----

def test_model_is_loaded_only_once_under_concurrent_requests(monkeypatch):
    import sys
    import threading
    import time
    import types

    loads = []

    class SlowModel:
        def __init__(self, name):
            loads.append(name)
            time.sleep(0.05)  # widen the race window

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = SlowModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    monkeypatch.setattr(embeddings, "_model", None)
    monkeypatch.setattr(embeddings, "_load_failed", False)

    results = []
    threads = [threading.Thread(target=lambda: results.append(embeddings._get_model())) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(loads) == 1
    assert len({id(m) for m in results}) == 1  # everyone got the same instance


def test_model_load_failure_falls_back_without_retrying(monkeypatch):
    import sys
    import types

    attempts = []

    class Broken:
        def __init__(self, name):
            attempts.append(name)
            raise OSError("no internet")

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = Broken
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    monkeypatch.setattr(embeddings, "_model", None)
    monkeypatch.setattr(embeddings, "_load_failed", False)

    assert embeddings._get_model() is None
    assert embeddings._get_model() is None
    assert embeddings.is_available() is False
    assert len(attempts) == 1  # gave up after the first failure


# ----------------------------------------------------- cosine_similarity ----

def test_cosine_identical_vectors_is_one():
    v = np.array([1.0, 2.0, 3.0])
    assert embeddings.cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors_is_zero():
    assert embeddings.cosine_similarity(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == pytest.approx(0.0)


def test_cosine_zero_vector_does_not_divide_by_zero():
    assert embeddings.cosine_similarity(np.zeros(3), np.array([1.0, 0.0, 0.0])) == 0.0


# ------------------------------------------------- semantic_similarity ----

def test_semantic_similarity_none_without_model(no_embedding_model):
    assert embeddings.embed(["a"]) is None
    assert embeddings.semantic_similarity("a", "b") is None


def test_semantic_similarity_scale(fake_model):
    assert embeddings.semantic_similarity("react", "reactjs") == 100.0  # identical -> 100
    assert embeddings.semantic_similarity("react", "python") == 50.0  # orthogonal -> 50


# --------------------------------------------------- skill_overlap_score ----

def test_no_required_skills_scores_full_marks(fake_model):
    assert embeddings.skill_overlap_score(["Python"], []) == (100.0, [], [])


def test_fallback_exact_match_is_case_insensitive(no_embedding_model):
    score, matched, missing = embeddings.skill_overlap_score(["python", " SQL "], ["Python", "Docker", "sql"])
    assert score == pytest.approx(66.7)
    assert matched == ["Python", "sql"]
    assert missing == ["Docker"]


def test_fallback_does_not_match_synonyms(no_embedding_model):
    score, matched, missing = embeddings.skill_overlap_score(["ReactJS"], ["React"])
    assert score == 0.0
    assert missing == ["React"]


def test_fuzzy_match_recognises_synonyms(fake_model):
    score, matched, missing = embeddings.skill_overlap_score(["ReactJS"], ["React", "Python"])
    assert matched == ["React"]
    assert missing == ["Python"]
    assert score == 50.0


def test_fuzzy_with_empty_cv_skills_returns_all_missing(fake_model):
    assert embeddings.skill_overlap_score([], ["React", "Java"]) == (0.0, [], ["React", "Java"])
