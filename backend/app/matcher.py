"""Hybrid CV <-> Job matching.

Combines two signals:
1. Embedding-based semantic similarity (fast, cheap, catches synonyms like
   "ReactJS" vs "React") for skill overlap and overall profile similarity.
2. LLM judgment (Claude) for things embeddings are bad at: weighing seniority,
   judging whether experience is *relevant* (not just present), spotting red
   flags, and writing a human-readable explanation.

final_score = 0.4 * embedding_score + 0.6 * llm_score  (falls back to 100%
llm_score if the embedding model isn't available in this environment).
"""
from __future__ import annotations

from . import embeddings
from .extractor import _call_json
from .models import MatchResult, ParsedCV, ParsedJob

EMBEDDING_WEIGHT = 0.4
LLM_WEIGHT = 0.6

MATCH_SYSTEM_PROMPT = """Bạn là chuyên gia tuyển dụng (recruiter) đánh giá mức độ phù hợp giữa một CV và một Job Description.
Bạn sẽ nhận được dữ liệu JSON đã được trích xuất sẵn của CV và JD, cùng với danh sách kỹ năng đã khớp/thiếu (tính toán trước bằng thuật toán).

Nhiệm vụ: trả về DUY NHẤT một JSON object theo đúng schema sau, không thêm text giải thích ngoài JSON, không dùng markdown code fence:

{
  "llm_score": number (0-100, đánh giá tổng thể mức độ phù hợp của ứng viên với vị trí, xét đến kỹ năng, kinh nghiệm liên quan, độ senior, học vấn),
  "experience_fit": string (1 câu ngắn nhận định số năm kinh nghiệm có đáp ứng yêu cầu không, ví dụ "Đáp ứng (5 năm, JD yêu cầu tối thiểu 3 năm)" hoặc "Chưa đủ (1.5 năm, JD yêu cầu tối thiểu 3 năm)"),
  "strengths": [string] (2-4 điểm mạnh cụ thể của ứng viên so với vị trí này),
  "concerns": [string] (0-4 điểm cần lưu ý/rủi ro, ví dụ thiếu kỹ năng bắt buộc, career gap, nhảy việc liên tục, kinh nghiệm không liên quan ngành. Để mảng rỗng nếu không có),
  "explanation": string (3-5 câu giải thích lý do cho điểm số, viết như một nhận xét của recruiter, súc tích và cụ thể, KHÔNG lặp lại nguyên văn dữ liệu JSON),
  "recommendation": string (một trong: "Rất phù hợp - nên phỏng vấn", "Phù hợp - nên phỏng vấn", "Cân nhắc", "Chưa phù hợp")
}

Nguyên tắc chấm điểm:
- Kỹ năng bắt buộc (required_skills) bị thiếu là yếu tố giảm điểm mạnh nhất.
- Kinh nghiệm liên quan trực tiếp đến JD quan trọng hơn tổng số năm kinh nghiệm nói chung.
- Không suy diễn thông tin ứng viên không cung cấp (ví dụ không đoán giới tính, tuổi tác, tình trạng hôn nhân để chấm điểm).
- Chỉ trả JSON hợp lệ, không thêm gì khác."""


def _profile_text(cv: ParsedCV) -> str:
    parts = [cv.summary, " ".join(cv.skills)]
    for exp in cv.work_experience:
        parts.append(f"{exp.title} {exp.company} {exp.description}")
    return "\n".join(p for p in parts if p)


def _job_text(job: ParsedJob) -> str:
    parts = [job.summary, job.title, " ".join(job.required_skills), " ".join(job.preferred_skills)]
    parts.extend(job.responsibilities)
    return "\n".join(p for p in parts if p)


def match_cv_to_job(cv: ParsedCV, job: ParsedJob) -> MatchResult:
    # 1. Embedding signals
    skill_score, matched_skills, missing_required = embeddings.skill_overlap_score(
        cv.skills, job.required_skills
    )
    overall_semantic = embeddings.semantic_similarity(_profile_text(cv), _job_text(job))

    if overall_semantic is not None:
        embedding_score = round(0.6 * skill_score + 0.4 * overall_semantic, 1)
    else:
        embedding_score = skill_score  # fallback: exact-match skill overlap only

    # 2. LLM judgment, given the pre-computed skill match as grounding
    payload = (
        "CV (JSON):\n"
        f"{cv.model_dump_json()}\n\n"
        "JD (JSON):\n"
        f"{job.model_dump_json()}\n\n"
        "Kỹ năng bắt buộc đã khớp (tính toán trước): "
        f"{matched_skills}\n"
        "Kỹ năng bắt buộc còn thiếu (tính toán trước): "
        f"{missing_required}"
    )
    llm_data = _call_json(MATCH_SYSTEM_PROMPT, payload, max_tokens=1200)

    llm_score = float(llm_data.get("llm_score", 0))
    final_score = round(EMBEDDING_WEIGHT * embedding_score + LLM_WEIGHT * llm_score, 1)

    return MatchResult(
        embedding_score=embedding_score,
        llm_score=llm_score,
        final_score=final_score,
        matched_skills=matched_skills,
        missing_required_skills=missing_required,
        experience_fit=llm_data.get("experience_fit", ""),
        strengths=llm_data.get("strengths", []),
        concerns=llm_data.get("concerns", []),
        explanation=llm_data.get("explanation", ""),
        recommendation=llm_data.get("recommendation", ""),
    )
