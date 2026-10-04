"""Deterministic institutional alert evaluation with privacy withholding."""

from __future__ import annotations

from typing import Any

from .models import CapacityFact, InstitutionalAlertResult, OfferingFact
from .registries import (
    AlertSideEffect,
    CapacityPressureState,
    InstitutionalAlertId,
    PlannedOfferingStatus,
    SignalStatus,
    StructuralGatewayStatus,
)


def evaluate_institutional_alerts(
    demand_count: int | None,
    demand_status: SignalStatus,
    capacity_fact: CapacityFact | None,
    offering_fact: OfferingFact | None,
    deficit: int | None,
    deficit_status: SignalStatus,
    pressure_state: CapacityPressureState | None,
    gateway_status: StructuralGatewayStatus,
    review_required_count: int | None,
    review_required_status: SignalStatus,
) -> tuple[InstitutionalAlertResult, ...]:
    """Evaluates all 6 institutional alerts with deterministic privacy withholding.

    Alert presence is strictly prevented from acting as a privacy side-channel.
    """
    alerts: list[InstitutionalAlertResult] = []

    # 1. INST_ALERT_CAPACITY_DEFICIT_DETECTED
    # Trigger: unsuppressed demand > supplied capacity (deficit > 0)
    emit_deficit = (
        demand_status is SignalStatus.AVAILABLE
        and deficit_status is SignalStatus.AVAILABLE
        and deficit is not None
        and deficit > 0
    )
    alerts.append(
        InstitutionalAlertResult(
            alert_id=InstitutionalAlertId.INST_ALERT_CAPACITY_DEFICIT_DETECTED,
            emitted=emit_deficit,
            category="CAPACITY_MISMATCH",
            message="Declared student registration intent exceeds published seat capacity.",
            side_effects=AlertSideEffect.NONE,
            evidence={
                "demand": demand_count if demand_status is SignalStatus.AVAILABLE else None,
                "capacity": capacity_fact.capacity if capacity_fact is not None else None,
                "deficit": deficit if deficit_status is SignalStatus.AVAILABLE else None,
            }
            if emit_deficit
            else {},
        )
    )

    # 2. INST_ALERT_ZERO_CAPACITY_WITH_DEMAND
    # Trigger: supplied capacity == 0 AND unsuppressed demand > 0
    is_verified_not_offered = (
        offering_fact is not None and offering_fact.status is PlannedOfferingStatus.NOT_OFFERED
    )
    emit_zero_cap = (
        not is_verified_not_offered
        and capacity_fact is not None
        and capacity_fact.capacity == 0
        and demand_status is SignalStatus.AVAILABLE
        and demand_count is not None
        and demand_count > 0
    )
    alerts.append(
        InstitutionalAlertResult(
            alert_id=InstitutionalAlertId.INST_ALERT_ZERO_CAPACITY_WITH_DEMAND,
            emitted=emit_zero_cap,
            category="CAPACITY_MISMATCH",
            message="Students have declared intent for a course currently listed with zero capacity.",
            side_effects=AlertSideEffect.NONE,
            evidence={
                "capacity": 0,
                "demand": demand_count if demand_status is SignalStatus.AVAILABLE else None,
            }
            if emit_zero_cap
            else {},
        )
    )

    # 3. INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE
    # Trigger: STRUCTURAL_GATEWAY AND unsuppressed deficit > 0
    emit_bottleneck = (
        gateway_status is StructuralGatewayStatus.STRUCTURAL_GATEWAY
        and deficit_status is SignalStatus.AVAILABLE
        and deficit is not None
        and deficit > 0
    )
    alerts.append(
        InstitutionalAlertResult(
            alert_id=InstitutionalAlertId.INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE,
            emitted=emit_bottleneck,
            category="STRUCTURAL_PRESSURE",
            message="A mandatory curricular gateway course is experiencing declared capacity pressure.",
            side_effects=AlertSideEffect.NONE,
            evidence={
                "structural_status": gateway_status.value,
                "deficit": deficit if deficit_status is SignalStatus.AVAILABLE else None,
            }
            if emit_bottleneck
            else {},
        )
    )

    # 4. INST_ALERT_REVIEW_REQUIRED_PRESENT
    # Trigger: unsuppressed review_required_count > 0
    emit_review = (
        review_required_status is SignalStatus.AVAILABLE
        and review_required_count is not None
        and review_required_count > 0
    )
    alerts.append(
        InstitutionalAlertResult(
            alert_id=InstitutionalAlertId.INST_ALERT_REVIEW_REQUIRED_PRESENT,
            emitted=emit_review,
            category="WORKLOAD_FLAG",
            message="One or more student intent declarations require human academic review due to prerequisite ambiguities.",
            side_effects=AlertSideEffect.NONE,
            evidence={
                "review_required_intent_owner_count": review_required_count
                if review_required_status is SignalStatus.AVAILABLE
                else None,
            }
            if emit_review
            else {},
        )
    )

    # 5. INST_ALERT_CAPACITY_DATA_MISSING
    # Trigger: capacity_fact is None, unless course is explicitly verified NOT_OFFERED
    emit_cap_missing = capacity_fact is None and not is_verified_not_offered
    alerts.append(
        InstitutionalAlertResult(
            alert_id=InstitutionalAlertId.INST_ALERT_CAPACITY_DATA_MISSING,
            emitted=emit_cap_missing,
            category="DATA_HYGIENE",
            message="Seat capacity information has not been published or verified for this course.",
            side_effects=AlertSideEffect.NONE,
            evidence={"capacity_fact_supplied": False} if emit_cap_missing else {},
        )
    )

    # 6. INST_ALERT_OFFERING_DATA_MISSING
    # Trigger: offering_fact is None
    emit_offering_missing = offering_fact is None
    alerts.append(
        InstitutionalAlertResult(
            alert_id=InstitutionalAlertId.INST_ALERT_OFFERING_DATA_MISSING,
            emitted=emit_offering_missing,
            category="DATA_HYGIENE",
            message="Course timetable schedule is not yet verified for the target planning period.",
            side_effects=AlertSideEffect.NONE,
            evidence={"offering_fact_supplied": False} if emit_offering_missing else {},
        )
    )

    return tuple(alerts)
