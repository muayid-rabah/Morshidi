"""Focused Phase P2 raw-performance foundation contracts."""

from decimal import Decimal

from app.api.schemas.student import AttemptCreateRequest, AttemptUpdateRequest, CourseAttemptResponse
from app.rules.models import AttemptOutcome
from app.student.models import PerformanceProvenance, PerformanceVerificationState
from app.student.performance_import import (
    PerformanceImportQuarantineReason,
    StudentAttemptImportRecord,
    validate_student_attempt_import_records,
)


def _record(**changes) -> StudentAttemptImportRecord:
    values = {
        "course_code": "SYN-101",
        "outcome": AttemptOutcome.PASSED,
        "provenance": PerformanceProvenance.STUDENT_RECORD,
        "source_record_id": "synthetic-row-1",
        "source_reference": "synthetic-batch-p2",
        "attempt_sequence": 1,
        "raw_numeric_grade": Decimal("87.5"),
        "raw_letter_grade": "B+",
        "raw_grade_points": Decimal("3.5"),
        "raw_academic_year": "SYN-2025-2026",
        "raw_term": "SYN-TERM-A",
        "attempt_credit_hours": Decimal("3"),
    }
    values.update(changes)
    return StudentAttemptImportRecord(**values)


def test_raw_import_records_are_accepted_without_grade_or_period_interpretation() -> None:
    result = validate_student_attempt_import_records([_record()], known_course_codes={"SYN-101"})
    assert result.accepted == (_record(),)
    assert result.quarantined == ()


def test_import_quarantines_only_structural_boundary_failures() -> None:
    records = [
        _record(course_code="UNKNOWN"),
        _record(outcome="NOT_A_REAL_OUTCOME"),
        _record(provenance=None),
        _record(provenance="NOT_A_REAL_PROVENANCE"),
        _record(
            provenance=PerformanceProvenance.OFFICIAL_VERIFIED,
            verification_state=PerformanceVerificationState.UNVERIFIED,
        ),
        _record(attempt_credit_hours=Decimal("-1")),
    ]
    result = validate_student_attempt_import_records(records, known_course_codes={"SYN-101"})
    assert result.accepted == ()
    assert [item.reason for item in result.quarantined] == [
        PerformanceImportQuarantineReason.UNKNOWN_COURSE,
        PerformanceImportQuarantineReason.INVALID_OUTCOME,
        PerformanceImportQuarantineReason.MISSING_PROVENANCE,
        PerformanceImportQuarantineReason.INVALID_PROVENANCE,
        PerformanceImportQuarantineReason.INVALID_VERIFICATION_STATE,
        PerformanceImportQuarantineReason.INVALID_RAW_VALUE,
    ]


def test_import_quarantines_only_defined_duplicate_identities() -> None:
    duplicate = _record(source_record_id="synthetic-row-1")
    distinct_repeat = _record(source_record_id="synthetic-row-2", attempt_sequence=2)
    result = validate_student_attempt_import_records(
        [_record(), duplicate, distinct_repeat], known_course_codes={"SYN-101"}
    )
    assert result.accepted == (_record(), distinct_repeat)
    assert result.quarantined[0].reason is PerformanceImportQuarantineReason.DUPLICATE_BATCH_IDENTITY


def test_self_service_contract_cannot_write_or_read_p2_sensitive_fields() -> None:
    protected = {
        "raw_numeric_grade", "raw_letter_grade", "raw_grade_points", "raw_academic_year",
        "raw_term", "attempt_credit_hours", "performance_provenance",
        "performance_verification_state", "performance_source_reference",
    }
    assert not protected & set(AttemptCreateRequest.model_fields)
    assert not protected & set(AttemptUpdateRequest.model_fields)
    assert not protected & set(CourseAttemptResponse.model_fields)
