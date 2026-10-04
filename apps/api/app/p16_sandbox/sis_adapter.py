"""Sandbox SIS Read Adapter.

Implements the P15 SISReadAdapter contract to provide canonical academic records
and attempts for the 5 synthetic student personas, without creating parallel domain models
or accepting credentials.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping

from app.p15_adapters.sis import (
    CanonicalSISAcademicRecord,
    Entity,
    Failure,
    Freshness,
    SISFailure,
    SISHealth,
    SISPage,
    SISReadAdapter,
    SourceEvidence,
)
from app.rules.models import AttemptOutcome, StudentCourseAttempt

from .tenant import SANDBOX_INSTITUTION_ID, assert_sandbox_institution
from .transport import SandboxUniversityTransport, StaticFixtureTransport

STATUS_TO_OUTCOME: Mapping[str, AttemptOutcome] = {
    "ناجح": AttemptOutcome.PASSED,
    "راسب": AttemptOutcome.FAILED,
    "منسحب": AttemptOutcome.WITHDRAWN,
    "PASSED": AttemptOutcome.PASSED,
    "FAILED": AttemptOutcome.FAILED,
    "WITHDRAWN": AttemptOutcome.WITHDRAWN,
}


class SandboxSISAdapter:
    """P15-compliant read adapter for Morshidi Sandbox University."""

    def __init__(
        self,
        transport: SandboxUniversityTransport | None = None,
        institution_id: str = SANDBOX_INSTITUTION_ID,
    ) -> None:
        assert_sandbox_institution(institution_id)
        self.institution_id = institution_id
        self.adapter_id = "sandbox-sis-adapter"
        self.capabilities = frozenset({
            Entity.STUDENT,
            Entity.COURSE,
            Entity.ATTEMPT,
            Entity.OFFERING,
        })
        self.transport = transport or StaticFixtureTransport()
        self.source_version = "2026.10.02.v1"
        self.mapping_version = "2026.10.02.v1"

    def _create_evidence(
        self,
        now: datetime | None = None,
        external_record_id: str | None = None,
        cursor: str | None = None,
    ) -> SourceEvidence:
        current_time = now or datetime.now(timezone.utc)
        return SourceEvidence(
            institution_id=self.institution_id,
            adapter_id=self.adapter_id,
            source_version=self.source_version,
            mapping_version=self.mapping_version,
            observed_at=current_time,
            source_updated_at=current_time - timedelta(hours=1),
            fresh_until=current_time + timedelta(days=365),
            source_system_id="MORSHIDI_SANDBOX_UNIVERSITY",
            external_record_id=external_record_id,
            cursor=cursor,
            provenance="SYNTHETIC_LOCAL_CONTRACT",
        )

    async def health(self) -> SISHealth:
        """Return safe metadata diagnostics. Zero credentials or endpoints exposed."""
        now = datetime.now(timezone.utc)
        return SISHealth(
            institution_id=self.institution_id,
            adapter_id=self.adapter_id,
            available=True,
            last_success_at=now,
            mapping_version=self.mapping_version,
            capabilities=self.capabilities,
            last_error=None,
            freshness=Freshness.FRESH,
        )

    async def fetch_page(
        self,
        entity: Entity,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> SISPage:
        """Read-only paginated access to synthetic sandbox entities."""
        if entity not in self.capabilities:
            raise SISFailure(Failure.UNAVAILABLE)

        if entity is Entity.STUDENT:
            items = list(await self.transport.load_students())
        elif entity is Entity.COURSE:
            items = list(await self.transport.load_courses())
        elif entity is Entity.OFFERING:
            items = list(await self.transport.load_offerings())
        elif entity is Entity.ATTEMPT:
            rec_doc = await self.transport.load_academic_records()
            items = []
            for r in rec_doc.get("records", []):
                for att in r.get("attempts", []):
                    items.append({
                        "student_id": r["student_id"],
                        **att,
                    })
        else:
            raise SISFailure(Failure.UNAVAILABLE)

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        page_slice = items[offset : offset + limit]
        next_offset = offset + limit
        next_cursor = str(next_offset) if next_offset < len(items) else None

        evidence = self._create_evidence(cursor=cursor)
        return SISPage(
            institution_id=self.institution_id,
            entity=entity,
            records=tuple(page_slice),
            next_cursor=next_cursor,
            evidence=evidence,
        )

    async def get_student_profile(self, student_id: str) -> Mapping[str, Any] | None:
        """Retrieve sanitized synthetic student profile."""
        students = await self.transport.load_students()
        for s in students:
            if s.get("student_id") == student_id or s.get("university_id") == student_id:
                return {
                    k: v
                    for k, v in s.items()
                    if k not in {"password", "token", "secret"}
                }
        return None

    async def get_canonical_record(self, student_id: str) -> CanonicalSISAcademicRecord:
        """Map synthetic student academic record to CanonicalSISAcademicRecord."""
        rec_doc = await self.transport.load_academic_records()
        records = rec_doc.get("records", [])

        target_record: Mapping[str, Any] | None = None
        for r in records:
            if r.get("student_id") == student_id:
                target_record = r
                break

        if not target_record:
            raise SISFailure(Failure.INVALID_RESPONSE)

        evidence = self._create_evidence(external_record_id=student_id)

        raw_attempts = target_record.get("attempts", [])
        attempts: list[StudentCourseAttempt] = []
        for att in raw_attempts:
            code = att.get("course_code")
            source_status = att.get("source_status") or att.get("outcome")
            outcome = STATUS_TO_OUTCOME.get(source_status, AttemptOutcome.PASSED)
            if code:
                attempts.append(StudentCourseAttempt(course_code=code, outcome=outcome))

        raw_credits = target_record.get("earned_credits", 0)
        earned_credits = Decimal(str(raw_credits))

        # Enrolled courses in current active semester if any
        enrolled_courses: list[str] = []
        for att in raw_attempts:
            if att.get("outcome") == "ENROLLED":
                enrolled_courses.append(att["course_code"])

        return CanonicalSISAcademicRecord(
            institution_id=self.institution_id,
            student_id=student_id,
            program_id=target_record.get("program_id", "IT"),
            major_id=target_record.get("major_id", "AI"),
            plan_id=target_record.get("plan_id", "12"),
            plan_version_id=target_record.get("plan_version_id", "PLAN-12-V1"),
            earned_credits=earned_credits,
            attempts=tuple(attempts),
            enrolled_course_codes=tuple(enrolled_courses),
            evidence=evidence,
        )
