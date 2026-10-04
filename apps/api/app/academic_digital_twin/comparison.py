"""Bounded factual comparison of Digital Twin results."""

from __future__ import annotations

from app.academic_digital_twin.deltas import extract_deltas
from app.academic_digital_twin.models import (
    DIGITAL_TWIN_CONTRACT_VERSION,
    ComparisonMetric,
    ComparisonMetricStatus,
    ComparisonType,
    DigitalTwinEvaluationResult,
    ScenarioComparisonResult,
    ScenarioStatus,
)

_LIMITATIONS = (
    "Comparison is factual and emits no overall score, winner, or hidden preference.",
    "Modeled registration-set counts are not graduation dates or calendar duration.",
)


def compare_baseline_to_scenario(result: DigitalTwinEvaluationResult) -> ScenarioComparisonResult:
    _require_comparable(result)
    status = (
        ComparisonMetricStatus.REVIEW_REQUIRED
        if result.lifecycle_status is ScenarioStatus.REVIEW_REQUIRED
        else ComparisonMetricStatus.COMPARABLE
    )
    return ScenarioComparisonResult(
        DIGITAL_TWIN_CONTRACT_VERSION,
        ComparisonType.BASELINE_VS_SCENARIO,
        result.scenario_identity.base_state_fingerprint,
        "BASELINE",
        result.scenario_identity.scenario_id,
        tuple(ComparisonMetric(delta, status) for delta in result.deltas),
        (),
        not result.deltas,
        _LIMITATIONS,
    )


def compare_scenarios(
    left: DigitalTwinEvaluationResult,
    right: DigitalTwinEvaluationResult,
) -> ScenarioComparisonResult:
    _require_comparable(left)
    _require_comparable(right)
    if left.owner_scope_id != right.owner_scope_id:
        raise ValueError("Scenario comparison requires the same authorized owner scope")
    if left.plan_identity != right.plan_identity:
        raise ValueError("Scenario comparison requires the same plan identity")
    if left.scenario_identity.base_state_fingerprint != right.scenario_identity.base_state_fingerprint:
        raise ValueError("Scenario comparison requires the same base-state fingerprint")
    if left.source_engine_policy_versions != right.source_engine_policy_versions:
        raise ValueError("Scenario comparison requires compatible engine/policy versions")
    if left.modeled_outputs is None or right.modeled_outputs is None:
        raise ValueError("Scenario results do not contain comparable modeled outputs")
    deltas = extract_deltas(left.modeled_outputs, right.modeled_outputs)
    review = ScenarioStatus.REVIEW_REQUIRED in {left.lifecycle_status, right.lifecycle_status}
    metric_status = (
        ComparisonMetricStatus.REVIEW_REQUIRED if review else ComparisonMetricStatus.COMPARABLE
    )
    return ScenarioComparisonResult(
        DIGITAL_TWIN_CONTRACT_VERSION,
        ComparisonType.SCENARIO_VS_SCENARIO,
        left.scenario_identity.base_state_fingerprint,
        left.scenario_identity.scenario_id,
        right.scenario_identity.scenario_id,
        tuple(ComparisonMetric(delta, metric_status) for delta in deltas),
        (),
        not deltas,
        _LIMITATIONS,
    )


def _require_comparable(result):
    if result.lifecycle_status in {ScenarioStatus.INVALID, ScenarioStatus.STALE_BASE_STATE}:
        raise ValueError(f"Scenario status {result.lifecycle_status.value} is not comparable")

