"""Exact supplied-fact offering and capacity matching."""

from __future__ import annotations

from .models import (
    AggregationScope,
    CapacityFact,
    CapacityState,
    FactProvenance,
    OfferingFact,
    OfferingState,
    TargetPeriod,
)


def offering_match(
    facts: tuple[OfferingFact, ...] | None,
    scope: AggregationScope,
    period: TargetPeriod,
    course_code: str,
) -> tuple[OfferingState, FactProvenance]:
    if facts is None:
        return OfferingState.OFFERING_DATA_UNAVAILABLE, FactProvenance.UNAVAILABLE
    match = next(
        (
            item for item in facts
            if item.university_id == scope.university_id
            and item.target_period == period
            and item.course_code == course_code
        ),
        None,
    )
    if match is None:
        return OfferingState.NO_MATCHING_OFFERING_FACT, FactProvenance.UNAVAILABLE
    return OfferingState.MATCHING_OFFERING_FACT, match.provenance


def capacity_match(
    facts: tuple[CapacityFact, ...] | None,
    scope: AggregationScope,
    period: TargetPeriod,
    course_code: str,
) -> CapacityFact | None:
    if facts is None:
        return None
    matches = tuple(
        item for item in facts
        if item.university_id == scope.university_id
        and item.target_period == period
        and item.course_code == course_code
        and _optional_equal(item.major_id, scope.major_id)
        and _optional_equal(item.study_plan_id, scope.study_plan_id)
        and _optional_equal(item.study_plan_version, scope.study_plan_version)
    )
    if len(matches) > 1:
        raise ValueError("multiple exact capacity facts")
    return matches[0] if matches else None


def _optional_equal(fact_value: str | None, scope_value: str | None) -> bool:
    return fact_value is None if scope_value is None else fact_value == scope_value
