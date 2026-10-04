"""Immutable contracts for Student Intelligence policy 1.0."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.progress.models import AcademicProgress
from app.rules.models import CanTakeDecision, CanTakeError
from app.student.models import StudentCourseAttemptRecord

POLICY_VERSION = "1.0"


class IntelligenceCapability(str, Enum):
    PERFORMANCE_INTELLIGENCE = "PERFORMANCE_INTELLIGENCE"
    ACADEMIC_STRENGTH = "ACADEMIC_STRENGTH"
    ACADEMIC_DIFFICULTY_SIGNAL = "ACADEMIC_DIFFICULTY_SIGNAL"
    ACADEMIC_PREPARATION_READINESS = "ACADEMIC_PREPARATION_READINESS"
    STRUCTURAL_RISK_SIGNAL = "STRUCTURAL_RISK_SIGNAL"
    PREDICTIVE_ACADEMIC_RISK = "PREDICTIVE_ACADEMIC_RISK"


class IntelligenceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    BLOCKED_BY_EXTERNAL_DATA = "BLOCKED_BY_EXTERNAL_DATA"


class ReadinessState(str, Enum):
    PREPARATION_EVIDENCE_AVAILABLE = "PREPARATION_EVIDENCE_AVAILABLE"
    CAUTION_EVIDENCE_AVAILABLE = "CAUTION_EVIDENCE_AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class EvidenceType(str, Enum):
    ATTEMPT_OUTCOME = "ATTEMPT_OUTCOME"
    COURSE_ATTEMPT = "COURSE_ATTEMPT"
    VERIFIED_RAW_GRADE = "VERIFIED_RAW_GRADE"
    REQUIREMENT_PROGRESS = "REQUIREMENT_PROGRESS"
    COURSE_DEPENDENCY = "COURSE_DEPENDENCY"
    ELIGIBILITY_RESULT = "ELIGIBILITY_RESULT"
    ACADEMIC_PROGRESS = "ACADEMIC_PROGRESS"
    PROVENANCE = "PROVENANCE"
    VERIFICATION_STATE = "VERIFICATION_STATE"


class MissingInput(str, Enum):
    NO_ATTEMPT_HISTORY = "NO_ATTEMPT_HISTORY"
    NO_VERIFIED_PERFORMANCE_DATA = "NO_VERIFIED_PERFORMANCE_DATA"
    NO_APPROVED_GRADING_POLICY = "NO_APPROVED_GRADING_POLICY"
    NO_DOMAIN_TAXONOMY = "NO_DOMAIN_TAXONOMY"
    NO_COHORT_DATA = "NO_COHORT_DATA"
    UNRESOLVED_PREREQUISITE = "UNRESOLVED_PREREQUISITE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    NO_CANONICAL_PERIOD_ORDER = "NO_CANONICAL_PERIOD_ORDER"
    NO_TARGET_COURSE_CONTEXT = "NO_TARGET_COURSE_CONTEXT"


@dataclass(frozen=True)
class IntelligenceEvidence:
    identifier: str
    evidence_type: EvidenceType
    course_codes: tuple[str, ...] = ()
    attempt_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntelligenceObservation:
    rule_id: str
    value: str
    count: int | None = None
    course_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntelligenceResult:
    policy_version: str
    capability: IntelligenceCapability
    status: IntelligenceStatus
    observations: tuple[IntelligenceObservation, ...] = ()
    signals: tuple[IntelligenceObservation, ...] = ()
    reason_codes: tuple[str, ...] = ()
    evidence: tuple[IntelligenceEvidence, ...] = ()
    missing_inputs: tuple[MissingInput, ...] = ()
    limitations: tuple[str, ...] = ()
    readiness_state: ReadinessState | None = None


@dataclass(frozen=True)
class DependencyExposure:
    target_course_code: str
    blocking_course_codes: tuple[str, ...]
    required_target: bool = True
    review_required: bool = False


@dataclass(frozen=True)
class StudentIntelligenceContext:
    attempts: tuple[StudentCourseAttemptRecord, ...]
    progress: AcademicProgress | None = None
    required_course_codes: frozenset[str] = frozenset()
    dependency_exposures: tuple[DependencyExposure, ...] = ()


@dataclass(frozen=True)
class ReadinessContext:
    eligibility: CanTakeDecision | CanTakeError
    attempts: tuple[StudentCourseAttemptRecord, ...]


@dataclass(frozen=True)
class StudentIntelligenceBundle:
    policy_version: str
    performance: IntelligenceResult
    strengths: IntelligenceResult
    difficulty: IntelligenceResult
    structural_risk: IntelligenceResult
    predictive_risk: IntelligenceResult
    readiness: IntelligenceResult | None = None
