"""Sandbox contract verification and schema drift detection.

Deterministic validation of the public synthetic contract against known invariants:
5 synthetic student personas, 68 Plan 12 courses, 204 offering sections, and zero credential leakage.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Sequence

EXPECTED_SCHEMA_VERSION = "1.0.0"
EXPECTED_FIXTURE_VERSION = "2026.10.02.v1"
EXPECTED_INSTITUTION_ID = "morshidi-sandbox"
EXPECTED_STUDENT_COUNT = 5
EXPECTED_COURSE_COUNT = 68
EXPECTED_OFFERING_COUNT = 204
EXPECTED_RECORD_COUNT = 5
EXPECTED_STUDENT_IDS = frozenset({
    "202310001",
    "202410002",
    "202410003",
    "202510004",
    "202610005",
})

FORBIDDEN_CREDENTIAL_KEYS = frozenset({
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "bearer",
    "api_key",
    "credential",
    "private_key",
})


class DriftStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    INVALID_FIXTURE = "INVALID_FIXTURE"


def _scan_for_forbidden_keys(obj: Any, path: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            k_lower = str(k).lower()
            current_path = f"{path}.{k}" if path else str(k)
            if any(forbidden in k_lower for forbidden in FORBIDDEN_CREDENTIAL_KEYS):
                violations.append(f"Forbidden credential key detected at {current_path}")
            violations.extend(_scan_for_forbidden_keys(v, current_path))
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            violations.extend(_scan_for_forbidden_keys(item, f"{path}[{i}]"))
    return violations


def validate_sandbox_contract(
    manifest: Mapping[str, Any],
    students: Sequence[Mapping[str, Any]],
    courses: Sequence[Mapping[str, Any]],
    offerings: Sequence[Mapping[str, Any]],
    academic_records: Mapping[str, Any],
) -> tuple[DriftStatus, list[str]]:
    """Validate sandbox data contract integrity, counts, and security invariants."""
    errors: list[str] = []

    # 1. Zero Credential Leakage Invariant
    credential_violations = (
        _scan_for_forbidden_keys(manifest, "manifest")
        + _scan_for_forbidden_keys(students, "students")
        + _scan_for_forbidden_keys(courses, "courses")
        + _scan_for_forbidden_keys(offerings, "offerings")
        + _scan_for_forbidden_keys(academic_records, "academic_records")
    )
    if credential_violations:
        return DriftStatus.INVALID_FIXTURE, credential_violations

    # 2. Manifest Invariants
    schema_version = manifest.get("schema_version")
    fixture_version = manifest.get("fixture_version")
    institution_id = manifest.get("institution_id")
    synthetic = manifest.get("synthetic")

    if not isinstance(manifest, Mapping):
        return DriftStatus.INVALID_FIXTURE, ["Manifest must be a JSON object"]

    if schema_version != EXPECTED_SCHEMA_VERSION:
        errors.append(f"Schema version mismatch: expected {EXPECTED_SCHEMA_VERSION}, got {schema_version}")
    if fixture_version != EXPECTED_FIXTURE_VERSION:
        errors.append(f"Fixture version mismatch: expected {EXPECTED_FIXTURE_VERSION}, got {fixture_version}")
    if institution_id != EXPECTED_INSTITUTION_ID:
        errors.append(f"Institution ID mismatch: expected {EXPECTED_INSTITUTION_ID}, got {institution_id}")
    if synthetic is not True:
        errors.append("Manifest synthetic flag must be strictly True")

    if errors:
        # Check if version mismatch is the only issue
        if all("version" in e.lower() for e in errors):
            return DriftStatus.VERSION_MISMATCH, errors
        return DriftStatus.INVALID_FIXTURE, errors

    # 3. Entity Count Invariants
    student_count = len(students)
    course_count = len(courses)
    offering_count = len(offerings)
    records_list = academic_records.get("records", [])
    record_count = len(records_list)

    if student_count != EXPECTED_STUDENT_COUNT:
        errors.append(f"Student count mismatch: expected {EXPECTED_STUDENT_COUNT}, got {student_count}")
    if course_count != EXPECTED_COURSE_COUNT:
        errors.append(f"Course count mismatch: expected {EXPECTED_COURSE_COUNT}, got {course_count}")
    if offering_count != EXPECTED_OFFERING_COUNT:
        errors.append(f"Offering count mismatch: expected {EXPECTED_OFFERING_COUNT}, got {offering_count}")
    if record_count != EXPECTED_RECORD_COUNT:
        errors.append(f"Academic records count mismatch: expected {EXPECTED_RECORD_COUNT}, got {record_count}")

    # 4. Persona Identity Invariants
    student_ids = {s.get("university_id") or s.get("student_id") for s in students}
    if student_ids != EXPECTED_STUDENT_IDS:
        errors.append(f"Unexpected student IDs: expected {sorted(EXPECTED_STUDENT_IDS)}, got {sorted(student_ids)}")

    record_student_ids = {r.get("student_id") for r in records_list}
    if record_student_ids != EXPECTED_STUDENT_IDS:
        errors.append(f"Academic records student IDs mismatch: expected {sorted(EXPECTED_STUDENT_IDS)}, got {sorted(record_student_ids)}")

    # 5. Course and Offering References
    course_codes = {c.get("code") for c in courses}
    offering_course_codes = {o.get("course_code") for o in offerings}
    orphan_offerings = offering_course_codes - course_codes
    if orphan_offerings:
        errors.append(f"Offerings reference unknown course codes: {sorted(orphan_offerings)}")

    if errors:
        return DriftStatus.INVALID_FIXTURE, errors

    return DriftStatus.SUPPORTED, []
