"""P11 route boundaries: authentication, owner derivation, analyst-first access."""

from types import SimpleNamespace
from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.offerings.fake_provider import FAKE_UNIVERSITY_ID
from app.p11_intelligence.fake_provider import FAKE_PLAN_ID, FakeP11Provider
from dataclasses import replace
from app.student.models import PerformanceProvenance, PerformanceVerificationState
from app.rules.models import AttemptOutcome
from app.student.models import StudentCourseAttemptRecord

USER = "10000000-0000-0000-0000-000000000001"


class StudentStub:
    def __init__(self, tenant=FAKE_UNIVERSITY_ID):
        self.tenant = tenant
        self.calls = []

    async def get_profile(self, owner):
        self.calls.append(("profile", owner))
        return SimpleNamespace(study_plan_id=FAKE_PLAN_ID)

    async def resolve_student_university_id(self, owner):
        self.calls.append(("university", owner))
        return self.tenant

    async def list_attempts(self, owner):
        self.calls.append(("attempts", owner))
        return (StudentCourseAttemptRecord("attempt-1", "profile-1", "CS101", AttemptOutcome.PASSED,
                                           1, None, None, None, "SYNTHETIC_TEST",
                                           datetime(2026, 9, 1, tzinfo=timezone.utc),
                                           datetime(2026, 9, 1, tzinfo=timezone.utc)),)


class AnalystStub:
    def __init__(self, allow=True):
        self.allow = allow
        self.calls = []

    async def authorize_analyst_university(self, subject, university_id):
        self.calls.append((subject, university_id))
        if not self.allow:
            from app.institutional_intelligence_service.errors import (
                InstitutionalIntelligenceServiceError, InstitutionalIntelligenceServiceErrorCode,
            )
            raise InstitutionalIntelligenceServiceError(InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED)
        return university_id


class SpyProvider(FakeP11Provider):
    def __init__(self): self.calls = 0

    async def load_snapshot(self, university_id, study_plan_id):
        self.calls += 1
        return await super().load_snapshot(university_id, study_plan_id)


class CrossScopeProvider(FakeP11Provider):
    async def load_taxonomy(self, university_id, study_plan_id):
        taxonomy = await super().load_taxonomy(university_id, study_plan_id)
        return replace(taxonomy, university_id="foreign")


class VerifiedStudentStub(StudentStub):
    async def list_attempts(self, owner):
        rows = await super().list_attempts(owner)
        return tuple(replace(row, performance_provenance=PerformanceProvenance.OFFICIAL_VERIFIED,
                             performance_verification_state=PerformanceVerificationState.VERIFIED) for row in rows)


def _client(*, student=None, analyst=None, provider=None):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(USER)
    client = TestClient(app)
    client.__enter__()
    app.state.student_service = student or StudentStub()
    app.state.institutional_intelligence_service = analyst or AnalystStub()
    app.state.p11_provider = provider or FakeP11Provider()
    app.state.p11_cohort_threshold = 3
    return client


def _close(client):
    client.__exit__(None, None, None)
    app.dependency_overrides.clear()


def test_unauthenticated_routes_reject_before_services():
    with TestClient(app) as client:
        assert client.get("/api/v1/me/intelligence").status_code == 401
        assert client.get("/api/v1/institutional/cohorts").status_code == 401


def test_student_view_uses_authenticated_owner_and_never_exposes_risk():
    service = StudentStub()
    client = _client(student=service)
    try:
        response = client.get("/api/v1/me/intelligence", params={"owner": "foreign", "university_id": "foreign"})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert response.headers["cache-control"] == "private, no-store"
        assert payload["source_type"] == "SYNTHETIC"
        assert payload["risk"] == "NOT_EXPOSED_TO_STUDENTS"
        assert payload["skills"]["items"][0]["state"] == "NOT_EVIDENCED"
        assert payload["strength_difficulty"]["strengths"]["policy_version"] == "1.0"
        assert all(owner == USER for _, owner in service.calls)
        assert "foreign" not in response.text
    finally:
        _close(client)


def test_foreign_tenant_and_absent_provider_fail_closed():
    client = _client(student=StudentStub("foreign"))
    try:
        response = client.get("/api/v1/me/intelligence")
        assert response.status_code == 200
        assert response.json()["source_type"] == "UNAVAILABLE"
        assert response.json()["skills"]["status"] == "UNRESOLVED"
        assert response.json()["workload"]["status"] == "UNKNOWN"
    finally:
        _close(client)


def test_cross_scope_taxonomy_fails_closed():
    client = _client(provider=CrossScopeProvider())
    try:
        assert client.get("/api/v1/me/intelligence").status_code == 503
    finally:
        _close(client)


def test_only_verified_official_attempt_yields_course_skill_evidence():
    client = _client(student=VerifiedStudentStub())
    try:
        result = client.get("/api/v1/me/intelligence")
        assert result.status_code == 200
        assert result.json()["skills"]["items"][0]["state"] == "EVIDENCED"
    finally:
        _close(client)


def test_cohort_authorization_precedes_provider_and_exposes_aggregate_only():
    provider = SpyProvider()
    analyst = AnalystStub(allow=False)
    client = _client(analyst=analyst, provider=provider)
    params = {"university_id": FAKE_UNIVERSITY_ID, "study_plan_id": FAKE_PLAN_ID,
              "entry_period": "SYN-2025-FALL", "period": "SYN-2026-FALL"}
    try:
        denied = client.get("/api/v1/institutional/cohorts", params=params)
        assert denied.status_code == 403
        assert provider.calls == 0
        analyst.allow = True
        allowed = client.get("/api/v1/institutional/cohorts", params=params)
        assert allowed.status_code == 200, allowed.text
        assert allowed.headers["cache-control"] == "private, no-store"
        assert allowed.json()["size"] == 6
        assert "anonymous_id" not in allowed.text
        assert "NOT_CAUSAL" in allowed.json()["causal_limits"]
        compared = client.get("/api/v1/institutional/cohorts", params={**params, "comparison_period": "SYN-2025-FALL"})
        assert compared.status_code == 200 and compared.json()["comparison"]["status"] == "DESCRIPTIVE"
        private_comparison = client.get("/api/v1/institutional/cohorts", params={**params, "comparison_period": "UNKNOWN"})
        assert private_comparison.json()["comparison"]["status"] == "UNAVAILABLE"
        assert client.get("/api/v1/institutional/cohorts", params={**params, "period": "UNKNOWN"}).json()["status"] == "UNAVAILABLE"
        assert client.get("/api/v1/institutional/cohorts", params={**params, "minimum_level": 8, "maximum_level": 1}).status_code == 422
    finally:
        _close(client)
