"""Immutable, transport-independent P6.2 domain contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.progress.models import AcademicProgress, AcademicProgressCatalog
from app.rules.models import CanTakeCatalog, Decision, StudentCourseAttempt

from .registries import DataQualityFlag, DemandMetricId, ReasonCode

MOCK_REGISTRATION_CONTRACT_VERSION = "1.0"
MAX_INTENT_COURSES = 10
MAX_INTENT_CREDITS = Decimal("30.00")


class IntentLifecycle(str, Enum):
    SUBMITTED = "SUBMITTED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


class ValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class TargetPeriodClass(str, Enum):
    DECLARED_PLANNING_PERIOD = "DECLARED_PLANNING_PERIOD"
    OFFICIAL_PERIOD_REFERENCE = "OFFICIAL_PERIOD_REFERENCE"
    SYNTHETIC_SANDBOX_PERIOD = "SYNTHETIC_SANDBOX_PERIOD"


class IntentProvenance(str, Enum):
    DECLARED_STUDENT_INTENT = "DECLARED_STUDENT_INTENT"
    SYNTHETIC_SANDBOX_INTENT = "SYNTHETIC_SANDBOX_INTENT"
    INSTITUTIONAL_IMPORT = "INSTITUTIONAL_IMPORT"


class FactProvenance(str, Enum):
    VERIFIED_INSTITUTIONAL_FACT = "VERIFIED_INSTITUTIONAL_FACT"
    SYNTHETIC_SANDBOX_FACT = "SYNTHETIC_SANDBOX_FACT"
    UNAVAILABLE = "UNAVAILABLE"


class ResolutionDisposition(str, Enum):
    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"


class DemandStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    SUPPRESSED = "SUPPRESSED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class OfferingState(str, Enum):
    OFFERING_DATA_UNAVAILABLE = "OFFERING_DATA_UNAVAILABLE"
    MATCHING_OFFERING_FACT = "MATCHING_OFFERING_FACT"
    NO_MATCHING_OFFERING_FACT = "NO_MATCHING_OFFERING_FACT"


class CapacityState(str, Enum):
    CAPACITY_DATA_UNAVAILABLE = "CAPACITY_DATA_UNAVAILABLE"
    MATCHING_CAPACITY_FACT = "MATCHING_CAPACITY_FACT"


@dataclass(frozen=True)
class TargetPeriod:
    university_id: str
    period_key: str
    period_class: TargetPeriodClass
    source_version: str
    verified_provider_source: bool = False


@dataclass(frozen=True)
class RegistrationIntent:
    intent_id: str
    owner_scope_id: str
    university_id: str
    major_id: str
    study_plan_id: str
    study_plan_version: str
    target_period: TargetPeriod
    revision: int
    lifecycle_status: IntentLifecycle
    course_codes: tuple[str, ...]
    source_class: IntentProvenance
    source_version: str
    contract_version: str = MOCK_REGISTRATION_CONTRACT_VERSION


@dataclass(frozen=True)
class MockRegistrationContext:
    owner_scope_id: str
    university_id: str
    major_id: str
    study_plan_id: str
    study_plan_version: str
    eligibility_catalog: CanTakeCatalog
    progress_catalog: AcademicProgressCatalog
    current_progress: AcademicProgress
    student_attempts: tuple[StudentCourseAttempt, ...]
    source_versions: tuple[str, ...]
    engine_policy_versions: tuple[str, ...]
    allowed_target_period: TargetPeriod


@dataclass(frozen=True)
class CourseValidationResult:
    course_code: str
    status: ValidationStatus
    reason_codes: tuple[ReasonCode, ...]
    phase5_decision: Decision | None
    phase5_reasons: tuple[str, ...]
    requirement_group_id: str | None
    requirement_group_code: str | None
    credit_hours: Decimal | None
    offering_state: OfferingState = OfferingState.OFFERING_DATA_UNAVAILABLE
    capacity_state: CapacityState = CapacityState.CAPACITY_DATA_UNAVAILABLE
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidatedIntent:
    intent: RegistrationIntent
    canonical_course_codes: tuple[str, ...]
    content_fingerprint: str
    status: ValidationStatus
    reason_codes: tuple[ReasonCode, ...]
    course_results: tuple[CourseValidationResult, ...]
    declared_credit_load: Decimal
    source_engine_policy_versions: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedIntent:
    record: ValidatedIntent
    disposition: ResolutionDisposition
    reason_codes: tuple[ReasonCode, ...] = ()


@dataclass(frozen=True)
class IntentResolutionResult:
    records: tuple[ResolvedIntent, ...]

    @property
    def current(self) -> tuple[ResolvedIntent, ...]:
        return tuple(item for item in self.records if item.disposition is ResolutionDisposition.CURRENT)


@dataclass(frozen=True)
class AggregationScope:
    university_id: str
    major_id: str | None = None
    study_plan_id: str | None = None
    study_plan_version: str | None = None


@dataclass(frozen=True)
class PlanCourseFact:
    university_id: str
    major_id: str
    study_plan_id: str
    study_plan_version: str
    course_code: str
    requirement_group_id: str
    credit_hours: Decimal
    source_version: str


@dataclass(frozen=True)
class OfferingFact:
    university_id: str
    target_period: TargetPeriod
    course_code: str
    source_version: str
    provenance: FactProvenance


@dataclass(frozen=True)
class CapacityFact:
    university_id: str
    target_period: TargetPeriod
    course_code: str
    capacity: int
    source_version: str
    provenance: FactProvenance
    major_id: str | None = None
    study_plan_id: str | None = None
    study_plan_version: str | None = None


@dataclass(frozen=True)
class PrivacyConfiguration:
    minimum_disclosure_group_size: int
    policy_version: str


@dataclass(frozen=True)
class AggregationLimits:
    max_intents: int
    max_catalog_courses: int


@dataclass(frozen=True)
class CoverageInput:
    population_denominator: int | None = None
    complete_declared_intent_input_set: bool = False


@dataclass(frozen=True)
class DemandAggregationInput:
    aggregation_scope: AggregationScope
    target_period: TargetPeriod
    resolved_intents: tuple[ResolvedIntent, ...]
    normalized_plan_course_catalog: tuple[PlanCourseFact, ...]
    privacy_configuration: PrivacyConfiguration
    aggregation_limits: AggregationLimits
    coverage: CoverageInput = CoverageInput()
    offering_facts: tuple[OfferingFact, ...] | None = None
    capacity_facts: tuple[CapacityFact, ...] | None = None
    include_review_metric: bool = False
    source_versions: tuple[str, ...] = ()
    contract_version: str = MOCK_REGISTRATION_CONTRACT_VERSION


@dataclass(frozen=True)
class DemandMetric:
    metric_id: DemandMetricId
    value: int | Decimal | None
    course_code: str | None = None
    major_id: str | None = None
    study_plan_id: str | None = None
    study_plan_version: str | None = None
    requirement_group_id: str | None = None
    denominator_metric_id: DemandMetricId | None = None
    offering_state: OfferingState | None = None
    capacity_state: CapacityState | None = None
    fact_provenance: FactProvenance | None = None


@dataclass(frozen=True)
class CoverageMetadata:
    observed_intents_only: bool
    valid_active_intent_owner_count: int | None
    population_denominator: int | None
    population_coverage_ratio: Decimal | None


@dataclass(frozen=True)
class DemandAggregationResult:
    contract_version: str
    status: DemandStatus
    aggregation_scope: AggregationScope
    target_period: TargetPeriod
    metrics: tuple[DemandMetric, ...]
    suppressed_metric_ids: tuple[DemandMetricId, ...]
    coverage: CoverageMetadata
    quality_flags: tuple[DataQualityFlag, ...]
    reason_codes: tuple[ReasonCode, ...]
    provenance: tuple[IntentProvenance, ...]
    source_versions: tuple[str, ...]
    limitations: tuple[str, ...]


class DemandAggregationError(ValueError):
    def __init__(self, code: ReasonCode, message: str):
        super().__init__(message)
        self.code = code
