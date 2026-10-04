"""P6.5 service/API/auth/revalidation/privacy contract tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.institutional_demand import get_institutional_demand_service
from app.api.routes.mock_registration import get_mock_registration_student_service
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.mock_registration.models import (
    IntentLifecycle, IntentProvenance, PlanCourseFact, TargetPeriodClass, ValidationStatus,
)
from app.mock_registration.registries import DemandMetricId, ReasonCode
from app.mock_registration_persistence.errors import (
    MockRegistrationPersistenceError, PersistenceFailureCode,
)
from app.mock_registration_persistence.models import (
    InstitutionalMembershipRecord, PersistRevisionResult, PersistedIntentCourse,
    PersistedIntentRevision, PersistedTargetPeriod, PersistenceResultKind,
)
from app.mock_registration_service.errors import MockRegistrationServiceError, ServiceErrorCode
from app.mock_registration_service.institutional_service import InstitutionalDemandService
from app.mock_registration_service.models import AcademicContextSnapshot, CurrentValidity
from app.mock_registration_service.revalidation import revalidate
from app.mock_registration_service.student_service import MockRegistrationStudentService
from app.progress.engine import calculate_academic_progress
from app.progress.models import (
    AcademicProgressCatalog, ProgressPlanCourse, ProgressRequirementGroup,
    ProgressStudyPlan, RequirementType,
)
from app.rules.models import (
    AttemptOutcome, CanTakeCatalog, CourseCatalogStatus, CourseIdentity,
    PlanCourseRule, PrerequisiteLogicStatus, StudentCourseAttempt,
)

OWNER = UUID("10000000-0000-0000-0000-000000000001")
OTHER = UUID("10000000-0000-0000-0000-000000000002")
ANALYST = UUID("10000000-0000-0000-0000-000000000003")
UNIVERSITY = UUID("20000000-0000-0000-0000-000000000001")
OTHER_UNIVERSITY = UUID("20000000-0000-0000-0000-000000000002")
MAJOR = UUID("30000000-0000-0000-0000-000000000001")
PLAN = UUID("40000000-0000-0000-0000-000000000001")
PERIOD = UUID("50000000-0000-0000-0000-000000000001")
COURSE_A = UUID("60000000-0000-0000-0000-000000000001")
COURSE_B = UUID("60000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def snapshot(owner=OWNER, *, attempts=(), conflict=False, version="plan-v1"):
    plan = str(PLAN)
    groups = (ProgressRequirementGroup("g", plan, "G", "مجموعة", "Group", "major",
                                       RequirementType.REQUIRED, Decimal("6"), 1),)
    courses = (
        ProgressPlanCourse("pa", plan, "g", "A", CourseCatalogStatus.KNOWN, Decimal("3"), 1),
        ProgressPlanCourse("pb", plan, "g", "B", CourseCatalogStatus.KNOWN, Decimal("3"), 2),
    )
    progress_catalog = AcademicProgressCatalog(ProgressStudyPlan(plan, Decimal("6")), groups, courses)
    rules = (
        PlanCourseRule("A", PrerequisiteLogicStatus.NOT_APPLICABLE),
        PlanCourseRule("B", PrerequisiteLogicStatus.SOURCE_CONFLICT if conflict else PrerequisiteLogicStatus.NOT_APPLICABLE),
    )
    eligibility = CanTakeCatalog(plan, rules, (
        CourseIdentity("A", CourseCatalogStatus.KNOWN),
        CourseIdentity("B", CourseCatalogStatus.KNOWN),
    ))
    attempt_rows = tuple(StudentCourseAttempt(code, outcome) for code, outcome in attempts)
    progress = calculate_academic_progress(progress_catalog, attempt_rows)
    facts = (
        PlanCourseFact(str(UNIVERSITY), str(MAJOR), plan, version, "A", "g", Decimal("3"), "source-v1"),
        PlanCourseFact(str(UNIVERSITY), str(MAJOR), plan, version, "B", "g", Decimal("3"), "source-v1"),
    )
    token = f"token:{owner}:{version}:{attempts}:{conflict}"
    return AcademicContextSnapshot(owner, UNIVERSITY, MAJOR, PLAN, version, eligibility,
        progress_catalog, progress, attempt_rows, (("A", COURSE_A), ("B", COURSE_B)),
        facts, ("source-v1",), f"progress:{attempts}", "profile", token)


def period(*, expired=False, university=UNIVERSITY):
    return PersistedTargetPeriod(PERIOD, university, "sandbox", "2027-spring",
        TargetPeriodClass.SYNTHETIC_SANDBOX_PERIOD, False, "period-v1", expired,
        "period-expiry-v1" if expired else None, NOW if expired else None, NOW, NOW)


class FakeContexts:
    def __init__(self, snapshots):
        self.snapshots = dict(snapshots)
        self.calls = []
        self.after_first = None

    async def load_owner_context(self, owner):
        self.calls.append(owner)
        value = self.snapshots[owner]
        if self.after_first is not None and len(self.calls) > 1:
            value = self.after_first
        return value

    async def validate_plan_scope(self, plan_id, university_id):
        value = next(iter(self.snapshots.values()))
        if plan_id != value.study_plan_id or university_id != value.university_id:
            raise ValueError("scope")
        return value.plan_course_facts


class FakePersistence:
    def __init__(self, target=None):
        self.period = target or period()
        self.rows = []
        self.members = set()
        self.candidates_loaded = False

    async def load_target_period(self, target_period_id, university_id):
        if target_period_id != self.period.target_period_id or university_id != self.period.university_id:
            raise MockRegistrationPersistenceError(PersistenceFailureCode.RESOURCE_NOT_FOUND, "period")
        return self.period

    async def load_revision_history(self, **scope):
        return tuple(row for row in self.rows if all(getattr(row, key) == value for key, value in scope.items()))

    async def persist_revision(self, command):
        matching = [row for row in self.rows if (
            row.owner_user_id, row.university_id, row.major_id, row.study_plan_id,
            row.study_plan_version, row.target_period_id) == (
            command.owner_user_id, command.university_id, command.major_id,
            command.study_plan_id, command.study_plan_version, command.target_period_id)]
        next_revision = (command.expected_current_revision or 0) + 1
        occupied = next((row for row in matching if row.revision == next_revision), None)
        if occupied:
            kind = (PersistenceResultKind.IDEMPOTENT_REPLAY
                    if occupied.content_fingerprint == command.content_fingerprint
                    else PersistenceResultKind.REVISION_CONFLICT)
            return PersistRevisionResult(kind, occupied.revision_id, occupied.revision,
                                         occupied.content_fingerprint)
        current = max((row.revision for row in matching), default=None)
        if current != command.expected_current_revision:
            return PersistRevisionResult(PersistenceResultKind.REVISION_CONFLICT, None, current, None)
        row = PersistedIntentRevision(
            uuid4(), command.intent_id, command.owner_user_id, command.university_id,
            command.major_id, command.study_plan_id, command.study_plan_version,
            command.target_period_id, next_revision, command.lifecycle_status,
            command.validation_status, command.content_fingerprint, command.intent_provenance,
            command.intent_source_version, command.validation_reason_codes,
            command.catalog_source_versions, command.prerequisite_source_versions,
            command.progress_state_version, command.progress_state_reference,
            command.phase5_policy_version, command.phase6_policy_version,
            command.p6_contract_version, command.target_period_source_version,
            command.transparency_notice_version, NOW, command.actor_class, NOW,
            tuple(PersistedIntentCourse(cid, code, index + 1)
                  for index, (cid, code) in enumerate(zip(command.course_ids, command.course_codes))),
        )
        self.rows.append(row)
        return PersistRevisionResult(PersistenceResultKind.INSERTED, row.revision_id,
                                     row.revision, row.content_fingerprint)

    async def load_active_membership(self, *, subject_user_id, university_id, role="INSTITUTIONAL_ANALYST"):
        if (subject_user_id, university_id) not in self.members:
            raise MockRegistrationPersistenceError(PersistenceFailureCode.RESOURCE_NOT_FOUND, "membership")
        return InstitutionalMembershipRecord(uuid4(), subject_user_id, university_id, "sandbox",
            role, True, "synthetic", "v1", NOW, NOW)

    async def load_institution_period_candidates(self, *, university_id, target_period_id, study_plan_id=None):
        self.candidates_loaded = True
        return tuple(row for row in self.rows if row.university_id == university_id
                     and row.target_period_id == target_period_id
                     and (study_plan_id is None or row.study_plan_id == study_plan_id))


def services(*, conflict=False, attempts=(), threshold=2):
    repo = FakePersistence()
    contexts = FakeContexts({OWNER: snapshot(OWNER, attempts=attempts, conflict=conflict),
                             OTHER: snapshot(OTHER)})
    return repo, contexts, MockRegistrationStudentService(repo, contexts), InstitutionalDemandService(
        repo, contexts, minimum_disclosure_group_size=threshold,
        max_intents=1000, max_catalog_courses=1000)


def test_registry_is_exactly_the_committed_14_codes():
    assert len(ServiceErrorCode) == 14


@pytest.mark.anyio
async def test_submit_replay_next_stale_withdraw_and_history_are_immutable():
    repo, _, student, _ = services()
    first = await student.submit(str(OWNER), target_period_id=PERIOD, course_codes=("A",),
        expected_current_revision=None, transparency_notice_version="notice-v1")
    assert first.revision == 1 and first.current_validity is CurrentValidity.CURRENT_VALID
    replay = await student.submit(str(OWNER), target_period_id=PERIOD, course_codes=("A",),
        expected_current_revision=None, transparency_notice_version="notice-v1")
    assert replay.idempotent_replay and len(repo.rows) == 1
    second = await student.submit(str(OWNER), target_period_id=PERIOD, course_codes=("B",),
        expected_current_revision=1, transparency_notice_version="notice-v1")
    assert second.revision == 2
    with pytest.raises(MockRegistrationServiceError) as stale:
        await student.submit(str(OWNER), target_period_id=PERIOD, course_codes=("A",),
            expected_current_revision=1, transparency_notice_version="notice-v1")
    assert stale.value.code is ServiceErrorCode.REVISION_CONFLICT
    withdrawn = await student.withdraw(str(OWNER), target_period_id=PERIOD,
        expected_current_revision=2, transparency_notice_version="notice-v1")
    assert withdrawn.lifecycle_status is IntentLifecycle.WITHDRAWN
    assert len(repo.rows) == 3 and repo.rows[0].lifecycle_status is IntentLifecycle.SUBMITTED


@pytest.mark.anyio
async def test_invalid_review_owner_plan_period_and_academic_race_boundaries():
    repo, contexts, student, _ = services()
    with pytest.raises(MockRegistrationServiceError) as invalid:
        await student.submit(str(OWNER), target_period_id=PERIOD, course_codes=("UNKNOWN",),
            expected_current_revision=None, transparency_notice_version="notice")
    assert invalid.value.code is ServiceErrorCode.INVALID_INTENT and not repo.rows
    repo, _, review_service, _ = services(conflict=True)
    review = await review_service.submit(str(OWNER), target_period_id=PERIOD, course_codes=("B",),
        expected_current_revision=None, transparency_notice_version="notice")
    assert review.submission_validation_status is ValidationStatus.REVIEW_REQUIRED
    repo, contexts, student, _ = services()
    contexts.after_first = replace(snapshot(OWNER), snapshot_token="changed")
    with pytest.raises(MockRegistrationServiceError) as raced:
        await student.submit(str(OWNER), target_period_id=PERIOD, course_codes=("A",),
            expected_current_revision=None, transparency_notice_version="notice")
    assert raced.value.code is ServiceErrorCode.ACADEMIC_STATE_CHANGED and not repo.rows
    repo.period = period(university=OTHER_UNIVERSITY)
    with pytest.raises(MockRegistrationServiceError) as foreign:
        await student.current(str(OWNER), PERIOD)
    assert foreign.value.code is ServiceErrorCode.PERIOD_INVALID


@pytest.mark.anyio
async def test_current_revalidation_completed_in_progress_conflict_resolved_plan_and_period():
    repo, contexts, student, _ = services()
    await student.submit(str(OWNER), target_period_id=PERIOD, course_codes=("A",),
        expected_current_revision=None, transparency_notice_version="notice")
    row = repo.rows[0]
    assert revalidate(row, repo.period, snapshot(OWNER)).current_validity is CurrentValidity.CURRENT_VALID
    assert revalidate(row, repo.period, snapshot(OWNER, attempts=(("A", AttemptOutcome.PASSED),))).current_validity is CurrentValidity.CURRENT_INVALID
    assert revalidate(row, repo.period, snapshot(OWNER, attempts=(("A", AttemptOutcome.IN_PROGRESS),))).current_validity is CurrentValidity.CURRENT_INVALID
    assert revalidate(replace(row, courses=(PersistedIntentCourse(COURSE_B, "B", 1),)),
        repo.period, snapshot(OWNER, conflict=True)).current_validity is CurrentValidity.REVIEW_REQUIRED
    assert revalidate(row, repo.period, snapshot(OWNER, version="plan-v2")).current_validity is CurrentValidity.STALE_REQUIRES_REVALIDATION
    assert revalidate(row, period(expired=True), snapshot(OWNER)).current_validity is CurrentValidity.EXPIRED


@pytest.mark.anyio
async def test_institutional_authorization_occurs_before_load_and_aggregation_is_private():
    repo, _, student, institution = services(threshold=2)
    await student.submit(str(OWNER), target_period_id=PERIOD, course_codes=("A",),
        expected_current_revision=None, transparency_notice_version="notice")
    with pytest.raises(MockRegistrationServiceError) as denied:
        await institution.demand(str(ANALYST), university_id=UNIVERSITY, target_period_id=PERIOD)
    assert denied.value.code is ServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED
    assert not repo.candidates_loaded
    repo.members.add((ANALYST, UNIVERSITY))
    suppressed = await institution.demand(str(ANALYST), university_id=UNIVERSITY,
                                            target_period_id=PERIOD)
    assert suppressed.demand.status.value == "SUPPRESSED"
    assert suppressed.demand.metrics == ()
    assert suppressed.demand.coverage.valid_active_intent_owner_count is None
    assert len(DemandMetricId) == 9


@pytest.mark.anyio
async def test_withdraw_nothing_wrong_tenant_and_supported_filter_fail_safely_before_load():
    repo, _, student, institution = services()
    with pytest.raises(MockRegistrationServiceError) as empty:
        await student.withdraw(str(OWNER), target_period_id=PERIOD,
            expected_current_revision=1, transparency_notice_version="notice")
    assert empty.value.code is ServiceErrorCode.RESOURCE_NOT_FOUND
    repo.members.add((ANALYST, UNIVERSITY))
    with pytest.raises(MockRegistrationServiceError) as unsupported:
        await institution.demand(str(ANALYST), university_id=UNIVERSITY,
            target_period_id=PERIOD, course_code="A")
    assert unsupported.value.code is ServiceErrorCode.AGGREGATION_SCOPE_INVALID
    assert not repo.candidates_loaded
    with pytest.raises(MockRegistrationServiceError) as wrong:
        await institution.demand(str(ANALYST), university_id=OTHER_UNIVERSITY,
            target_period_id=PERIOD)
    assert wrong.value.code is ServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED
    repo.period = replace(period(), provider_namespace="other-provider")
    repo.candidates_loaded = False
    with pytest.raises(MockRegistrationServiceError) as provider:
        await institution.demand(str(ANALYST), university_id=UNIVERSITY,
            target_period_id=PERIOD)
    assert provider.value.code is ServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED
    assert not repo.candidates_loaded


def test_four_routes_auth_http_semantics_and_openapi_authority_minimization():
    repo, _, student, institution = services(threshold=2)
    repo.members.add((ANALYST, UNIVERSITY))
    app.dependency_overrides[get_mock_registration_student_service] = lambda: student
    app.dependency_overrides[get_institutional_demand_service] = lambda: institution
    try:
        with TestClient(app) as client:
            assert client.get(f"/api/v1/me/mock-registration/current?target_period_id={PERIOD}").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(OWNER))
        with TestClient(app) as client:
            missing = client.get(f"/api/v1/me/mock-registration/current?target_period_id={PERIOD}")
            assert missing.status_code == 404 and missing.json()["error_code"] == "RESOURCE_NOT_FOUND"
            created = client.post("/api/v1/me/mock-registration/revisions", json={
                "target_period_id": str(PERIOD), "course_codes": ["A"],
                "expected_current_revision": None, "transparency_notice_version": "notice"})
            assert created.status_code == 201 and created.json()["non_binding"] is True
            forged = client.post("/api/v1/me/mock-registration/revisions", json={
                "target_period_id": str(PERIOD), "course_codes": ["A"],
                "expected_current_revision": 1, "transparency_notice_version": "notice",
                "owner_id": str(OTHER)})
            assert forged.status_code == 422
            assert client.get(f"/api/v1/institutional/demand?university_id={UNIVERSITY}&target_period_id={PERIOD}").status_code == 403
            schema = client.get("/openapi.json").json()
            expected = {"/api/v1/me/mock-registration/current",
                "/api/v1/me/mock-registration/revisions",
                "/api/v1/me/mock-registration/withdrawals",
                "/api/v1/institutional/demand"}
            assert expected <= set(schema["paths"])
            submit_schema = str(schema["components"]["schemas"]["SubmitIntentRequest"])
            assert all(field not in submit_schema for field in ("owner_id", "student_id", "user_id", "study_plan_id", "university_id", "fingerprint"))
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST))
        with TestClient(app) as client:
            response = client.get(f"/api/v1/institutional/demand?university_id={UNIVERSITY}&target_period_id={PERIOD}")
            assert response.status_code == 200
            serialized = str(response.json()).lower()
            assert all(word not in serialized for word in ("owner_user_id", "student_id", "email", "grade", "conversation", "scenario"))
    finally:
        app.dependency_overrides.clear()
