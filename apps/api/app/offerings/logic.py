"""Pure P10 timetable, availability, and aggregate reconciliation calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from enum import Enum

from app.mock_registration.models import DemandAggregationResult, DemandStatus
from app.mock_registration.registries import DemandMetricId

from .models import CapacityState, MeetingBlock, OfferingSection, OfferingSnapshot


@dataclass(frozen=True)
class TimeConflict:
    reason: str
    first_section_id: str
    second_section_id: str
    day: int
    starts_at: time | None
    ends_at: time | None
    timezone: str | None


class OperationalState(str, Enum):
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    SNAPSHOT_STALE = "SNAPSHOT_STALE"
    NO_MATCHING_OFFERING = "NO_MATCHING_OFFERING"
    OFFERING_COVERAGE_INCOMPLETE = "OFFERING_COVERAGE_INCOMPLETE"
    SECTION_OPEN = "SECTION_OPEN"
    SECTION_FULL = "SECTION_FULL"
    SECTION_CLOSED = "SECTION_CLOSED"
    SECTION_UNKNOWN_CAPACITY = "SECTION_UNKNOWN_CAPACITY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_ACADEMICALLY_ELIGIBLE = "NOT_ACADEMICALLY_ELIGIBLE"


def conflict(first: OfferingSection, second: OfferingSection) -> tuple[TimeConflict, ...]:
    result = []
    for a in first.meetings:
        for b in second.meetings:
            if a.day == b.day and a.timezone != b.timezone:
                result.append(TimeConflict("TIMEZONE_UNCOMPARABLE", first.section_id,
                                           second.section_id, a.day, None, None, None))
            elif a.day == b.day:
                start, end = max(a.starts_at, b.starts_at), min(a.ends_at, b.ends_at)
                if start < end:
                    result.append(TimeConflict("TIME_OVERLAP", first.section_id,
                                               second.section_id, a.day, start, end, a.timezone))
    return tuple(result)


def capacity_state(section: OfferingSection, *, stale: bool = False) -> CapacityState:
    values = (section.capacity, section.enrolled, section.available, section.waitlist)
    if any(value is not None and (type(value) is not int or value < 0) for value in values):
        return CapacityState.INVALID_PROVIDER_FACT
    if section.capacity is not None and section.enrolled is not None:
        derived = section.capacity - section.enrolled
        if derived < 0:
            return CapacityState.KNOWN_OVER_CAPACITY
        if ((section.status == "FULL" and derived > 0)
                or (section.status == "OPEN" and derived <= 0)):
            return CapacityState.INVALID_PROVIDER_FACT
        if section.available is not None and section.available != max(derived, 0):
            return CapacityState.INVALID_PROVIDER_FACT
    elif section.available is not None:
        # A provider may supply this fact independently, but it cannot validate total seats.
        return CapacityState.STALE_CAPACITY if stale else (
            CapacityState.KNOWN_OPEN if section.available else CapacityState.KNOWN_FULL)
    if stale:
        return CapacityState.STALE_CAPACITY
    if section.capacity is None or section.enrolled is None:
        return CapacityState.UNKNOWN_CAPACITY
    return CapacityState.KNOWN_OPEN if section.capacity > section.enrolled else CapacityState.KNOWN_FULL


def operational_state(course_code: str, academically_eligible: bool | None,
                      snapshot: OfferingSnapshot | None, now: datetime) -> OperationalState:
    if academically_eligible is None:
        return OperationalState.REVIEW_REQUIRED
    if academically_eligible is False:
        return OperationalState.NOT_ACADEMICALLY_ELIGIBLE
    if snapshot is None:
        return OperationalState.PROVIDER_UNAVAILABLE
    if now > snapshot.fresh_until:
        return OperationalState.SNAPSHOT_STALE
    sections = tuple(section for section in snapshot.sections if section.course_code == course_code)
    if not sections:
        return (OperationalState.NO_MATCHING_OFFERING if snapshot.complete
                else OperationalState.OFFERING_COVERAGE_INCOMPLETE)
    active_sections = tuple(section for section in sections if section.status in {"OPEN", "FULL"})
    if not active_sections:
        return (OperationalState.SECTION_CLOSED if all(section.status in {"CLOSED", "CANCELLED"}
                                                    for section in sections)
                else OperationalState.REVIEW_REQUIRED)
    states = {capacity_state(section) for section in active_sections}
    if CapacityState.INVALID_PROVIDER_FACT in states or CapacityState.KNOWN_OVER_CAPACITY in states:
        return OperationalState.REVIEW_REQUIRED
    if CapacityState.KNOWN_OPEN in states:
        return OperationalState.SECTION_OPEN
    if CapacityState.UNKNOWN_CAPACITY in states:
        return OperationalState.SECTION_UNKNOWN_CAPACITY
    return OperationalState.SECTION_FULL


@dataclass(frozen=True)
class SupplyComparison:
    status: str
    observed_intent_demand: int | None
    supplied_section_capacity: int | None
    seat_gap: int | None  # positive means observed demand exceeds supplied seats
    demand_to_capacity_ratio: Decimal | None
    full_sections: int | None
    unknown_capacity_sections: int | None
    source_version: str | None
    source_type: str | None
    provenance: str | None
    freshness_status: str
    fresh_until: datetime | None
    coverage_complete: bool | None
    demand_status: str
    demand_quality_flags: tuple[str, ...]
    observed_only: bool
    population_coverage_ratio: Decimal | None


def reconcile(demand: DemandAggregationResult, snapshot: OfferingSnapshot | None,
              course_code: str, now: datetime) -> SupplyComparison:
    if snapshot is not None and (snapshot.university_id != demand.aggregation_scope.university_id
                                 or snapshot.period_key != demand.target_period.period_key):
        raise ValueError("demand and offering scope mismatch")
    demand_meta = (demand.status.value, tuple(flag.value for flag in demand.quality_flags),
                   demand.coverage.observed_intents_only, demand.coverage.population_coverage_ratio)
    if demand.status is DemandStatus.SUPPRESSED:
        return SupplyComparison("SUPPRESSED", None, None, None, None, None, None,
                                snapshot.source_version if snapshot else None,
                                snapshot.source_type.value if snapshot else None,
                                snapshot.provenance if snapshot else None,
                                ("STALE" if now > snapshot.fresh_until else "FRESH") if snapshot else "UNAVAILABLE",
                                snapshot.fresh_until if snapshot else None,
                                snapshot.complete if snapshot else None, *demand_meta)
    counts = tuple(m.value for m in demand.metrics if m.metric_id is DemandMetricId.COURSE_INTENT_OWNER_COUNT
                   and m.course_code == course_code and m.study_plan_id is None)
    observed = counts[0] if len(counts) == 1 and type(counts[0]) is int else None
    if snapshot is None:
        return SupplyComparison("PROVIDER_UNAVAILABLE", observed, None, None, None, None, None,
                                None, None, None, "UNAVAILABLE", None, None, *demand_meta)
    selected = tuple(s for s in snapshot.sections if s.course_code == course_code
                     and (s.status in {"OPEN", "FULL"} or
                          (s.status == "MODELLED" and snapshot.provenance.startswith("MODELLED ASSUMPTIONS"))))
    states = tuple(capacity_state(s, stale=now > snapshot.fresh_until) for s in selected)
    stale = now > snapshot.fresh_until
    unknown = None if stale else sum(section.capacity is None for section in selected)
    full = None if stale else sum(state is CapacityState.KNOWN_FULL for state in states)
    valid = (snapshot.complete and not stale and bool(selected)
             and all(s.capacity is not None and state not in (
                 CapacityState.INVALID_PROVIDER_FACT, CapacityState.KNOWN_OVER_CAPACITY)
                 for s, state in zip(selected, states)))
    supplied = sum(s.capacity for s in selected) if valid else None
    gap = observed - supplied if observed is not None and supplied is not None else None
    ratio = ((Decimal(observed) / Decimal(supplied)).quantize(Decimal("0.0001"))
             if gap is not None and supplied else None)
    status = ("AVAILABLE" if gap is not None else "INCOMPLETE_OR_STALE_SUPPLY"
              if not valid else "DEMAND_UNAVAILABLE")
    return SupplyComparison(status, observed, supplied, gap, ratio, full, unknown,
                            snapshot.source_version, snapshot.source_type.value, snapshot.provenance,
                            "STALE" if stale else "FRESH", snapshot.fresh_until, snapshot.complete,
                            *demand_meta)


def select_nonconflicting_sections(snapshot: OfferingSnapshot | None,
                                   course_codes: tuple[str, ...], now: datetime) -> tuple[str, ...] | None:
    """Explicit operational overlay; None means a known-open conflict-free set is unavailable."""
    if snapshot is None or now > snapshot.fresh_until or not snapshot.complete or len(course_codes) > 10:
        return None
    by_course = {
        code: tuple(s for s in snapshot.sections if s.course_code == code and s.status == "OPEN"
                    and capacity_state(s) is CapacityState.KNOWN_OPEN)
        for code in course_codes
    }
    if any(not sections for sections in by_course.values()):
        return None

    visited = 0

    def choose(index: int, selected: tuple[OfferingSection, ...]) -> tuple[str, ...] | None:
        nonlocal visited
        visited += 1
        if visited > 5000:
            return None  # Bounded search; never claim a definitive absence of feasible sections.
        if index == len(course_codes):
            return tuple(section.section_id for section in selected)
        for candidate in by_course[course_codes[index]]:
            if all(not conflict(candidate, existing) for existing in selected):
                result = choose(index + 1, (*selected, candidate))
                if result is not None:
                    return result
        return None

    return choose(0, ())
