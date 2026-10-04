"""Immutable, transport-independent contracts for P4 Decision Intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.degree_path.models import DegreePathConstraints, DegreePathResult
from app.progress.models import AcademicProgress, AcademicProgressCatalog
from app.recommendations.models import RecommendationCandidate, RecommendationResult
from app.rules.models import CanTakeCatalog, StudentCourseAttempt
from app.student_intelligence.models import IntelligenceResult

DECISION_INTELLIGENCE_INTEGRATION_POLICY_VERSION = "1.0"
DELAY_CONSEQUENCE_POLICY_VERSION = "1.0"


class DecisionMode(str, Enum):
    STRUCTURAL_BASELINE = "STRUCTURAL_BASELINE"
    READINESS_AWARE = "READINESS_AWARE"


class FactorClassification(str, Enum):
    HARD_GATE = "HARD_GATE"
    ORDERING_FACTOR = "ORDERING_FACTOR"
    EXPLANATION_ONLY = "EXPLANATION_ONLY"
    NOT_ALLOWED = "NOT_ALLOWED"


class FactorAction(str, Enum):
    APPLY = "APPLY"
    ABSTAIN = "ABSTAIN"


class FactorReason(str, Enum):
    P4_READINESS_PREPARATION_TIE_BREAK = "P4_READINESS_PREPARATION_TIE_BREAK"
    P4_READINESS_CAUTION_TIE_BREAK = "P4_READINESS_CAUTION_TIE_BREAK"
    P4_READINESS_NOT_APPLICABLE_TIE_BREAK = "P4_READINESS_NOT_APPLICABLE_TIE_BREAK"
    P4_ABSTAIN_BASELINE_MODE = "P4_ABSTAIN_BASELINE_MODE"
    P4_ABSTAIN_MISSING_RESULT = "P4_ABSTAIN_MISSING_RESULT"
    P4_ABSTAIN_STATUS = "P4_ABSTAIN_STATUS"
    P4_ABSTAIN_REVIEW_REQUIRED = "P4_ABSTAIN_REVIEW_REQUIRED"
    P4_ABSTAIN_IDENTITY_MISMATCH = "P4_ABSTAIN_IDENTITY_MISMATCH"
    P4_ABSTAIN_POLICY_MISMATCH = "P4_ABSTAIN_POLICY_MISMATCH"
    P4_ABSTAIN_UNVERIFIED_EVIDENCE = "P4_ABSTAIN_UNVERIFIED_EVIDENCE"
    P4_ABSTAIN_INCOMPLETE_PROVENANCE = "P4_ABSTAIN_INCOMPLETE_PROVENANCE"
    P4_ABSTAIN_UNSUPPORTED_STATE = "P4_ABSTAIN_UNSUPPORTED_STATE"


class SimulationStateKind(str, Enum):
    AUTHORITATIVE = "AUTHORITATIVE"
    SIMULATED = "SIMULATED"


@dataclass(frozen=True)
class SimulationProvenance:
    state_kind: SimulationStateKind
    state_reference: str
    parent_state_reference: str | None = None
    scenario_id: str | None = None

    def __post_init__(self) -> None:
        if not self.state_reference.strip():
            raise ValueError("state_reference must be nonblank")
        if self.state_kind is SimulationStateKind.SIMULATED:
            if not self.parent_state_reference or not self.parent_state_reference.strip():
                raise ValueError("simulated state requires parent_state_reference")
            if not self.scenario_id or not self.scenario_id.strip():
                raise ValueError("simulated state requires scenario_id")


@dataclass(frozen=True)
class EvidenceReference:
    source: str
    identifier: str
    course_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadinessFactorInput:
    course_code: str
    result_course_code: str
    result: IntelligenceResult | None
    evidence_verified: bool = True
    provenance_complete: bool = True


@dataclass(frozen=True)
class FactorEvaluation:
    factor_id: str
    classification: FactorClassification
    action: FactorAction
    categorical_value: str | None
    ordering_value: int | None
    reason: FactorReason
    evidence_references: tuple[EvidenceReference, ...] = ()


@dataclass(frozen=True)
class RelativeOrderChange:
    course_code: str
    baseline_rank: int
    final_rank: int


@dataclass(frozen=True)
class DecisionIntelligenceTrace:
    decision_type: str
    decision_mode: DecisionMode
    base_policy_name: str
    base_policy_version: str
    integration_policy_version: str
    intelligence_policy_version: str
    baseline_order: tuple[str, ...]
    applied_factors: tuple[FactorEvaluation, ...]
    ignored_factors: tuple[FactorEvaluation, ...]
    changed_relative_orders: tuple[RelativeOrderChange, ...]
    final_order: tuple[str, ...]
    limitations: tuple[str, ...]
    simulation_provenance: SimulationProvenance


@dataclass(frozen=True)
class DecisionCandidateView:
    candidate: RecommendationCandidate
    baseline_rank: int
    final_rank: int
    readiness_factor: FactorEvaluation


@dataclass(frozen=True)
class EnhancedRecommendationResult:
    baseline_result: RecommendationResult
    decision_mode: DecisionMode
    ranked_candidates: tuple[DecisionCandidateView, ...]
    trace: DecisionIntelligenceTrace


@dataclass(frozen=True)
class CourseIntelligenceAnnotation:
    course_code: str
    readiness_state: str | None = None
    readiness_reason_codes: tuple[str, ...] = ()
    difficulty_reason_codes: tuple[str, ...] = ()
    structural_risk_reason_codes: tuple[str, ...] = ()
    strength_reason_codes: tuple[str, ...] = ()
    performance_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RankedOptionAnnotation:
    rank: int
    course_annotations: tuple[CourseIntelligenceAnnotation, ...]


@dataclass(frozen=True)
class AnnotatedResult:
    baseline_result: object
    option_annotations: tuple[RankedOptionAnnotation, ...]
    integration_policy_version: str = DECISION_INTELLIGENCE_INTEGRATION_POLICY_VERSION


class DelayStatus(str, Enum):
    NO_MODELED_STRUCTURAL_IMPACT = "NO_MODELED_STRUCTURAL_IMPACT"
    MODELED_STRUCTURAL_IMPACT = "MODELED_STRUCTURAL_IMPACT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DelayReason(str, Enum):
    DELAY_TARGET_ALREADY_COMPLETED = "DELAY_TARGET_ALREADY_COMPLETED"
    DELAY_TARGET_IN_PROGRESS_UNRESOLVED = "DELAY_TARGET_IN_PROGRESS_UNRESOLVED"
    DELAY_NO_MODELED_STRUCTURAL_IMPACT = "DELAY_NO_MODELED_STRUCTURAL_IMPACT"
    DELAY_DIRECT_DEPENDENCY_AFFECTED = "DELAY_DIRECT_DEPENDENCY_AFFECTED"
    DELAY_TRANSITIVE_DEPENDENCY_AFFECTED = "DELAY_TRANSITIVE_DEPENDENCY_AFFECTED"
    DELAY_REQUIREMENT_PROGRESS_AFFECTED = "DELAY_REQUIREMENT_PROGRESS_AFFECTED"
    DELAY_MODELED_CREDIT_PROGRESS_AFFECTED = "DELAY_MODELED_CREDIT_PROGRESS_AFFECTED"
    DELAY_MODELED_PATH_CHANGED = "DELAY_MODELED_PATH_CHANGED"
    DELAY_MODELED_PATH_UNCHANGED = "DELAY_MODELED_PATH_UNCHANGED"
    DELAY_ELECTIVE_SUBSTITUTE_AVAILABLE = "DELAY_ELECTIVE_SUBSTITUTE_AVAILABLE"
    DELAY_RULE_REVIEW_REQUIRED = "DELAY_RULE_REVIEW_REQUIRED"
    DELAY_CONTEXT_INSUFFICIENT = "DELAY_CONTEXT_INSUFFICIENT"


class DelayEvidenceType(str, Enum):
    TARGET_COURSE = "TARGET_COURSE"
    DEPENDENCY_GROUP = "DEPENDENCY_GROUP"
    DEPENDENCY_OPTION = "DEPENDENCY_OPTION"
    AFFECTED_COURSE = "AFFECTED_COURSE"
    REQUIREMENT_GROUP = "REQUIREMENT_GROUP"
    PROGRESS_DELTA = "PROGRESS_DELTA"
    DEGREE_PATH_COMPARISON = "DEGREE_PATH_COMPARISON"


@dataclass(frozen=True)
class DelayEvidence:
    evidence_type: DelayEvidenceType
    identifier: str
    course_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AffectedCourse:
    course_code: str
    minimum_dependency_depth: int
    evidence_path: tuple[str, ...]
    is_plan_member: bool
    requirement_type: str | None


@dataclass(frozen=True)
class RequirementImpact:
    requirement_group_code: str
    baseline_is_satisfied: bool
    delayed_is_satisfied: bool
    baseline_remaining_credits: Decimal
    delayed_remaining_credits: Decimal


@dataclass(frozen=True)
class ProgressImpact:
    baseline_completed_plan_credits: Decimal
    delayed_completed_plan_credits: Decimal
    modeled_completed_credit_delta: Decimal
    baseline_remaining_plan_credits: Decimal
    delayed_remaining_plan_credits: Decimal
    affected_requirement_group_codes: tuple[str, ...]


@dataclass(frozen=True)
class DegreePathComparison:
    baseline_path_rank: int | None
    delayed_path_rank: int | None
    modeled_registration_set_count_delta: int | None
    modeled_completed_credit_delta: Decimal | None
    introduced_blocker_codes: tuple[str, ...]
    removed_blocker_codes: tuple[str, ...]
    baseline_termination_status: str | None
    delayed_termination_status: str | None
    canonical_path_changed: bool


@dataclass(frozen=True)
class DelayConsequenceInput:
    target_course_code: str
    study_plan_id: str
    student_attempts: tuple[StudentCourseAttempt, ...]
    simulation_provenance: SimulationProvenance
    progress_catalog: AcademicProgressCatalog | None = None
    eligibility_catalog: CanTakeCatalog | None = None
    current_progress: AcademicProgress | None = None
    source_versions: tuple[str, ...] = ()
    baseline_path_result: DegreePathResult | None = None
    delayed_path_result: DegreePathResult | None = None


@dataclass(frozen=True)
class DelayConsequenceResult:
    contract_version: str
    status: DelayStatus
    target_course_code: str
    current_target_state: str | None
    baseline_scenario_reference: str
    delayed_scenario_reference: str
    directly_affected_courses: tuple[AffectedCourse, ...]
    transitively_affected_courses: tuple[AffectedCourse, ...]
    requirement_impacts: tuple[RequirementImpact, ...]
    progress_impact: ProgressImpact | None
    degree_path_comparison: DegreePathComparison | None
    reason_codes: tuple[DelayReason, ...]
    evidence: tuple[DelayEvidence, ...]
    missing_inputs: tuple[str, ...]
    limitations: tuple[str, ...]
    source_and_policy_versions: tuple[str, ...]
    simulation_provenance: SimulationProvenance


@dataclass(frozen=True)
class DegreePathRunContext:
    progress_catalog: AcademicProgressCatalog
    eligibility_catalog: CanTakeCatalog
    attempts: tuple[StudentCourseAttempt, ...]
    constraints: DegreePathConstraints
