"""Focused mocked tests for ownership-scoped student writes."""

import asyncio
import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.rules.models import AttemptOutcome
from app.student.models import PerformanceProvenance, PerformanceVerificationState
from app.student.errors import (
    StudentAttemptNotFound, StudentCourseNotFound, StudentCourseUniversityMismatch,
    StudentProfileAlreadyExists, StudentProfileTransportError,
)
from app.student.supabase_repository import SupabaseStudentAcademicRepository

OWNER = "11111111-1111-1111-1111-111111111111"
PROFILE = "22222222-2222-2222-2222-222222222222"
PLAN = "33333333-3333-3333-3333-333333333333"
UNIVERSITY = "44444444-4444-4444-4444-444444444444"
COURSE = "55555555-5555-5555-5555-555555555555"
ATTEMPT = "66666666-6666-6666-6666-666666666666"
KEY = "test-server-key-not-a-real-secret"
NOW = "2026-09-17T10:00:00Z"


def profile(nested: bool = False) -> dict:
    row = {"id": PROFILE, "owner_user_id": OWNER, "study_plan_id": PLAN,
        "reported_cumulative_gpa": "3.25", "reported_gpa_scale": "4",
        "reported_earned_credit_hours": "15", "created_at": NOW, "updated_at": NOW}
    if nested:
        row["study_plans"] = {"majors": {"faculties": {"university_id": UNIVERSITY}}}
    return row


def attempt(outcome: str = "PASSED", code: str = "0300103") -> dict:
    return {"id": ATTEMPT, "profile_id": PROFILE, "outcome": outcome,
        "attempt_sequence": None, "term_label": None, "attempted_on": None,
        "reported_grade_text": "A", "record_source": "manual_entry",
        "created_at": NOW, "updated_at": NOW, "courses": {"course_code": code}}


class WriteFixture:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.duplicate = False
        self.course_rows = [{"id": COURSE, "course_code": "0300103", "university_id": UNIVERSITY, "catalog_status": "referenced_only"}]
        self.attempt_rows: list[dict] = []
        self.missing_mutation = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        assert request.headers["apikey"] == KEY
        resource = request.url.path.rsplit("/", 1)[-1]
        if request.method == "POST" and resource == "student_academic_profiles":
            return httpx.Response(409, json={"code": "23505"}) if self.duplicate else httpx.Response(201, json=[profile()])
        if request.method == "GET" and resource == "student_academic_profiles":
            return httpx.Response(200, json=[profile(nested="study_plans" in request.url.params.get("select", ""))])
        if request.method == "GET" and resource == "courses":
            return httpx.Response(200, json=self.course_rows)
        if request.method == "GET" and resource == "student_course_attempts":
            return httpx.Response(200, json=self.attempt_rows)
        if request.method == "POST" and resource == "student_course_attempts":
            payload = json.loads(request.content); row = attempt(payload["outcome"], self.course_rows[0]["course_code"])
            row["reported_grade_text"] = payload.get("reported_grade_text")
            for field in (
                "raw_numeric_grade", "raw_letter_grade", "raw_grade_points", "raw_academic_year",
                "raw_term", "attempt_credit_hours", "performance_provenance",
                "performance_verification_state", "performance_source_reference",
            ):
                row[field] = payload.get(field)
            self.attempt_rows.append(row); return httpx.Response(201, json=[row])
        if request.method == "PATCH" and resource == "student_course_attempts":
            return httpx.Response(200, json=[] if self.missing_mutation else [attempt(json.loads(request.content)["outcome"])])
        if request.method in {"PATCH", "DELETE"}:
            return httpx.Response(200, json=[] if self.missing_mutation else [profile()])
        raise AssertionError(f"unexpected request {request.method} {resource}")


def run(data: WriteFixture, operation):
    async def invoke():
        async with httpx.AsyncClient(transport=httpx.MockTransport(data.handler)) as client:
            return await operation(SupabaseStudentAcademicRepository("https://student.example", KEY, client))
    return asyncio.run(invoke())


def test_profile_create_update_delete_are_owner_scoped_and_plan_is_not_mutable() -> None:
    data = WriteFixture()
    created = run(data, lambda repo: repo.create_profile(OWNER, PLAN, reported_cumulative_gpa=Decimal("3.25"), reported_gpa_scale=Decimal("4")))
    updated = run(data, lambda repo: repo.update_profile(OWNER, reported_cumulative_gpa=Decimal("3.5"), reported_gpa_scale=Decimal("4"), reported_earned_credit_hours=Decimal("18")))
    run(data, lambda repo: repo.delete_profile(OWNER))
    assert created.study_plan_id == updated.study_plan_id == PLAN
    patch = next(call for call in data.calls if call.method == "PATCH")
    assert "study_plan_id" not in json.loads(patch.content)
    assert patch.url.params["owner_user_id"] == f"eq.{OWNER}"
    delete = next(call for call in data.calls if call.method == "DELETE")
    assert delete.url.params["owner_user_id"] == f"eq.{OWNER}"


def test_duplicate_profile_has_typed_safe_error() -> None:
    data = WriteFixture(); data.duplicate = True
    with pytest.raises(StudentProfileAlreadyExists) as raised:
        run(data, lambda repo: repo.create_profile(OWNER, PLAN))
    assert KEY not in str(raised.value)


def test_exact_referenced_only_and_leading_zero_course_is_resolved() -> None:
    data = WriteFixture()
    record = run(data, lambda repo: repo.create_attempt(OWNER, "0300103", AttemptOutcome.PASSED))
    assert record.course_code == "0300103"
    course_call = next(call for call in data.calls if call.url.path.endswith("/courses"))
    assert course_call.url.params["course_code"] == "eq.0300103"


@pytest.mark.parametrize("code", ["1501110", "0300103"])
def test_known_and_referenced_only_courses_are_accepted(code: str) -> None:
    data = WriteFixture(); data.course_rows[0]["course_code"] = code
    assert run(data, lambda repo: repo.create_attempt(OWNER, code, AttemptOutcome.PASSED)).course_code == code


def test_unknown_and_cross_university_courses_are_typed() -> None:
    data = WriteFixture(); data.course_rows = []
    with pytest.raises(StudentCourseNotFound): run(data, lambda repo: repo.create_attempt(OWNER, "missing", AttemptOutcome.PASSED))
    data = WriteFixture(); data.course_rows[0]["university_id"] = "77777777-7777-7777-7777-777777777777"
    with pytest.raises(StudentCourseUniversityMismatch): run(data, lambda repo: repo.create_attempt(OWNER, "0300103", AttemptOutcome.PASSED))


@pytest.mark.parametrize("outcome", list(AttemptOutcome))
def test_all_attempt_statuses_create_without_grade_inference(outcome: AttemptOutcome) -> None:
    data = WriteFixture()
    row = run(data, lambda repo: repo.create_attempt(OWNER, "0300103", outcome, reported_grade_text="contradictory evidence"))
    assert row.outcome is outcome


def test_internal_performance_facts_round_trip_without_changing_outcome() -> None:
    data = WriteFixture()
    row = run(data, lambda repo: repo.create_attempt(
        OWNER, "0300103", AttemptOutcome.FAILED,
        raw_numeric_grade=Decimal("91.25"), raw_letter_grade="A-",
        raw_grade_points=Decimal("3.7"), raw_academic_year="SYN-2025-2026",
        raw_term="SYN-TERM-A", attempt_credit_hours=Decimal("3"),
        performance_provenance=PerformanceProvenance.MANUAL_ACADEMIC_REVIEW,
        performance_verification_state=PerformanceVerificationState.VERIFIED,
        performance_source_reference="synthetic-p2-fixture",
    ))
    assert row.outcome is AttemptOutcome.FAILED
    assert row.raw_numeric_grade == Decimal("91.25")
    assert row.raw_letter_grade == "A-"
    assert row.raw_grade_points == Decimal("3.7")
    assert row.raw_academic_year == "SYN-2025-2026"
    assert row.raw_term == "SYN-TERM-A"
    assert row.attempt_credit_hours == Decimal("3")
    assert row.performance_provenance is PerformanceProvenance.MANUAL_ACADEMIC_REVIEW
    assert row.performance_verification_state is PerformanceVerificationState.VERIFIED
    assert row.performance_source_reference == "synthetic-p2-fixture"


def test_repeated_attempts_are_not_collapsed() -> None:
    data = WriteFixture()
    run(data, lambda repo: repo.create_attempt(OWNER, "0300103", AttemptOutcome.FAILED))
    run(data, lambda repo: repo.create_attempt(OWNER, "0300103", AttemptOutcome.PASSED))
    assert len([call for call in data.calls if call.method == "POST" and call.url.path.endswith("student_course_attempts")]) == 2


def test_update_and_delete_filter_by_owner_profile_and_keep_course_immutable() -> None:
    data = WriteFixture(); data.attempt_rows = [attempt()]
    run(data, lambda repo: repo.update_attempt(OWNER, ATTEMPT, outcome=AttemptOutcome.FAILED, reported_grade_text="F"))
    run(data, lambda repo: repo.delete_attempt(OWNER, ATTEMPT))
    writes = [call for call in data.calls if call.method in {"PATCH", "DELETE"}]
    assert all(call.url.params["profile_id"] == f"eq.{PROFILE}" for call in writes)
    assert "course_id" not in json.loads(writes[0].content)


def test_foreign_attempt_is_indistinguishable_from_missing() -> None:
    data = WriteFixture(); data.missing_mutation = True
    with pytest.raises(StudentAttemptNotFound):
        run(data, lambda repo: repo.delete_attempt(OWNER, ATTEMPT))


def test_write_transport_failure_is_safe() -> None:
    def handler(request: httpx.Request): raise httpx.ReadTimeout("secret-looking timeout", request=request)
    async def operation():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await SupabaseStudentAcademicRepository("https://student.example", KEY, client).create_profile(OWNER, PLAN)
    with pytest.raises(StudentProfileTransportError) as raised: asyncio.run(operation())
    assert KEY not in str(raised.value)
