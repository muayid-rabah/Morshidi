"""API request and response contracts for multi-semester degree path planning."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.semester_planner import SemesterPlanOptionResponse
from app.degree_path.models import (
    BlockerType,
    PathReasonCode,
    PathStatus,
)


class DegreePathRequest(BaseModel):
    """Client request schema for multi-semester degree path planning.

    Extra fields are strictly forbidden (extra="forbid") so internal engine parameters
    (beam_width, semester_branch_width, candidate_window_size), owner_user_id, study_plan_id,
    attempts, etc. cannot be supplied.
    """

    model_config = ConfigDict(extra="forbid")

    max_credit_hours_per_semester: Annotated[
        Decimal,
        Field(
            ge=Decimal("0.00"),
            le=Decimal("30.00"),
            description="Maximum credit hours preference per semester (0.00 to 30.00).",
        ),
    ]
    max_courses_per_semester: Annotated[
        int | None,
        Field(
            default=None,
            ge=1,
            le=10,
            description="Optional maximum number of courses per semester (1 to 10).",
        ),
    ] = None
    max_semesters_ahead: Annotated[
        int,
        Field(
            default=8,
            ge=1,
            le=16,
            description="Maximum number of future semesters to plan ahead (1 to 16).",
        ),
    ] = 8
    max_paths: Annotated[
        int,
        Field(
            default=3,
            ge=1,
            le=10,
            description="Maximum number of ranked degree paths to return (1 to 10).",
        ),
    ] = 3


class DegreePathConstraintsResponse(BaseModel):
    max_credit_hours_per_semester: Decimal
    max_courses_per_semester: int | None
    max_semesters_ahead: int
    max_paths: int


class ModeledSemesterResponse(BaseModel):
    semester_index: int
    plan_option: SemesterPlanOptionResponse
    completed_plan_credits_after: Decimal
    remaining_plan_credits_after: Decimal
    newly_satisfied_requirement_group_codes: list[str]


class DegreePathOptionResponse(BaseModel):
    rank: int
    status: PathStatus
    semesters: list[ModeledSemesterResponse]
    semester_count: int
    total_planned_courses: int
    total_planned_credits: Decimal
    completed_plan_credit_delta: Decimal
    final_completed_plan_credits: Decimal
    final_remaining_plan_credits: Decimal
    newly_satisfied_requirement_group_count: int
    newly_satisfied_requirement_group_codes: list[str]
    remaining_required_course_codes: list[str]
    unresolved_blocker_codes: list[str]
    aggregate_semester_rank_sum: int
    priority_tuple: list[Any]
    reason_codes: list[PathReasonCode]


class DegreePathResponse(BaseModel):
    study_plan_id: UUID
    degree_path_policy_version: str
    planning_scope: str
    constraints: DegreePathConstraintsResponse
    paths: list[DegreePathOptionResponse]
    initial_completed_credits: Decimal
    initial_remaining_credits: Decimal
    initial_satisfied_group_count: int
    total_requirement_group_count: int
    unresolved_review_required_courses: list[str]
    persisted_in_progress_courses: list[str]
    total_parent_states_expanded: int
    methodology_note: str
    limitations: list[str]

