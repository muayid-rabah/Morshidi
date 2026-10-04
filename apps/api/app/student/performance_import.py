"""Pure Phase P2 validation for synthetic or future performance imports.

This module deliberately validates only structural facts.  It neither persists
records nor interprets grades, periods, credits, or outcomes.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from app.rules.models import AttemptOutcome
from app.student.models import PerformanceProvenance, PerformanceVerificationState


class PerformanceImportQuarantineReason(str, Enum):
    UNKNOWN_COURSE = "UNKNOWN_COURSE"
    INVALID_OUTCOME = "INVALID_OUTCOME"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"
    INVALID_VERIFICATION_STATE = "INVALID_VERIFICATION_STATE"
    INVALID_RAW_VALUE = "INVALID_RAW_VALUE"
    DUPLICATE_BATCH_IDENTITY = "DUPLICATE_BATCH_IDENTITY"


@dataclass(frozen=True)
class StudentAttemptImportRecord:
    """An import-ready raw record; all academic semantics remain opaque."""

    course_code: str
    outcome: AttemptOutcome | str
    provenance: PerformanceProvenance | str | None
    verification_state: PerformanceVerificationState | str = PerformanceVerificationState.UNVERIFIED
    source_record_id: str | None = None
    source_reference: str | None = None
    attempt_sequence: int | None = None
    raw_numeric_grade: Decimal | str | int | float | None = None
    raw_letter_grade: str | None = None
    raw_grade_points: Decimal | str | int | float | None = None
    raw_academic_year: str | None = None
    raw_term: str | None = None
    attempt_credit_hours: Decimal | str | int | float | None = None


@dataclass(frozen=True)
class QuarantinedPerformanceRecord:
    record: StudentAttemptImportRecord
    reason: PerformanceImportQuarantineReason


@dataclass(frozen=True)
class PerformanceImportValidationResult:
    accepted: tuple[StudentAttemptImportRecord, ...]
    quarantined: tuple[QuarantinedPerformanceRecord, ...]


def validate_student_attempt_import_records(
    records: Collection[StudentAttemptImportRecord], *, known_course_codes: Collection[str]
) -> PerformanceImportValidationResult:
    """Accept structurally valid raw records and quarantine only stated defects."""

    known_codes = set(known_course_codes)
    accepted: list[StudentAttemptImportRecord] = []
    quarantined: list[QuarantinedPerformanceRecord] = []
    identities: set[tuple[str, str | int]] = set()

    for record in records:
        reason = _validation_reason(record, known_codes)
        if reason is None:
            identity = _batch_identity(record)
            if identity is not None and identity in identities:
                reason = PerformanceImportQuarantineReason.DUPLICATE_BATCH_IDENTITY
            elif identity is not None:
                identities.add(identity)
        if reason is None:
            accepted.append(record)
        else:
            quarantined.append(QuarantinedPerformanceRecord(record, reason))
    return PerformanceImportValidationResult(tuple(accepted), tuple(quarantined))


def _validation_reason(
    record: StudentAttemptImportRecord, known_codes: set[str]
) -> PerformanceImportQuarantineReason | None:
    if not _nonblank(record.course_code) or record.course_code not in known_codes:
        return PerformanceImportQuarantineReason.UNKNOWN_COURSE
    try:
        AttemptOutcome(record.outcome)
    except ValueError:
        return PerformanceImportQuarantineReason.INVALID_OUTCOME
    if record.provenance is None or not _nonblank_value(record.provenance):
        return PerformanceImportQuarantineReason.MISSING_PROVENANCE
    try:
        provenance = PerformanceProvenance(record.provenance)
    except ValueError:
        return PerformanceImportQuarantineReason.INVALID_PROVENANCE
    try:
        verification_state = PerformanceVerificationState(record.verification_state)
    except ValueError:
        return PerformanceImportQuarantineReason.INVALID_VERIFICATION_STATE
    if provenance is PerformanceProvenance.OFFICIAL_VERIFIED and verification_state is not PerformanceVerificationState.VERIFIED:
        return PerformanceImportQuarantineReason.INVALID_VERIFICATION_STATE
    if record.attempt_sequence is not None and (isinstance(record.attempt_sequence, bool) or record.attempt_sequence <= 0):
        return PerformanceImportQuarantineReason.INVALID_RAW_VALUE
    if record.attempt_credit_hours is not None:
        credit_hours = _decimal(record.attempt_credit_hours)
        if credit_hours is None or credit_hours < 0:
            return PerformanceImportQuarantineReason.INVALID_RAW_VALUE
    for value in (record.raw_numeric_grade, record.raw_grade_points):
        if value is not None and _decimal(value) is None:
            return PerformanceImportQuarantineReason.INVALID_RAW_VALUE
    for value in (record.source_record_id, record.source_reference, record.raw_letter_grade, record.raw_academic_year, record.raw_term):
        if value is not None and not _nonblank(value):
            return PerformanceImportQuarantineReason.INVALID_RAW_VALUE
    return None


def _batch_identity(record: StudentAttemptImportRecord) -> tuple[str, str | int] | None:
    if _nonblank(record.source_record_id):
        return ("source_record_id", record.source_record_id)
    if record.attempt_sequence is not None:
        return ("course_attempt_sequence", f"{record.course_code}:{record.attempt_sequence}")
    return None


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonblank_value(value: PerformanceProvenance | str) -> bool:
    return not isinstance(value, str) or bool(value.strip())


def _decimal(value: Decimal | str | int | float) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
