"""Bounded, replayable, no-write modeled offering scenarios."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import time
from enum import Enum
from hashlib import sha256
import json

from .models import MeetingBlock, Modality, OfferingSection, OfferingSnapshot


@dataclass(frozen=True)
class Assumption:
    kind: str
    section_id: str
    course_code: str | None = None
    capacity: int | None = None
    demand_delta: int = 0
    day: int | None = None
    starts_at: time | None = None
    ends_at: time | None = None
    modality: Modality | None = None
    campus: str | None = None
    location: str | None = None
    provenance: str = "MODELLED_ASSUMPTION_ONLY"

    def __post_init__(self) -> None:
        if self.provenance != "MODELLED_ASSUMPTION_ONLY":
            raise ValueError("assumption provenance is fixed")


class CurriculumAssumptionKind(str, Enum):
    COURSE_AVAILABLE_IN_MODELED_PERIOD = "COURSE_AVAILABLE_IN_MODELED_PERIOD"
    COURSE_NOT_AVAILABLE_IN_MODELED_PERIOD = "COURSE_NOT_AVAILABLE_IN_MODELED_PERIOD"


class SensitivityKind(str, Enum):
    CAPACITY = "CAPACITY"
    DEMAND_DELTA = "DEMAND_DELTA"
    ADDED_SECTION_COUNT = "ADDED_SECTION_COUNT"


@dataclass(frozen=True)
class SensitivityPoint:
    value: int
    comparison: ScenarioComparison


def sensitivity(snapshot: OfferingSnapshot, *, kind: SensitivityKind, course_code: str,
                section_id: str, start: int, stop: int, step: int,
                section_capacity: int | None = None) -> tuple[SensitivityPoint, ...]:
    """Sweep one modeled variable over at most eleven deterministic points."""
    if (type(start) is not int or type(stop) is not int or type(step) is not int
            or step < 1 or start > stop or (stop - start) // step >= 11
            or not any(s.course_code == course_code for s in snapshot.sections)):
        raise ValueError("invalid sensitivity range or course")
    if kind is SensitivityKind.CAPACITY:
        if not 0 <= start <= stop <= 1000 or not any(
            s.section_id == section_id and s.course_code == course_code for s in snapshot.sections
        ):
            raise ValueError("invalid sensitivity section or capacity")
    elif kind is SensitivityKind.DEMAND_DELTA:
        if not -1000 <= start <= stop <= 1000:
            raise ValueError("invalid sensitivity demand")
    elif kind is SensitivityKind.ADDED_SECTION_COUNT:
        if not 0 <= start <= stop <= 5 or type(section_capacity) is not int or not 0 <= section_capacity <= 1000:
            raise ValueError("invalid sensitivity section count")
    else:
        raise ValueError("unsupported sensitivity kind")
    points = []
    for value in range(start, stop + 1, step):
        if kind is SensitivityKind.CAPACITY:
            assumptions = (Assumption("CHANGE_CAPACITY", section_id, course_code, capacity=value),)
        elif kind is SensitivityKind.DEMAND_DELTA:
            assumptions = (Assumption("CHANGE_DEMAND", "", course_code, demand_delta=value),)
        else:
            assumptions = tuple(Assumption("ADD_SECTION", f"MODELLED-SENS-{course_code}-{n}",
                                           course_code, section_capacity) for n in range(value))
            # simulate requires a nonempty assumption set; a zero-addition point
            # is represented by a zero demand delta, preserving the base supply.
            if not assumptions:
                assumptions = (Assumption("CHANGE_DEMAND", "", course_code, demand_delta=0),)
        points.append(SensitivityPoint(value, simulate(snapshot, assumptions)))
    return tuple(points)


@dataclass(frozen=True)
class ScenarioComparison:
    base_fingerprint: str
    scenario_fingerprint: str
    assumptions: tuple[Assumption, ...]
    base_supplied_seats: int | None
    modeled_supplied_seats: int | None
    seat_delta: int | None
    modeled_demand_delta: int
    section_delta: int
    modeled_snapshot: OfferingSnapshot
    label: str = "MODELLED ASSUMPTIONS ONLY — NO OPERATIONAL WRITE"


def fingerprint(snapshot: OfferingSnapshot) -> str:
    payload = (
        snapshot.university_id, snapshot.period_key, snapshot.snapshot_id,
        snapshot.source_version, snapshot.source_at.isoformat(), snapshot.fresh_until.isoformat(),
        snapshot.complete,
        tuple((s.section_id, s.course_code, s.status, s.modality.value, s.campus, s.location,
               tuple((m.day, m.starts_at.isoformat(), m.ends_at.isoformat(), m.timezone) for m in s.meetings),
               s.capacity, s.enrolled, s.available, s.waitlist, s.provenance) for s in snapshot.sections),
        tuple(s.student_visible for s in snapshot.sections),
    )
    return sha256(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _total(snapshot: OfferingSnapshot) -> int | None:
    return sum(section.capacity for section in snapshot.sections) if all(
        section.capacity is not None for section in snapshot.sections) else None


def simulate(snapshot: OfferingSnapshot, assumptions: tuple[Assumption, ...]) -> ScenarioComparison:
    if not 1 <= len(assumptions) <= 5 or len(snapshot.sections) > 200:
        raise ValueError("scenario exceeds bounds")
    sections = {section.section_id: section for section in snapshot.sections}
    original = set(sections)
    demand_delta = 0
    for item in assumptions:
        if item.kind == "ADD_SECTION":
            if item.section_id in sections or not item.section_id.startswith("MODELLED-") or not item.course_code:
                raise ValueError("invalid modeled section")
            if item.capacity is None or not 0 <= item.capacity <= 1000:
                raise ValueError("invalid modeled capacity")
            sections[item.section_id] = OfferingSection(item.section_id, item.course_code, "MODELLED",
                item.modality or Modality.UNKNOWN, item.campus, item.location,
                (), item.capacity, None, None, None,
                "MODELLED_ASSUMPTION")
        elif item.kind == "REMOVE_SECTION":
            if item.section_id not in original or item.section_id not in sections:
                raise ValueError("section absent from base")
            del sections[item.section_id]
        elif item.kind == "CHANGE_CAPACITY":
            if item.section_id not in sections or item.capacity is None or not 0 <= item.capacity <= 1000:
                raise ValueError("invalid capacity assumption")
            section = sections[item.section_id]
            sections[item.section_id] = replace(section, capacity=item.capacity, available=None,
                                                provenance="MODELLED_ASSUMPTION")
        elif item.kind == "SHIFT_TIME":
            if item.section_id not in sections or item.day not in range(1, 8) or item.starts_at is None or item.ends_at is None:
                raise ValueError("invalid time assumption")
            section = sections[item.section_id]
            zone = section.meetings[0].timezone if section.meetings else "Asia/Amman"
            block = MeetingBlock(item.day, item.starts_at, item.ends_at, zone)
            sections[item.section_id] = replace(section, meetings=(block,), provenance="MODELLED_ASSUMPTION")
        elif item.kind == "CHANGE_MODALITY":
            if item.section_id not in sections or item.modality is None:
                raise ValueError("invalid modality assumption")
            sections[item.section_id] = replace(sections[item.section_id], modality=item.modality,
                                                provenance="MODELLED_ASSUMPTION")
        elif item.kind == "CHANGE_LOCATION":
            if item.section_id not in sections or (item.campus is None and item.location is None):
                raise ValueError("invalid location assumption")
            sections[item.section_id] = replace(sections[item.section_id], campus=item.campus,
                                                location=item.location,
                                                provenance="MODELLED_ASSUMPTION")
        elif item.kind == "CHANGE_DEMAND":
            if not -1000 <= item.demand_delta <= 1000:
                raise ValueError("invalid demand assumption")
            demand_delta += item.demand_delta
        elif item.kind in {kind.value for kind in CurriculumAssumptionKind}:
            if not item.course_code or not any(s.course_code == item.course_code for s in snapshot.sections):
                raise ValueError("modeled curriculum course must exist in base supply")
            if item.kind == CurriculumAssumptionKind.COURSE_NOT_AVAILABLE_IN_MODELED_PERIOD.value:
                sections = {key: section for key, section in sections.items()
                            if section.course_code != item.course_code}
            else:
                # Availability means only known base sections can be restored.
                # It does not create a catalog fact or change academic rules.
                sections.update({s.section_id: replace(s, provenance="MODELLED_CURRICULUM_ASSUMPTION")
                                 for s in snapshot.sections if s.course_code == item.course_code})
        else:
            raise ValueError("unsupported scenario assumption")
    modeled = replace(snapshot, snapshot_id=f"modeled:{snapshot.snapshot_id}",
                      sections=tuple(sorted(sections.values(), key=lambda s: s.section_id)),
                      provenance="MODELLED ASSUMPTIONS; BASE: " + snapshot.provenance)
    base_total, modeled_total = _total(snapshot), _total(modeled)
    base_fingerprint = fingerprint(snapshot)
    scenario_payload = (base_fingerprint, fingerprint(modeled), tuple(asdict(item) for item in assumptions))
    scenario_fingerprint = sha256(json.dumps(scenario_payload, sort_keys=True, default=str,
                                            separators=(",", ":")).encode()).hexdigest()
    return ScenarioComparison(base_fingerprint, scenario_fingerprint, assumptions,
                              base_total, modeled_total,
                              modeled_total - base_total if base_total is not None and modeled_total is not None else None,
                              demand_delta, len(modeled.sections) - len(snapshot.sections), modeled)
