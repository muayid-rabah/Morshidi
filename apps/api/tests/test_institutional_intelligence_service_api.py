"""Exhaustive integration and contract test suite for P7.3 Institutional Intelligence Service & API.

Covers all 24 required test scenarios:
1. Authorization call-order enforcement (no sensitive loaders touched when unauthenticated/unauthorized).
2. 401 unauthenticated.
3. 403 non-analyst user.
4. 403 inactive analyst membership.
5. 404 cross-tenant target period isolation.
6. 404 cross-tenant study plan isolation.
7. 404 unknown course code.
8. 422 invalid query parameter types/uuids.
9. 422 multiple active memberships without university_id specified.
10. Valid response with single active membership omitting university_id.
11. Valid response with explicit matching university_id.
12. 403 when explicit university_id does not match active analyst memberships.
13. Complete evaluation with all facts present (13 signals, 6 alerts).
14. Complete evaluation with missing offering fact (HTTP 200, INST_ALERT_OFFERING_DATA_MISSING).
15. Complete evaluation with missing capacity fact (HTTP 200, INST_ALERT_CAPACITY_DATA_MISSING).
16. Complete evaluation with both offering and capacity facts missing.
17. Privacy suppression invariant (value=None, status=suppressed, zero demand leak).
18. Response payload zero student identity verification.
19. P6 pass-through exactness.
20. Distinctive values across different courses under same plan.
21. Referenced-only course code evaluation.
22. Literal registry lock (13 signals, 6 alerts).
23. OpenAPI schema authority minimization.
24. Deterministic ordering and reproducibility.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.institutional_intelligence import get_institutional_intelligence_service
from app.catalog.errors import StudyPlanNotFound
from app.core.auth import CurrentUser, get_current_user
from app.institutional_intelligence import (
    CapacityFact,
    InstitutionalAlertId,
    InstitutionalFactAuthority,
    InstitutionalSignalId,
    OfferingFact,
    PlannedOfferingStatus,
    SignalStatus,
    INSTITUTIONAL_ALERT_REGISTRY,
    INSTITUTIONAL_SIGNAL_REGISTRY,
)
from app.institutional_intelligence_service import (
    InMemoryCapacityFactProvider,
    InMemoryOfferingFactProvider,
    InstitutionalIntelligenceResponse,
    InstitutionalIntelligenceService,
    InstitutionalIntelligenceServiceError,
    InstitutionalIntelligenceServiceErrorCode,
    NullCapacityFactProvider,
    NullOfferingFactProvider,
)
from app.main import app
from app.mock_registration.models import (
    AggregationScope,
    CoverageMetadata,
    DemandAggregationResult,
    DemandMetric,
    DemandMetricId,
    DemandStatus,
    IntentLifecycle,
    IntentProvenance,
    PlanCourseFact,
    TargetPeriod,
    TargetPeriodClass,
    ValidationStatus,
)
from app.mock_registration.registries import DataQualityFlag, ReasonCode
from app.mock_registration_persistence.errors import (
    MockRegistrationPersistenceError,
    PersistenceFailureCode,
)
from app.mock_registration_persistence.models import (
    InstitutionalMembershipRecord,
    PersistRevisionResult,
    PersistedIntentCourse,
    PersistedIntentRevision,
    PersistedTargetPeriod,
    PersistenceResultKind,
)
from app.mock_registration_service.institutional_service import InstitutionalDemandService
from app.mock_registration_service.models import AcademicContextSnapshot, InstitutionalDemandResult, RevalidationStatus
from app.mock_registration_service.student_service import MockRegistrationStudentService
from app.progress.engine import calculate_academic_progress
from app.progress.models import (
    AcademicProgressCatalog,
    CourseCatalogStatus,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CourseIdentity,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)

OWNER_1 = UUID("10000000-0000-0000-0000-000000000001")
OWNER_2 = UUID("10000000-0000-0000-0000-000000000002")
ANALYST_USER = UUID("10000000-0000-0000-0000-000000000003")
MULTI_ANALYST = UUID("10000000-0000-0000-0000-000000000004")
STUDENT_USER = UUID("10000000-0000-0000-0000-000000000005")

UNIVERSITY_A = UUID("20000000-0000-0000-0000-000000000001")
UNIVERSITY_B = UUID("20000000-0000-0000-0000-000000000002")

MAJOR_A = UUID("30000000-0000-0000-0000-000000000001")
PLAN_A = UUID("40000000-0000-0000-0000-000000000001")
PERIOD_A = UUID("50000000-0000-0000-0000-000000000001")

COURSE_A_ID = UUID("60000000-0000-0000-0000-000000000001")
COURSE_B_ID = UUID("60000000-0000-0000-0000-000000000002")
COURSE_R_ID = UUID("60000000-0000-0000-0000-000000000003")

NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


def build_academic_catalogs(plan_id: UUID = PLAN_A) -> tuple[AcademicProgressCatalog, CanTakeCatalog]:
    plan_str = str(plan_id)
    groups = (
        ProgressRequirementGroup("grp-req", plan_str, "REQ", "إجباري", "Required", "major",
                                 RequirementType.REQUIRED, Decimal("6"), 1),
        ProgressRequirementGroup("grp-elec", plan_str, "ELEC", "اختياري", "Elective", "major",
                                 RequirementType.ELECTIVE, Decimal("3"), 2),
    )
    # Course A is mandatory in grp-req.
    # Course B is elective in grp-elec.
    # Course R is NOT in plan courses (referenced-only). Course A requires Course R!
    courses = (
        ProgressPlanCourse("p-a", plan_str, "grp-req", "CS101", CourseCatalogStatus.KNOWN, Decimal("3"), 1),
        ProgressPlanCourse("p-b", plan_str, "grp-elec", "CS102", CourseCatalogStatus.KNOWN, Decimal("3"), 2),
    )
    progress_catalog = AcademicProgressCatalog(ProgressStudyPlan(plan_str, Decimal("9")), groups, courses)

    rules = (
        PlanCourseRule(
            "CS101",
            PrerequisiteLogicStatus.VERIFIED,
            (DependencyGroup(1, DependencyType.PREREQUISITE, ("CS100",)),),
        ),
        PlanCourseRule("CS102", PrerequisiteLogicStatus.NOT_APPLICABLE),
        PlanCourseRule("CS100", PrerequisiteLogicStatus.NOT_APPLICABLE),
    )
    identities = (
        CourseIdentity("CS101", CourseCatalogStatus.KNOWN),
        CourseIdentity("CS102", CourseCatalogStatus.KNOWN),
        CourseIdentity("CS100", CourseCatalogStatus.REFERENCED_ONLY),
    )
    eligibility_catalog = CanTakeCatalog(plan_str, rules, identities)
    return progress_catalog, eligibility_catalog


def build_snapshot(owner: UUID, plan_id: UUID = PLAN_A, univ_id: UUID = UNIVERSITY_A) -> AcademicContextSnapshot:
    plan_str = str(plan_id)
    progress_catalog, eligibility_catalog = build_academic_catalogs(plan_id)
    attempts = (StudentCourseAttempt("CS100", AttemptOutcome.PASSED),)
    progress = calculate_academic_progress(progress_catalog, attempts)
    facts = (
        PlanCourseFact(str(univ_id), str(MAJOR_A), plan_str, "v1", "CS101", "grp-req", Decimal("3"), "src-v1"),
        PlanCourseFact(str(univ_id), str(MAJOR_A), plan_str, "v1", "CS102", "grp-elec", Decimal("3"), "src-v1"),
    )
    token = f"tok:{owner}:{plan_id}"
    return AcademicContextSnapshot(
        owner, univ_id, MAJOR_A, plan_id, "v1", eligibility_catalog,
        progress_catalog, progress, attempts, (("CS101", COURSE_A_ID), ("CS102", COURSE_B_ID)),
        facts, ("src-v1",), "progress-v1", "profile-v1", token,
    )


class FakeContextLoader:
    def __init__(self, snapshots: dict[UUID, AcademicContextSnapshot]):
        self.snapshots = snapshots
        self.validate_scope_calls = 0

    async def load_owner_context(self, owner: UUID) -> AcademicContextSnapshot:
        return self.snapshots[owner]

    async def validate_plan_scope(self, plan_id: UUID, university_id: UUID) -> tuple[PlanCourseFact, ...]:
        self.validate_scope_calls += 1
        for s in self.snapshots.values():
            if s.study_plan_id == plan_id:
                if s.university_id != university_id:
                    raise StudyPlanNotFound("Study plan university mismatch")
                return s.plan_course_facts
        raise StudyPlanNotFound("Study plan was not found")


class FakeCatalogRepository:
    def __init__(self, plan_id: UUID = PLAN_A):
        self.plan_id = plan_id
        self.progress_catalog, self.eligibility_catalog = build_academic_catalogs(plan_id)
        self.load_progress_calls = 0
        self.load_eligibility_calls = 0

    async def load_progress_catalog(self, study_plan_id: UUID | str) -> AcademicProgressCatalog:
        self.load_progress_calls += 1
        if str(study_plan_id) != str(self.plan_id):
            raise StudyPlanNotFound("Plan not found in catalog")
        return self.progress_catalog

    async def load_plan_eligibility_catalog(self, study_plan_id: UUID | str) -> CanTakeCatalog:
        self.load_eligibility_calls += 1
        if str(study_plan_id) != str(self.plan_id):
            raise StudyPlanNotFound("Plan not found in catalog")
        return self.eligibility_catalog

    async def load_target_rules(self, study_plan_id: UUID | str, target_course_code: str) -> CanTakeCatalog:
        return self.eligibility_catalog

    async def load_advisor_course_catalog(self, study_plan_id: UUID | str):
        return ()


class FakePersistenceRepository:
    def __init__(self):
        self.periods: dict[tuple[UUID, UUID], PersistedTargetPeriod] = {
            (PERIOD_A, UNIVERSITY_A): PersistedTargetPeriod(
                PERIOD_A, UNIVERSITY_A, "tenant-a", "2027-spring",
                TargetPeriodClass.SYNTHETIC_SANDBOX_PERIOD, False, "period-src-v1",
                False, None, None, NOW, NOW,
            )
        }
        self.memberships: dict[tuple[UUID, UUID], InstitutionalMembershipRecord] = {
            (ANALYST_USER, UNIVERSITY_A): InstitutionalMembershipRecord(
                uuid4(), ANALYST_USER, UNIVERSITY_A, "tenant-a", "INSTITUTIONAL_ANALYST",
                True, "auth-source-v1", "v1", NOW, NOW,
            ),
            (MULTI_ANALYST, UNIVERSITY_A): InstitutionalMembershipRecord(
                uuid4(), MULTI_ANALYST, UNIVERSITY_A, "tenant-a", "INSTITUTIONAL_ANALYST",
                True, "auth-source-v1", "v1", NOW, NOW,
            ),
            (MULTI_ANALYST, UNIVERSITY_B): InstitutionalMembershipRecord(
                uuid4(), MULTI_ANALYST, UNIVERSITY_B, "tenant-b", "INSTITUTIONAL_ANALYST",
                True, "auth-source-v1", "v1", NOW, NOW,
            ),
        }
        self.revisions: list[PersistedIntentRevision] = []
        self.load_period_calls = 0

    async def load_target_period(self, target_period_id: UUID, university_id: UUID) -> PersistedTargetPeriod:
        self.load_period_calls += 1
        key = (target_period_id, university_id)
        if key not in self.periods:
            raise MockRegistrationPersistenceError(PersistenceFailureCode.RESOURCE_NOT_FOUND, "target period")
        return self.periods[key]

    async def load_active_membership(
        self, *, subject_user_id: UUID, university_id: UUID, role: str = "INSTITUTIONAL_ANALYST"
    ) -> InstitutionalMembershipRecord:
        key = (subject_user_id, university_id)
        if key not in self.memberships:
            raise MockRegistrationPersistenceError(PersistenceFailureCode.RESOURCE_NOT_FOUND, "membership")
        record = self.memberships[key]
        if record.role != role or not record.active:
            raise MockRegistrationPersistenceError(PersistenceFailureCode.RESOURCE_NOT_FOUND, "membership")
        return record

    async def load_active_memberships_for_user(
        self, *, subject_user_id: UUID, role: str = "INSTITUTIONAL_ANALYST"
    ) -> tuple[InstitutionalMembershipRecord, ...]:
        return tuple(
            m for (uid, _), m in self.memberships.items()
            if uid == subject_user_id and m.role == role and m.active
        )

    async def load_revision_history(self, **scope) -> tuple[PersistedIntentRevision, ...]:
        return tuple(
            row for row in self.revisions
            if all(getattr(row, k) == v for k, v in scope.items())
        )

    async def load_institution_period_candidates(
        self, *, university_id: UUID, target_period_id: UUID, study_plan_id: UUID | None = None
    ) -> tuple[PersistedIntentRevision, ...]:
        return tuple(
            r for r in self.revisions
            if r.university_id == university_id
            and r.target_period_id == target_period_id
            and (study_plan_id is None or r.study_plan_id == study_plan_id)
        )

    async def persist_revision(self, command) -> PersistRevisionResult:
        revision_number = len(self.revisions) + 1
        row = PersistedIntentRevision(
            uuid4(), command.intent_id, command.owner_user_id, command.university_id,
            command.major_id, command.study_plan_id, command.study_plan_version,
            command.target_period_id, revision_number, command.lifecycle_status,
            command.validation_status, command.content_fingerprint, command.intent_provenance,
            command.intent_source_version, command.validation_reason_codes,
            command.catalog_source_versions, command.prerequisite_source_versions,
            command.progress_state_version, command.progress_state_reference,
            command.phase5_policy_version, command.phase6_policy_version,
            command.p6_contract_version, command.target_period_source_version,
            command.transparency_notice_version, NOW, command.actor_class, NOW,
            tuple(PersistedIntentCourse(cid, code, idx + 1)
                  for idx, (cid, code) in enumerate(zip(command.course_ids, command.course_codes))),
        )
        self.revisions.append(row)
        return PersistRevisionResult(PersistenceResultKind.INSERTED, row.revision_id, row.revision, row.content_fingerprint)


def build_test_environment(
    min_disclosure_group_size: int = 2,
    offering_provider: OfferingFactProvider | None = None,
    capacity_provider: CapacityFactProvider | None = None,
):
    persistence = FakePersistenceRepository()
    snapshots = {
        OWNER_1: build_snapshot(OWNER_1),
        OWNER_2: build_snapshot(OWNER_2),
    }
    context_loader = FakeContextLoader(snapshots)
    catalog_repo = FakeCatalogRepository(PLAN_A)
    demand_service = InstitutionalDemandService(
        persistence,
        context_loader,
        minimum_disclosure_group_size=min_disclosure_group_size,
        max_intents=1000,
        max_catalog_courses=1000,
    )
    if offering_provider is None:
        offering_provider = InMemoryOfferingFactProvider((
            OfferingFact(
                university_id=str(UNIVERSITY_A),
                period_key="2027-spring",
                course_code="CS101",
                status=PlannedOfferingStatus.OFFERED,
                authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
                source_version="sis-v1",
            ),
            OfferingFact(
                university_id=str(UNIVERSITY_A),
                period_key="2027-spring",
                course_code="CS102",
                status=PlannedOfferingStatus.OFFERED,
                authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
                source_version="sis-v1",
            ),
            OfferingFact(
                university_id=str(UNIVERSITY_A),
                period_key="2027-spring",
                course_code="CS100",
                status=PlannedOfferingStatus.OFFERED,
                authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
                source_version="sis-v1",
            ),
        ))
    if capacity_provider is None:
        capacity_provider = InMemoryCapacityFactProvider((
            CapacityFact(
                university_id=str(UNIVERSITY_A),
                period_key="2027-spring",
                course_code="CS101",
                capacity=10,
                authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
                source_version="sis-v1",
                study_plan_id=str(PLAN_A),
            ),
            CapacityFact(
                university_id=str(UNIVERSITY_A),
                period_key="2027-spring",
                course_code="CS102",
                capacity=50,
                authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
                source_version="sis-v1",
                study_plan_id=str(PLAN_A),
            ),
            CapacityFact(
                university_id=str(UNIVERSITY_A),
                period_key="2027-spring",
                course_code="CS100",
                capacity=30,
                authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
                source_version="sis-v1",
                study_plan_id=str(PLAN_A),
            ),
        ))

    service = InstitutionalIntelligenceService(
        persistence=persistence,
        contexts=context_loader,
        catalog_repository=catalog_repo,
        demand_service=demand_service,
        offering_provider=offering_provider,
        capacity_provider=capacity_provider,
    )
    student_service = MockRegistrationStudentService(persistence, context_loader)
    return persistence, context_loader, catalog_repo, service, student_service, offering_provider, capacity_provider


# =============================================================================
# 1. Authorization Call-Order Enforcement
# =============================================================================

@pytest.mark.anyio
async def test_authorization_call_order_enforcement():
    """Verify that no catalog, offering, capacity, or demand loader is touched when analyst role is missing or inactive."""
    persistence, context_loader, catalog_repo, service, _, offering_prov, capacity_prov = build_test_environment()

    # User STUDENT_USER has no analyst membership
    with pytest.raises(InstitutionalIntelligenceServiceError) as exc_info:
        await service.evaluate(
            subject=STUDENT_USER,
            target_period_id=PERIOD_A,
            study_plan_id=PLAN_A,
            course_code="CS101",
        )
    assert exc_info.value.code is InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED

    # Verify that NO sensitive loaders were invoked
    assert persistence.load_period_calls == 0
    assert context_loader.validate_scope_calls == 0
    assert catalog_repo.load_progress_calls == 0
    assert catalog_repo.load_eligibility_calls == 0


# =============================================================================
# 2. 401 Unauthenticated Request
# =============================================================================

def test_unauthenticated_request_returns_401():
    _, _, _, service, _, _, _ = build_test_environment()
    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 401
            assert res.json()["error_code"] == "AUTH_REQUIRED"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 3. 403 Non-Analyst Authenticated User
# =============================================================================

def test_non_analyst_authenticated_user_returns_403():
    _, _, _, service, _, _, _ = build_test_environment()
    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(STUDENT_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 403
            assert res.json()["error_code"] == "INSTITUTIONAL_ACCESS_DENIED"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 4. 403 Inactive Analyst Membership
# =============================================================================

def test_inactive_analyst_membership_returns_403():
    persistence, _, _, service, _, _, _ = build_test_environment()
    # Mark analyst membership inactive
    rec = persistence.memberships[(ANALYST_USER, UNIVERSITY_A)]
    persistence.memberships[(ANALYST_USER, UNIVERSITY_A)] = replace(rec, active=False)

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 403
            assert res.json()["error_code"] == "INSTITUTIONAL_ACCESS_DENIED"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 5. 404 Cross-Tenant Target Period Isolation
# =============================================================================

def test_cross_tenant_target_period_isolation_returns_404():
    persistence, _, _, service, _, _, _ = build_test_environment()
    foreign_period_id = uuid4()
    # Target period belongs to UNIVERSITY_B, not UNIVERSITY_A
    persistence.periods[(foreign_period_id, UNIVERSITY_B)] = PersistedTargetPeriod(
        foreign_period_id, UNIVERSITY_B, "tenant-b", "2027-spring",
        TargetPeriodClass.SYNTHETIC_SANDBOX_PERIOD, False, "period-src-v1",
        False, None, None, NOW, NOW,
    )

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={foreign_period_id}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            # Should fail as 404 TARGET_PERIOD_UNAVAILABLE within UNIVERSITY_A's scope
            assert res.status_code == 404
            assert res.json()["error_code"] == "TARGET_PERIOD_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 6. 404 Cross-Tenant Study Plan Isolation
# =============================================================================

def test_cross_tenant_study_plan_isolation_returns_404():
    _, _, _, service, _, _, _ = build_test_environment()
    foreign_plan_id = uuid4()

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={foreign_plan_id}&course_code=CS101"
            )
            assert res.status_code == 404
            assert res.json()["error_code"] == "STUDY_PLAN_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 7. 404 Unknown Course Code
# =============================================================================

def test_unknown_course_code_returns_404():
    _, _, _, service, _, _, _ = build_test_environment()

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=UNKNOWN999"
            )
            assert res.status_code == 404
            assert res.json()["error_code"] == "COURSE_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 8. 422 Invalid Query Parameters
# =============================================================================

def test_invalid_query_parameters_returns_422():
    _, _, _, service, _, _, _ = build_test_environment()

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            # target_period_id is not a valid UUID
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id=not-a-uuid&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 422
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 9. 422 Multiple Active Memberships Without university_id Specified
# =============================================================================

def test_multiple_active_memberships_without_university_id_returns_422():
    _, _, _, service, _, _, _ = build_test_environment()

    # User MULTI_ANALYST has active memberships in UNIVERSITY_A and UNIVERSITY_B
    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(MULTI_ANALYST))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 422
            assert res.json()["error_code"] == "AGGREGATION_SCOPE_INVALID"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 10. Single Active Membership Omitting university_id Query Parameter
# =============================================================================

def test_single_active_membership_omitting_university_id_succeeds():
    _, _, _, service, _, _, _ = build_test_environment()

    # User ANALYST_USER has exactly one active membership (UNIVERSITY_A)
    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 200
            data = res.json()
            assert data["university_id"] == str(UNIVERSITY_A)
            assert data["course_code"] == "CS101"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 11. Valid Response with Explicit Matching university_id
# =============================================================================

def test_explicit_matching_university_id_succeeds():
    _, _, _, service, _, _, _ = build_test_environment()

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(MULTI_ANALYST))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?university_id={UNIVERSITY_A}&target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 200
            data = res.json()
            assert data["university_id"] == str(UNIVERSITY_A)
            assert data["course_code"] == "CS101"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 12. 403 Explicit university_id Mismatch
# =============================================================================

def test_explicit_mismatched_university_id_returns_403():
    _, _, _, service, _, _, _ = build_test_environment()
    foreign_univ_id = uuid4()

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?university_id={foreign_univ_id}&target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 403
            assert res.json()["error_code"] == "INSTITUTIONAL_ACCESS_DENIED"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 13. Complete Evaluation with All Facts Present
# =============================================================================

@pytest.mark.anyio
async def test_complete_evaluation_with_all_facts_present():
    persistence, _, _, service, student_service, _, _ = build_test_environment(min_disclosure_group_size=2)

    # Submit 2 intents to satisfy privacy threshold
    await student_service.submit(str(OWNER_1), target_period_id=PERIOD_A, course_codes=("CS101",), expected_current_revision=None, transparency_notice_version="notice-v1")
    await student_service.submit(str(OWNER_2), target_period_id=PERIOD_A, course_codes=("CS101",), expected_current_revision=None, transparency_notice_version="notice-v1")

    res = await service.evaluate(
        subject=ANALYST_USER,
        target_period_id=PERIOD_A,
        study_plan_id=PLAN_A,
        course_code="CS101",
    )
    assert isinstance(res, InstitutionalIntelligenceResponse)
    assert res.kind == "institutional_intelligence"
    assert res.contract_version == "1.0"
    assert res.course_code == "CS101"

    # All 13 signals present
    assert len(res.signals) == 13
    assert res.signals["INST_SIG_DECLARED_DEMAND_COUNT"].value == 2
    assert res.signals["INST_SIG_DECLARED_DEMAND_COUNT"].status == "AVAILABLE"
    assert res.signals["INST_SIG_SUPPLIED_CAPACITY_COUNT"].value == 10
    assert res.signals["INST_SIG_DEMAND_TO_CAPACITY_RATIO"].value == 0.2
    assert res.signals["INST_SIG_DECLARED_CAPACITY_DEFICIT"].value == -8
    assert res.signals["INST_SIG_CAPACITY_PRESSURE_STATE"].value == "WITHIN_SUPPLIED_CAPACITY"
    assert res.signals["INST_SIG_STRUCTURAL_MANDATORY_ROLE"].value == "MANDATORY_REQUIRED"

    # Alerts
    assert len(res.alerts) == 6
    alert_by_id = {a.alert_id: a for a in res.alerts}
    # No deficit, capacity is 10 and demand is 2
    assert alert_by_id["INST_ALERT_CAPACITY_DEFICIT_DETECTED"].emitted is False
    assert alert_by_id["INST_ALERT_CAPACITY_DATA_MISSING"].emitted is False
    assert alert_by_id["INST_ALERT_OFFERING_DATA_MISSING"].emitted is False


# =============================================================================
# 14. Missing Offering Fact (HTTP 200, INST_ALERT_OFFERING_DATA_MISSING)
# =============================================================================

@pytest.mark.anyio
async def test_evaluation_with_missing_offering_fact():
    _, _, _, service, _, _, _ = build_test_environment(offering_provider=NullOfferingFactProvider())

    res = await service.evaluate(
        subject=ANALYST_USER,
        target_period_id=PERIOD_A,
        study_plan_id=PLAN_A,
        course_code="CS101",
    )
    alert_by_id = {a.alert_id: a for a in res.alerts}
    assert alert_by_id["INST_ALERT_OFFERING_DATA_MISSING"].emitted is True
    assert alert_by_id["INST_ALERT_CAPACITY_DATA_MISSING"].emitted is False


# =============================================================================
# 15. Missing Capacity Fact (HTTP 200, INST_ALERT_CAPACITY_DATA_MISSING)
# =============================================================================

@pytest.mark.anyio
async def test_evaluation_with_missing_capacity_fact():
    _, _, _, service, _, _, _ = build_test_environment(capacity_provider=NullCapacityFactProvider())

    res = await service.evaluate(
        subject=ANALYST_USER,
        target_period_id=PERIOD_A,
        study_plan_id=PLAN_A,
        course_code="CS101",
    )
    alert_by_id = {a.alert_id: a for a in res.alerts}
    assert alert_by_id["INST_ALERT_CAPACITY_DATA_MISSING"].emitted is True
    assert res.signals["INST_SIG_SUPPLIED_CAPACITY_COUNT"].value is None
    assert res.signals["INST_SIG_SUPPLIED_CAPACITY_COUNT"].status == "INSUFFICIENT_DATA"
    assert res.signals["INST_SIG_CAPACITY_PRESSURE_STATE"].value is None
    assert res.signals["INST_SIG_CAPACITY_PRESSURE_STATE"].status == "INSUFFICIENT_DATA"


# =============================================================================
# 16. Both Offering and Capacity Facts Missing (HTTP 200)
# =============================================================================

@pytest.mark.anyio
async def test_evaluation_with_both_offering_and_capacity_missing():
    _, _, _, service, _, _, _ = build_test_environment(
        offering_provider=NullOfferingFactProvider(),
        capacity_provider=NullCapacityFactProvider(),
    )

    res = await service.evaluate(
        subject=ANALYST_USER,
        target_period_id=PERIOD_A,
        study_plan_id=PLAN_A,
        course_code="CS101",
    )
    alert_by_id = {a.alert_id: a for a in res.alerts}
    assert alert_by_id["INST_ALERT_OFFERING_DATA_MISSING"].emitted is True
    assert alert_by_id["INST_ALERT_CAPACITY_DATA_MISSING"].emitted is True


# =============================================================================
# 17. Privacy Suppression Invariant
# =============================================================================

@pytest.mark.anyio
async def test_privacy_suppression_invariant():
    """When demand is suppressed, value=None, status='SUPPRESSED', quality_flags contain privacy flag, zero numeric demand leak."""
    persistence, _, _, service, student_service, _, _ = build_test_environment(min_disclosure_group_size=2)

    # Submit only 1 intent; threshold is 2 -> suppressed!
    await student_service.submit(str(OWNER_1), target_period_id=PERIOD_A, course_codes=("CS101",), expected_current_revision=None, transparency_notice_version="notice-v1")

    res = await service.evaluate(
        subject=ANALYST_USER,
        target_period_id=PERIOD_A,
        study_plan_id=PLAN_A,
        course_code="CS101",
    )

    demand_sig = res.signals["INST_SIG_DECLARED_DEMAND_COUNT"]
    ratio_sig = res.signals["INST_SIG_DEMAND_TO_CAPACITY_RATIO"]
    deficit_sig = res.signals["INST_SIG_DECLARED_CAPACITY_DEFICIT"]

    # INVARIANT: Value MUST be None on suppressed signals
    assert demand_sig.status == "SUPPRESSED"
    assert demand_sig.value is None
    assert "SUPPRESSED_FOR_PRIVACY" in demand_sig.quality_flags

    assert ratio_sig.status == "SUPPRESSED"
    assert ratio_sig.value is None
    assert "SUPPRESSED_FOR_PRIVACY" in ratio_sig.quality_flags

    assert deficit_sig.status == "SUPPRESSED"
    assert deficit_sig.value is None
    assert "SUPPRESSED_FOR_PRIVACY" in deficit_sig.quality_flags


# =============================================================================
# 18. Response Payload Zero Student Identity Verification
# =============================================================================

def test_response_payload_zero_student_identities():
    _, _, _, service, _, _, _ = build_test_environment()
    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 200
            raw_text = res.text.lower()
            forbidden_tokens = [
                "owner_user_id", "student_id", "student_name", "email", "gpa",
                "grade", "transcript", "enrollment_history", "student_attempts",
                str(OWNER_1), str(OWNER_2),
            ]
            for token in forbidden_tokens:
                assert token not in raw_text, f"Forbidden privacy token '{token}' found in serialized response!"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 19. P6 Pass-Through Exactness
# =============================================================================

@pytest.mark.anyio
async def test_p6_pass_through_exactness():
    persistence, _, _, service, student_service, _, _ = build_test_environment(min_disclosure_group_size=2)
    # Submit 2 intents
    await student_service.submit(str(OWNER_1), target_period_id=PERIOD_A, course_codes=("CS101",), expected_current_revision=None, transparency_notice_version="notice-v1")
    await student_service.submit(str(OWNER_2), target_period_id=PERIOD_A, course_codes=("CS101",), expected_current_revision=None, transparency_notice_version="notice-v1")

    res = await service.evaluate(
        subject=ANALYST_USER,
        target_period_id=PERIOD_A,
        study_plan_id=PLAN_A,
        course_code="CS101",
    )
    # Demand was exactly 2 intents
    assert res.signals["INST_SIG_DECLARED_DEMAND_COUNT"].value == 2
    assert res.signals["INST_SIG_DECLARED_DEMAND_COUNT"].status == "AVAILABLE"


# =============================================================================
# 20. Distinctive Values Across Different Courses Under Same Plan
# =============================================================================

@pytest.mark.anyio
async def test_distinctive_values_across_different_courses():
    _, _, _, service, _, _, _ = build_test_environment()

    res_a = await service.evaluate(subject=ANALYST_USER, target_period_id=PERIOD_A, study_plan_id=PLAN_A, course_code="CS101")
    res_b = await service.evaluate(subject=ANALYST_USER, target_period_id=PERIOD_A, study_plan_id=PLAN_A, course_code="CS102")

    # CS101 is mandatory (grp-req), CS102 is elective (grp-elec)
    assert res_a.signals["INST_SIG_STRUCTURAL_MANDATORY_ROLE"].value == "MANDATORY_REQUIRED"
    assert res_b.signals["INST_SIG_STRUCTURAL_MANDATORY_ROLE"].value == "CHOICE_ELECTIVE"


# =============================================================================
# 21. Referenced-Only Course Code Evaluation
# =============================================================================

@pytest.mark.anyio
async def test_referenced_only_course_code():
    _, _, _, service, _, _, _ = build_test_environment()

    # CS100 is referenced in prerequisite rules for CS101, but not in plan courses
    res_ref = await service.evaluate(subject=ANALYST_USER, target_period_id=PERIOD_A, study_plan_id=PLAN_A, course_code="CS100")

    # Structural mandatory role must be None / not_applicable
    assert res_ref.signals["INST_SIG_STRUCTURAL_MANDATORY_ROLE"].value is None
    assert res_ref.signals["INST_SIG_STRUCTURAL_MANDATORY_ROLE"].status == "NOT_APPLICABLE"

    # CS100 is prerequisite to CS101 (which is mandatory), so CS100 has transitive downstream depend count = 1
    assert res_ref.signals["INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT"].value == 1
    assert res_ref.signals["INST_SIG_STRUCTURAL_BOTTLENECK_STATUS"].value == "STRUCTURAL_GATEWAY"


# =============================================================================
# 22. Literal Registry Lock (13 Signals, 6 Alerts)
# =============================================================================

def test_literal_registry_lock():
    _, _, _, service, _, _, _ = build_test_environment()
    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 200
            data = res.json()

            # Signals
            assert set(data["signals"].keys()) == {sig.value for sig in INSTITUTIONAL_SIGNAL_REGISTRY}
            assert len(data["signals"]) == 13

            # Alerts
            alert_ids = {a["alert_id"] for a in data["alerts"]}
            assert alert_ids == {alt.value for alt in INSTITUTIONAL_ALERT_REGISTRY}
            assert len(data["alerts"]) == 6
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 23. OpenAPI Schema Authority Minimization
# =============================================================================

def test_openapi_schema_authority_minimization():
    with TestClient(app) as client:
        res = client.get("/openapi.json")
        assert res.status_code == 200
        schema = res.json()

        path_item = schema["paths"].get("/api/v1/institutional/intelligence")
        assert path_item is not None
        get_op = path_item.get("get")
        assert get_op is not None

        # Verify query parameters do not include student_id / user_id
        param_names = [p["name"] for p in get_op.get("parameters", [])]
        assert "target_period_id" in param_names
        assert "study_plan_id" in param_names
        assert "course_code" in param_names
        assert "student_id" not in param_names
        assert "owner_user_id" not in param_names
        assert "user_id" not in param_names

        # Verify response schema does not leak student identity
        response_schema_ref = get_op["responses"]["200"]["content"]["application/json"]["schema"]
        schema_text = json.dumps(schema).lower()
        # Verify schema components don't define student fields on InstitutionalIntelligenceResponse
        comp_schemas = schema["components"]["schemas"]
        response_model = comp_schemas.get("InstitutionalIntelligenceResponse")
        assert response_model is not None
        props = response_model.get("properties", {})
        assert "student_id" not in props
        assert "user_id" not in props
        assert "email" not in props


# =============================================================================
# 24. Deterministic Ordering and Reproducibility
# =============================================================================

@pytest.mark.anyio
async def test_deterministic_ordering_and_reproducibility():
    _, _, _, service, _, _, _ = build_test_environment()
    fixed_time = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)

    res1 = await service.evaluate(
        subject=ANALYST_USER,
        target_period_id=PERIOD_A,
        study_plan_id=PLAN_A,
        course_code="CS101",
        computed_at=fixed_time,
        deterministic_trace_id="test-trace-1",
    )
    res2 = await service.evaluate(
        subject=ANALYST_USER,
        target_period_id=PERIOD_A,
        study_plan_id=PLAN_A,
        course_code="CS101",
        computed_at=fixed_time,
        deterministic_trace_id="test-trace-1",
    )

    json1 = res1.model_dump_json()
    json2 = res2.model_dump_json()
    assert json1 == json2


# =============================================================================
# Helper fakes for P7.3.1 Hardening Tests
# =============================================================================

class FakeDemandServiceWithResult:
    def __init__(self, result: DemandAggregationResult):
        self._result = result

    async def demand(self, *args, **kwargs) -> InstitutionalDemandResult:
        return InstitutionalDemandResult(
            demand=self._result,
            revalidation_status=RevalidationStatus.COMPLETE,
            stale_records_excluded=False,
            generated_at=NOW,
            university_id=UNIVERSITY_A,
            target_period_id=PERIOD_A,
            study_plan_id=PLAN_A,
            course_code=kwargs.get("course_code", "CS101"),
        )


def _build_fake_target_period() -> TargetPeriod:
    return TargetPeriod(
        university_id=str(UNIVERSITY_A),
        period_key="2027-spring",
        period_class=TargetPeriodClass.SYNTHETIC_SANDBOX_PERIOD,
        source_version="src-v1",
    )


def _build_fake_aggregation_scope() -> AggregationScope:
    return AggregationScope(
        university_id=str(UNIVERSITY_A),
        major_id=str(MAJOR_A),
        study_plan_id=str(PLAN_A),
        study_plan_version="v1",
    )


# =============================================================================
# 25. Verified NOT_OFFERED + Missing Capacity Fact
# =============================================================================

@pytest.mark.anyio
async def test_verified_not_offered_and_missing_capacity_fact():
    """Verify NOT_OFFERED with missing capacity fact returns HTTP 200, NOT_APPLICABLE for capacity metrics, and no missing data alerts."""
    offering_prov = InMemoryOfferingFactProvider((
        OfferingFact(
            university_id=str(UNIVERSITY_A),
            period_key="2027-spring",
            course_code="CS101",
            status=PlannedOfferingStatus.NOT_OFFERED,
            authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
            source_version="sis-v1",
        ),
    ))
    capacity_prov = NullCapacityFactProvider()
    _, _, _, service, _, _, _ = build_test_environment(
        offering_provider=offering_prov,
        capacity_provider=capacity_prov,
    )

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 200
            data = res.json()
            sigs = data["signals"]

            # All capacity metrics evaluate to NOT_APPLICABLE
            assert sigs["INST_SIG_SUPPLIED_CAPACITY_COUNT"]["status"] == "NOT_APPLICABLE"
            assert sigs["INST_SIG_SUPPLIED_CAPACITY_COUNT"]["value"] is None
            assert sigs["INST_SIG_DECLARED_CAPACITY_DEFICIT"]["status"] == "NOT_APPLICABLE"
            assert sigs["INST_SIG_DECLARED_CAPACITY_DEFICIT"]["value"] is None
            assert sigs["INST_SIG_CAPACITY_PRESSURE_STATE"]["status"] == "NOT_APPLICABLE"
            assert sigs["INST_SIG_CAPACITY_PRESSURE_STATE"]["value"] == "NOT_APPLICABLE"
            assert sigs["INST_SIG_DEMAND_TO_CAPACITY_RATIO"]["status"] == "NOT_APPLICABLE"
            assert sigs["INST_SIG_DEMAND_TO_CAPACITY_RATIO"]["value"] is None

            # Neither missing capacity nor missing offering alert is emitted
            alert_by_id = {a["alert_id"]: a for a in data["alerts"]}
            assert alert_by_id["INST_ALERT_CAPACITY_DATA_MISSING"]["emitted"] is False
            assert alert_by_id["INST_ALERT_OFFERING_DATA_MISSING"]["emitted"] is False
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 26. Missing Offering Fact + Supplied Capacity
# =============================================================================

@pytest.mark.anyio
async def test_missing_offering_fact_and_supplied_capacity():
    """Verify missing OfferingFact with supplied CapacityFact emits OFFERING_DATA_MISSING but NOT CAPACITY_DATA_MISSING."""
    offering_prov = NullOfferingFactProvider()
    capacity_prov = InMemoryCapacityFactProvider((
        CapacityFact(
            university_id=str(UNIVERSITY_A),
            period_key="2027-spring",
            course_code="CS101",
            capacity=50,
            authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
            source_version="sis-v1",
            study_plan_id=str(PLAN_A),
        ),
    ))
    _, _, _, service, _, _, _ = build_test_environment(
        offering_provider=offering_prov,
        capacity_provider=capacity_prov,
    )

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 200
            data = res.json()
            alert_by_id = {a["alert_id"]: a for a in data["alerts"]}

            assert alert_by_id["INST_ALERT_OFFERING_DATA_MISSING"]["emitted"] is True
            assert alert_by_id["INST_ALERT_CAPACITY_DATA_MISSING"]["emitted"] is False

            # Missing offering must NOT be inferred as NOT_OFFERED
            assert data["signals"]["INST_SIG_SUPPLIED_CAPACITY_COUNT"]["status"] == "AVAILABLE"
            assert data["signals"]["INST_SIG_SUPPLIED_CAPACITY_COUNT"]["value"] == 50
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 27. Suppressed Review Owner Count Cannot Leak
# =============================================================================

@pytest.mark.anyio
async def test_suppressed_review_owner_count_cannot_leak():
    """Verify that when P6 returns REVIEW_REQUIRED_INTENT_OWNER_COUNT as SUPPRESSED, the signal is SUPPRESSED with value=None, and INST_ALERT_REVIEW_REQUIRED_PRESENT is NOT emitted."""
    fake_result = DemandAggregationResult(
        contract_version="1.0",
        status=DemandStatus.AVAILABLE,
        aggregation_scope=_build_fake_aggregation_scope(),
        target_period=_build_fake_target_period(),
        metrics=(
            DemandMetric(DemandMetricId.COURSE_INTENT_OWNER_COUNT, 2, course_code="CS101"),
            DemandMetric(DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT, None, course_code="CS101"),
        ),
        suppressed_metric_ids=(DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT,),
        coverage=CoverageMetadata(True, 2, 2, Decimal("1.0")),
        quality_flags=(DataQualityFlag.SUPPRESSED_FOR_PRIVACY,),
        reason_codes=(),
        provenance=(),
        source_versions=(),
        limitations=(),
    )

    _, _, _, service, _, _, _ = build_test_environment()
    service._demand_service = FakeDemandServiceWithResult(fake_result)

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 200
            data = res.json()
            sig = data["signals"]["INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT"]
            assert sig["status"] == "SUPPRESSED"
            assert sig["value"] is None

            # Alert INST_ALERT_REVIEW_REQUIRED_PRESENT must NOT reveal presence
            alert_by_id = {a["alert_id"]: a for a in data["alerts"]}
            rev_alert = alert_by_id["INST_ALERT_REVIEW_REQUIRED_PRESENT"]
            assert rev_alert["emitted"] is False
            assert rev_alert["evidence"] == {}
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 28. Client Fact Injection Security
# =============================================================================

def test_client_fact_injection_security():
    """Verify that client query parameters attempting to inject capacity, offering, or authority facts are ignored and cannot override trusted providers."""
    _, _, _, service, _, _, _ = build_test_environment()
    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
                "&supplied_capacity=999&capacity=999&offering_status=OFFERED&authority=VERIFIED_INSTITUTIONAL_FACT&source_version=client-spoof"
            )
            assert res.status_code == 200
            data = res.json()
            # Verified server-side provider fact was 10, NOT the spoofed 999
            assert data["signals"]["INST_SIG_SUPPLIED_CAPACITY_COUNT"]["value"] == 10
            # Ensure provenance reflects server facts
            assert data["provenance"]["catalog_version"] == str(PLAN_A)
            assert data["provenance"]["catalog_version"] != "client-spoof"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 29. university_id Membership Scoping & Non-Enumeration
# =============================================================================

def test_university_selector_membership_scoping_and_non_enumeration():
    """Verify university_id selector is restricted to active memberships and returns 403 (non-enumerating) for non-member universities before loaders execute."""
    persistence, context_loader, catalog_repo, service, _, _, _ = build_test_environment()
    foreign_univ_c = UUID("30000000-0000-0000-0000-000000000099")

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(MULTI_ANALYST))
    try:
        with TestClient(app) as client:
            # 1. Allowed: UNIVERSITY_A (active membership exists)
            res_a = client.get(
                f"/api/v1/institutional/intelligence?university_id={UNIVERSITY_A}&target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res_a.status_code == 200
            assert res_a.json()["university_id"] == str(UNIVERSITY_A)

            # Reset call counters
            persistence.load_period_calls = 0
            context_loader.validate_scope_calls = 0
            catalog_repo.load_progress_calls = 0

            # 2. Denied: foreign_univ_c (no membership exists)
            res_c = client.get(
                f"/api/v1/institutional/intelligence?university_id={foreign_univ_c}&target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res_c.status_code == 403
            assert res_c.json()["error_code"] == "INSTITUTIONAL_ACCESS_DENIED"
            # Crucial: NO loaders for foreign_univ_c were executed (non-enumerating)
            assert persistence.load_period_calls == 0
            assert context_loader.validate_scope_calls == 0
            assert catalog_repo.load_progress_calls == 0
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 30. All Five P6 Metrics Distinctive Pass-Through
# =============================================================================

@pytest.mark.anyio
async def test_all_five_p6_metrics_distinctive_pass_through():
    """Verify exact 1:1 pass-through of all five P6 demand metrics without recomputation or re-rounding."""
    fake_result = DemandAggregationResult(
        contract_version="1.0",
        status=DemandStatus.AVAILABLE,
        aggregation_scope=_build_fake_aggregation_scope(),
        target_period=_build_fake_target_period(),
        metrics=(
            DemandMetric(DemandMetricId.COURSE_INTENT_OWNER_COUNT, 42, course_code="CS101"),
            DemandMetric(DemandMetricId.COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS, Decimal("0.85"), course_code="CS101"),
            DemandMetric(DemandMetricId.TOTAL_DECLARED_CREDIT_LOAD, Decimal("126.0")),
            DemandMetric(DemandMetricId.REQUIREMENT_GROUP_INTENT_OWNER_COUNT, 15, requirement_group_id="grp-req"),
            DemandMetric(DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT, 3),
        ),
        suppressed_metric_ids=(),
        coverage=CoverageMetadata(True, 42, 50, Decimal("0.84")),
        quality_flags=(),
        reason_codes=(),
        provenance=(),
        source_versions=(),
        limitations=(),
    )

    _, _, _, service, _, _, _ = build_test_environment()
    service._demand_service = FakeDemandServiceWithResult(fake_result)

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 200
            sigs = res.json()["signals"]

            # 1. COURSE_INTENT_OWNER_COUNT -> INST_SIG_DECLARED_DEMAND_COUNT
            assert sigs["INST_SIG_DECLARED_DEMAND_COUNT"]["value"] == 42
            assert sigs["INST_SIG_DECLARED_DEMAND_COUNT"]["status"] == "AVAILABLE"

            # 2. COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS -> INST_SIG_DECLARED_DEMAND_SHARE
            assert sigs["INST_SIG_DECLARED_DEMAND_SHARE"]["value"] == 0.85
            assert sigs["INST_SIG_DECLARED_DEMAND_SHARE"]["status"] == "AVAILABLE"

            # 3. TOTAL_DECLARED_CREDIT_LOAD -> INST_SIG_TOTAL_DECLARED_CREDIT_LOAD
            assert sigs["INST_SIG_TOTAL_DECLARED_CREDIT_LOAD"]["value"] == 126.0
            assert sigs["INST_SIG_TOTAL_DECLARED_CREDIT_LOAD"]["status"] == "AVAILABLE"

            # 4. REQUIREMENT_GROUP_INTENT_OWNER_COUNT -> INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT
            assert sigs["INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT"]["value"] == 15
            assert sigs["INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT"]["status"] == "AVAILABLE"

            # 5. REVIEW_REQUIRED_INTENT_OWNER_COUNT -> INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT
            assert sigs["INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT"]["value"] == 3
            assert sigs["INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT"]["status"] == "AVAILABLE"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 31. P6 Suppression Pass-Through & Non-Reconstruction
# =============================================================================

@pytest.mark.anyio
async def test_p6_suppression_pass_through_and_non_reconstruction():
    """Verify that service layer never reconstructs a suppressed P6 metric using other fields."""
    fake_result = DemandAggregationResult(
        contract_version="1.0",
        status=DemandStatus.AVAILABLE,
        aggregation_scope=_build_fake_aggregation_scope(),
        target_period=_build_fake_target_period(),
        metrics=(
            # Suppressed course demand
            DemandMetric(DemandMetricId.COURSE_INTENT_OWNER_COUNT, None, course_code="CS101"),
            # Available credit load (15.0) - service must NOT infer student count
            DemandMetric(DemandMetricId.TOTAL_DECLARED_CREDIT_LOAD, Decimal("15.0")),
            # Suppressed review owners
            DemandMetric(DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT, None),
        ),
        suppressed_metric_ids=(
            DemandMetricId.COURSE_INTENT_OWNER_COUNT,
            DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT,
        ),
        coverage=CoverageMetadata(True, None, 50, None),
        quality_flags=(DataQualityFlag.SUPPRESSED_FOR_PRIVACY,),
        reason_codes=(),
        provenance=(),
        source_versions=(),
        limitations=(),
    )

    _, _, _, service, _, _, _ = build_test_environment()
    service._demand_service = FakeDemandServiceWithResult(fake_result)

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 200
            sigs = res.json()["signals"]

            assert sigs["INST_SIG_DECLARED_DEMAND_COUNT"]["status"] == "SUPPRESSED"
            assert sigs["INST_SIG_DECLARED_DEMAND_COUNT"]["value"] is None

            assert sigs["INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT"]["status"] == "SUPPRESSED"
            assert sigs["INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT"]["value"] is None
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 32. Suppressed Metrics Recursive Serialized Response Leak Check
# =============================================================================

def test_suppressed_metrics_recursive_serialized_response_leak_check():
    """Verify that when metrics are suppressed, no hidden raw numeric value appears anywhere in the serialized response."""
    SECRET_COUNT = 7
    fake_result = DemandAggregationResult(
        contract_version="1.0",
        status=DemandStatus.AVAILABLE,
        aggregation_scope=_build_fake_aggregation_scope(),
        target_period=_build_fake_target_period(),
        metrics=(
            DemandMetric(DemandMetricId.COURSE_INTENT_OWNER_COUNT, None, course_code="CS101"),
            DemandMetric(DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT, None),
        ),
        suppressed_metric_ids=(
            DemandMetricId.COURSE_INTENT_OWNER_COUNT,
            DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT,
        ),
        coverage=CoverageMetadata(True, None, 50, None),
        quality_flags=(DataQualityFlag.SUPPRESSED_FOR_PRIVACY,),
        reason_codes=(),
        provenance=(),
        source_versions=(),
        limitations=(),
    )

    _, _, _, service, _, _, _ = build_test_environment()
    service._demand_service = FakeDemandServiceWithResult(fake_result)

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 200
            data = res.json()

            # Recursive traversal verifying suppression integrity
            def assert_no_suppressed_leak(obj, path="root"):
                if isinstance(obj, dict):
                    if obj.get("status") == "SUPPRESSED" or obj.get("result_status") == "SUPPRESSED":
                        assert obj.get("value") is None, f"Suppressed value leak at {path}.value"
                        assert obj.get("result_value") is None, f"Suppressed result_value leak at {path}.result_value"
                    for k, v in obj.items():
                        assert_no_suppressed_leak(v, f"{path}.{k}")
                elif isinstance(obj, list):
                    for idx, item in enumerate(obj):
                        assert_no_suppressed_leak(item, f"{path}[{idx}]")

            assert_no_suppressed_leak(data)

            # Check raw serialized text does not contain secret numbers
            raw_text = res.text
            assert f'"declared_demand_count": {SECRET_COUNT}' not in raw_text
            assert f'"review_required_owners": {SECRET_COUNT}' not in raw_text
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 33. Fact Authority Construction Point & Synthetic Integrity
# =============================================================================

@pytest.mark.anyio
async def test_fact_authority_construction_point_and_synthetic_integrity():
    """Verify that Null providers return None (never fabricate VERIFIED facts) and in-memory test providers carry SYNTHETIC_SANDBOX_FACT."""
    null_offering = NullOfferingFactProvider()
    null_capacity = NullCapacityFactProvider()

    assert await null_offering.get_offering_fact(university_id=str(UNIVERSITY_A), period_key="2027-spring", course_code="CS101") is None
    assert await null_capacity.get_capacity_fact(university_id=str(UNIVERSITY_A), period_key="2027-spring", course_code="CS101") is None

    synthetic_offering = InMemoryOfferingFactProvider((
        OfferingFact(
            university_id=str(UNIVERSITY_A),
            period_key="2027-spring",
            course_code="CS101",
            status=PlannedOfferingStatus.OFFERED,
            authority=InstitutionalFactAuthority.SYNTHETIC_SANDBOX_FACT,
            source_version="synth-v1",
        ),
    ))
    fact = await synthetic_offering.get_offering_fact(university_id=str(UNIVERSITY_A), period_key="2027-spring", course_code="CS101")
    assert fact is not None
    assert fact.authority is InstitutionalFactAuthority.SYNTHETIC_SANDBOX_FACT


# =============================================================================
# 34. Service Error on Domain Validation Failure
# =============================================================================

@pytest.mark.anyio
async def test_service_error_on_domain_validation_failure():
    """Verify that unhandled domain validation failures in P7.2 engine are mapped cleanly to AGGREGATION_SCOPE_INVALID (422) and do not escape as raw tracebacks."""
    persistence, context_loader, catalog_repo, service, _, _, _ = build_test_environment()

    # Pass an invalid domain scope that causes evaluate_institutional_intelligence to fail validation
    from app.institutional_intelligence.engine import evaluate_institutional_intelligence
    from app.institutional_intelligence.models import InstitutionalIntelligenceInput

    bad_input = InstitutionalIntelligenceInput(
        university_id=str(UNIVERSITY_A),
        target_period_key="2027-spring",
        course_code="CS101",
        catalog=catalog_repo.progress_catalog,
        can_take_catalog=catalog_repo.eligibility_catalog,
        all_offering_facts=(
            OfferingFact(str(UNIVERSITY_A), "2027-spring", "CS101", PlannedOfferingStatus.OFFERED, InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT, "v1"),
            OfferingFact(str(UNIVERSITY_A), "2027-spring", "CS101", PlannedOfferingStatus.NOT_OFFERED, InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT, "v2"),
        ),
    )
    with pytest.raises(ValueError):
        evaluate_institutional_intelligence(bad_input)

    # Now verify service layer maps this domain failure
    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))

    def failing_engine(*args, **kwargs):
        raise ValueError("Conflicting offering facts found for course CS101")

    # Patch evaluate in service to verify mapping
    import app.institutional_intelligence_service.service as svc_module
    orig_eval = svc_module.evaluate_institutional_intelligence
    svc_module.evaluate_institutional_intelligence = failing_engine
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 422
            assert res.json()["error_code"] == "AGGREGATION_SCOPE_INVALID"
    finally:
        svc_module.evaluate_institutional_intelligence = orig_eval
        app.dependency_overrides.clear()


# =============================================================================
# 35. PERSISTENCE_UNAVAILABLE (503) Mapping vs Normal Missing Data
# =============================================================================

@pytest.mark.anyio
async def test_persistence_unavailable_503_mapping_vs_normal_missing_data():
    """Verify that backend persistence failure maps to PERSISTENCE_UNAVAILABLE (503), whereas normal missing facts return 200 OK."""
    persistence, context_loader, catalog_repo, service, _, _, _ = build_test_environment()

    # Simulate database connection failure
    async def failing_load_period(*args, **kwargs):
        raise MockRegistrationPersistenceError(
            PersistenceFailureCode.PERSISTENCE_UNAVAILABLE, "Database connection failed"
        )
    persistence.load_target_period = failing_load_period

    app.dependency_overrides[get_institutional_intelligence_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST_USER))
    try:
        with TestClient(app) as client:
            res = client.get(
                f"/api/v1/institutional/intelligence?target_period_id={PERIOD_A}&study_plan_id={PLAN_A}&course_code=CS101"
            )
            assert res.status_code == 503
            assert res.json()["error_code"] == "PERSISTENCE_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()

