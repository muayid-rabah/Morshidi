"""Immutable, transport-independent contracts for Institutional Intelligence V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.mock_registration.models import DemandAggregationResult
from app.mock_registration.registries import DataQualityFlag
from app.progress.models import AcademicProgressCatalog
from app.rules.models import CanTakeCatalog

from .registries import (
    AlertSideEffect,
    InstitutionalAlertId,
    InstitutionalFactAuthority,
    InstitutionalScopeType,
    InstitutionalSignalId,
    PlannedOfferingStatus,
    SignalStatus,
)

INSTITUTIONAL_INTELLIGENCE_CONTRACT_VERSION = "1.0"


@dataclass(frozen=True)
class OfferingFact:
    """External fact declaring whether a course is offered in a target period."""

    university_id: str
    period_key: str
    course_code: str
    status: PlannedOfferingStatus
    authority: InstitutionalFactAuthority
    source_version: str


@dataclass(frozen=True, init=False)
class CapacityFact:
    """External fact supplying total scheduled seat capacity for a course in a target period."""

    university_id: str
    period_key: str
    course_code: str
    capacity: int
    authority: InstitutionalFactAuthority
    source_version: str
    study_plan_id: str | None = None

    def __init__(
        self,
        university_id: str,
        period_key: str,
        course_code: str,
        capacity: int | None = None,
        authority: InstitutionalFactAuthority = InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
        source_version: str = "",
        study_plan_id: str | None = None,
        supplied_capacity: int | None = None,
    ) -> None:
        actual_cap = capacity if capacity is not None else supplied_capacity
        if actual_cap is None:
            raise TypeError("CapacityFact requires capacity or supplied_capacity")
        if actual_cap < 0:
            raise ValueError(f"Supplied capacity cannot be negative: {actual_cap}")
        if authority is None:
            raise ValueError("CapacityFact requires an explicit InstitutionalFactAuthority")
        if not source_version:
            raise ValueError("CapacityFact requires an explicit source_version")
        object.__setattr__(self, "university_id", university_id)
        object.__setattr__(self, "period_key", period_key)
        object.__setattr__(self, "course_code", course_code)
        object.__setattr__(self, "capacity", actual_cap)
        object.__setattr__(self, "authority", authority)
        object.__setattr__(self, "source_version", source_version)
        object.__setattr__(self, "study_plan_id", study_plan_id)

    @property
    def supplied_capacity(self) -> int:
        return self.capacity


@dataclass(frozen=True)
class InstitutionalPrivacyConfiguration:
    """Privacy configuration governing minimum disclosure thresholds."""

    minimum_disclosure_threshold: int = 3
    policy_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.minimum_disclosure_threshold < 2:
            raise ValueError(
                f"Minimum disclosure threshold must be >= 2, got {self.minimum_disclosure_threshold}"
            )


@dataclass(frozen=True)
class InstitutionalSignalResult:
    """Deterministic result for an individual institutional signal."""

    signal_id: InstitutionalSignalId
    status: SignalStatus
    value: int | Decimal | str | None
    unit: str
    quality_flags: tuple[DataQualityFlag, ...] = ()
    trace_id: str = ""
    trace_id: str | None = None


@dataclass(frozen=True)
class InstitutionalAlertResult:
    """Deterministic result for an individual institutional alert condition."""

    alert_id: InstitutionalAlertId
    emitted: bool
    category: str
    message: str
    side_effects: AlertSideEffect = AlertSideEffect.NONE
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InstitutionalDecisionTrace:
    """Auditable decision trace documenting exact formula, inputs, and limitations."""

    trace_id: str
    trace_id: str | None
    signal_id: InstitutionalSignalId
    inputs: dict[str, Any]
    rule_id: str
    result_status: SignalStatus
    result_value: Any
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class SignalProvenance:
    """Immutable provenance metadata for institutional intelligence outputs."""

    university_id: str
    target_period_key: str
    scope_type: InstitutionalScopeType
    scope_id: str
    catalog_version: str
    prerequisite_version: str
    demand_source_version: str
    policy_version: str = INSTITUTIONAL_INTELLIGENCE_CONTRACT_VERSION
    computed_at: str | None = None


@dataclass(frozen=True)
class InstitutionalIntelligenceInput:
    """Pure-domain input package for evaluating institutional intelligence."""

    university_id: str
    target_period_key: str
    course_code: str
    catalog: AcademicProgressCatalog
    can_take_catalog: CanTakeCatalog
    study_plan_id: str | None = None
    demand_result: DemandAggregationResult | None = None
    offering_fact: OfferingFact | None = None
    capacity_fact: CapacityFact | None = None
    all_offering_facts: tuple[OfferingFact, ...] = ()
    all_capacity_facts: tuple[CapacityFact, ...] = ()
    privacy_config: InstitutionalPrivacyConfiguration = InstitutionalPrivacyConfiguration()
    policy_version: str = INSTITUTIONAL_INTELLIGENCE_CONTRACT_VERSION
    computed_at: str | None = None
    deterministic_trace_id: str | None = None


@dataclass(frozen=True)
class InstitutionalIntelligenceResult:
    """Top-level aggregate response for Institutional Intelligence."""

    contract_version: str
    university_id: str
    target_period_key: str
    course_code: str
    study_plan_id: str | None
    provenance: SignalProvenance
    signals: dict[InstitutionalSignalId, InstitutionalSignalResult]
    alerts: tuple[InstitutionalAlertResult, ...]
    traces: tuple[InstitutionalDecisionTrace, ...]
    quality_flags: tuple[DataQualityFlag, ...]
    coverage_notes: tuple[str, ...] = ()
