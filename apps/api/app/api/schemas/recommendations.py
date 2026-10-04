"""API response contracts for course recommendations."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.recommendations.models import RecommendationReason


class RecommendationCandidateResponse(BaseModel):
    course_code: str
    course_name_ar: str | None
    course_name_en: str | None = None
    credit_hours: Decimal
    requirement_group_code: str
    requirement_type: str
    course_state: str
    eligibility_decision: str
    effective_credit_contribution: Decimal
    group_remaining_credits_before: Decimal
    group_remaining_credits_after: Decimal
    completes_requirement_group: bool
    newly_eligible_count: int
    newly_eligible_course_codes: list[str]
    priority_tuple: tuple[int, int, Decimal, int, int, int, str]
    rank: int
    reason_codes: list[RecommendationReason]
    previously_attempted: bool


class ReviewRequiredCourseResponse(BaseModel):
    course_code: str
    course_name_ar: str | None
    course_name_en: str | None = None
    credit_hours: Decimal
    requirement_group_code: str
    requirement_type: str
    review_reason: str
    previously_attempted: bool


class RecommendationResponse(BaseModel):
    study_plan_id: UUID
    recommendation_policy_version: str
    ranked_recommendations: list[RecommendationCandidateResponse]
    review_required_courses: list[ReviewRequiredCourseResponse]
    excluded_in_progress: list[str]
    methodology_note: str
    limitations: list[str]

