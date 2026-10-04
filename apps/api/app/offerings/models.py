"""Immutable P10 provider facts. Unknown is represented by None, never zero."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum


class SourceType(str, Enum):
    SYNTHETIC = "SYNTHETIC"
    INSTITUTIONAL = "INSTITUTIONAL"


class Modality(str, Enum):
    IN_PERSON = "IN_PERSON"
    ONLINE = "ONLINE"
    HYBRID = "HYBRID"
    UNKNOWN = "UNKNOWN"


class CapacityState(str, Enum):
    KNOWN_OPEN = "KNOWN_OPEN"
    KNOWN_FULL = "KNOWN_FULL"
    KNOWN_OVER_CAPACITY = "KNOWN_OVER_CAPACITY"
    UNKNOWN_CAPACITY = "UNKNOWN_CAPACITY"
    STALE_CAPACITY = "STALE_CAPACITY"
    INVALID_PROVIDER_FACT = "INVALID_PROVIDER_FACT"


@dataclass(frozen=True)
class MeetingBlock:
    day: int  # ISO weekday, 1-7
    starts_at: time
    ends_at: time
    timezone: str

    def __post_init__(self) -> None:
        if (type(self.day) is not int or self.day not in range(1, 8)
                or not isinstance(self.starts_at, time) or not isinstance(self.ends_at, time)
                or self.starts_at >= self.ends_at or not self.timezone):
            raise ValueError("invalid meeting block")


@dataclass(frozen=True)
class OfferingSection:
    section_id: str
    course_code: str
    status: str | None
    modality: Modality
    campus: str | None
    location: str | None
    meetings: tuple[MeetingBlock, ...]
    capacity: int | None
    enrolled: int | None
    available: int | None
    waitlist: int | None
    provenance: str
    student_visible: bool = False

    def __post_init__(self) -> None:
        if not self.section_id or not self.course_code or not self.provenance:
            raise ValueError("section identity and provenance are required")
        if not isinstance(self.modality, Modality):
            raise ValueError("invalid section modality")
        if type(self.student_visible) is not bool:
            raise ValueError("invalid student visibility fact")


@dataclass(frozen=True)
class OfferingSnapshot:
    university_id: str
    period_key: str
    snapshot_id: str
    source_version: str
    source_type: SourceType
    source_at: datetime
    fresh_until: datetime
    complete: bool
    sections: tuple[OfferingSection, ...]
    provenance: str

    def __post_init__(self) -> None:
        if not all((self.university_id, self.period_key, self.snapshot_id, self.source_version, self.provenance)):
            raise ValueError("snapshot provenance is required")
        if self.source_at.tzinfo is None or self.fresh_until.tzinfo is None:
            raise ValueError("snapshot timestamps must be timezone aware")
        if self.fresh_until < self.source_at:
            raise ValueError("freshness precedes source timestamp")
        if type(self.complete) is not bool or not isinstance(self.source_type, SourceType):
            raise ValueError("invalid snapshot coverage or source type")
        if self.source_type is SourceType.SYNTHETIC and "SYNTHETIC" not in self.provenance:
            raise ValueError("synthetic snapshot requires visible provenance")
        if len({section.section_id for section in self.sections}) != len(self.sections):
            raise ValueError("duplicate section identity")
