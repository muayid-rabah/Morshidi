"""Immutable domain contracts for the deterministic semester planning engine.

No FastAPI, Starlette, Supabase, httpx, or I/O dependency is permitted in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

# ---------------------------------------------------------------------------
# Policy Constants
# ---------------------------------------------------------------------------

SEMESTER_PLANNER_POLICY_VERSION = "1.0"
PLANNING_SCOPE = "ACADEMIC_STRUCTURE_ONLY"
DEFAULT_CANDIDATE_WINDOW_SIZE = 15
MAX_CREDIT_HOURS_SAFETY_CEILING = Decimal("30.00")

# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------


class PlannerConstraintError(ValueError):
    """Raised when user planning constraints fail validation."""


class PlannerIntegrityError(RuntimeError):
    """Raised when input catalogs or recommendation results fail integrity checks."""


# ---------------------------------------------------------------------------
# Reason Codes (from Phase 8.1 specification §15)
# ---------------------------------------------------------------------------


class PlanReasonCode(str, Enum):
    """Stable, machine-readable reason codes for generated semester plans."""

    CONTAINS_MANDATORY_COURSES = "CONTAINS_MANDATORY_COURSES"
    """Plan contains at least one course from a required requirement group."""

    INCLUDES_ZERO_CREDIT_REQUIRED = "INCLUDES_ZERO_CREDIT_REQUIRED"
    """Plan contains at least one zero-credit required study plan course."""

    COMPLETES_REQUIREMENT_GROUP = "COMPLETES_REQUIREMENT_GROUP"
    """Plan transitions exactly one requirement group from unsatisfied to satisfied."""

    COMPLETES_MULTIPLE_REQUIREMENT_GROUPS = "COMPLETES_MULTIPLE_REQUIREMENT_GROUPS"
    """Plan transitions two or more requirement groups from unsatisfied to satisfied."""

    MAXIMIZES_MODELED_CREDIT_PROGRESS = "MAXIMIZES_MODELED_CREDIT_PROGRESS"
    """Plan achieves the maximal modeled credit delta among all evaluated valid combinations."""

    UNLOCKS_FUTURE_COURSE = "UNLOCKS_FUTURE_COURSE"
    """Plan newly unlocks exactly one downstream course."""

    UNLOCKS_MULTIPLE_FUTURE_COURSES = "UNLOCKS_MULTIPLE_FUTURE_COURSES"
    """Plan newly unlocks two or more downstream courses."""

    NO_DIRECT_PREREQUISITE_IMPACT = "NO_DIRECT_PREREQUISITE_IMPACT"
    """Plan newly unlocks zero downstream courses."""

    USES_FULL_CREDIT_PREFERENCE = "USES_FULL_CREDIT_PREFERENCE"
    """Total planned credits exactly equals the requested max_credit_hours."""

    INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE = "INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE"
    """Plan includes at least one course where the student has a prior non-passing attempt."""


# ---------------------------------------------------------------------------
# Constraints Model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannerConstraints:
    """Immutable user planning preferences and presentation constraints."""

    max_credit_hours: Decimal
    max_courses: int | None = None
    max_options: int = 5

    def __post_init__(self) -> None:
        # Validate max_credit_hours
        raw_credits = self.max_credit_hours
        if isinstance(raw_credits, bool):
            raise PlannerConstraintError("max_credit_hours cannot be a boolean")
        if isinstance(raw_credits, float):
            raise PlannerConstraintError("max_credit_hours must be a Decimal, string, or integer, not float")
        try:
            if isinstance(raw_credits, int):
                dec_val = Decimal(str(raw_credits))
            elif isinstance(raw_credits, Decimal):
                dec_val = raw_credits
            elif isinstance(raw_credits, str):
                dec_val = Decimal(raw_credits)
            else:
                raise PlannerConstraintError(f"Unsupported type for max_credit_hours: {type(raw_credits)}")
        except PlannerConstraintError:
            raise
        except Exception as exc:
            raise PlannerConstraintError(f"Invalid max_credit_hours: {exc}") from exc

        if dec_val.is_nan() or dec_val.is_infinite():
            raise PlannerConstraintError("max_credit_hours must be a finite number")
        if dec_val < Decimal("0"):
            raise PlannerConstraintError("max_credit_hours cannot be negative")
        if dec_val > MAX_CREDIT_HOURS_SAFETY_CEILING:
            raise PlannerConstraintError(
                f"max_credit_hours cannot exceed safety limit of {MAX_CREDIT_HOURS_SAFETY_CEILING}"
            )
        object.__setattr__(self, "max_credit_hours", dec_val)

        # Validate max_courses
        if self.max_courses is not None:
            if isinstance(self.max_courses, bool) or not isinstance(self.max_courses, int):
                raise PlannerConstraintError("max_courses must be an integer or None")
            if self.max_courses < 1 or self.max_courses > 10:
                raise PlannerConstraintError("max_courses must be between 1 and 10")

        # Validate max_options
        if isinstance(self.max_options, bool) or not isinstance(self.max_options, int):
            raise PlannerConstraintError("max_options must be an integer")
        if self.max_options < 1 or self.max_options > 10:
            raise PlannerConstraintError("max_options must be between 1 and 10")


# ---------------------------------------------------------------------------
# Result Domain Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedCourseEntry:
    """A selected course entry within a proposed semester plan option."""

    course_code: str
    course_name_ar: str | None
    course_name_en: str | None
    credit_hours: Decimal
    requirement_group_code: str
    requirement_type: str  # "required" | "elective"
    phase7_rank: int  # 1-based rank from Phase 7 RecommendationCandidate.rank
    previously_attempted: bool
    display_order: int  # from study_plan_courses for stable canonical presentation


@dataclass(frozen=True)
class SemesterPlanOption:
    """A single ranked course combination option for the semester."""

    rank: int  # 1-based rank within returned options (1 = best)
    courses: tuple[PlannedCourseEntry, ...]  # Ordered by display_order, course_code
    total_credit_hours: Decimal
    total_courses: int
    mandatory_course_count: int  # P1
    zero_credit_required_count: int
    completed_plan_credit_delta: Decimal  # P3
    newly_satisfied_requirement_group_codes: tuple[str, ...]
    newly_satisfied_requirement_group_count: int  # P2
    newly_eligible_course_codes: tuple[str, ...]  # sorted ascending by course_code
    newly_eligible_count: int  # P4
    recommendation_rank_sum: int  # P6 (sum of phase7_rank)
    priority_tuple: tuple[int, int, Decimal, int, Decimal, int, tuple[str, ...]]
    reason_codes: tuple[PlanReasonCode, ...]
    memorization_heavy_count: int = 0
    learning_type_counts: tuple[tuple[str, int], ...] = ()
    estimated_workload: str = "UNKNOWN"
    balance_warning: str | None = None


@dataclass(frozen=True)
class SemesterPlannerResult:
    """Complete deterministic result returned by the semester planning engine."""

    study_plan_id: str
    semester_planner_policy_version: str
    planning_scope: str  # "ACADEMIC_STRUCTURE_ONLY"
    constraints: PlannerConstraints
    candidate_window_size: int
    eligible_ranked_candidate_count: int
    evaluated_candidate_count: int
    valid_combination_count: int
    plan_options: tuple[SemesterPlanOption, ...]
    review_required_courses: tuple[str, ...]
    excluded_in_progress: tuple[str, ...]
    methodology_note: str
    limitations: tuple[str, ...]
    balance_relaxation_required: bool = False
    balance_policy_version: str = "MODELED_COURSE_LOAD_PROFILE_V1"

