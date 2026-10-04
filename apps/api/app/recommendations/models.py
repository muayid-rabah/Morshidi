"""Immutable domain contracts for the deterministic recommendation engine.

No FastAPI, Supabase, httpx, or I/O dependency is permitted in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Policy version
# ---------------------------------------------------------------------------

RECOMMENDATION_POLICY_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Reason codes (stable vocabulary from Phase 7.1 spec §19)
# ---------------------------------------------------------------------------


class RecommendationReason(str, Enum):
    """Stable, machine-readable reason codes for recommendation candidates."""

    REQUIRED_PLAN_COURSE = "REQUIRED_PLAN_COURSE"
    """Candidate belongs to a required requirement group."""

    MANDATORY_ZERO_CREDIT_COURSE = "MANDATORY_ZERO_CREDIT_COURSE"
    """Required plan course with credit_hours == 0."""

    ADVANCES_REQUIRED_GROUP = "ADVANCES_REQUIRED_GROUP"
    """Hypothetical pass contributes credits toward an unsatisfied required group."""

    ADVANCES_ELECTIVE_REQUIREMENT = "ADVANCES_ELECTIVE_REQUIREMENT"
    """Hypothetical pass contributes credits toward an unsatisfied elective group."""

    COMPLETES_REQUIREMENT_GROUP = "COMPLETES_REQUIREMENT_GROUP"
    """Hypothetical pass transitions the requirement group from unsatisfied to satisfied."""

    UNLOCKS_FUTURE_COURSE = "UNLOCKS_FUTURE_COURSE"
    """Hypothetical pass makes exactly one other plan course newly eligible."""

    UNLOCKS_MULTIPLE_FUTURE_COURSES = "UNLOCKS_MULTIPLE_FUTURE_COURSES"
    """Hypothetical pass makes two or more plan courses newly eligible."""

    NO_REMAINING_GROUP_NEED = "NO_REMAINING_GROUP_NEED"
    """Candidate's requirement group already has zero remaining required credits."""

    PREVIOUSLY_ATTEMPTED = "PREVIOUSLY_ATTEMPTED"
    """Student has at least one prior non-passing attempt for this course."""

    NO_DIRECT_PREREQUISITE_IMPACT = "NO_DIRECT_PREREQUISITE_IMPACT"
    """Hypothetical pass does not unlock any currently ineligible plan course."""


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecommendationCandidate:
    """A single ranked recommendation candidate.

    All fields required for ranking, explanation, and auditability are included.
    Internal DB identifiers (plan_course_id, group_id, profile_id) are excluded.
    """

    course_code: str
    course_name_ar: str | None
    credit_hours: Decimal
    requirement_group_code: str
    requirement_type: str           # "required" | "elective"

    # Course progress state — ATTEMPTED_NOT_COMPLETED or NOT_ATTEMPTED only
    course_state: str               # CourseProgressState value

    # Phase 5 decision — always "ELIGIBLE" for ranked candidates
    eligibility_decision: str

    # --- Factors derived from progress simulation ---
    effective_credit_contribution: Decimal
    """Credits this candidate contributes toward remaining group need (capped for elective)."""

    group_remaining_credits_before: Decimal
    """Remaining required credits in the group before this candidate is hypothetically passed."""

    group_remaining_credits_after: Decimal
    """Remaining required credits in the group after this candidate is hypothetically passed."""

    completes_requirement_group: bool
    """True when the hypothetical pass transitions the group from unsatisfied to satisfied."""

    # --- Factors derived from eligibility simulation ---
    newly_eligible_count: int
    """Number of currently non-eligible plan courses that become ELIGIBLE after hypothetical pass."""

    newly_eligible_course_codes: tuple[str, ...]
    """Exact codes of those newly eligible courses, sorted ascending."""

    # --- Priority tuple for auditability (P1..P7) ---
    priority_tuple: tuple[int, int, Decimal, int, int, int, str]
    """
    Lexicographic sort key:
      P1: required_mandatory_priority  (2 = positive-credit required, 1 = zero-credit required, 0 = elective)
      P2: group_has_remaining_need     (1 = remaining need exists, 0 = satisfied)
      P3: effective_credit_contribution (Decimal, higher is better)
      P4: completes_requirement_group  (1 = True, 0 = False)
      P5: newly_eligible_count         (int, higher is better)
      P6: -display_order               (int, lower display_order wins → negate)
      P7: course_code                  (str, ascending)
    """

    # --- Context ---
    rank: int
    """1-based rank within ranked_recommendations."""

    reason_codes: tuple[RecommendationReason, ...]
    """Mechanically derived reason codes from Phase 7.1 §19 vocabulary."""

    previously_attempted: bool
    """True when course_state is ATTEMPTED_NOT_COMPLETED."""
    course_name_en: str | None = None


@dataclass(frozen=True)
class ReviewRequiredCourse:
    """A plan course excluded from ranking because Phase 5 returned REVIEW_REQUIRED."""

    course_code: str
    course_name_ar: str | None
    credit_hours: Decimal
    requirement_group_code: str
    requirement_type: str           # "required" | "elective"
    review_reason: str
    """Phase 5 DecisionReason string (PREREQUISITE_LOGIC_UNRESOLVED / PREREQUISITE_SOURCE_CONFLICT)."""
    previously_attempted: bool
    course_name_en: str | None = None


@dataclass(frozen=True)
class RecommendationResult:
    """Complete deterministic recommendation result for one student plan."""

    study_plan_id: str
    recommendation_policy_version: str

    ranked_recommendations: tuple[RecommendationCandidate, ...]
    """All eligible, degree-progress-useful candidates, ordered by rank (rank=1 is best)."""

    review_required_courses: tuple[ReviewRequiredCourse, ...]
    """Incomplete plan courses with REVIEW_REQUIRED Phase 5 decision."""

    excluded_in_progress: tuple[str, ...]
    """Course codes of plan courses currently IN_PROGRESS (informational)."""

    methodology_note: str
    limitations: tuple[str, ...]

