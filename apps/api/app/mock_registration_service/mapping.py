"""Allowlist-only service-to-transport mapping."""

from app.api.schemas.mock_registration import (
    CoverageResponse, DemandMetricResponse, DemandScopeResponse,
    InstitutionalDemandResponse, StudentIntentResponse, TargetPeriodResponse,
)
from .models import InstitutionalDemandResult, StudentIntentResult


def student_response(result: StudentIntentResult) -> StudentIntentResponse:
    return StudentIntentResponse.model_validate(result, from_attributes=True)


def institutional_response(result: InstitutionalDemandResult) -> InstitutionalDemandResponse:
    value = result.demand
    return InstitutionalDemandResponse(
        contract_version=value.contract_version, status=value.status,
        scope=DemandScopeResponse.model_validate(value.aggregation_scope, from_attributes=True),
        target_period=TargetPeriodResponse.model_validate(value.target_period, from_attributes=True),
        target_period_id=result.target_period_id, study_plan_filter=result.study_plan_id,
        course_filter=result.course_code,
        metrics=tuple(DemandMetricResponse.model_validate(item, from_attributes=True) for item in value.metrics),
        suppressed_metric_ids=value.suppressed_metric_ids,
        coverage=CoverageResponse.model_validate(value.coverage, from_attributes=True),
        quality_flags=value.quality_flags, reason_codes=value.reason_codes,
        provenance=value.provenance, source_versions=value.source_versions,
        revalidation_status=result.revalidation_status,
        stale_records_excluded=result.stale_records_excluded,
        generated_at=result.generated_at, limitations=value.limitations,
    )

