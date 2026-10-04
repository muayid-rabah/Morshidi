"""Safe typed HTTP contracts for P6.5."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.mock_registration.models import (
    CapacityState, DemandStatus, FactProvenance, IntentLifecycle, IntentProvenance,
    OfferingState, TargetPeriodClass, ValidationStatus,
)
from app.mock_registration.registries import DataQualityFlag, DemandMetricId, ReasonCode
from app.mock_registration_service.models import CurrentValidity, RevalidationStatus

CourseCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
NoticeVersion = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class SubmitIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_period_id: UUID
    course_codes: tuple[CourseCode, ...] = Field(min_length=1, max_length=10)
    expected_current_revision: int | None = Field(default=None, ge=1)
    transparency_notice_version: NoticeVersion


class WithdrawIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_period_id: UUID
    expected_current_revision: int = Field(ge=1)
    transparency_notice_version: NoticeVersion


class StudentIntentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mock_registration_intent"] = "mock_registration_intent"
    intent_id: UUID
    target_period_id: UUID
    target_period_class: TargetPeriodClass
    revision: int
    lifecycle_status: IntentLifecycle
    course_codes: tuple[str, ...]
    submission_validation_status: ValidationStatus
    submission_reason_codes: tuple[ReasonCode, ...]
    current_validity: CurrentValidity | None
    revalidation_status: RevalidationStatus
    current_reason_codes: tuple[ReasonCode, ...]
    idempotent_replay: bool
    created_at: datetime
    non_binding: Literal[True] = True
    limitations: tuple[str, ...]


class ServiceErrorResponse(BaseModel):
    kind: Literal["error"] = "error"
    error_code: str
    detail: str
    reason_codes: tuple[ReasonCode, ...] = ()
    current_revision: int | None = None


class DemandScopeResponse(BaseModel):
    university_id: str
    major_id: str | None
    study_plan_id: str | None
    study_plan_version: str | None


class TargetPeriodResponse(BaseModel):
    university_id: str
    period_key: str
    period_class: TargetPeriodClass
    source_version: str
    verified_provider_source: bool


class DemandMetricResponse(BaseModel):
    metric_id: DemandMetricId
    value: int | Decimal | None
    course_code: str | None
    major_id: str | None
    study_plan_id: str | None
    study_plan_version: str | None
    requirement_group_id: str | None
    denominator_metric_id: DemandMetricId | None
    offering_state: OfferingState | None
    capacity_state: CapacityState | None
    fact_provenance: FactProvenance | None


class CoverageResponse(BaseModel):
    observed_intents_only: bool
    valid_active_intent_owner_count: int | None
    population_denominator: int | None
    population_coverage_ratio: Decimal | None


class InstitutionalDemandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["institutional_demand"] = "institutional_demand"
    contract_version: str
    status: DemandStatus
    scope: DemandScopeResponse
    target_period: TargetPeriodResponse
    target_period_id: UUID
    study_plan_filter: UUID | None
    course_filter: str | None
    metrics: tuple[DemandMetricResponse, ...]
    suppressed_metric_ids: tuple[DemandMetricId, ...]
    coverage: CoverageResponse
    quality_flags: tuple[DataQualityFlag, ...]
    reason_codes: tuple[ReasonCode, ...]
    provenance: tuple[IntentProvenance, ...]
    source_versions: tuple[str, ...]
    revalidation_status: RevalidationStatus
    stale_records_excluded: bool
    generated_at: datetime
    observed_intents_only: Literal[True] = True
    limitations: tuple[str, ...]
