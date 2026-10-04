"""Read-only SIS contract and deterministic, tenant-bound normalization.

No vendor client or production credential is configured here. A caller must
explicitly bind an adapter through the institution registry before use.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, Protocol

from app.offerings.models import OfferingSnapshot
from app.plan_transition.ingestion import ImportPreview, stage_structured_import
from app.rules.models import AttemptOutcome, StudentCourseAttempt


class Entity(str, Enum):
    INSTITUTION = "INSTITUTION"
    STUDENT = "STUDENT"
    PROGRAM = "PROGRAM"
    MAJOR = "MAJOR"
    PLAN = "PLAN"
    PLAN_VERSION = "PLAN_VERSION"
    COURSE = "COURSE"
    ATTEMPT = "ATTEMPT"
    ENROLLMENT = "ENROLLMENT"
    OFFERING = "OFFERING"
    SECTION = "SECTION"


class Freshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class Failure(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    AUTHENTICATION = "AUTHENTICATION"
    PERMISSION = "PERMISSION"
    RATE_LIMIT = "RATE_LIMIT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    MAPPING_CONFLICT = "MAPPING_CONFLICT"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    STALE_DATA = "STALE_DATA"


class Reconciliation(str, Enum):
    MATCH = "MATCH"
    SOURCE_NEWER = "SOURCE_NEWER"
    LOCAL_NEWER = "LOCAL_NEWER"
    CONFLICT = "CONFLICT"
    MISSING_SOURCE = "MISSING_SOURCE"
    MISSING_LOCAL = "MISSING_LOCAL"
    UNMAPPED = "UNMAPPED"
    INVALID = "INVALID"


class SISFailure(RuntimeError):
    def __init__(self, code: Failure):
        self.code = code
        super().__init__(code.value)  # Never include upstream messages or credentials.


@dataclass(frozen=True)
class SourceEvidence:
    institution_id: str
    adapter_id: str
    source_version: str
    mapping_version: str
    observed_at: datetime
    source_updated_at: datetime | None
    fresh_until: datetime | None
    source_system_id: str = "UNCONFIGURED"
    external_record_id: str | None = None
    cursor: str | None = None
    provenance: str = "LOCAL_CONTRACT"

    def __post_init__(self) -> None:
        if not all((self.institution_id, self.adapter_id, self.source_version,
                    self.mapping_version, self.source_system_id, self.provenance)):
            raise ValueError("Incomplete SIS provenance")
        for instant in (self.observed_at, self.source_updated_at, self.fresh_until):
            if instant is not None and (instant.tzinfo is None or instant.utcoffset() is None):
                raise ValueError("SIS timestamps must be timezone-aware")
        if self.source_updated_at is not None and self.source_updated_at > self.observed_at:
            raise ValueError("SIS source update is after observation")

    def freshness_at(self, now: datetime) -> Freshness:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Current time must be timezone-aware")
        if self.fresh_until is None:
            return Freshness.UNKNOWN
        if now < self.observed_at:
            return Freshness.UNKNOWN
        return Freshness.FRESH if now <= self.fresh_until else Freshness.STALE


@dataclass(frozen=True)
class SISPage:
    institution_id: str
    entity: Entity
    records: tuple[Mapping[str, Any], ...]
    next_cursor: str | None
    evidence: SourceEvidence


@dataclass(frozen=True)
class SISHealth:
    """Safe internal diagnostics: no endpoint, credentials, or raw provider error."""

    institution_id: str
    adapter_id: str
    available: bool
    last_success_at: datetime | None
    mapping_version: str
    capabilities: frozenset[Entity]
    last_error: Failure | None
    freshness: Freshness


@dataclass(frozen=True)
class CanonicalSISAcademicRecord:
    """Validated read model. Not an authenticated owner or academic decision."""

    institution_id: str
    student_id: str
    program_id: str
    major_id: str
    plan_id: str
    plan_version_id: str
    earned_credits: Decimal
    attempts: tuple[StudentCourseAttempt, ...]
    enrolled_course_codes: tuple[str, ...]
    evidence: SourceEvidence


class SISReadAdapter(Protocol):
    institution_id: str
    adapter_id: str
    capabilities: frozenset[Entity]

    async def health(self) -> SISHealth:
        """Return safe metadata only; the caller still enforces authorization."""

    async def fetch_page(self, entity: Entity, *, cursor: str | None, limit: int) -> SISPage:
        """Read only. Never expose a mutation method through this contract."""


async def read_pages(adapter: SISReadAdapter, institution_id: str, entity: Entity, *,
                     page_size: int = 50, max_pages: int = 10,
                     timeout_seconds: float = 2.0) -> tuple[SISPage, ...]:
    """Bounded read, no retries; reject malformed/foreign/cyclic pagination."""
    if not institution_id or adapter.institution_id != institution_id:
        raise SISFailure(Failure.TENANT_MISMATCH)
    if entity not in adapter.capabilities:
        raise SISFailure(Failure.UNAVAILABLE)
    if not 1 <= page_size <= 100 or not 1 <= max_pages <= 20 or not 0 < timeout_seconds <= 10:
        raise ValueError("SIS read bounds exceeded")
    cursor: str | None = None
    seen: set[str] = set()
    pages: list[SISPage] = []
    for _ in range(max_pages):
        try:
            page = await asyncio.wait_for(adapter.fetch_page(entity, cursor=cursor, limit=page_size),
                                          timeout=timeout_seconds)
        except TimeoutError:
            raise SISFailure(Failure.TIMEOUT) from None
        except SISFailure:
            raise
        except Exception:
            raise SISFailure(Failure.UNAVAILABLE) from None
        if (not isinstance(page, SISPage) or page.institution_id != institution_id
                or page.evidence.institution_id != institution_id):
            raise SISFailure(Failure.TENANT_MISMATCH)
        if (page.entity is not entity or len(page.records) > page_size
                or not all(isinstance(row, Mapping) for row in page.records)):
            raise SISFailure(Failure.INVALID_RESPONSE)
        pages.append(page)
        if page.next_cursor is None:
            return tuple(pages)
        if not isinstance(page.next_cursor, str) or not page.next_cursor or page.next_cursor in seen:
            raise SISFailure(Failure.INVALID_RESPONSE)
        seen.add(page.next_cursor)
        cursor = page.next_cursor
    raise SISFailure(Failure.INVALID_RESPONSE)


@dataclass(frozen=True)
class IdentifierMapping:
    institution_id: str
    entity: Entity
    external_id: str
    local_id: str
    mapping_version: str


class IdentifierRegistry:
    """Immutable exact-tenant map; duplicate external or local identities fail closed."""

    def __init__(self, mappings: tuple[IdentifierMapping, ...]):
        forward: dict[tuple[str, Entity, str], str] = {}
        reverse: dict[tuple[str, Entity, str], str] = {}
        external_seen: set[tuple[str, str]] = set()
        for item in mappings:
            if not all((item.institution_id, item.external_id, item.local_id, item.mapping_version)):
                raise SISFailure(Failure.MAPPING_CONFLICT)
            key = (item.institution_id, item.entity, item.external_id)
            inverse = (item.institution_id, item.entity, item.local_id)
            external_key = (item.institution_id, item.external_id)
            if key in forward or inverse in reverse or external_key in external_seen:
                raise SISFailure(Failure.MAPPING_CONFLICT)
            forward[key] = item.local_id
            reverse[inverse] = item.external_id
            external_seen.add(external_key)
        self._forward = forward

    def resolve(self, institution_id: str, entity: Entity, external_id: str) -> str:
        if not institution_id or not external_id:
            raise SISFailure(Failure.MAPPING_CONFLICT)
        try:
            return self._forward[(institution_id, entity, external_id)]
        except KeyError:
            raise SISFailure(Failure.MAPPING_CONFLICT) from None


def map_academic_record(payload: Mapping[str, Any], *, institution_id: str,
                        mappings: IdentifierRegistry,
                        evidence: SourceEvidence) -> CanonicalSISAcademicRecord:
    """Strict vendor-to-domain normalization; never pass vendor JSON to engines."""
    if evidence.institution_id != institution_id or payload.get("institution_id") != institution_id:
        raise SISFailure(Failure.TENANT_MISMATCH)
    if payload.get("schema_version") != "P15_SIS_RECORD_V1":
        raise SISFailure(Failure.SCHEMA_MISMATCH)
    try:
        student = mappings.resolve(institution_id, Entity.STUDENT, payload["student_external_id"])
        program = mappings.resolve(institution_id, Entity.PROGRAM, payload["program_external_id"])
        major = mappings.resolve(institution_id, Entity.MAJOR, payload["major_external_id"])
        plan = mappings.resolve(institution_id, Entity.PLAN, payload["plan_external_id"])
        plan_version = mappings.resolve(institution_id, Entity.PLAN_VERSION,
                                        payload["plan_version_external_id"])
        credits = Decimal(str(payload["earned_credits"]))
        if not credits.is_finite() or credits < 0:
            raise ValueError("Invalid credits")
        raw_attempts = payload["attempts"]
        raw_enrollments = payload["enrollments"]
        if not isinstance(raw_attempts, (list, tuple)) or not isinstance(raw_enrollments, (list, tuple)):
            raise ValueError("Invalid academic collections")
        attempts = tuple(StudentCourseAttempt(
            mappings.resolve(institution_id, Entity.COURSE, row["course_external_id"]),
            AttemptOutcome(row["outcome"])) for row in raw_attempts)
        enrolled = tuple(mappings.resolve(institution_id, Entity.COURSE, row["course_external_id"])
                         for row in raw_enrollments)
    except SISFailure:
        raise
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise SISFailure(Failure.INVALID_RESPONSE) from None
    return CanonicalSISAcademicRecord(institution_id, student, program, major,
                                      plan, plan_version, credits, attempts, enrolled, evidence)




def reconcile(source: object | None, local: object | None, *,
              source_updated_at: datetime | None, local_updated_at: datetime | None,
              mapped: bool = True, valid: bool = True) -> Reconciliation:
    """Classification only. Never write local academic facts automatically."""
    if not valid:
        return Reconciliation.INVALID
    if not mapped:
        return Reconciliation.UNMAPPED
    if source is None:
        return Reconciliation.MISSING_SOURCE
    if local is None:
        return Reconciliation.MISSING_LOCAL
    if source == local:
        return Reconciliation.MATCH
    if source_updated_at is None or local_updated_at is None:
        return Reconciliation.CONFLICT
    if (source_updated_at.tzinfo is None or source_updated_at.utcoffset() is None
            or local_updated_at.tzinfo is None or local_updated_at.utcoffset() is None):
        return Reconciliation.INVALID
    if source_updated_at > local_updated_at:
        return Reconciliation.SOURCE_NEWER
    if local_updated_at > source_updated_at:
        return Reconciliation.LOCAL_NEWER
    return Reconciliation.CONFLICT


def decision_ready(evidence: SourceEvidence, now: datetime) -> bool:
    """Unknown/stale source data cannot authorize an academic decision."""
    return evidence.freshness_at(now) is Freshness.FRESH


def stage_curriculum(document: Mapping[str, Any], *, institution_id: str,
                     evidence: SourceEvidence) -> ImportPreview:
    """Feed P12's existing review/quarantine gate, never publish or persist."""
    identity = document.get("identity")
    if (evidence.institution_id != institution_id or not isinstance(identity, Mapping)
            or identity.get("institution_id") != institution_id):
        raise SISFailure(Failure.TENANT_MISMATCH)
    return stage_structured_import(document, source=f"SIS:{evidence.adapter_id}:{evidence.source_version}")


def validate_offering_snapshot(snapshot: OfferingSnapshot, *, institution_id: str,
                               evidence: SourceEvidence, now: datetime) -> OfferingSnapshot:
    """Reuse P10's snapshot contract; reject foreign/stale facts at the boundary."""
    if snapshot.university_id != institution_id or evidence.institution_id != institution_id:
        raise SISFailure(Failure.TENANT_MISMATCH)
    if not decision_ready(evidence, now) or now > snapshot.fresh_until or not snapshot.complete:
        raise SISFailure(Failure.INVALID_RESPONSE)
    return snapshot
