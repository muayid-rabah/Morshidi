"""Sandbox Offering Provider.

Reuses the P10 OfferingProvider and OfferingSnapshot architecture to map
all 204 canonical sandbox course sections into a complete synthetic snapshot.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Sequence

from app.offerings.models import (
    MeetingBlock,
    Modality,
    OfferingSection,
    OfferingSnapshot,
    SourceType,
)
from app.offerings.provider import CourseOfferingProvider

from .tenant import SANDBOX_INSTITUTION_ID, assert_sandbox_institution
from .transport import SandboxUniversityTransport, StaticFixtureTransport

ARABIC_DAY_TO_ISO: dict[str, int] = {
    "الأحد": 7,
    "الاثنين": 1,
    "الثلاثاء": 2,
    "الأربعاء": 3,
    "الخميس": 4,
    "الجمعة": 5,
    "السبت": 6,
}


def _parse_time(time_str: str | None, default_hour: int) -> time:
    if not time_str:
        return time(default_hour, 0)
    try:
        parts = time_str.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return time(default_hour, 0)


def _resolve_days(section_dict: dict) -> list[int]:
    days_array = section_dict.get("days_array")
    if days_array and isinstance(days_array, (list, tuple)):
        iso_days = [ARABIC_DAY_TO_ISO[d] for d in days_array if d in ARABIC_DAY_TO_ISO]
        if iso_days:
            return iso_days

    days_str = str(section_dict.get("days", "")).strip()
    if "ح ث خ" in days_str:
        return [7, 2, 4]
    if "ن ر" in days_str:
        return [1, 3]
    if "الخميس" in days_str:
        return [4]
    if "الثلاثاء" in days_str:
        return [2]
    if "الأربعاء" in days_str:
        return [3]
    if "الاثنين" in days_str:
        return [1]
    if "الأحد" in days_str:
        return [7]

    return [1]


class SandboxOfferingProvider(CourseOfferingProvider):
    """P10-compliant course offering provider for Morshidi Sandbox University."""

    def __init__(
        self,
        transport: SandboxUniversityTransport | None = None,
        institution_id: str = SANDBOX_INSTITUTION_ID,
    ) -> None:
        assert_sandbox_institution(institution_id)
        self.institution_id = institution_id
        self.transport = transport or StaticFixtureTransport()
        self.source_version = "2026.10.02.v1"
        self._source_at = datetime(2026, 10, 2, tzinfo=timezone.utc)

    async def load_snapshot(
        self,
        university_id: str,
        period_key: str,
    ) -> OfferingSnapshot | None:
        """Load synthetic offering snapshot for the sandbox tenant only.

        Returns None if university_id does not match the sandbox tenant.
        """
        if university_id != self.institution_id:
            return None

        raw_sections = await self.transport.load_offerings()
        sections: list[OfferingSection] = []

        for sec in raw_sections:
            sec_id = sec.get("id") or f"SEC-{sec.get('course_code')}-{sec.get('section_number', 1)}"
            course_code = sec.get("course_code", "")
            status = sec.get("status", "متاحة")
            location = sec.get("room")
            campus = "عمان - الحرم الرئيسي"

            days = _resolve_days(sec)
            start_t = _parse_time(sec.get("start_time"), 8)
            end_t = _parse_time(sec.get("end_time"), 9)
            if start_t >= end_t:
                end_t = time(min(start_t.hour + 1, 23), start_t.minute)

            meeting_blocks = tuple(
                MeetingBlock(day=day, starts_at=start_t, ends_at=end_t, timezone="Asia/Amman")
                for day in days
            )

            cap = int(sec["capacity"]) if sec.get("capacity") is not None else 40
            enrolled = int(sec["enrolled"]) if sec.get("enrolled") is not None else 0
            available = int(sec["available"]) if sec.get("available") is not None else (cap - enrolled)

            section_obj = OfferingSection(
                section_id=sec_id,
                course_code=course_code,
                status=status,
                modality=Modality.IN_PERSON,
                campus=campus,
                location=location,
                meetings=meeting_blocks,
                capacity=cap,
                enrolled=enrolled,
                available=available,
                waitlist=None,
                provenance="MORSHIDI_SANDBOX_UNIVERSITY / SYNTHETIC OFFERING",
                student_visible=True,
            )
            sections.append(section_obj)

        return OfferingSnapshot(
            university_id=self.institution_id,
            period_key=period_key,
            snapshot_id=f"snapshot-sandbox-{period_key}",
            source_version=self.source_version,
            source_type=SourceType.SYNTHETIC,
            source_at=self._source_at,
            fresh_until=self._source_at + timedelta(days=365),
            complete=True,
            sections=tuple(sections),
            provenance="MORSHIDI_SANDBOX_UNIVERSITY / SYNTHETIC DATA",
        )
