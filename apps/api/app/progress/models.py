"""Immutable, transport-independent academic-progress contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.rules.models import CourseCatalogStatus


class CourseProgressState(str, Enum):
    COMPLETED = "COMPLETED"
    IN_PROGRESS = "IN_PROGRESS"
    ATTEMPTED_NOT_COMPLETED = "ATTEMPTED_NOT_COMPLETED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


class RequirementType(str, Enum):
    REQUIRED = "required"
    ELECTIVE = "elective"


@dataclass(frozen=True)
class ProgressStudyPlan:
    study_plan_id: str
    total_credit_hours: Decimal


@dataclass(frozen=True)
class ProgressRequirementGroup:
    group_id: str
    study_plan_id: str
    group_code: str
    name_ar: str
    name_en: str | None
    scope: str
    requirement_type: RequirementType
    required_credit_hours: Decimal
    display_order: int


@dataclass(frozen=True)
class ProgressPlanCourse:
    plan_course_id: str
    study_plan_id: str
    requirement_group_id: str
    course_code: str
    catalog_status: CourseCatalogStatus
    credit_hours: Decimal
    display_order: int
    course_name_ar: str | None = None
    course_name_en: str | None = None


@dataclass(frozen=True)
class AcademicProgressCatalog:
    study_plan: ProgressStudyPlan
    requirement_groups: tuple[ProgressRequirementGroup, ...]
    plan_courses: tuple[ProgressPlanCourse, ...]


@dataclass(frozen=True)
class CourseProgress:
    course_code: str
    credit_hours: Decimal
    requirement_group_id: str
    requirement_group_code: str
    state: CourseProgressState
    course_name_ar: str | None = None
    course_name_en: str | None = None


@dataclass(frozen=True)
class RequirementGroupProgress:
    group_id: str
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


@dataclass(frozen=True)
class AcademicProgress:
    study_plan_id: str
    plan_total_required_credits: Decimal
    completed_plan_credits: Decimal
    in_progress_plan_credits: Decimal
    remaining_plan_credits: Decimal
    satisfied_requirement_group_count: int
    total_requirement_group_count: int
    all_modeled_plan_requirements_satisfied: bool
    requirement_groups: tuple[RequirementGroupProgress, ...]
    courses: tuple[CourseProgress, ...]
    reported_cumulative_gpa: Decimal | None
    reported_gpa_scale: Decimal | None
    reported_earned_credit_hours: Decimal | None


class ProgressIntegrityError(RuntimeError):
    """Persisted plan data cannot form one internally consistent snapshot."""
