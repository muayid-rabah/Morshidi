"""P10 pure synthetic contracts and fail-closed calculations."""

from dataclasses import replace
from datetime import datetime, time, timezone
import asyncio

import pytest

from app.mock_registration.models import (
    AggregationScope, CoverageMetadata, DemandAggregationResult, DemandMetric, DemandStatus,
    TargetPeriod, TargetPeriodClass,
)
from app.mock_registration.registries import DemandMetricId
from app.offerings.fake_provider import FAKE_PERIOD, FAKE_UNIVERSITY_ID, FakeUniversityOfferingProvider, fake_snapshot
from app.offerings.logic import (
    OperationalState, capacity_state, conflict, operational_state, reconcile,
    select_nonconflicting_sections,
)
from app.offerings.models import CapacityState, MeetingBlock, Modality, OfferingSection
from app.offerings.simulation import (
    Assumption, SensitivityKind, fingerprint, sensitivity, simulate,
)

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def section(identifier="A", *, start=9, end=11, day=1, capacity=30, enrolled=10, available=None):
    return OfferingSection(identifier, "CS101", "FULL" if capacity is not None and capacity == enrolled else "OPEN",
                           Modality.IN_PERSON, None, None,
                           (MeetingBlock(day, time(start), time(end), "Asia/Amman"),),
                           capacity, enrolled, available, None, "SYNTHETIC_SANDBOX_FACT")


def demand(count: int | None, status: DemandStatus = DemandStatus.AVAILABLE):
    metrics = (() if count is None else (DemandMetric(DemandMetricId.COURSE_INTENT_OWNER_COUNT,
                                                    count, course_code="CS101"),))
    return DemandAggregationResult(
        "1.0", status, AggregationScope(FAKE_UNIVERSITY_ID),
        TargetPeriod(FAKE_UNIVERSITY_ID, FAKE_PERIOD, TargetPeriodClass.SYNTHETIC_SANDBOX_PERIOD, "v1"),
        metrics, (), CoverageMetadata(True, None, None, None), (), (), (), (), (),
    )


def test_fake_provider_is_tenant_and_period_scoped():
    provider = FakeUniversityOfferingProvider()
    snapshot = asyncio.run(provider.load_snapshot(FAKE_UNIVERSITY_ID, FAKE_PERIOD))
    assert snapshot.source_version == "p10-synthetic-v1"
    assert snapshot.provenance == "SANDBOX / SYNTHETIC DATA"
    assert len(snapshot.sections) == 5
    assert asyncio.run(provider.load_snapshot("another-tenant", FAKE_PERIOD)) is None
    assert asyncio.run(provider.load_snapshot(FAKE_UNIVERSITY_ID, "other-period")) is None


def test_snapshot_normalization_rejects_unversioned_or_ambiguous_facts():
    snapshot = fake_snapshot()
    with pytest.raises(ValueError):
        replace(snapshot, source_version="")
    with pytest.raises(ValueError):
        replace(snapshot, sections=(snapshot.sections[0], snapshot.sections[0]))
    with pytest.raises(ValueError):
        replace(snapshot, provenance="official")
    with pytest.raises(ValueError):
        replace(snapshot.sections[0], section_id="")
    with pytest.raises(ValueError):
        MeetingBlock(True, time(9), time(10), "Asia/Amman")


def test_modeled_location_is_separate_from_provider_location():
    snapshot = fake_snapshot()
    location = simulate(snapshot, (Assumption("CHANGE_LOCATION", "SYN-CS101-A",
                                              campus="MODELLED-CAMPUS", location="MODELLED-ROOM"),))
    assert location.modeled_snapshot.sections[0].campus == "MODELLED-CAMPUS"
    assert snapshot.sections[0].campus != "MODELLED-CAMPUS"


@pytest.mark.parametrize("start,end,expected", [(9, 11, True), (10, 12, True),
                                                   (8, 12, True), (11, 13, False)])
def test_exact_overlap_and_back_to_back(start, end, expected):
    actual = conflict(section(), section("B", start=start, end=end))
    assert bool(actual) is expected
    if actual:
        assert actual[0].reason == "TIME_OVERLAP"


def test_different_day_has_no_conflict():
    assert not conflict(section(), section("B", day=2))


def test_mismatched_timezones_are_not_declared_conflict_free():
    other = replace(section("B"), meetings=(MeetingBlock(1, time(12), time(13), "UTC"),))
    assert conflict(section(), other)[0].reason == "TIMEZONE_UNCOMPARABLE"


def test_capacity_states_and_bad_provider_facts():
    assert capacity_state(section()) is CapacityState.KNOWN_OPEN
    assert capacity_state(section(enrolled=30)) is CapacityState.KNOWN_FULL
    assert capacity_state(section(capacity=None, enrolled=None)) is CapacityState.UNKNOWN_CAPACITY
    assert capacity_state(section(capacity=-1)) is CapacityState.INVALID_PROVIDER_FACT
    assert capacity_state(section(available=99)) is CapacityState.INVALID_PROVIDER_FACT
    assert capacity_state(section(enrolled=31)) is CapacityState.KNOWN_OVER_CAPACITY
    assert capacity_state(section(), stale=True) is CapacityState.STALE_CAPACITY


def test_operational_and_academic_states_remain_separate():
    snapshot = fake_snapshot()
    assert operational_state("CS101", True, snapshot, NOW) is OperationalState.SECTION_OPEN
    assert operational_state("CS101", False, snapshot, NOW) is OperationalState.NOT_ACADEMICALLY_ELIGIBLE
    assert operational_state("CS101", None, snapshot, NOW) is OperationalState.REVIEW_REQUIRED
    assert operational_state("CS101", True, None, NOW) is OperationalState.PROVIDER_UNAVAILABLE
    assert operational_state("UNLISTED", True, snapshot, NOW) is OperationalState.NO_MATCHING_OFFERING
    assert operational_state("UNLISTED", True, replace(snapshot, complete=False), NOW) is OperationalState.OFFERING_COVERAGE_INCOMPLETE
    assert operational_state("CS101", True, fake_snapshot(stale=True), NOW) is OperationalState.SNAPSHOT_STALE
    assert operational_state("HIST101", True, snapshot, NOW) is OperationalState.SECTION_UNKNOWN_CAPACITY
    closed = replace(snapshot, sections=(replace(snapshot.sections[0], status="CLOSED"),))
    assert operational_state("CS101", True, closed, NOW) is OperationalState.SECTION_CLOSED
    assert select_nonconflicting_sections(closed, ("CS101",), NOW) is None


@pytest.mark.parametrize("count,gap", [(10, -45), (55, 0), (60, 5)])
def test_exact_reconciliation(count, gap):
    result = reconcile(demand(count), fake_snapshot(), "CS101", NOW)
    assert result.observed_intent_demand == count
    assert result.supplied_section_capacity == 60
    assert result.seat_gap == count - 60
    assert result.full_sections == 1


def test_suppression_and_incomplete_supply_do_not_leak_or_fabricate():
    suppressed = reconcile(demand(None, DemandStatus.SUPPRESSED), fake_snapshot(), "CS101", NOW)
    assert suppressed.status == "SUPPRESSED" and suppressed.seat_gap is None
    assert suppressed.full_sections is None and suppressed.unknown_capacity_sections is None
    missing = reconcile(demand(10), None, "CS101", NOW)
    assert missing.status == "PROVIDER_UNAVAILABLE" and missing.supplied_section_capacity is None
    assert missing.observed_intent_demand == 10
    assert missing.full_sections is None
    unknown = reconcile(demand(10), fake_snapshot(), "HIST101", NOW)
    assert unknown.seat_gap is None and unknown.unknown_capacity_sections == 1
    stale = reconcile(demand(10), fake_snapshot(stale=True), "CS101", NOW)
    assert stale.seat_gap is None
    assert stale.freshness_status == "STALE" and stale.full_sections is None
    with pytest.raises(ValueError):
        reconcile(demand(10), replace(fake_snapshot(), university_id="another-tenant"), "CS101", NOW)


def test_explicit_planner_overlay_rejects_conflict_without_changing_base():
    snapshot = fake_snapshot()
    # Only the morning CS101 section has seats; it conflicts with MATH101.
    assert select_nonconflicting_sections(snapshot, ("CS101", "MATH101"), NOW) is None
    assert select_nonconflicting_sections(None, ("CS101",), NOW) is None
    assert select_nonconflicting_sections(snapshot, ("CS101", "HIST101"), NOW) is None
    assert select_nonconflicting_sections(snapshot, ("CS101", "PHYS101"), NOW) == (
        "SYN-CS101-A", "SYN-PHYS101-A")


def test_simulation_is_deterministic_bounded_and_no_write():
    snapshot = fake_snapshot()
    base_hash = fingerprint(snapshot)
    assumptions = (Assumption("ADD_SECTION", "MODELLED-CS101-C", "CS101", 30),
                   Assumption("CHANGE_CAPACITY", "SYN-CS101-A", capacity=40),
                   Assumption("CHANGE_DEMAND", "", demand_delta=15))
    first = simulate(snapshot, assumptions)
    second = simulate(snapshot, assumptions)
    assert first.scenario_fingerprint == second.scenario_fingerprint
    assert first.scenario_fingerprint != base_hash
    assert simulate(snapshot, (Assumption("CHANGE_DEMAND", "", demand_delta=1),)).scenario_fingerprint != (
        simulate(snapshot, (Assumption("CHANGE_DEMAND", "", demand_delta=2),)).scenario_fingerprint)
    assert first.base_fingerprint == base_hash == fingerprint(snapshot)
    assert first.section_delta == 1 and first.modeled_demand_delta == 15
    assert first.seat_delta is None  # Unknown-capacity base prevents an invented total.
    assert "MODELLED" in first.label and not hasattr(first, "winner")
    assert len(snapshot.sections) == 5
    with pytest.raises(ValueError):
        simulate(snapshot, (Assumption("ADD_SECTION", "SYN-CS101-A", "CS101", 30),))


def test_closed_curriculum_assumption_only_changes_modeled_supply():
    base = fake_snapshot()
    before = fingerprint(base)
    disabled = simulate(base, (Assumption("COURSE_NOT_AVAILABLE_IN_MODELED_PERIOD", "", "CS101"),))
    replay = simulate(base, (Assumption("COURSE_NOT_AVAILABLE_IN_MODELED_PERIOD", "", "CS101"),))
    assert disabled.scenario_fingerprint == replay.scenario_fingerprint
    assert all(s.course_code != "CS101" for s in disabled.modeled_snapshot.sections)
    assert disabled.section_delta == -2
    assert fingerprint(base) == before and len(base.sections) == 5
    enabled = simulate(base, (Assumption("COURSE_AVAILABLE_IN_MODELED_PERIOD", "", "CS101"),))
    assert len(enabled.modeled_snapshot.sections) == 5
    assert enabled.scenario_fingerprint != disabled.scenario_fingerprint
    with pytest.raises(ValueError):
        simulate(base, (Assumption("CHANGE_PREREQUISITE", "", "CS101"),))
    with pytest.raises(ValueError):
        simulate(base, (Assumption("COURSE_AVAILABLE_IN_MODELED_PERIOD", "", "UNKNOWN"),))


@pytest.mark.parametrize("kind,start,stop,step,capacity,expected", [
    (SensitivityKind.CAPACITY, 30, 50, 10, None, (30, 40, 50)),
    (SensitivityKind.DEMAND_DELTA, -10, 10, 10, None, (-10, 0, 10)),
    (SensitivityKind.ADDED_SECTION_COUNT, 0, 2, 1, 20, (0, 1, 2)),
])
def test_sensitivity_is_bounded_deterministic_and_no_write(kind, start, stop, step, capacity, expected):
    base = fake_snapshot()
    before = fingerprint(base)
    kwargs = dict(kind=kind, course_code="CS101", section_id="SYN-CS101-A",
                  start=start, stop=stop, step=step, section_capacity=capacity)
    points = sensitivity(base, **kwargs)
    assert tuple(point.value for point in points) == expected
    assert tuple(p.comparison.scenario_fingerprint for p in points) == tuple(
        p.comparison.scenario_fingerprint for p in sensitivity(base, **kwargs))
    assert len({p.comparison.scenario_fingerprint for p in points}) == len(points)
    assert fingerprint(base) == before
    if kind is SensitivityKind.ADDED_SECTION_COUNT:
        assert tuple(point.comparison.section_delta for point in points) == expected


def test_sensitivity_rejects_large_or_invalid_sweeps():
    base = fake_snapshot()
    for kwargs in (
        dict(kind=SensitivityKind.CAPACITY, start=0, stop=100, step=1),
        dict(kind=SensitivityKind.CAPACITY, start=20, stop=10, step=1),
        dict(kind=SensitivityKind.DEMAND_DELTA, start=-1001, stop=0, step=100),
        dict(kind=SensitivityKind.ADDED_SECTION_COUNT, start=0, stop=6, step=1),
    ):
        with pytest.raises(ValueError):
            sensitivity(base, course_code="CS101", section_id="SYN-CS101-A",
                        section_capacity=20, **kwargs)
