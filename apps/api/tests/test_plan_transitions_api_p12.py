"""Focused authenticated P12 API checks with isolated in-memory plan artifacts."""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.plan_transition.ingestion import IngestionState, LocalPublication
from app.plan_transition.models import (CourseIdentity, PlanCourse, PlanIdentity,
                                        PlanVersion, RequirementGroup, StagedRule)
from app.plan_transition.provider import ApprovedLocalModelingProvider
from app.rules.models import AttemptOutcome
from app.student.models import (PerformanceProvenance, PerformanceVerificationState,
                                StudentCourseAttemptRecord)

OWNER = "10000000-0000-0000-0000-000000000111"
OTHER = "10000000-0000-0000-0000-000000000222"
INSTITUTION = "isolated-p12-api-test"


def _plan(version: str, major: str, course_id: str, code: str) -> PlanVersion:
    identity = PlanIdentity(INSTITUTION, "program-test", major, "plan-test", version,
                            date(2025, 1, 1), None, "isolated-v1")
    course = PlanCourse(CourseIdentity(INSTITUTION, course_id, code), "core", Decimal(3))
    return PlanVersion(identity, (RequirementGroup("core", Decimal(3)),), (course,),
                       "source-" + version, "content-" + version + major,
                       "isolated-in-memory-api-test")


class StudentStub:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def get_profile(self, owner):
        self.calls.append(("profile", owner))
        return SimpleNamespace(study_plan_id="owner-plan")

    async def resolve_student_university_id(self, owner):
        self.calls.append(("university", owner))
        return INSTITUTION

    async def list_attempts(self, owner):
        self.calls.append(("attempts", owner))
        return (StudentCourseAttemptRecord(
            "attempt", "profile", "CS101", AttemptOutcome.PASSED,
            1, None, None, None, "TEST", datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 1, tzinfo=timezone.utc), attempt_credit_hours=Decimal(3),
            performance_provenance=PerformanceProvenance.OFFICIAL_VERIFIED,
            performance_verification_state=PerformanceVerificationState.VERIFIED),)


def _provider(*, include_equivalency=False):
    source = _plan("v1", "major-a", "a", "CS101")
    target = _plan("v2", "major-a", "b", "CS102")
    transfer = _plan("v3", "major-b", "c", "CS103")
    if include_equivalency:
        from dataclasses import replace
        rule = StagedRule("eq-p12", "a", "b", source.identity.key, target.identity.key,
                          date(2025, 1, 1), None, "isolated-test-authority",
                          "isolated-test-source", "v1", "APPROVED")
        target = replace(target, staged_rules=(rule,))
    published = tuple(LocalPublication(IngestionState.PUBLISHED, p, "test-actor",
                                       date(2026, 1, 1), "isolated-test")
                      for p in (source, target, transfer))
    provider = ApprovedLocalModelingProvider(
        published, {(INSTITUTION, "owner-plan"): source.identity.key},
        {source.identity.key: (target.identity.key, transfer.identity.key)})
    return provider, source, target, transfer


def test_authentication_required_and_no_default_target_provider():
    with TestClient(app) as client:
        assert client.get("/api/v1/me/plan-transitions").status_code == 401
        assert client.post("/api/v1/me/plan-transitions/evaluate", json={}).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/me/plan-transitions").status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_owner_target_allowlist_no_arbitrary_student_or_curriculum_and_no_write():
    provider, source, target, transfer = _provider(include_equivalency=True)
    student = StudentStub()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    try:
        with TestClient(app) as client:
            app.state.student_service = student
            app.state.p12_modeling_provider = provider
            listing = client.get("/api/v1/me/plan-transitions", params={"student_id": OTHER})
            assert listing.status_code == 200
            assert listing.json()["current"]["plan_key"] == list(source.identity.key)
            assert len(listing.json()["targets"]) == 2
            assert listing.headers["cache-control"] == "private, no-store"
            injection = client.post("/api/v1/me/plan-transitions/evaluate",
                                    json={"target_plan_key": target.identity.key,
                                          "student_id": OTHER, "curriculum": {"course_id": "injected"}})
            assert injection.status_code == 422
            result = client.post("/api/v1/me/plan-transitions/evaluate",
                                 json={"target_plan_key": target.identity.key})
            assert result.status_code == 200, result.text
            body = result.json()
            assert body["kind"] == "PLAN_VERSION_TRANSITION"
            assert body["projection"]["recognized_credits"] == "3"
            assert body["projection"]["lines"][0]["rule_ids"] == ["eq-p12"]
            evidence = body["projection"]["lines"][0]["rule_evidence"][0]
            assert evidence["authority"] == "isolated-test-authority"
            assert evidence["source_plan_key"] == list(source.identity.key)
            assert body["write_performed"] is False
            assert body["label"] == "MODELED_UNOFFICIAL"
            assert OTHER not in result.text
            assert all(owner == OWNER for _, owner in student.calls)
            invalid = client.post("/api/v1/me/plan-transitions/evaluate",
                                  json={"target_plan_key": [INSTITUTION, "program-test", "major-a", "other", "v99"]})
            assert invalid.status_code == 404 and invalid.json()["detail"] == "TARGET_PLAN_UNAVAILABLE"
            cross_major = client.post("/api/v1/me/plan-transitions/evaluate",
                                      json={"target_plan_key": transfer.identity.key})
            assert cross_major.status_code == 200
            assert cross_major.json()["kind"] == "CROSS_MAJOR_PROJECTION"
            assert cross_major.json()["status"] == "EQUIVALENCY_UNRESOLVED"
            assert {name for name, _ in student.calls} == {"profile", "university", "attempts"}
    finally:
        app.dependency_overrides.clear()
        app.state.p12_modeling_provider = None


def test_unverified_attempt_is_not_silently_recognized():
    provider, _, target, _ = _provider(include_equivalency=True)

    class UnverifiedStudent(StudentStub):
        async def list_attempts(self, owner):
            from dataclasses import replace
            return tuple(replace(row, performance_verification_state=PerformanceVerificationState.UNVERIFIED)
                         for row in await super().list_attempts(owner))

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    try:
        with TestClient(app) as client:
            app.state.student_service = UnverifiedStudent()
            app.state.p12_modeling_provider = provider
            result = client.post("/api/v1/me/plan-transitions/evaluate",
                                 json={"target_plan_key": target.identity.key})
            assert result.status_code == 200
            assert result.json()["status"] == "EQUIVALENCY_UNRESOLVED"
            assert result.json()["projection"]["recognized_credits"] == "0"
            assert result.json()["unmapped_attempt_codes"] == ["CS101"]
    finally:
        app.dependency_overrides.clear()
        app.state.p12_modeling_provider = None


def test_p13_guessed_foreign_target_and_request_tenant_spoofing_fail_closed():
    from dataclasses import replace

    provider, source, target, _ = _provider()
    foreign_institution = "10000000-0000-0000-0000-00000000000b"
    foreign = replace(target,
                      identity=replace(target.identity, institution_id=foreign_institution),
                      courses=tuple(replace(course, identity=replace(
                          course.identity, institution_id=foreign_institution))
                                    for course in target.courses),
                      content_fingerprint="foreign-target")
    publications = tuple(LocalPublication(IngestionState.PUBLISHED, plan,
                                          "p13-local", date(2026, 1, 1), "P13_SYNTHETIC")
                         for plan in (source, target, foreign))
    scoped = ApprovedLocalModelingProvider(
        publications, {(INSTITUTION, "owner-plan"): source.identity.key},
        {source.identity.key: (target.identity.key,)})
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    try:
        with TestClient(app) as client:
            app.state.student_service = StudentStub()
            app.state.p12_modeling_provider = scoped
            listing = client.get("/api/v1/me/plan-transitions",
                                 params={"institution_id": foreign_institution})
            assert listing.status_code == 200
            assert all(item["institution_id"] == INSTITUTION
                       for item in listing.json()["targets"])
            guessed = client.post("/api/v1/me/plan-transitions/evaluate",
                                  json={"target_plan_key": foreign.identity.key})
            assert guessed.status_code == 404
            assert guessed.json()["detail"] == "TARGET_PLAN_UNAVAILABLE"
            injected = client.post("/api/v1/me/plan-transitions/evaluate",
                                   json={"target_plan_key": foreign.identity.key,
                                         "institution_id": foreign_institution})
            assert injected.status_code == 422
    finally:
        app.dependency_overrides.clear()
        app.state.p12_modeling_provider = None


def test_rules_unavailable_conflict_and_version_mismatch_are_explicit():
    provider, source, target, _ = _provider(include_equivalency=True)

    class MissingRulesProvider(ApprovedLocalModelingProvider):
        async def rules_for(self, source_identity, target_identity):
            raise NotImplementedError

    missing = MissingRulesProvider(provider_publications(provider),
                                   {(INSTITUTION, "owner-plan"): source.identity.key},
                                   {source.identity.key: (target.identity.key,)})
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    try:
        with TestClient(app) as client:
            app.state.student_service = StudentStub()
            app.state.p12_modeling_provider = missing
            result = client.post("/api/v1/me/plan-transitions/evaluate",
                                 json={"target_plan_key": target.identity.key})
            assert result.status_code == 503 and result.json()["detail"] == "RULES_UNAVAILABLE"
            app.state.p12_modeling_provider = provider
            from dataclasses import replace
            extra = replace(target.staged_rules[0], rule_id="eq-p12-conflict")
            conflicting = replace(target, staged_rules=(target.staged_rules[0], extra))
            publications = tuple(LocalPublication(IngestionState.PUBLISHED, p, "test-actor",
                                                  date(2026, 1, 1), "isolated-test")
                                 for p in (source, conflicting))
            app.state.p12_modeling_provider = ApprovedLocalModelingProvider(
                publications, {(INSTITUTION, "owner-plan"): source.identity.key},
                {source.identity.key: (target.identity.key,)})
            conflict = client.post("/api/v1/me/plan-transitions/evaluate",
                                   json={"target_plan_key": target.identity.key})
            assert conflict.status_code == 200
            assert conflict.json()["status"] == "EQUIVALENCY_CONFLICT"

            class ForeignSourceProvider(ApprovedLocalModelingProvider):
                async def source_for(self, institution_id, study_plan_id):
                    return replace(source, identity=replace(source.identity, institution_id="foreign"))

            app.state.p12_modeling_provider = ForeignSourceProvider(
                publications, {(INSTITUTION, "owner-plan"): source.identity.key},
                {source.identity.key: (target.identity.key,)})
            mismatch = client.get("/api/v1/me/plan-transitions")
            assert mismatch.status_code == 409 and mismatch.json()["detail"] == "VERSION_MISMATCH"
    finally:
        app.dependency_overrides.clear()
        app.state.p12_modeling_provider = None


def provider_publications(provider):
    return tuple(LocalPublication(IngestionState.PUBLISHED, p, "test-actor",
                                  date(2026, 1, 1), "isolated-test")
                 for p in provider._plans.values())
