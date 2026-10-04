"""Deterministic fictional facts; never serves an actual university tenant."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from .models import MeetingBlock, Modality, OfferingSection, OfferingSnapshot, SourceType

FAKE_UNIVERSITY_ID = "f1000000-0000-0000-0000-000000000010"
FAKE_PERIOD = "SANDBOX-P10-FALL"
_SOURCE_AT = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _section(identifier: str, course: str, day: int, start: int, end: int, *,
             modality: Modality = Modality.IN_PERSON, campus: str | None = "FICTIONAL-CAMPUS",
             capacity: int | None = 30, enrolled: int | None = 10,
             waitlist: int | None = None, status: str = "OPEN") -> OfferingSection:
    return OfferingSection(identifier, course, status, modality, campus,
                           "SYNTHETIC-ROOM" if campus else None,
                           (MeetingBlock(day, time(start), time(end), "Asia/Amman"),),
                           capacity, enrolled, None, waitlist, "SYNTHETIC_SANDBOX_FACT", True)


class FakeUniversityOfferingProvider:
    async def load_snapshot(self, university_id: str, period_key: str) -> OfferingSnapshot | None:
        if university_id != FAKE_UNIVERSITY_ID or period_key != FAKE_PERIOD:
            return None
        return fake_snapshot()


def fake_snapshot(*, stale: bool = False) -> OfferingSnapshot:
    sections = (
        _section("SYN-CS101-A", "CS101", 1, 9, 11),
        _section("SYN-CS101-B", "CS101", 1, 13, 15, capacity=30, enrolled=30, waitlist=4,
                 status="FULL"),
        _section("SYN-MATH101-A", "MATH101", 1, 10, 12, capacity=25, enrolled=24),
        _section("SYN-HIST101-A", "HIST101", 2, 9, 11, modality=Modality.ONLINE,
                 campus=None, capacity=None, enrolled=None),
        _section("SYN-PHYS101-A", "PHYS101", 3, 14, 16, modality=Modality.HYBRID),
    )
    return OfferingSnapshot(
        FAKE_UNIVERSITY_ID, FAKE_PERIOD, "synthetic-p10-1", "p10-synthetic-v1",
        SourceType.SYNTHETIC, _SOURCE_AT,
        _SOURCE_AT + (timedelta(days=1) if stale else timedelta(days=365)),
        True, sections, "SANDBOX / SYNTHETIC DATA",
    )
