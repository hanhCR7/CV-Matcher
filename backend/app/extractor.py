"""Structured extraction of CV / Job Description text using Claude.

Both Vietnamese and English documents are supported transparently: the
prompt instructs the model to read whichever language the source is in and
always return normalized, structured JSON.
"""
from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

from .models import ParsedCV, ParsedJob

_client: genai.Client | None = None
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Thiếu GEMINI_API_KEY. Hãy đặt biến môi trường này trước khi chạy server."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def repair_json(s: str) -> str:
    """Repair truncated or malformed JSON strings from LLMs.
    Closes open quotes, brackets, braces and escapes literal newlines.
    """
    s = s.strip()
    if not s:
        return "{}"
    
    in_string = False
    escaped = False
    stack = []
    repaired = []
    
    for char in s:
        if escaped:
            repaired.append(char)
            escaped = False
            continue
        if char == '\\':
            repaired.append(char)
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            repaired.append(char)
            continue
        if in_string:
            if char == '\n':
                repaired.append('\\n')
            elif char == '\r':
                repaired.append('\\r')
            else:
                repaired.append(char)
            continue
        if char == '{':
            stack.append('}')
        elif char == '[':
            stack.append(']')
        elif char == '}':
            if stack and stack[-1] == '}':
                stack.pop()
        elif char == ']':
            if stack and stack[-1] == ']':
                stack.pop()
        repaired.append(char)
        
    repaired_str = "".join(repaired)
    if in_string:
        repaired_str += '"'
    while stack:
        repaired_str += stack.pop()
    return repaired_str


def _call_json(system_prompt: str, user_content: str, max_tokens: int = 2000) -> dict:
    """Call Gemini and parse a JSON object out of its reply."""
    client = get_client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            max_output_tokens=max_tokens,
        ),
    )
    raw = resp.text or ""
    raw = raw.strip()
    
    repaired = repair_json(raw)
    
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as exc:
        # Fallback to robust raw_decode to extract the first valid JSON object
        start_idx = repaired.find("{")
        if start_idx != -1:
            try:
                obj, _ = json.JSONDecoder().raw_decode(repaired, start_idx)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Không parse được JSON từ phản hồi của model: {exc}\nRaw: {raw[:800]}\nRepaired: {repaired[:800]}") from exc


CV_SYSTEM_PROMPT = """Bạn là hệ thống trích xuất thông tin CV (resume parser). CV có thể viết bằng tiếng Việt hoặc tiếng Anh.
Nhiệm vụ: đọc CV và trả về DUY NHẤT một JSON object hợp lệ theo đúng schema sau, không thêm text giải thích, không dùng markdown code fence:

{
  "full_name": string,
  "email": string,
  "phone": string,
  "location": string,
  "total_years_experience": number hoặc null (tổng số năm kinh nghiệm làm việc, ước tính từ timeline nếu CV không ghi rõ),
  "skills": [string] (chuẩn hóa tên kỹ năng, ví dụ "ReactJS" -> "React", viết hoa chữ cái đầu công nghệ),
  "work_experience": [
    {"company": string, "title": string, "start_date": string, "end_date": string ("Present"/"Hiện tại" nếu đang làm), "duration_years": number hoặc null, "description": string (tóm tắt ngắn gọn, không quá 2 câu)}
  ],
  "education": [
    {"school": string, "degree": string, "major": string, "graduation_year": string}
  ],
  "certifications": [string],
  "languages": [string],
  "summary": string (tóm tắt 2-3 câu về ứng viên: chuyên môn chính, số năm kinh nghiệm, điểm mạnh nổi bật)
}

Quy tắc:
- Nếu thiếu thông tin, để chuỗi rỗng "" hoặc mảng rỗng [], không bịa đặt dữ liệu.
- total_years_experience: cộng dồn thời gian làm việc thực tế, loại trừ khoảng trống lớn nếu có thể suy ra.
- Chỉ trả JSON, không thêm bất kỳ ký tự nào khác trước/sau."""

JD_SYSTEM_PROMPT = """Bạn là hệ thống trích xuất thông tin mô tả công việc (Job Description parser). JD có thể viết bằng tiếng Việt hoặc tiếng Anh.
Nhiệm vụ: đọc JD và trả về DUY NHẤT một JSON object hợp lệ theo đúng schema sau, không thêm text giải thích, không dùng markdown code fence:

{
  "title": string (tên vị trí tuyển dụng),
  "seniority_level": string (một trong: "Intern", "Junior", "Mid", "Senior", "Lead", "Manager", "Director", hoặc "" nếu không rõ),
  "required_skills": [string] (kỹ năng/công nghệ BẮT BUỘC, chuẩn hóa tên, ví dụ "ReactJS" -> "React"),
  "preferred_skills": [string] (kỹ năng ưu tiên/là điểm cộng, không bắt buộc),
  "min_years_experience": number hoặc null (số năm kinh nghiệm tối thiểu yêu cầu),
  "education_requirement": string (yêu cầu bằng cấp nếu có, ví dụ "Cử nhân CNTT hoặc tương đương"),
  "languages_required": [string] (ngoại ngữ yêu cầu, ví dụ "English - Intermediate"),
  "responsibilities": [string] (danh sách trách nhiệm công việc chính, mỗi mục ngắn gọn),
  "location": string,
  "summary": string (tóm tắt 2-3 câu về vị trí và yêu cầu cốt lõi)
}

Quy tắc:
- Nếu thiếu thông tin, để chuỗi rỗng "" hoặc mảng rỗng [], không bịa đặt dữ liệu.
- Phân biệt rõ required_skills (bắt buộc) và preferred_skills (điểm cộng/ưu tiên) dựa trên ngôn từ trong JD.
- Chỉ trả JSON, không thêm bất kỳ ký tự nào khác trước/sau."""


def extract_cv(raw_text: str) -> ParsedCV:
    data = _call_json(CV_SYSTEM_PROMPT, raw_text, max_tokens=2500)
    return ParsedCV.model_validate(data)


def extract_job(raw_text: str) -> ParsedJob:
    data = _call_json(JD_SYSTEM_PROMPT, raw_text, max_tokens=1500)
    return ParsedJob.model_validate(data)
