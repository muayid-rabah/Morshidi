"""Immutable domain contracts for Academic Digital Twin V1."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.decision_intelligence.models import (
    DelayConsequenceResult,
    EnhancedRecommendationResult,
    ReadinessFactorInput,
)
from app.degree_path.models import DegreePathConstraints, DegreePathResult
from app.planner.models import PlannerConstraints, SemesterPlannerResult
from app.progress.models import AcademicProgress, AcademicProgressCatalog
from app.recommendations.models import RecommendationResult
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    Decision,
    StudentCourseAttempt,
)

DIGITAL_TWIN_CONTRACT_VERSION = "1.0"
SCENARIO_VERSION = 1


class StateKind(str, Enum):
    AUTHORITATIVE_STATE = "AUTHORITATIVE_STATE"
    MODELED_STATE = "MODELED_STATE"


class SimulationProvenanceClass(str, Enum):
    AUTHORITATIVE_INPUT = "AUTHORITATIVE_INPUT"
    MODELED_OPERATION = "MODELED_OPERATION"
    DERIVED_FROM_MODELED_STATE = "DERIVED_FROM_MODELED_STATE"


class ScenarioStatus(str, Enum):
    CREATED = "CREATED"
    EVALUATED = "EVALUATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INVALID = "INVALID"
    STALE_BASE_STATE = "STALE_BASE_STATE"


class OperationId(str, Enum):
    MODEL_COURSE_COMPLETION = "TWIN_OP_MODEL_COURSE_COMPLETION"
    OMIT_NEXT_PLAN_COURSE = "TWIN_OP_OMIT_NEXT_PLAN_COURSE"
    SET_PLANNING_CONSTRAINTS = "TWIN_OP_SET_PLANNING_CONSTRAINTS"


class ValidationCode(str, Enum):
    UNKNOWN_OPERATION = "TWIN_UNKNOWN_OPERATION"
    UNKNOWN_COURSE = "TWIN_UNKNOWN_COURSE"
    TARGET_NOT_PLAN_MEMBER = "TWIN_TARGET_NOT_PLAN_MEMBER"
    TARGET_ALREADY_COMPLETED = "TWIN_TARGET_ALREADY_COMPLETED"
    TARGET_IN_PROGRESS = "TWIN_TARGET_IN_PROGRESS"
    TARGET_NOT_ELIGIBLE = "TWIN_TARGET_NOT_ELIGIBLE"
    TARGET_REVIEW_REQUIRED = "TWIN_TARGET_REVIEW_REQUIRED"
    ELECTIVE_GROUP_ALREADY_SATISFIED = "TWIN_ELECTIVE_GROUP_ALREADY_SATISFIED"
    INVALID_CONSTRAINT = "TWIN_INVALID_CONSTRAINT"
    DUPLICATE_OPERATION = "TWIN_DUPLICATE_OPERATION"
    CONFLICTING_OPERATIONS = "TWIN_CONFLICTING_OPERATIONS"
    TOO_MANY_STRUCTURAL_OPERATIONS = "TWIN_TOO_MANY_STRUCTURAL_OPERATIONS"
    BASE_IDENTITY_MISMATCH = "TWIN_BASE_IDENTITY_MISMATCH"
    STALE_BASE_STATE = "TWIN_STALE_BASE_STATE"
    REQUIRED_CONTEXT_MISSING = "TWIN_REQUIRED_CONTEXT_MISSING"
    OPERATION_DEFERRED = "TWIN_OPERATION_DEFERRED"
    OPERATION_FORBIDDEN = "TWIN_OPERATION_FORBIDDEN"


class OperationResultCode(str, Enum):
    MODELED_COMPLETION_APPLIED = "TWIN_MODELED_COMPLETION_APPLIED"
    DELAY_COMPOSED = "TWIN_DELAY_COMPOSED"
    CONSTRAINTS_APPLIED = "TWIN_CONSTRAINTS_APPLIED"


class DeltaType(str, Enum):
    NEWLY_MODELED_ELIGIBLE = "NEWLY_MODELED_ELIGIBLE"
    NO_LONGER_MODELED_ELIGIBLE = "NO_LONGER_MODELED_ELIGIBLE"
    NEWLY_MODELED_COMPLETED_REQUIREMENT = "NEWLY_MODELED_COMPLETED_REQUIREMENT"
    NO_LONGER_MODELED_SATISFIED_REQUIREMENT = "NO_LONGER_MODELED_SATISFIED_REQUIREMENT"
    COMPLETED_PLAN_CREDIT_DELTA = "COMPLETED_PLAN_CREDIT_DELTA"
    REMAINING_PLAN_CREDIT_DELTA = "REMAINING_PLAN_CREDIT_DELTA"
    RECOMMENDATION_MEMBERSHIP_CHANGE = "RECOMMENDATION_MEMBERSHIP_CHANGE"
    RECOMMENDATION_ORDER_CHANGE = "RECOMMENDATION_ORDER_CHANGE"
    MODELED_PLAN_CHANGE = "MODELED_PLAN_CHANGE"
    MODELED_PATH_CHANGE = "MODELED_PATH_CHANGE"
    MODELED_REGISTRATION_SET_COUNT_DELTA = "MODELED_REGISTRATION_SET_COUNT_DELTA"
    NEWLY_MODELED_BLOCKED = "NEWLY_MODELED_BLOCKED"
    NEWLY_MODELED_UNLOCKED = "NEWLY_MODELED_UNLOCKED"
    STRUCTURAL_WARNING_CHANGE = "STRUCTURAL_WARNING_CHANGE"
    REVIEW_STATE_CHANGE = "REVIEW_STATE_CHANGE"
    DELAY_CONSEQUENCE_CHANGE = "DELAY_CONSEQUENCE_CHANGE"


class ComparisonType(str, Enum):
    BASELINE_VS_SCENARIO = "BASELINE_VS_SCENARIO"
    SCENARIO_VS_SCENARIO = "SCENARIO_VS_SCENARIO"


class ComparisonMetricStatus(str, Enum):
    COMPARABLE = "COMPARABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class PlanIdentity:
    university_id: str
    major_id: str
    study_plan_id: str
    plan_version: str


@dataclass(frozen=True)
class AuthoritativeAttempt:
    course_code: str
    outcome: AttemptOutcome
    attempt_sequence: int | None = None
    provenance: str = "OFFICIAL_VERIFIED"
    verification_state: str = "VERIFIED"

    def as_engine_attempt(self) -> StudentCourseAttempt:
        return StudentCourseAttempt(self.course_code, self.outcome)


@dataclass(frozen=True)
class PlanningConstraintBundle:
    max_credit_hours: Decimal
    max_courses: int | None = None
    max_options: int = 5
    max_credit_hours_per_semester: Decimal | None = None
    max_courses_per_semester: int | None = None
    max_semesters_ahead: int = 8
    max_paths: int = 3

    def planner_constraints(self) -> PlannerConstraints:
        return PlannerConstraints(self.max_credit_hours, self.max_courses, self.max_options)

    def path_constraints(self) -> DegreePathConstraints:
        return DegreePathConstraints(
            self.max_credit_hours_per_semester
            if self.max_credit_hours_per_semester is not None
            else self.max_credit_hours,
            self.max_courses_per_semester
            if self.max_courses_per_semester is not None
            else self.max_courses,
            self.max_semesters_ahead,
            self.max_paths,
        )


@dataclass(frozen=True)
class ScenarioOperation:
    operation_id: str
    target_course_code: str | None = None
    constraints: PlanningConstraintBundle | None = None


@dataclass(frozen=True)
class ScenarioIdentity:
    scenario_id: str
    base_state_fingerprint: str
    operations: tuple[ScenarioOperation, ...]
    constraint_bundle: PlanningConstraintBundle | None = None
    scenario_contract_version: str = DIGITAL_TWIN_CONTRACT_VERSION
    scenario_version: int = SCENARIO_VERSION
    scenario_name: str | None = None


@dataclass(frozen=True)
class AuthoritativeAcademicSnapshot:
    owner_scope_id: str
    plan_identity: PlanIdentity
    attempts: tuple[AuthoritativeAttempt, ...]
    eligibility_catalog: CanTakeCatalog
    progress_catalog: AcademicProgressCatalog
    current_progress: AcademicProgress
    baseline_planner_constraints: PlannerConstraints
    baseline_path_constraints: DegreePathConstraints
    source_versions: tuple[str, ...]
    engine_policy_versions: tuple[str, ...]
    readiness_by_course: tuple[tuple[str, ReadinessFactorInput], ...] = ()
    structural_warnings: tuple[str, ...] = ()

    @property
    def engine_attempts(self) -> tuple[StudentCourseAttempt, ...]:
        return tuple(item.as_engine_attempt() for item in self.attempts)


@dataclass(frozen=True)
class ModeledCourseCompletion:
    course_code: str
    scenario_id: str
    operation_id: str = OperationId.MODEL_COURSE_COMPLETION.value
    outcome: AttemptOutcome = AttemptOutcome.PASSED
    provenance: SimulationProvenanceClass = SimulationProvenanceClass.MODELED_OPERATION


@dataclass(frozen=True)
class SimulationProvenance:
    provenance_class: SimulationProvenanceClass
    scenario_id: str
    base_state_fingerprint: str
    operation_ids: tuple[str, ...]
    source_versions: tuple[str, ...]
    engine_policy_versions: tuple[str, ...]


@dataclass(frozen=True)
class EligibilityFact:
    course_code: str
    decision: Decision


@dataclass(frozen=True)
class EngineOutputs:
    eligibility: tuple[EligibilityFact, ...]
    progress: AcademicProgress
    recommendations: RecommendationResult
    decision_intelligence: EnhancedRecommendationResult
    semester_plan: SemesterPlannerResult
    degree_path: DegreePathResult
    structural_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class StateSummary:
    state_kind: StateKind
    study_plan_id: str
    completed_plan_credits: Decimal
    remaining_plan_credits: Decimal
    satisfied_requirement_group_codes: tuple[str, ...]
    attempt_count: int


@dataclass(frozen=True)
class ScenarioValidationIssue:
    code: ValidationCode
    operation_id: str | None = None
    target_course_code: str | None = None


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    applied: bool
    result_code: str
    target_course_code: str | None = None


@dataclass(frozen=True)
class TwinDelta:
    delta_type: DeltaType
    source_engine: str
    target: str
    base_value: str
    modeled_value: str
    provenance: SimulationProvenanceClass = SimulationProvenanceClass.DERIVED_FROM_MODELED_STATE


@dataclass(frozen=True)
class ScenarioContext:
    authoritative_snapshot: AuthoritativeAcademicSnapshot
    scenario_identity: ScenarioIdentity
    canonical_operations: tuple[ScenarioOperation, ...]
    simulation_provenance: SimulationProvenance


@dataclass(frozen=True)
class DigitalTwinEvaluationResult:
    contract_version: str
    scenario_identity: ScenarioIdentity
    lifecycle_status: ScenarioStatus
    owner_scope_id: str
    plan_identity: PlanIdentity
    base_state_summary: StateSummary
    modeled_state_summary: StateSummary | None
    modeled_completion: ModeledCourseCompletion | None
    operation_results: tuple[OperationResult, ...]
    validation_issues: tuple[ScenarioValidationIssue, ...]
    base_outputs: EngineOutputs | None
    modeled_outputs: EngineOutputs | None
    delay_consequence: DelayConsequenceResult | None
    deltas: tuple[TwinDelta, ...]
    decision_traces: tuple[str, ...]
    warnings: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    limitations: tuple[str, ...]
    source_engine_policy_versions: tuple[str, ...]
    simulation_provenance: SimulationProvenance


@dataclass(frozen=True)
class ComparisonMetric:
    delta: TwinDelta
    status: ComparisonMetricStatus


@dataclass(frozen=True)
class ScenarioComparisonResult:
    contract_version: str
    comparison_type: ComparisonType
    base_state_fingerprint: str
    left_scenario_reference: str
    right_scenario_reference: str
    metrics: tuple[ComparisonMetric, ...]
    excluded_metrics: tuple[str, ...]
    equal: bool
    limitations: tuple[str, ...]

