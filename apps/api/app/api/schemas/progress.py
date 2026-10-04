"""Academic-progress response contracts."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.progress.models import CourseProgressState, RequirementType


class CourseProgressResponse(BaseModel):
    course_code: str
    course_name_ar: str | None = None
    course_name_en: str | None = None
    credit_hours: Decimal
    requirement_group_id: UUID
    requirement_group_code: str
    state: CourseProgressState


class RequirementGroupProgressResponse(BaseModel):
    group_id: UUID
    group_code: str
    name_ar: str
    name_en: str | None
    scope: str
    requirement_type: RequirementType
    required_credits: Decimal
    listed_credits: Decimal
    completed_listed_credits: Decimal
    credited_toward_requirement: Decimal
    in_progress_listed_credits: Decimal
    remaining_required_credits: Decimal
    completed_course_count: int
    in_progress_course_count: int
    attempted_not_completed_count: int
    not_attempted_count: int
    total_listed_course_count: int
    is_satisfied: bool


class AcademicProgressResponse(BaseModel):
    study_plan_id: UUID
    plan_total_required_credits: Decimal
    completed_plan_credits: Decimal
    in_progress_plan_credits: Decimal
    remaining_plan_credits: Decimal
    satisfied_requirement_group_count: int
    total_requirement_group_count: int
    all_modeled_plan_requirements_satisfied: bool
    requirement_groups: list[RequirementGroupProgressResponse]
    courses: list[CourseProgressResponse]
    reported_cumulative_gpa: Decimal | None
    reported_gpa_scale: Decimal | None
    reported_earned_credit_hours: Decimal | None
