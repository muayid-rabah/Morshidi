"""Mocked transport tests for the read-only student repository."""

import asyncio

import httpx
import pytest

from app.rules.models import AttemptOutcome
from app.student.errors import (
    StudentProfileIntegrityError,
    StudentProfileNotFound,
    StudentProfileTransportError,
)
from app.student.supabase_repository import SupabaseStudentAcademicRepository

OWNER = "11111111-1111-1111-1111-111111111111"
PROFILE = "22222222-2222-2222-2222-222222222222"
KEY = "test-server-key-not-a-real-secret"


class Fixture:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.profiles = [{"id": PROFILE, "owner_user_id": OWNER, "study_plan_id": "33333333-3333-3333-3333-333333333333", "reported_cumulative_gpa": "3.25", "reported_gpa_scale": "4", "reported_earned_credit_hours": "15"}]
        self.attempts = [
            {"id": "2", "profile_id": PROFILE, "outcome": "FAILED", "created_at": "2026-01-01T00:00:00Z", "courses": {"course_code": "1501110"}},
            {"id": "3", "profile_id": PROFILE, "outcome": "PASSED", "created_at": "2026-02-01T00:00:00Z", "courses": {"course_code": "0300103"}},
        ]
        self.status: int | None = None
        self.malformed = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        assert request.method == "GET"
        assert request.headers["apikey"] == KEY
        if self.status:
            return httpx.Response(self.status, json={"message": "safe"})
        if self.malformed:
            return httpx.Response(200, content=b"{")
        resource = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=self.profiles if resource == "student_academic_profiles" else self.attempts)


def load(data: Fixture):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(data.handler)) as client:
            return await SupabaseStudentAcademicRepository("https://student.example", KEY, client).load_student_academic_state(OWNER)
    return asyncio.run(run())


def test_loads_profile_facts_and_preserves_all_attempts() -> None:
    data = Fixture()
    state = load(data)
    assert state.study_plan_id == "33333333-3333-3333-3333-333333333333"
    assert str(state.reported_cumulative_gpa) == "3.25"
    assert str(state.reported_gpa_scale) == "4"
    assert str(state.reported_earned_credit_hours) == "15"
    assert state.attempts[0].outcome is AttemptOutcome.FAILED
    assert state.attempts[1].course_code == "0300103"  # referenced-only, exact text
    assert data.calls[0].url.params["owner_user_id"] == f"eq.{OWNER}"
    assert data.calls[1].url.params["order"] == "created_at.asc,id.asc"


@pytest.mark.parametrize("outcome", ["PASSED", "FAILED", "IN_PROGRESS", "WITHDRAWN"])
def test_all_persisted_statuses_map_exactly(outcome: str) -> None:
    data = Fixture()
    data.attempts = [{"id": "1", "profile_id": PROFILE, "outcome": outcome, "created_at": "2026-01-01T00:00:00Z", "courses": {"course_code": "0200115"}}]
    assert load(data).attempts[0].outcome.value == outcome


def test_profile_not_found_is_typed() -> None:
    data = Fixture(); data.profiles = []
    with pytest.raises(StudentProfileNotFound): load(data)


@pytest.mark.parametrize("mutate", ["multiple", "bad_status", "missing_course"])
def test_malformed_rows_fail_without_partial_history(mutate: str) -> None:
    data = Fixture()
    if mutate == "multiple": data.profiles.append(data.profiles[0].copy())
    elif mutate == "bad_status": data.attempts[1]["outcome"] = "INVENTED"
    else: data.attempts[1]["courses"] = None
    with pytest.raises(StudentProfileIntegrityError): load(data)


def test_transport_and_json_failures_are_safe_and_secret_free() -> None:
    data = Fixture(); data.status = 503
    with pytest.raises(StudentProfileTransportError) as raised: load(data)
    assert KEY not in str(raised.value)
    data = Fixture(); data.malformed = True
    with pytest.raises(StudentProfileTransportError): load(data)
