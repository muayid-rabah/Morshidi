"""API request and response contracts for semester planning."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.planner.models import PlanReasonCode


class SemesterPlanRequest(BaseModel):
    """Client request schema for semester planning.

    Extra fields are strictly forbidden (extra="forbid") so candidate_window_size,
    owner_user_id, study_plan_id, attempts, etc. cannot be supplied.
    """

    model_config = ConfigDict(extra="forbid")

    max_credit_hours: Annotated[
        Decimal,
        Field(
            ge=Decimal("0.00"),
            le=Decimal("30.00"),
            description="Maximum credit hours preference for the planned semester (0.00 to 30.00).",
        ),
    ]
    max_courses: Annotated[
        int | None,
        Field(
            default=None,
            ge=1,
            le=10,
            description="Optional maximum number of courses to plan (1 to 10).",
        ),
    ] = None
    max_options: Annotated[
        int,
        Field(
            default=5,
            ge=1,
            le=10,
            description="Maximum number of ranked plan options to return (1 to 10).",
        ),
    ] = 5
    accept_heavy_balance: bool = False


class PlannerConstraintsResponse(BaseModel):
    max_credit_hours: Decimal
    max_courses: int | None
    max_options: int


class PlannedCourseEntryResponse(BaseModel):
    course_code: str
    course_name_ar: str | None
    course_name_en: str | None
    credit_hours: Decimal
    requirement_group_code: str
    requirement_type: str
    phase7_rank: int
    previously_attempted: bool


class SemesterPlanOptionResponse(BaseModel):
    rank: int
    courses: list[PlannedCourseEntryResponse]
    total_credit_hours: Decimal
    total_courses: int
    mandatory_course_count: int
    zero_credit_required_count: int
    completed_plan_credit_delta: Decimal
    newly_satisfied_requirement_group_codes: list[str]
    newly_satisfied_requirement_group_count: int
    newly_eligible_course_codes: list[str]
    newly_eligible_count: int
    recommendation_rank_sum: int
    priority_tuple: tuple[int, int, Decimal, int, Decimal, int, list[str]]
    reason_codes: list[PlanReasonCode]
    memorization_heavy_count: int = 0
    learning_type_counts: list[tuple[str, int]] = []
    estimated_workload: str = "UNKNOWN"
    balance_warning: str | None = None


class SemesterPlannerResponse(BaseModel):
    study_plan_id: UUID
    semester_planner_policy_version: str
    planning_scope: str
    constraints: PlannerConstraintsResponse
    candidate_window_size: int
    eligible_ranked_candidate_count: int
    evaluated_candidate_count: int
    valid_combination_count: int
    plan_options: list[SemesterPlanOptionResponse]
    review_required_courses: list[str]
    excluded_in_progress: list[str]
    methodology_note: str
    limitations: list[str]
    balance_relaxation_required: bool = False
    balance_policy_version: str = "MODELED_COURSE_LOAD_PROFILE_V1"

