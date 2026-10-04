"""Owner-only batch response for modeled P15.5 course intelligence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SkillEvidenceResponse(BaseModel):
    skill_id: str
    mastery_score: int | None
    evidence_count: int
    confidence: str
    contributing_courses: list[str]
    version: str


class AcademicIntelligenceProfileResponse(BaseModel):
    student_id: str
    institution_id: str
    study_plan_id: str
    generated_at: datetime
    source_snapshot_version: str
    cumulative_gpa: Decimal | None
    gpa_scale: Decimal | None
    gpa_provenance: str
    grade_scale_version: str | None
    grade_scale_provenance: str
    earned_completed_credits: Decimal
    completed_courses: list[str]
    failed_courses: list[str]
    repeated_courses: list[str]
    strong_courses: list[str]
    weak_courses: list[str]
    academic_stage: str
    skills: list[SkillEvidenceResponse]
    freshness: str


class CourseSkillProfileResponse(BaseModel):
    course_code: str
    skills: list[str]
    provenance: str
    version: str


class GeneralDifficultyResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    level: str
    provenance: str
    model_version: str


class PersonalizedDifficultyResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    level: str
    confidence: str
    provenance: str
    reason_codes: list[str]
    contributing_skills: list[str]
    risk_factors: list[str]
    model_version: str


class CourseDifficultyResponse(BaseModel):
    course_code: str
    course_name_ar: str | None
    general: GeneralDifficultyResponse
    personalized: PersonalizedDifficultyResponse
    skill_profile: CourseSkillProfileResponse


class AdaptiveRecommendationResponse(BaseModel):
    course_code: str
    rank: int
    recommendation_score: int = Field(ge=0, le=100)
    eligible: bool
    general_difficulty: GeneralDifficultyResponse
    personalized_difficulty: PersonalizedDifficultyResponse
    fit_score: int
    progress_value: int
    prerequisite_readiness: int
    workload_risk: int
    confidence: str
    key_strengths: list[str]
    risk_factors: list[str]
    deterministic_reasons: list[str]
    factor_scores: list[tuple[str, int]]
    trace_version: str


class AdaptiveCourseResponse(BaseModel):
    profile: AcademicIntelligenceProfileResponse
    courses: list[CourseDifficultyResponse]
    recommendations: list[AdaptiveRecommendationResponse]
    eligible_set_version: str
    model_version: str
    weights: dict[str, int]
    limitations: list[str]
