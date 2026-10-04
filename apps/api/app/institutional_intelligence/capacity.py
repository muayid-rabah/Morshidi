"""Deterministic capacity pressure arithmetic and state transitions."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.mock_registration.registries import DataQualityFlag

from .models import CapacityFact, OfferingFact
from .registries import (
    CapacityPressureState,
    PlannedOfferingStatus,
    SignalStatus,
)


def evaluate_capacity_metrics(
    demand_count: int | None,
    demand_status: SignalStatus,
    offering_fact: OfferingFact | None,
    capacity_fact: CapacityFact | None,
) -> tuple[
    tuple[SignalStatus, int | None],
    tuple[SignalStatus, int | None],
    tuple[SignalStatus, CapacityPressureState | None],
    tuple[SignalStatus, Decimal | None],
    tuple[DataQualityFlag, ...],
]:
    """Evaluates capacity-related signals with strict offering and privacy applicability.

    Returns:
        (
            supplied_capacity_result,
            capacity_deficit_result,
            capacity_pressure_state_result,
            demand_to_capacity_ratio_result,
            quality_flags,
        )
    """
    quality_flags: list[DataQualityFlag] = []

    # 1. Offering missing check
    if offering_fact is None:
        quality_flags.append(DataQualityFlag.MISSING_OFFERING_DATA)

    # 2. Verified NOT_OFFERED rule:
    # If explicitly verified NOT_OFFERED, capacity is structurally NOT_APPLICABLE.
    # No missing capacity data alert or flag is emitted.
    if offering_fact is not None and offering_fact.status is PlannedOfferingStatus.NOT_OFFERED:
        return (
            (SignalStatus.NOT_APPLICABLE, None),
            (SignalStatus.NOT_APPLICABLE, None),
            (SignalStatus.NOT_APPLICABLE, CapacityPressureState.NOT_APPLICABLE),
            (SignalStatus.NOT_APPLICABLE, None),
            tuple(quality_flags),
        )

    # 3. Privacy suppression propagation:
    # If demand count is suppressed, all derived capacity arithmetic must be withheld.
    if demand_status is SignalStatus.SUPPRESSED:
        quality_flags.append(DataQualityFlag.SUPPRESSED_FOR_PRIVACY)
        # Supplied capacity is a public institutional fact
        if capacity_fact is not None:
            cap_result = (SignalStatus.AVAILABLE, capacity_fact.capacity)
        else:
            cap_result = (SignalStatus.INSUFFICIENT_DATA, None)
            quality_flags.append(DataQualityFlag.MISSING_CAPACITY_DATA)

        return (
            cap_result,
            (SignalStatus.SUPPRESSED, None),
            (SignalStatus.SUPPRESSED, None),
            (SignalStatus.SUPPRESSED, None),
            tuple(quality_flags),
        )

    # 4. Capacity fact missing (offering is OFFERED or UNAVAILABLE)
    if capacity_fact is None:
        quality_flags.append(DataQualityFlag.MISSING_CAPACITY_DATA)
        cap_result = (SignalStatus.INSUFFICIENT_DATA, None)
        deficit_result = (SignalStatus.INSUFFICIENT_DATA, None)
        ratio_result = (SignalStatus.INSUFFICIENT_DATA, None)

        if demand_status is SignalStatus.AVAILABLE:
            state_result = (SignalStatus.AVAILABLE, CapacityPressureState.NO_CAPACITY_DATA)
        else:
            state_result = (SignalStatus.INSUFFICIENT_DATA, None)

        return (
            cap_result,
            deficit_result,
            state_result,
            ratio_result,
            tuple(quality_flags),
        )

    # 5. Supplied capacity is available
    cap_val = capacity_fact.capacity
    cap_result = (SignalStatus.AVAILABLE, cap_val)

    if demand_status is not SignalStatus.AVAILABLE or demand_count is None:
        return (
            cap_result,
            (SignalStatus.INSUFFICIENT_DATA, None),
            (SignalStatus.INSUFFICIENT_DATA, None),
            (SignalStatus.INSUFFICIENT_DATA, None),
            tuple(quality_flags),
        )

    # 6. Both demand and capacity are available: compute signed deficit and pressure state
    deficit = demand_count - cap_val
    deficit_result = (SignalStatus.AVAILABLE, deficit)

    if demand_count > cap_val:
        pressure_state = CapacityPressureState.DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY
    else:
        pressure_state = CapacityPressureState.WITHIN_SUPPLIED_CAPACITY

    state_result = (SignalStatus.AVAILABLE, pressure_state)

    # 7. Compute ratio
    if cap_val > 0:
        raw_ratio = Decimal(demand_count) / Decimal(cap_val)
        rounded_ratio = raw_ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        ratio_result = (SignalStatus.AVAILABLE, rounded_ratio)
    else:
        # cap_val == 0: division by zero is structurally NOT_APPLICABLE
        ratio_result = (SignalStatus.NOT_APPLICABLE, None)

    return (
        cap_result,
        deficit_result,
        state_result,
        ratio_result,
        tuple(quality_flags),
    )
