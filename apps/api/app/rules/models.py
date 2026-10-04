"""Immutable, transport-independent contracts for prerequisite evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Decision(str, Enum):
    """The only academic prerequisite decisions the engine can make."""

    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class AttemptOutcome(str, Enum):
    """Minimal outcome facts required for completion-based prerequisites."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    IN_PROGRESS = "IN_PROGRESS"
    WITHDRAWN = "WITHDRAWN"


class PrerequisiteLogicStatus(str, Enum):
    """Persisted academic-source confidence of a plan course's prerequisite."""

    NOT_APPLICABLE = "not_applicable"
    VERIFIED = "verified"
    UNRESOLVED = "unresolved"
    SOURCE_CONFLICT = "source_conflict"


class DependencyType(str, Enum):
    """Dependency kinds supported by the catalog model."""

    PREREQUISITE = "prerequisite"
    COREQUISITE = "corequisite"


class DecisionReason(str, Enum):
    NO_PREREQUISITES = "NO_PREREQUISITES"
    PREREQUISITES_SATISFIED = "PREREQUISITES_SATISFIED"
    MISSING_PREREQUISITE_GROUP = "MISSING_PREREQUISITE_GROUP"
    PREREQUISITE_LOGIC_UNRESOLVED = "PREREQUISITE_LOGIC_UNRESOLVED"
    PREREQUISITE_SOURCE_CONFLICT = "PREREQUISITE_SOURCE_CONFLICT"
    VERIFIED_PREREQUISITE_MODEL_INCOMPLETE = "VERIFIED_PREREQUISITE_MODEL_INCOMPLETE"
    TARGET_ALREADY_COMPLETED = "TARGET_ALREADY_COMPLETED"
    TARGET_CURRENTLY_ENROLLED = "TARGET_CURRENTLY_ENROLLED"
    GRADUATION_PROJECT_MIN_EARNED_CREDITS = "GRADUATION_PROJECT_MIN_EARNED_CREDITS"
    GRADUATION_PROJECT_CREDIT_EVIDENCE_UNKNOWN = "GRADUATION_PROJECT_CREDIT_EVIDENCE_UNKNOWN"


class RequestErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    STUDY_PLAN_NOT_FOUND = "STUDY_PLAN_NOT_FOUND"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_NOT_IN_STUDY_PLAN = "TARGET_NOT_IN_STUDY_PLAN"


class CourseCatalogStatus(str, Enum):
    KNOWN = "known"
    REFERENCED_ONLY = "referenced_only"
    LEGACY = "legacy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class StudentCourseAttempt:
    course_code: str
    outcome: AttemptOutcome


@dataclass(frozen=True)
class DependencyGroup:
    """Options are OR'ed; groups are AND'ed by the evaluator."""

    group_number: int
    dependency_type: DependencyType
    option_course_codes: tuple[str, ...]


@dataclass(frozen=True)
class PlanCourseRule:
    course_code: str
    prerequisite_logic_status: PrerequisiteLogicStatus
    dependency_groups: tuple[DependencyGroup, ...] = ()
    raw_prerequisite_text: str | None = None
    target_name_ar: str | None = None
    credit_hours: Decimal | None = None
    target_name_en: str | None = None


@dataclass(frozen=True)
class CourseIdentity:
    course_code: str
    catalog_status: CourseCatalogStatus


@dataclass(frozen=True)
class CanTakeCatalog:
    study_plan_id: str
    plan_courses: tuple[PlanCourseRule, ...]
    courses: tuple[CourseIdentity, ...]
    complete_plan_credits: bool = False


@dataclass(frozen=True)
class CanTakeRequest:
    study_plan_id: str
    target_course_code: str
    student_attempts: tuple[StudentCourseAttempt, ...]
    earned_completed_credits: Decimal | None = None


@dataclass(frozen=True)
class AcademicRuleTrace:
    rule_id: str
    rule_version: str
    provenance: str
    required_credits: Decimal
    earned_completed_credits: Decimal | None
    result: str
    reason_ar: str
    reason_en: str


@dataclass(frozen=True)
class TargetAttemptState:
    has_passed_target: bool
    has_in_progress_target: bool


@dataclass(frozen=True)
class DependencyGroupEvidence:
    group_number: int
    dependency_type: DependencyType
    option_course_codes: tuple[str, ...]
    passed_option_course_codes: tuple[str, ...]
    non_passed_option_course_codes: tuple[str, ...]


@dataclass(frozen=True)
class CanTakeDecision:
    kind: str
    decision: Decision
    study_plan_id: str
    target_course_code: str
    prerequisite_logic_status: PrerequisiteLogicStatus
    target_attempt_state: TargetAttemptState
    satisfied_dependency_groups: tuple[DependencyGroupEvidence, ...]
    missing_dependency_groups: tuple[DependencyGroupEvidence, ...]
    reasons: tuple[DecisionReason, ...]
    review_reasons: tuple[DecisionReason, ...]
    raw_prerequisite_text: str | None
    target_name_ar: str | None
    academic_rule_traces: tuple[AcademicRuleTrace, ...] = ()
    target_name_en: str | None = None


@dataclass(frozen=True)
class CanTakeError:
    kind: str
    error_code: RequestErrorCode
    study_plan_id: str | None
    target_course_code: str | None
