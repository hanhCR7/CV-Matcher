"""Pydantic schemas shared across the API."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------- Parsed structures (produced by the LLM extractor) ----------

class ParsedJob(BaseModel):
    title: str = ""
    seniority_level: str = ""  # intern / junior / mid / senior / lead / manager...
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    min_years_experience: Optional[float] = None
    education_requirement: str = ""
    languages_required: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    location: str = ""
    summary: str = ""


class WorkExperienceItem(BaseModel):
    company: str = ""
    title: str = ""
    start_date: str = ""
    end_date: str = ""
    duration_years: Optional[float] = None
    description: str = ""


class EducationItem(BaseModel):
    school: str = ""
    degree: str = ""
    major: str = ""
    graduation_year: str = ""


class ParsedCV(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    total_years_experience: Optional[float] = None
    skills: List[str] = Field(default_factory=list)
    work_experience: List[WorkExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    summary: str = ""


# ---------- Matching result ----------

class MatchResult(BaseModel):
    embedding_score: float  # 0-100, semantic similarity (skills+experience vs JD)
    llm_score: float  # 0-100, LLM judgment of overall fit
    final_score: float  # 0-100, weighted combination
    matched_skills: List[str] = Field(default_factory=list)
    missing_required_skills: List[str] = Field(default_factory=list)
    experience_fit: str = ""  # short verdict e.g. "Đáp ứng (5/3 năm yêu cầu)"
    strengths: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    explanation: str = ""
    recommendation: str = ""  # "Nên phỏng vấn" / "Cân nhắc" / "Không phù hợp"


# ---------- API request/response models ----------

class CreateJobRequest(BaseModel):
    title: Optional[str] = None
    raw_text: str


class JobOut(BaseModel):
    id: str
    title: str
    raw_text: str
    parsed: ParsedJob
    created_at: datetime
    candidate_count: int = 0


class CandidateOut(BaseModel):
    id: str
    job_id: str
    filename: str
    parsed: ParsedCV
    match: MatchResult
    created_at: datetime


class UploadError(BaseModel):
    filename: str
    detail: str


class UploadResponse(BaseModel):
    """Result of a multi-CV upload: the ones that worked and the ones that failed."""

    candidates: List[CandidateOut] = Field(default_factory=list)
    errors: List[UploadError] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str
