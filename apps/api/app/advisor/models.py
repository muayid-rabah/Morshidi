"""Pure, immutable contracts for the Morshidi AI Academic Advisor.

This module defines Phase 10.2 domain contracts only. It contains no academic
decision logic, orchestration, provider integration, transport, persistence,
or environment access.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import TypeAlias

from app.degree_path.models import DegreePathConstraints, DegreePathOption, DegreePathResult
from app.planner.models import PlannerConstraints, SemesterPlanOption, SemesterPlannerResult
from app.progress.models import AcademicProgress
from app.recommendations.models import RecommendationCandidate, RecommendationResult
from app.rules.models import CanTakeDecision, CanTakeError


AI_ADVISOR_POLICY_VERSION = "1.0"


class AdvisorContractError(ValueError):
    """Raised when an advisor domain contract is internally inconsistent."""


class AdvisorIntent(str, Enum):
    """Finite routing categories established by the Phase 10.1 policy."""

    ACADEMIC_STATUS = "ACADEMIC_STATUS"
    """Explain current academic progress or stored academic-state facts."""

    COURSE_ELIGIBILITY = "COURSE_ELIGIBILITY"
    """Obtain or explain the Phase 5 decision for one resolved course."""

    COURSE_RECOMMENDATIONS = "COURSE_RECOMMENDATIONS"
    """Obtain or explain the existing Phase 7 recommendation ordering."""

    REMAINING_REQUIREMENTS = "REMAINING_REQUIREMENTS"
    """Explain incomplete modeled requirements from Phase 6 progress."""

    SEMESTER_PLANNING = "SEMESTER_PLANNING"
    """Obtain, explain, or compare Phase 8 next-registration-set options."""

    DEGREE_PATH_MODELING = "DEGREE_PATH_MODELING"
    """Obtain, explain, or compare Phase 9 modeled multi-semester paths."""

    OPTION_COMPARISON = "OPTION_COMPARISON"
    """Compare existing deterministic options without reranking them."""

    COURSE_INFORMATION = "COURSE_INFORMATION"
    """Return canonical catalog facts for a resolved course."""

    GENERAL_ACADEMIC_INFORMATION = "GENERAL_ACADEMIC_INFORMATION"
    """Explain a general concept without a student-specific decision."""

    GENERAL_CHAT = "GENERAL_CHAT"
    """Conversational answer with no student-specific academic authority."""

    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    """Represent an intent, entity, option, or constraint ambiguity."""

    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    """Represent a request outside the initial advisor's authority."""


class AnswerAuthority(str, Enum):
    """Semantic authority of an advisor result; never a confidence score."""

    DETERMINISTIC = "DETERMINISTIC"
    """Grounded in authoritative catalog, state, or Phase 5-9 output."""

    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    """Verified state explicitly requires academic or manual review."""

    GENERAL_INFORMATION = "GENERAL_INFORMATION"
    """General education content with no student-specific decision."""

    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    """Available authoritative context cannot safely support an answer."""


class AuthoritativeSource(str, Enum):
    """Application subsystems that may supply authoritative evidence."""

    ACADEMIC_CATALOG = "ACADEMIC_CATALOG"
    STUDENT_ACADEMIC_STATE = "STUDENT_ACADEMIC_STATE"
    PHASE5_ELIGIBILITY = "PHASE5_ELIGIBILITY"
    PHASE6_PROGRESS = "PHASE6_PROGRESS"
    PHASE7_RECOMMENDATIONS = "PHASE7_RECOMMENDATIONS"
    PHASE8_SEMESTER_PLANNER = "PHASE8_SEMESTER_PLANNER"
    PHASE9_DEGREE_PATH = "PHASE9_DEGREE_PATH"


class PolicySource(str, Enum):
    """Non-academic policy identities that may be versioned in a trace."""

    AI_ADVISOR = "AI_ADVISOR"


class EntityResolutionStatus(str, Enum):
    """Outcome of resolving a user course reference against catalog data."""

    RESOLVED = "RESOLVED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"


class ClarificationReason(str, Enum):
    """Finite reasons that require user clarification before orchestration."""

    AMBIGUOUS_COURSE = "AMBIGUOUS_COURSE"
    MISSING_COURSE = "MISSING_COURSE"
    AMBIGUOUS_INTENT = "AMBIGUOUS_INTENT"
    MISSING_REQUIRED_CONSTRAINT = "MISSING_REQUIRED_CONSTRAINT"
    AMBIGUOUS_OPTION_REFERENCE = "AMBIGUOUS_OPTION_REFERENCE"


class OutOfScopeReason(str, Enum):
    """Small initial classification for unsupported requests."""

    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    REQUIRES_OFFICIAL_AUTHORITY = "REQUIRES_OFFICIAL_AUTHORITY"
    REQUIRES_UNMODELED_DATA = "REQUIRES_UNMODELED_DATA"


_SOURCE_ORDER = {source: index for index, source in enumerate(AuthoritativeSource)}
_POLICY_SOURCE_ORDER = {
    PolicySource.AI_ADVISOR: 0,
    **{source: index + 1 for index, source in enumerate(AuthoritativeSource)},
}


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdvisorContractError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise AdvisorContractError(f"{field_name} must not contain surrounding whitespace")
    return value


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _sorted_unique_strings(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(_required_text(value, field_name) for value in values)
    return tuple(sorted(set(normalized)))


@dataclass(frozen=True)
class ResolvedCourseReference:
    """Canonical course identity resolved exclusively from authoritative data."""

    course_code: str
    canonical_arabic_name: str
    canonical_english_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "course_code", _required_text(self.course_code, "course_code"))
        object.__setattr__(
            self,
            "canonical_arabic_name",
            _required_text(self.canonical_arabic_name, "canonical_arabic_name"),
        )
        object.__setattr__(
            self,
            "canonical_english_name",
            _optional_text(self.canonical_english_name, "canonical_english_name"),
        )


@dataclass(frozen=True)
class CourseResolution:
    """Explicit resolved, not-found, or ambiguous course-resolution outcome."""

    status: EntityResolutionStatus
    resolved_course: ResolvedCourseReference | None = None
    candidate_course_codes: tuple[str, ...] = ()
    candidate_courses: tuple[ResolvedCourseReference, ...] = ()

    def __post_init__(self) -> None:
        candidates = _sorted_unique_strings(
            self.candidate_course_codes,
            "candidate_course_codes",
        )
        object.__setattr__(self, "candidate_course_codes", candidates)
        if self.candidate_courses and (
                {course.course_code for course in self.candidate_courses} != set(candidates) or
                len(self.candidate_courses) != len(candidates)):
            raise AdvisorContractError("Candidate display identities must match candidate codes")

        if self.status is EntityResolutionStatus.RESOLVED:
            if self.resolved_course is None:
                raise AdvisorContractError("RESOLVED requires resolved_course")
            if candidates:
                raise AdvisorContractError("RESOLVED must not include candidate_course_codes")
        elif self.status is EntityResolutionStatus.NOT_FOUND:
            if self.resolved_course is not None or candidates:
                raise AdvisorContractError("NOT_FOUND cannot include a course or candidates")
        elif self.status is EntityResolutionStatus.AMBIGUOUS:
            if self.resolved_course is not None:
                raise AdvisorContractError("AMBIGUOUS cannot include resolved_course")
            if len(candidates) < 2:
                raise AdvisorContractError("AMBIGUOUS requires at least two candidate course codes")


@dataclass(frozen=True)
class DecisionReference:
    """Exact upstream reason, decision, status, or blocker code with its source."""

    source: AuthoritativeSource
    code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _required_text(self.code, "decision code"))


@dataclass(frozen=True)
class PolicyVersionReference:
    """Version emitted by a source that defines an explicit policy version."""

    source: AuthoritativeSource | PolicySource
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _required_text(self.version, "policy version"))


@dataclass(frozen=True)
class AdvisorEvidence:
    """Minimal reference to authoritative material used for explanation.

    The referenced Phase 5-9 result remains the source of truth; this model does
    not copy or reinterpret its academic payload.
    """

    source: AuthoritativeSource
    result_reference: str
    course_codes: tuple[str, ...] = ()
    decision_references: tuple[DecisionReference, ...] = ()
    policy_version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "result_reference",
            _required_text(self.result_reference, "result_reference"),
        )
        object.__setattr__(
            self,
            "course_codes",
            _sorted_unique_strings(self.course_codes, "course_codes"),
        )
        references = tuple(
            sorted(
                set(self.decision_references),
                key=lambda item: (_SOURCE_ORDER[item.source], item.code),
            )
        )
        if any(reference.source is not self.source for reference in references):
            raise AdvisorContractError(
                "AdvisorEvidence decision references must use the evidence source"
            )
        object.__setattr__(self, "decision_references", references)
        object.__setattr__(
            self,
            "policy_version",
            _optional_text(self.policy_version, "policy_version"),
        )


PlanningConstraints: TypeAlias = PlannerConstraints | DegreePathConstraints


@dataclass(frozen=True)
class CourseInformation:
    """Authoritative catalog facts for one resolved course, without inference."""

    course_code: str
    canonical_arabic_name: str
    canonical_english_name: str | None = None
    credit_hours: Decimal | None = None
    requirement_group_code: str | None = None
    catalog_status: str | None = None
    prerequisite_logic_status: str | None = None
    raw_prerequisite_text: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "course_code", _required_text(self.course_code, "course_code"))
        object.__setattr__(
            self,
            "canonical_arabic_name",
            _required_text(self.canonical_arabic_name, "canonical_arabic_name"),
        )
        for field_name in (
            "canonical_english_name",
            "requirement_group_code",
            "catalog_status",
            "prerequisite_logic_status",
            "raw_prerequisite_text",
        ):
            object.__setattr__(self, field_name, _optional_text(getattr(self, field_name), field_name))
        if self.credit_hours is not None:
            if not isinstance(self.credit_hours, Decimal) or not self.credit_hours.is_finite():
                raise AdvisorContractError("credit_hours must be a finite Decimal or None")
            if self.credit_hours < Decimal("0"):
                raise AdvisorContractError("credit_hours cannot be negative")


AdvisorPayload: TypeAlias = (
    CanTakeDecision
    | CanTakeError
    | AcademicProgress
    | RecommendationResult
    | SemesterPlannerResult
    | DegreePathResult
    | CourseInformation
    | tuple[RecommendationCandidate, ...]
    | tuple[SemesterPlanOption, ...]
    | tuple[DegreePathOption, ...]
)


@dataclass(frozen=True)
class ClarificationRequest:
    """Deterministic clarification requirement without generated answer text."""

    reason: ClarificationReason
    message_key: str
    candidate_course_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "message_key", _required_text(self.message_key, "message_key"))
        candidates = _sorted_unique_strings(
            self.candidate_course_codes,
            "candidate_course_codes",
        )
        object.__setattr__(self, "candidate_course_codes", candidates)
        if self.reason is ClarificationReason.AMBIGUOUS_COURSE and len(candidates) < 2:
            raise AdvisorContractError(
                "AMBIGUOUS_COURSE clarification requires at least two candidates"
            )
        if self.reason is not ClarificationReason.AMBIGUOUS_COURSE and candidates:
            raise AdvisorContractError(
                "Only AMBIGUOUS_COURSE clarification may include course candidates"
            )


@dataclass(frozen=True)
class AdvisorTrace:
    """Internal, deterministic, secret-free trace for one advisor result."""

    advisor_intent: AdvisorIntent
    answer_authority: AnswerAuthority
    authoritative_sources_used: tuple[AuthoritativeSource, ...] = ()
    course_codes: tuple[str, ...] = ()
    decision_references: tuple[DecisionReference, ...] = ()
    policy_versions: tuple[PolicyVersionReference, ...] = ()
    planning_constraints: PlanningConstraints | None = None
    option_references: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        sources = tuple(
            sorted(set(self.authoritative_sources_used), key=lambda item: _SOURCE_ORDER[item])
        )
        object.__setattr__(self, "authoritative_sources_used", sources)
        object.__setattr__(
            self,
            "course_codes",
            _sorted_unique_strings(self.course_codes, "course_codes"),
        )

        decisions = tuple(
            sorted(
                set(self.decision_references),
                key=lambda item: (_SOURCE_ORDER[item.source], item.code),
            )
        )
        if any(reference.source not in sources for reference in decisions):
            raise AdvisorContractError(
                "decision reference sources must appear in authoritative_sources_used"
            )
        object.__setattr__(self, "decision_references", decisions)

        versions = tuple(
            sorted(
                set(self.policy_versions),
                key=lambda item: (_POLICY_SOURCE_ORDER[item.source], item.version),
            )
        )
        if any(
            isinstance(reference.source, AuthoritativeSource)
            and reference.source not in sources
            for reference in versions
        ):
            raise AdvisorContractError(
                "policy version sources must appear in authoritative_sources_used"
            )
        object.__setattr__(self, "policy_versions", versions)

        option_references = tuple(sorted(set(self.option_references)))
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in option_references):
            raise AdvisorContractError("option_references must contain positive integers")
        object.__setattr__(self, "option_references", option_references)

        if self.answer_authority is AnswerAuthority.GENERAL_INFORMATION:
            if (
                sources
                or decisions
                or self.course_codes
                or self.planning_constraints
                or any(reference.source is not PolicySource.AI_ADVISOR for reference in versions)
            ):
                raise AdvisorContractError(
                    "GENERAL_INFORMATION trace cannot claim student-specific authoritative evidence"
                )


@dataclass(frozen=True)
class NormalizedAdvisorRequest:
    """Internal request after intent interpretation and entity resolution."""

    user_message: str
    intent: AdvisorIntent
    course_resolution: CourseResolution | None = None
    planning_constraints: PlanningConstraints | None = None
    option_references: tuple[int, ...] = ()
    clarification_request: ClarificationRequest | None = None
    out_of_scope_reason: OutOfScopeReason | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_message", _required_text(self.user_message, "user_message"))
        options = tuple(sorted(set(self.option_references)))
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in options):
            raise AdvisorContractError("option_references must contain positive integers")
        object.__setattr__(self, "option_references", options)

        if isinstance(self.planning_constraints, PlannerConstraints):
            if self.intent is not AdvisorIntent.SEMESTER_PLANNING:
                raise AdvisorContractError(
                    "PlannerConstraints are valid only for SEMESTER_PLANNING"
                )
        elif isinstance(self.planning_constraints, DegreePathConstraints):
            if self.intent is not AdvisorIntent.DEGREE_PATH_MODELING:
                raise AdvisorContractError(
                    "DegreePathConstraints are valid only for DEGREE_PATH_MODELING"
                )
        elif self.planning_constraints is not None:
            raise AdvisorContractError("unsupported planning constraints type")

        if self.intent is AdvisorIntent.CLARIFICATION_REQUIRED:
            if self.clarification_request is None:
                raise AdvisorContractError(
                    "CLARIFICATION_REQUIRED request requires clarification_request"
                )
        elif self.clarification_request is not None:
            raise AdvisorContractError(
                "clarification_request is valid only for CLARIFICATION_REQUIRED"
            )

        if self.intent is AdvisorIntent.OUT_OF_SCOPE:
            if self.out_of_scope_reason is None:
                raise AdvisorContractError("OUT_OF_SCOPE request requires out_of_scope_reason")
        elif self.out_of_scope_reason is not None:
            raise AdvisorContractError(
                "out_of_scope_reason is valid only for OUT_OF_SCOPE"
            )


@dataclass(frozen=True)
class StructuredAdvisorResult:
    """Provider-neutral orchestration result before natural-language generation."""

    intent: AdvisorIntent
    authority: AnswerAuthority
    trace: AdvisorTrace
    course_resolution: CourseResolution | None = None
    evidence: tuple[AdvisorEvidence, ...] = ()
    clarification: ClarificationRequest | None = None
    out_of_scope_reason: OutOfScopeReason | None = None
    authoritative_payload: AdvisorPayload | None = None

    def __post_init__(self) -> None:
        if self.trace.advisor_intent is not self.intent:
            raise AdvisorContractError("trace intent must match result intent")
        if self.trace.answer_authority is not self.authority:
            raise AdvisorContractError("trace authority must match result authority")

        evidence = tuple(
            sorted(
                set(self.evidence),
                key=lambda item: (
                    _SOURCE_ORDER[item.source],
                    item.result_reference,
                    item.course_codes,
                ),
            )
        )
        object.__setattr__(self, "evidence", evidence)

        evidence_sources = {item.source for item in evidence}
        if not evidence_sources.issubset(set(self.trace.authoritative_sources_used)):
            raise AdvisorContractError("evidence sources must appear in the trace")

        if self.authority is AnswerAuthority.DETERMINISTIC and not evidence:
            raise AdvisorContractError("DETERMINISTIC result requires authoritative evidence")
        if self.authority is AnswerAuthority.REVIEW_REQUIRED:
            if not evidence or not any(item.decision_references for item in evidence):
                raise AdvisorContractError(
                    "REVIEW_REQUIRED result requires evidence retaining upstream decision references"
                )
        if self.authority is AnswerAuthority.GENERAL_INFORMATION and evidence:
            raise AdvisorContractError(
                "GENERAL_INFORMATION result cannot carry student-specific evidence"
            )

        if self.intent is AdvisorIntent.CLARIFICATION_REQUIRED:
            if self.authority is not AnswerAuthority.INSUFFICIENT_CONTEXT:
                raise AdvisorContractError(
                    "CLARIFICATION_REQUIRED must use INSUFFICIENT_CONTEXT authority"
                )
            if self.clarification is None:
                raise AdvisorContractError(
                    "CLARIFICATION_REQUIRED result requires a clarification contract"
                )
        elif self.clarification is not None:
            raise AdvisorContractError(
                "clarification is valid only for CLARIFICATION_REQUIRED results"
            )

        if self.intent is AdvisorIntent.OUT_OF_SCOPE:
            if self.authority is not AnswerAuthority.INSUFFICIENT_CONTEXT:
                raise AdvisorContractError(
                    "OUT_OF_SCOPE must use INSUFFICIENT_CONTEXT authority"
                )
            if self.out_of_scope_reason is None:
                raise AdvisorContractError("OUT_OF_SCOPE requires out_of_scope_reason")
        elif self.out_of_scope_reason is not None:
            raise AdvisorContractError(
                "out_of_scope_reason is valid only for OUT_OF_SCOPE results"
            )
