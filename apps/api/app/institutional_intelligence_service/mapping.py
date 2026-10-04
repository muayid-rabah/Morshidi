"""Mapping pure-domain InstitutionalIntelligenceResult to allowlisted API response DTOs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.institutional_intelligence.models import (
    InstitutionalAlertResult,
    InstitutionalDecisionTrace,
    InstitutionalIntelligenceResult,
    InstitutionalSignalResult,
)
from app.institutional_intelligence.registries import SignalStatus

from .models import (
    AlertResponseDTO,
    DecisionTraceResponseDTO,
    InstitutionalIntelligenceResponse,
    ProvenanceResponseDTO,
    SignalResponseDTO,
)


def _sanitize_evidence_val(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, dict):
        return {k: _sanitize_evidence_val(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize_evidence_val(item) for item in val]
    return val


def _map_signal(sig: InstitutionalSignalResult) -> SignalResponseDTO:
    val: int | float | str | None
    # Suppression Invariant: strictly withhold numeric values when suppressed
    if sig.status is SignalStatus.SUPPRESSED:
        val = None
    elif isinstance(sig.value, Decimal):
        val = float(sig.value)
    else:
        val = sig.value

    return SignalResponseDTO(
        signal_id=sig.signal_id.value,
        status=sig.status.value,
        value=val,
        unit=sig.unit,
        quality_flags=[f.value for f in sig.quality_flags],
        trace_id=sig.trace_id,
    )


def _map_alert(alert: InstitutionalAlertResult) -> AlertResponseDTO:
    clean_evidence = {k: _sanitize_evidence_val(v) for k, v in alert.evidence.items()}
    return AlertResponseDTO(
        alert_id=alert.alert_id.value,
        emitted=alert.emitted,
        category=alert.category,
        message=alert.message,
        side_effects=alert.side_effects.value,
        evidence=clean_evidence,
    )


def _map_trace(trace: InstitutionalDecisionTrace) -> DecisionTraceResponseDTO:
    return DecisionTraceResponseDTO(
        trace_id=trace.trace_id,
        signal_id=trace.signal_id.value,
        rule_id=trace.rule_id,
        result_status=trace.result_status.value,
        result_value=_sanitize_evidence_val(trace.result_value),
        limitations=list(trace.limitations),
    )


def map_institutional_intelligence_response(
    result: InstitutionalIntelligenceResult,
    *,
    university_id: UUID,
    target_period_id: UUID,
    study_plan_id: UUID | None,
    generated_at: datetime,
) -> InstitutionalIntelligenceResponse:
    signals_dict = {
        sig_id.value: _map_signal(sig_res)
        for sig_id, sig_res in result.signals.items()
    }
    alerts_list = [_map_alert(a) for a in result.alerts]
    traces_list = [_map_trace(t) for t in result.traces]

    prov_dto = ProvenanceResponseDTO(
        university_id=result.provenance.university_id,
        target_period_key=result.provenance.target_period_key,
        scope_type=result.provenance.scope_type.value,
        scope_id=result.provenance.scope_id,
        catalog_version=result.provenance.catalog_version,
        prerequisite_version=result.provenance.prerequisite_version,
        demand_source_version=result.provenance.demand_source_version,
        policy_version=result.provenance.policy_version,
        computed_at=result.provenance.computed_at,
    )

    return InstitutionalIntelligenceResponse(
        contract_version=result.contract_version,
        university_id=university_id,
        target_period_id=target_period_id,
        target_period_key=result.target_period_key,
        study_plan_id=study_plan_id,
        course_code=result.course_code,
        provenance=prov_dto,
        signals=signals_dict,
        alerts=alerts_list,
        traces=traces_list,
        quality_flags=[q.value for q in result.quality_flags],
        coverage_notes=list(result.coverage_notes),
        generated_at=generated_at,
    )
