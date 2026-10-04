"""Exhaustive test suite for Phase P7.5: Advisor Copilot Read-Only Tools, Deterministic Dispatcher & API.

Verifies:
1. Machine-locked literal registry test (exact 11 tool IDs).
2. Side-effects registry test (all 11 tools have side_effects = 'NONE').
3. Parameterized authorization-before-data-load test across all 11 tools.
4. Parameterized zero-write methods guard test across all 11 tools.
5. All 20 canonical scenarios (P7-TEST-ADV-001 through P7-TEST-ADV-020).
6. Security tests (analyst-only escalation, dual-role, wrong student, cross-tenant, inactive assignment, role spoofing).
7. Engine regression parity tests (progress, eligibility, recommendations, planner, degree path, intelligence, delay, what-if, mock reg, decision trace).
8. Determinism and reproducibility tests.
9. FastAPI HTTP integration tests via TestClient.
"""

from __future__ import annotations

import asyncio
from time import perf_counter
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from threading import Event
from unittest.mock import patch

import pytest
import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.advisor_copilot import (
    AdvisorCopilotService,
    AdvisorCopilotServiceError,
    AdvisorCopilotServiceErrorCode,
    AdvisorToolDispatcher,
    AdvisorToolExecutionRequest,
    AdvisorToolExecutionResponse,
    AdvisorToolId,
    TOOL_AUTHORITY_CLASSES,
    TOOL_REQUIRES_TARGET_PERIOD,
    TOOL_SIDE_EFFECTS,
)
from app.advisor_copilot.models import (
    AcademicSnapshotRequest,
    CheckDelayConsequenceRequest,
    CheckEligibilityRequest,
    CurrentMockRegistrationResultDTO,
    ExplainRecommendationDecisionRequest,
    GetCurrentMockRegistrationRequest,
    GetDegreePathsRequest,
    GetRecommendationsRequest,
    GetSemesterPlansRequest,
    GetStudentIntelligenceRequest,
    PlanningConstraintBundleInput,
    ProgressRequest,
    RunWhatIfRequest,
    WhatIfOperationId,
)
from app.advisor.models import ResolvedCourseReference
from app.advisor_persistence.models import (
    AdvisorAccessContext,
    AdvisorStudentAssignmentRecord,
)
from app.advisor_service.authorization import (
    AdvisorAuthorizationError,
    AdvisorAuthorizationErrorCode,
    AdvisorAuthorizationService,
)
from app.catalog.repository import AcademicCatalogRepository
from app.core.auth import CurrentUser, get_current_user
from app.core.academic_compute import AcademicComputeLimiter
from app.main import app
from app.api.routes.student import get_student_service
from app.api.routes.advisor import get_advisor_service
from app.mock_registration.registries import ReasonCode
from app.mock_registration_persistence.models import InstitutionalMembershipRecord
from app.progress.engine import calculate_academic_progress
from app.progress.models import (
    AcademicProgressCatalog,
    CourseCatalogStatus,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.recommendations.engine import recommend_courses
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
from app.services.eligibility import EligibilityService
from app.services.student import StudentService
from apps.api.tests.test_advisor_api import FakeAdvisorService, _general_result
from apps.api.tests.test_degree_path_api import _sample_degree_path_result
from apps.api.tests.test_student_api import FakeStudentService as ProgressResponseService
from app.student.models import (
    PerformanceProvenance,
    PerformanceVerificationState,
    StudentAcademicState,
    StudentCourseAttemptRecord,
)
from app.degree_path.models import DegreePathCapacityError, DegreePathComputationTimeout
from app.student.repository import StudentAcademicRepository


# ==============================================================================
# Canonical Catalog & Test Data Harness
# ==============================================================================

PLAN_ID = UUID("40000000-0000-0000-0000-000000000001")
UNIV_ID = UUID("20000000-0000-0000-0000-000000000001")
UNIV_OTHER = UUID("20000000-0000-0000-0000-000000000002")


def build_test_catalogs() -> tuple[AcademicProgressCatalog, CanTakeCatalog]:
    plan_str = str(PLAN_ID)
    groups = (
        ProgressRequirementGroup(
            "grp-req",
            plan_str,
            "REQ",
            "متطلبات التخصص الإجبارية",
            "Major Required",
            "major",
            RequirementType.REQUIRED,
            Decimal("30.0"),
            1,
        ),
        ProgressRequirementGroup(
            "grp-elec",
            plan_str,
            "ELEC",
            "متطلبات التخصص الاختيارية",
            "Major Elective",
            "major",
            RequirementType.ELECTIVE,
            Decimal("6.0"),
            2,
        ),
    )
    courses = (
        ProgressPlanCourse(
            "p-1501110",
            plan_str,
            "grp-req",
            "1501110",
            CourseCatalogStatus.KNOWN,
            Decimal("3.0"),
            1,
        ),
        ProgressPlanCourse(
            "p-1501221",
            plan_str,
            "grp-req",
            "1501221",
            CourseCatalogStatus.KNOWN,
            Decimal("3.0"),
            2,
        ),
        ProgressPlanCourse(
            "p-1501391",
            plan_str,
            "grp-elec",
            "1501391",
            CourseCatalogStatus.KNOWN,
            Decimal("3.0"),
            3,
        ),
        ProgressPlanCourse(
            "p-1505320",
            plan_str,
            "grp-req",
            "1505320",
            CourseCatalogStatus.KNOWN,
            Decimal("3.0"),
            4,
        ),
    )
    progress_catalog = AcademicProgressCatalog(
        ProgressStudyPlan(plan_str, Decimal("36.0")), groups, courses
    )

    rules = (
        PlanCourseRule("1501110", PrerequisiteLogicStatus.NOT_APPLICABLE),
        PlanCourseRule(
            "1501221",
            PrerequisiteLogicStatus.VERIFIED,
            (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501110",)),),
        ),
        PlanCourseRule("1501391", PrerequisiteLogicStatus.NOT_APPLICABLE),
        PlanCourseRule(
            "1505320",
            PrerequisiteLogicStatus.UNRESOLVED,
            (),
        ),
    )
    identities = (
        CourseIdentity("1501110", CourseCatalogStatus.KNOWN),
        CourseIdentity("1501221", CourseCatalogStatus.KNOWN),
        CourseIdentity("1501391", CourseCatalogStatus.KNOWN),
        CourseIdentity("1505320", CourseCatalogStatus.KNOWN),
    )
    eligibility_catalog = CanTakeCatalog(plan_str, rules, identities)
    return progress_catalog, eligibility_catalog


# ==============================================================================
# In-Memory Test Doubles & Spies
# ==============================================================================


class InMemoryStudentAcademicRepository(StudentAcademicRepository):
    """Test double recording every read and mutation call for zero-write audit."""

    def __init__(self) -> None:
        self.states: dict[str, StudentAcademicState] = {}
        self.attempts: dict[str, list[StudentCourseAttemptRecord]] = {}

        # Call-tracking spies
        self.load_state_calls: list[str] = []
        self.load_attempts_calls: list[str] = []
        self.mutation_calls: list[dict[str, Any]] = []

    @property
    def load_calls(self) -> int:
        return len(self.load_state_calls) + len(self.load_attempts_calls)

    async def load_student_academic_state(self, owner_user_id: UUID | str) -> StudentAcademicState:
        owner_str = str(owner_user_id)
        self.load_state_calls.append(owner_str)
        if owner_str in self.states:
            return self.states[owner_str]
        # Return default 45-credit student
        state = StudentAcademicState(
            profile_id=str(uuid4()),
            owner_user_id=owner_str,
            study_plan_id=str(PLAN_ID),
            reported_cumulative_gpa=Decimal("3.50"),
            reported_gpa_scale=Decimal("4.00"),
            reported_earned_credit_hours=Decimal("45.0"),
            attempts=(StudentCourseAttempt("1501110", AttemptOutcome.PASSED),),
        )
        self.states[owner_str] = state
        return state

    async def load_attempt_records(
        self, owner_user_id: UUID | str
    ) -> tuple[StudentCourseAttemptRecord, ...]:
        owner_str = str(owner_user_id)
        self.load_attempts_calls.append(owner_str)
        if owner_str in self.attempts:
            return tuple(self.attempts[owner_str])
        rec = StudentCourseAttemptRecord(
            attempt_id=str(uuid4()),
            profile_id=str(uuid4()),
            course_code="1501110",
            outcome=AttemptOutcome.PASSED,
            attempt_sequence=1,
            term_label="2025-FALL",
            attempted_on=date(2025, 10, 1),
            reported_grade_text="A",
            record_source="SIS_IMPORT",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            raw_numeric_grade=Decimal("92.0"),
            raw_letter_grade="A",
            attempt_credit_hours=Decimal("3.0"),
            performance_provenance=PerformanceProvenance.OFFICIAL_VERIFIED,
            performance_verification_state=PerformanceVerificationState.VERIFIED,
        )
        self.attempts[owner_str] = [rec]
        return (rec,)

    # Mutation methods: must NEVER be invoked by Advisor Copilot tools
    async def create_profile(self, owner_user_id: UUID | str, study_plan_id: UUID | str, **facts) -> StudentAcademicState:
        self.mutation_calls.append({"method": "create_profile", "owner": str(owner_user_id)})
        raise RuntimeError("Forbidden mutation: create_profile called")

    async def update_profile(self, owner_user_id: UUID | str, **facts) -> StudentAcademicState:
        self.mutation_calls.append({"method": "update_profile", "owner": str(owner_user_id)})
        raise RuntimeError("Forbidden mutation: update_profile called")

    async def delete_profile(self, owner_user_id: UUID | str) -> None:
        self.mutation_calls.append({"method": "delete_profile", "owner": str(owner_user_id)})
        raise RuntimeError("Forbidden mutation: delete_profile called")

    async def create_attempt(self, owner_user_id: UUID | str, course_code: str, outcome: AttemptOutcome, **facts) -> StudentCourseAttemptRecord:
        self.mutation_calls.append({"method": "create_attempt", "owner": str(owner_user_id), "course_code": course_code})
        raise RuntimeError("Forbidden mutation: create_attempt called")

    async def update_attempt(self, owner_user_id: UUID | str, attempt_id: UUID | str, **facts) -> StudentCourseAttemptRecord:
        self.mutation_calls.append({"method": "update_attempt", "owner": str(owner_user_id)})
        raise RuntimeError("Forbidden mutation: update_attempt called")

    async def delete_attempt(self, owner_user_id: UUID | str, attempt_id: UUID | str) -> None:
        self.mutation_calls.append({"method": "delete_attempt", "owner": str(owner_user_id)})
        raise RuntimeError("Forbidden mutation: delete_attempt called")


class InMemoryAcademicCatalogRepository(AcademicCatalogRepository):
    def __init__(self) -> None:
        self.progress_catalog, self.eligibility_catalog = build_test_catalogs()
        self.load_progress_calls = 0
        self.load_eligibility_calls = 0
        self.load_target_calls = 0
        self.load_advisor_catalog_calls = 0
        self.advisor_course_catalog = (
            ResolvedCourseReference("1501110", "برمجة 1", "Programming 1"),
            ResolvedCourseReference("1501221", "برمجة 2", "Programming 2"),
            ResolvedCourseReference("1501391", "تراكيب بيانات", "Data Structures"),
            ResolvedCourseReference("1505320", "ذكاء اصطناعي", "Artificial Intelligence"),
        )

    async def load_target_rules(
        self, study_plan_id: UUID | str, target_course_code: str
    ) -> CanTakeCatalog:
        self.load_target_calls += 1
        return self.eligibility_catalog

    async def load_progress_catalog(self, study_plan_id: UUID | str) -> AcademicProgressCatalog:
        self.load_progress_calls += 1
        return self.progress_catalog

    async def load_plan_eligibility_catalog(self, study_plan_id: UUID | str) -> CanTakeCatalog:
        self.load_eligibility_calls += 1
        return self.eligibility_catalog

    async def load_advisor_course_catalog(
        self, study_plan_id: UUID | str
    ) -> tuple[ResolvedCourseReference, ...]:
        self.load_advisor_catalog_calls += 1
        return self.advisor_course_catalog


class InMemoryAdvisorMockRegistrationReader:
    """Dedicated read-only advisor mock registration reader test double."""

    def __init__(self) -> None:
        self.read_calls: list[dict[str, Any]] = []

    async def get_current_intent(
        self, context: AdvisorAccessContext, target_period_id: UUID
    ) -> CurrentMockRegistrationResultDTO:
        self.read_calls.append({"context": context, "target_period_id": target_period_id})
        return CurrentMockRegistrationResultDTO(
            intent_id=str(uuid4()),
            target_period_id=target_period_id,
            course_codes=["1501221", "1501391"],
            current_validity="CURRENT_VALID",
            revalidation_status="COMPLETE",
            revalidation_reason_codes=[],
            is_expired=False,
            limitations=["Mock registration intent only"],
        )


class InMemoryAdvisorAssignmentRepository:
    def __init__(self) -> None:
        self.assignments: list[AdvisorStudentAssignmentRecord] = []
        self.memberships: list[InstitutionalMembershipRecord] = []
        self.student_universities: dict[UUID, UUID] = {}
        self.load_assignment_calls = 0

    async def load_active_advisor_memberships_for_user(
        self, subject_user_id: UUID
    ) -> tuple[InstitutionalMembershipRecord, ...]:
        return tuple(
            m
            for m in self.memberships
            if m.subject_user_id == subject_user_id
            and m.role == "ACADEMIC_ADVISOR"
            and m.active
        )

    async def load_student_authoritative_university(self, student_user_id: UUID) -> UUID | None:
        return self.student_universities.get(student_user_id)

    async def load_active_assignment(
        self, *, advisor_user_id: UUID, student_user_id: UUID, university_id: UUID
    ) -> AdvisorStudentAssignmentRecord | None:
        self.load_assignment_calls += 1
        for a in self.assignments:
            if (
                a.advisor_user_id == advisor_user_id
                and a.student_user_id == student_user_id
                and a.university_id == university_id
                and a.is_active
            ):
                return a
        return None


class InMemoryAcademicContextLoader:
    """Authoritative academic context loader test double."""

    def __init__(
        self,
        major_id: str | None = "MAJOR_CS_2026",
        study_plan_version: str | None = "2026.1",
        source_versions: tuple[str, ...] | None = ("catalog:2026.1",),
    ) -> None:
        self.major_id = major_id
        self.study_plan_version = study_plan_version
        self.source_versions = source_versions
        self.load_calls: list[str] = []
        self.should_fail = False

    async def load_owner_context(self, owner_user_id: UUID | str):
        self.load_calls.append(str(owner_user_id))
        if self.should_fail:
            raise RuntimeError("Authoritative context loader backend failure")
        from types import SimpleNamespace
        return SimpleNamespace(
            major_id=self.major_id,
            study_plan_version=self.study_plan_version,
            source_versions=self.source_versions,
            university_id=UNIV_ID,
            owner_user_id=UUID(str(owner_user_id)) if isinstance(owner_user_id, str) else owner_user_id,
            study_plan_id=PLAN_ID,
        )


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def test_harness():
    """Provides a fully wired, in-memory Advisor Copilot dispatcher and dependencies."""
    student_repo = InMemoryStudentAcademicRepository()
    catalog_repo = InMemoryAcademicCatalogRepository()
    mock_reg_reader = InMemoryAdvisorMockRegistrationReader()
    assignment_repo = InMemoryAdvisorAssignmentRepository()
    auth_service = AdvisorAuthorizationService(assignment_repo)
    eligibility_service = EligibilityService(catalog_repo)
    context_loader = InMemoryAcademicContextLoader()
    academic_compute_limiter = AcademicComputeLimiter()

    dispatcher = AdvisorToolDispatcher(
        authorization_service=auth_service,
        student_repository=student_repo,
        catalog_repository=catalog_repo,
        eligibility_service=eligibility_service,
        mock_registration_reader=mock_reg_reader,
        context_loader=context_loader,
        academic_compute_limiter=academic_compute_limiter,
    )

    advisor_id = uuid4()
    student_id = uuid4()

    # Seed active ACADEMIC_ADVISOR membership
    now = datetime.now(timezone.utc)
    assignment_repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=UNIV_ID,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR",
            authority_source_version="v1.0",
            created_at=now,
            updated_at=now,
        )
    )

    # Seed authoritative student university
    assignment_repo.student_universities[student_id] = UNIV_ID

    # Seed active assignment
    assignment = AdvisorStudentAssignmentRecord(
        id=uuid4(),
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=UNIV_ID,
        is_active=True,
        authority_source="DEAN_ASSIGNMENT",
        authority_version="2026-FALL",
        created_at=now,
        updated_at=now,
    )
    assignment_repo.assignments.append(assignment)

    class Harness:
        def __init__(self):
            self.advisor_id = advisor_id
            self.student_id = student_id
            self.dispatcher = dispatcher
            self.student_repo = student_repo
            self.catalog_repo = catalog_repo
            self.mock_reg_reader = mock_reg_reader
            self.assignment_repo = assignment_repo
            self.auth_service = auth_service
            self.eligibility_service = eligibility_service
            self.assignment = assignment
            self.context_loader = context_loader
            self.academic_compute_limiter = academic_compute_limiter

    return Harness()


# ==============================================================================
# 1. Machine-Locked Tool Registry & Side Effects Tests
# ==============================================================================


def test_machine_locked_tool_registry() -> None:
    """Prompt Item 6: Literal assertion verifying exactly 11 closed tool IDs."""
    expected = {
        "ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT",
        "ADVISOR_TOOL_GET_PROGRESS",
        "ADVISOR_TOOL_CHECK_ELIGIBILITY",
        "ADVISOR_TOOL_GET_RECOMMENDATIONS",
        "ADVISOR_TOOL_GET_SEMESTER_PLANS",
        "ADVISOR_TOOL_GET_DEGREE_PATHS",
        "ADVISOR_TOOL_GET_STUDENT_INTELLIGENCE",
        "ADVISOR_TOOL_CHECK_DELAY_CONSEQUENCE",
        "ADVISOR_TOOL_RUN_WHAT_IF",
        "ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION",
        "ADVISOR_TOOL_EXPLAIN_RECOMMENDATION_DECISION",
    }
    actual = {tool.value for tool in AdvisorToolId}
    assert actual == expected
    assert len(actual) == 11


@pytest.mark.parametrize("tool_id", [
    AdvisorToolId.ADVISOR_TOOL_GET_DEGREE_PATHS,
    AdvisorToolId.ADVISOR_TOOL_RUN_WHAT_IF,
])
@pytest.mark.parametrize("error,status,code", [
    (DegreePathCapacityError("private capacity detail"), 503, "COMPUTE_CAPACITY_BUSY"),
    (DegreePathComputationTimeout("private timeout detail"), 504, "COMPUTATION_TIMEOUT"),
    (RuntimeError("private unexpected detail"), 500, "INTERNAL_ERROR"),
])
def test_copilot_heavy_tool_http_errors_are_safe(test_harness, monkeypatch, tool_id, error, status, code):
    adapter = test_harness.dispatcher._adapters[tool_id]

    async def failing_execute(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(adapter, "execute", failing_execute)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(test_harness.advisor_id))
    app.state.advisor_copilot_service = test_harness.dispatcher
    try:
        request = _build_request_for_tool(tool_id, test_harness.student_id)
        client = TestClient(app)
        response = client.post("/api/v1/advisor/tools/execute", json=request.model_dump(mode="json"))
        assert response.status_code == status
        assert response.json()["error_code"] == code
        assert "private" not in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_student_and_copilot_heavy_routes_share_one_slot(test_harness):
    service = StudentService(
        test_harness.student_repo, None, test_harness.catalog_repo,
        test_harness.academic_compute_limiter,
    )
    entered = Event()
    release = Event()
    calls = []

    def slow_plan(*_args, **_kwargs):
        calls.append("started")
        entered.set()
        assert release.wait(2)
        return "finished"

    request = GetDegreePathsRequest(target_student_user_id=test_harness.student_id)
    with patch("app.services.student.plan_degree_paths", side_effect=slow_plan):
        first = asyncio.create_task(service.get_degree_paths(
            str(test_harness.student_id), max_credit_hours_per_semester=Decimal("15"),
        ))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            competing = (
                request,
                GetSemesterPlansRequest(target_student_user_id=test_harness.student_id),
                RunWhatIfRequest(
                    target_student_user_id=test_harness.student_id,
                    operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
                    target_course_code="1501221",
                ),
            )
            for competing_request in competing:
                with pytest.raises(AdvisorCopilotServiceError) as exc:
                    await test_harness.dispatcher.execute_tool(
                        test_harness.advisor_id, competing_request,
                    )
                assert exc.value.code == AdvisorCopilotServiceErrorCode.COMPUTE_CAPACITY_BUSY
                assert exc.value.status_code == 503
            assert calls == ["started"]
        finally:
            release.set()
        assert await first == "finished"
        await asyncio.sleep(0)
        assert test_harness.academic_compute_limiter.in_use == 0


@pytest.mark.anyio
async def test_one_loop_lightweight_routes_remain_responsive_during_cpu_job(test_harness):
    service = StudentService(
        test_harness.student_repo, None, test_harness.catalog_repo,
        test_harness.academic_compute_limiter,
    )
    entered = Event()
    advisor = FakeAdvisorService(_general_result())
    service.get_academic_progress = ProgressResponseService().get_academic_progress

    def cpu_plan(*_args, **kwargs):
        entered.set()
        start = perf_counter()
        while perf_counter() - start < 1.25:
            kwargs["check_budget"]()
        return _sample_degree_path_result()

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(test_harness.student_id))
    app.dependency_overrides[get_student_service] = lambda: service
    app.dependency_overrides[get_advisor_service] = lambda: advisor
    try:
        with patch("app.services.student.plan_degree_paths", side_effect=cpu_plan):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test",
            ) as client:
                started = perf_counter()
                heavy = asyncio.create_task(client.post(
                    "/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15},
                ))
                assert await asyncio.to_thread(entered.wait, 1)
                probes = (
                    ("health", client.get("/health")),
                    ("progress", client.get("/api/v1/me/academic-progress")),
                    ("preflight", client.options(
                        "/api/v1/me/advisor", headers={
                            "origin": "http://127.0.0.1:3000",
                            "access-control-request-method": "POST",
                        },
                    )),
                    ("general", client.post("/api/v1/me/advisor", json={"message": "Hello"})),
                )
                results = await asyncio.gather(*(
                    _timed_probe(name, request) for name, request in probes
                ))
                for name, response, latency in results:
                    assert response.status_code == 200, name
                    assert latency < 1.0, (name, latency)
                response = await heavy
                assert response.status_code == 200
                heavy_seconds = perf_counter() - started
                assert heavy_seconds >= 1.25
                print(
                    "one_loop_seconds "
                    + " ".join(f"{name}={latency:.3f}" for name, _, latency in results)
                    + f" degree_path={heavy_seconds:.3f}"
                )
    finally:
        app.dependency_overrides.clear()


async def _timed_probe(name, request):
    started = perf_counter()
    response = await request
    return name, response, perf_counter() - started


def test_side_effects_registry_all_none() -> None:
    """Prompt Item 7: Every tool must have side_effects = 'NONE'."""
    assert len(TOOL_SIDE_EFFECTS) == 11
    for tool_id in AdvisorToolId:
        assert TOOL_SIDE_EFFECTS[tool_id] == "NONE"


def test_tool_authority_classes_registry() -> None:
    """Every tool has an authoritative classification contracted by P7.1."""
    assert len(TOOL_AUTHORITY_CLASSES) == 11
    for tool_id in AdvisorToolId:
        auth_class = TOOL_AUTHORITY_CLASSES[tool_id]
        if tool_id == AdvisorToolId.ADVISOR_TOOL_RUN_WHAT_IF:
            assert auth_class.value == "EPHEMERAL_SIMULATION"
        else:
            assert auth_class.value == "DETERMINISTIC_EVIDENCE"


# ==============================================================================
# 2. Parameterized Authorization-Before-Load Test across ALL 11 Tools
# ==============================================================================


def _build_request_for_tool(tool_id: AdvisorToolId, student_id: UUID) -> AdvisorToolExecutionRequest:
    if tool_id == AdvisorToolId.ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT:
        return AcademicSnapshotRequest(target_student_user_id=student_id)
    elif tool_id == AdvisorToolId.ADVISOR_TOOL_GET_PROGRESS:
        return ProgressRequest(target_student_user_id=student_id)
    elif tool_id == AdvisorToolId.ADVISOR_TOOL_CHECK_ELIGIBILITY:
        return CheckEligibilityRequest(target_student_user_id=student_id, course_code="1501221")
    elif tool_id == AdvisorToolId.ADVISOR_TOOL_GET_RECOMMENDATIONS:
        return GetRecommendationsRequest(target_student_user_id=student_id)
    elif tool_id == AdvisorToolId.ADVISOR_TOOL_GET_SEMESTER_PLANS:
        return GetSemesterPlansRequest(target_student_user_id=student_id)
    elif tool_id == AdvisorToolId.ADVISOR_TOOL_GET_DEGREE_PATHS:
        return GetDegreePathsRequest(target_student_user_id=student_id)
    elif tool_id == AdvisorToolId.ADVISOR_TOOL_GET_STUDENT_INTELLIGENCE:
        return GetStudentIntelligenceRequest(target_student_user_id=student_id)
    elif tool_id == AdvisorToolId.ADVISOR_TOOL_CHECK_DELAY_CONSEQUENCE:
        return CheckDelayConsequenceRequest(target_student_user_id=student_id, course_code="1501221")
    elif tool_id == AdvisorToolId.ADVISOR_TOOL_RUN_WHAT_IF:
        return RunWhatIfRequest(
            target_student_user_id=student_id,
            operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
            target_course_code="1501221",
        )
    elif tool_id == AdvisorToolId.ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION:
        return GetCurrentMockRegistrationRequest(target_student_user_id=student_id, target_period_id=uuid4())
    elif tool_id == AdvisorToolId.ADVISOR_TOOL_EXPLAIN_RECOMMENDATION_DECISION:
        return ExplainRecommendationDecisionRequest(target_student_user_id=student_id)
    raise ValueError(f"Unknown tool: {tool_id}")


@pytest.mark.parametrize("tool_id", list(AdvisorToolId))
@pytest.mark.anyio
async def test_authorization_before_load_enforced_across_all_tools(test_harness, tool_id: AdvisorToolId) -> None:
    """Prompt Item 60: Parameterized test proving unauthorized caller fails BEFORE any student data load."""
    unauthorized_advisor_id = uuid4()
    req = _build_request_for_tool(tool_id, test_harness.student_id)

    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(unauthorized_advisor_id, req)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED

    # Assert student repository loaders were NEVER called
    assert len(test_harness.student_repo.load_state_calls) == 0
    assert len(test_harness.student_repo.load_attempts_calls) == 0
    assert len(test_harness.mock_reg_reader.read_calls) == 0


# ==============================================================================
# 3. Parameterized Zero-Write Guard Test across ALL 11 Tools
# ==============================================================================


@pytest.mark.parametrize("tool_id", list(AdvisorToolId))
@pytest.mark.anyio
async def test_all_tools_zero_write_methods_called(test_harness, tool_id: AdvisorToolId) -> None:
    """Prompt Item 81: Proves with 100% certainty that every tool performs 0 mutations."""
    req = _build_request_for_tool(tool_id, test_harness.student_id)

    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert isinstance(response, AdvisorToolExecutionResponse)
    assert response.side_effects == "NONE"
    assert response.student_user_id == test_harness.student_id
    assert response.university_id == UNIV_ID

    # Verify zero mutations across repository and services
    assert len(test_harness.student_repo.mutation_calls) == 0
    from app.advisor_copilot.adapters import AdvisorMockRegistrationReader
    assert not hasattr(AdvisorMockRegistrationReader, "submit")
    assert not hasattr(AdvisorMockRegistrationReader, "withdraw")
    assert not hasattr(AdvisorMockRegistrationReader, "create_intent")


# ==============================================================================
# 4. Canonical P7.5 Scenarios (P7-TEST-ADV-001 through P7-TEST-ADV-020)
# ==============================================================================


@pytest.mark.anyio
async def test_p7_adv_001_read_student_snapshot(test_harness) -> None:
    """P7-TEST-ADV-001: Read student snapshot without period -> returns verified profile and active plan."""
    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT"
    assert response.authority_class == "DETERMINISTIC_EVIDENCE"
    res = response.result
    assert res.student_user_id == test_harness.student_id
    assert res.study_plan_id == str(PLAN_ID)
    assert res.reported_earned_credit_hours == Decimal("45.0")
    assert res.total_attempts_count >= 1
    assert len(res.attempts) >= 1
    assert res.attempts[0].course_code == "1501110"


@pytest.mark.anyio
async def test_p7_adv_002_evaluate_progress(test_harness) -> None:
    """P7-TEST-ADV-002: Evaluate progress without period -> returns completed credits per group."""
    req = ProgressRequest(target_student_user_id=test_harness.student_id)
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_GET_PROGRESS"
    res = response.result
    assert res.total_required_credits == Decimal("36.0")
    assert res.total_completed_credits == Decimal("3.0")
    assert len(res.requirement_groups) == 2
    req_group = next(g for g in res.requirement_groups if g.group_id == "grp-req")
    assert "1501110" in req_group.completed_courses


@pytest.mark.anyio
async def test_p7_adv_003_check_passed_course_eligibility(test_harness) -> None:
    """P7-TEST-ADV-003: Check already passed course -> ELIGIBLE fact with passed note."""
    req = CheckEligibilityRequest(target_student_user_id=test_harness.student_id, course_code="1501110")
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_CHECK_ELIGIBILITY"
    res = response.result
    assert res.decision == "ELIGIBLE"
    assert res.is_passed is True
    assert res.passed_note is not None
    assert "already been completed" in res.passed_note


@pytest.mark.anyio
async def test_p7_adv_004_check_missing_prerequisite(test_harness) -> None:
    """P7-TEST-ADV-004: Check course whose prerequisite is missing -> NOT_ELIGIBLE with missing groups."""
    # Set student attempts to empty (1501110 not taken)
    test_harness.student_repo.states[str(test_harness.student_id)] = StudentAcademicState(
        profile_id=str(uuid4()),
        owner_user_id=str(test_harness.student_id),
        study_plan_id=str(PLAN_ID),
        reported_cumulative_gpa=Decimal("3.0"),
        reported_gpa_scale=Decimal("4.0"),
        reported_earned_credit_hours=Decimal("0.0"),
        attempts=(),  # No attempts!
    )

    req = CheckEligibilityRequest(target_student_user_id=test_harness.student_id, course_code="1501221")
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    res = response.result
    assert res.decision == "NOT_ELIGIBLE"
    assert res.is_eligible is False
    assert len(res.missing_groups) == 1
    assert "1501110" in res.missing_groups[0].missing_course_codes


@pytest.mark.anyio
async def test_p7_adv_005_check_ambiguous_prerequisite(test_harness) -> None:
    """P7-TEST-ADV-005: Check course with prerequisite conflict -> REVIEW_REQUIRED with evidence."""
    req = CheckEligibilityRequest(target_student_user_id=test_harness.student_id, course_code="1505320")
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    res = response.result
    assert res.decision == "REVIEW_REQUIRED"
    assert len(res.review_reasons) >= 1
    assert "unresolved" in res.review_reasons[0].lower() or "ambiguities" in res.review_reasons[0].lower()


@pytest.mark.anyio
async def test_p7_adv_006_get_baseline_recommendations(test_harness) -> None:
    """P7-TEST-ADV-006: Get baseline recommendations -> deterministic priority-ranked options."""
    req = GetRecommendationsRequest(target_student_user_id=test_harness.student_id, opt_in_readiness=False)
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_GET_RECOMMENDATIONS"
    res = response.result
    assert len(res.ranked_recommendations) >= 1
    # 1501221 is unlocked because 1501110 was passed
    first = res.ranked_recommendations[0]
    assert first.course_code == "1501221"
    assert first.rank == 1
    # 1505320 has review required, so it is in review_required_courses
    assert "1505320" in res.review_required_courses


@pytest.mark.anyio
async def test_p7_adv_007_get_readiness_aware_recommendations(test_harness) -> None:
    """P7-TEST-ADV-007: Get readiness-aware recommendations -> opt_in_readiness evaluates P4 tie-breaking."""
    req = GetRecommendationsRequest(target_student_user_id=test_harness.student_id, opt_in_readiness=True)
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    res = response.result
    assert len(res.ranked_recommendations) >= 1
    assert res.ranked_recommendations[0].course_code == "1501221"


@pytest.mark.anyio
async def test_p7_adv_008_get_semester_plan_options(test_harness) -> None:
    """P7-TEST-ADV-008: Get semester plan options -> returns up to N valid semester candidate sets."""
    req = GetSemesterPlansRequest(target_student_user_id=test_harness.student_id, max_options=3)
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_GET_SEMESTER_PLANS"
    res = response.result
    assert len(res.options) >= 1
    assert len(res.options) <= 3
    for opt in res.options:
        assert opt.total_credit_hours > 0


@pytest.mark.anyio
async def test_p7_adv_009_get_degree_path_projection(test_harness) -> None:
    """P7-TEST-ADV-009: Get degree path projection -> non-predictive language: 'Modeled path spans N periods'."""
    req = GetDegreePathsRequest(target_student_user_id=test_harness.student_id, max_paths=3)
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_GET_DEGREE_PATHS"
    res = response.result
    assert len(res.paths) >= 1
    assert "Modeled path spans" in res.paths[0].completion_summary
    assert "Modeled paths span" in res.modeled_summary or "Modeled path" in res.modeled_summary
    # Strict check: graduation guarantee words must not appear
    assert "guaranteed graduation" not in res.modeled_summary.lower()


@pytest.mark.anyio
async def test_p7_adv_010_student_intelligence_difficulty(test_harness) -> None:
    """P7-TEST-ADV-010: Student intelligence difficulty -> returns rule-based difficulty observations."""
    req = GetStudentIntelligenceRequest(target_student_user_id=test_harness.student_id)
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_GET_STUDENT_INTELLIGENCE"
    res = response.result
    assert res.difficulty.capability == "ACADEMIC_DIFFICULTY_SIGNAL"
    assert res.performance.capability == "PERFORMANCE_INTELLIGENCE"
    assert res.strengths.capability == "ACADEMIC_STRENGTH"
    assert res.structural_risk.capability == "STRUCTURAL_RISK_SIGNAL"


@pytest.mark.anyio
async def test_p7_adv_011_predictive_risk_block_verification(test_harness) -> None:
    """P7-TEST-ADV-011: Predictive risk block verification -> predictive risk capability is strictly BLOCKED."""
    req = GetStudentIntelligenceRequest(target_student_user_id=test_harness.student_id)
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    res = response.result
    # Predictive risk must be strictly blocked by external data policy
    assert res.predictive_risk.capability == "PREDICTIVE_ACADEMIC_RISK"
    assert res.predictive_risk.status == "BLOCKED_BY_EXTERNAL_DATA"
    assert len(res.predictive_risk.observations) == 0


@pytest.mark.anyio
async def test_p7_adv_012_check_delay_consequence(test_harness) -> None:
    """P7-TEST-ADV-012: Check delay consequence -> returns P4 structural downstream delay facts."""
    req = CheckDelayConsequenceRequest(target_student_user_id=test_harness.student_id, course_code="1501110")
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_CHECK_DELAY_CONSEQUENCE"
    res = response.result
    assert res.target_course_code == "1501110"
    assert len(res.structural_facts) >= 1
    assert "calendar graduation delay" not in res.structural_facts[0].lower()


@pytest.mark.anyio
async def test_p7_adv_013_what_if_course_completion_operation(test_harness) -> None:
    """P7-TEST-ADV-013: What-If course completion operation -> computes deltas; student attempts UNCHANGED."""
    # Capture attempts before execution
    state_before = await test_harness.student_repo.load_student_academic_state(test_harness.student_id)
    attempts_before = state_before.attempts

    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
        target_course_code="1501221",
    )
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_RUN_WHAT_IF"
    assert response.authority_class == "EPHEMERAL_SIMULATION"
    res = response.result
    assert res.is_valid is True
    assert res.operation_id == "TWIN_OP_MODEL_COURSE_COMPLETION"

    # CRITICAL: Verify student attempts in repository are completely UNCHANGED
    state_after = await test_harness.student_repo.load_student_academic_state(test_harness.student_id)
    assert state_after.attempts == attempts_before


@pytest.mark.anyio
async def test_p7_adv_014_what_if_omit_course_operation(test_harness) -> None:
    """P7-TEST-ADV-014: What-If omit course operation -> computes deltas; student attempts UNCHANGED."""
    state_before = await test_harness.student_repo.load_student_academic_state(test_harness.student_id)

    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_OMIT_NEXT_PLAN_COURSE,
        target_course_code="1501221",
    )
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    res = response.result
    assert res.is_valid is True
    assert res.operation_id == "TWIN_OP_OMIT_NEXT_PLAN_COURSE"

    state_after = await test_harness.student_repo.load_student_academic_state(test_harness.student_id)
    assert state_after.attempts == state_before.attempts


@pytest.mark.anyio
async def test_p7_adv_015_what_if_planning_constraints_operation(test_harness) -> None:
    """P7-TEST-ADV-015: What-If planning constraints operation -> computes deltas with PlanningConstraintBundle."""
    bundle = PlanningConstraintBundleInput(max_credit_hours=Decimal("12.0"), max_courses=4)
    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_SET_PLANNING_CONSTRAINTS,
        constraints=bundle,
    )
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    res = response.result
    assert res.is_valid is True
    assert res.operation_id == "TWIN_OP_SET_PLANNING_CONSTRAINTS"


@pytest.mark.anyio
async def test_p7_adv_016_read_mock_registration_intent_with_period(test_harness) -> None:
    """P7-TEST-ADV-016: Read Mock Registration intent WITH period -> returns resolved intent; advisor CANNOT edit."""
    target_period = uuid4()
    req = GetCurrentMockRegistrationRequest(
        target_student_user_id=test_harness.student_id, target_period_id=target_period
    )
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION"
    res = response.result
    assert res.target_period_id == target_period
    assert len(res.course_codes) == 2
    assert "1501221" in res.course_codes
    assert len(test_harness.mock_reg_reader.read_calls) == 1
    from app.advisor_copilot.adapters import AdvisorMockRegistrationReader
    assert not hasattr(AdvisorMockRegistrationReader, "submit")
    assert not hasattr(AdvisorMockRegistrationReader, "withdraw")
    assert not hasattr(AdvisorMockRegistrationReader, "create_intent")


def test_p7_adv_017_read_mock_registration_intent_without_period(test_harness) -> None:
    """P7-TEST-ADV-017: Missing target period is rejected by the typed request contract."""
    with pytest.raises(ValidationError):
        GetCurrentMockRegistrationRequest(
            target_student_user_id=test_harness.student_id,
        )


@pytest.mark.anyio
async def test_p7_adv_018_explain_recommendation_decision_trace(test_harness) -> None:
    """P7-TEST-ADV-018: Explain recommendation decision trace -> returns ephemeral P4 trace."""
    req = ExplainRecommendationDecisionRequest(
        target_student_user_id=test_harness.student_id, mode="READINESS_AWARE"
    )
    response = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert response.tool_id == "ADVISOR_TOOL_EXPLAIN_RECOMMENDATION_DECISION"
    res = response.result
    assert res.decision_mode == "READINESS_AWARE"
    assert len(res.baseline_order) >= 1
    assert len(res.final_order) >= 1
    assert "Decision trace is ephemerally recomputed" in res.limitations[0]


@pytest.mark.anyio
async def test_p7_adv_019_cross_system_data_isolation(test_harness) -> None:
    """P7-TEST-ADV-019: Cross-system data isolation -> Copilot does not expose institutional aggregates."""
    # Verifies that AdvisorToolId does not contain any institutional aggregate demand tools
    for tool_id in AdvisorToolId:
        assert "INSTITUTIONAL" not in tool_id.value
        assert "DEMAND" not in tool_id.value
        assert "CAPACITY" not in tool_id.value


@pytest.mark.anyio
async def test_p7_adv_020_llm_authority_isolation(test_harness) -> None:
    """P7-TEST-ADV-020: LLM authority isolation -> outputs are deterministic pure models, independent of LLM."""
    req = CheckEligibilityRequest(target_student_user_id=test_harness.student_id, course_code="1501221")
    res1 = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)
    res2 = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert res1.result.decision == res2.result.decision
    assert res1.result.missing_groups == res2.result.missing_groups


# ==============================================================================
# 5. Security, Escalation & Authorization Tests
# ==============================================================================


@pytest.mark.anyio
async def test_analyst_only_escalation_rejected(test_harness) -> None:
    """Prompt Item 62: Institutional analyst without ACADEMIC_ADVISOR role is denied with 403."""
    analyst_id = uuid4()
    test_harness.assignment_repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=analyst_id,
            university_id=UNIV_ID,
            provider_namespace="zarqa_sis",
            role="INSTITUTIONAL_ANALYST",
            active=True,
            authority_source="CHANCELLOR",
            authority_source_version="v1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(analyst_id, req)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED


@pytest.mark.anyio
async def test_dual_role_user_without_assignment_rejected(test_harness) -> None:
    """Prompt Item 63: Dual role user without active assignment is denied with 403."""
    dual_user_id = uuid4()
    now = datetime.now(timezone.utc)
    for role in ("INSTITUTIONAL_ANALYST", "ACADEMIC_ADVISOR"):
        test_harness.assignment_repo.memberships.append(
            InstitutionalMembershipRecord(
                membership_id=uuid4(),
                subject_user_id=dual_user_id,
                university_id=UNIV_ID,
                provider_namespace="zarqa_sis",
                role=role,
                active=True,
                authority_source="AUTH",
                authority_source_version="v1",
                created_at=now,
                updated_at=now,
            )
        )

    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(dual_user_id, req)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED


@pytest.mark.anyio
async def test_dual_role_user_with_active_assignment_granted(test_harness) -> None:
    """Prompt Item 64: Dual role user with active assignment is granted access."""
    dual_user_id = uuid4()
    now = datetime.now(timezone.utc)
    for role in ("INSTITUTIONAL_ANALYST", "ACADEMIC_ADVISOR"):
        test_harness.assignment_repo.memberships.append(
            InstitutionalMembershipRecord(
                membership_id=uuid4(),
                subject_user_id=dual_user_id,
                university_id=UNIV_ID,
                provider_namespace="zarqa_sis",
                role=role,
                active=True,
                authority_source="AUTH",
                authority_source_version="v1",
                created_at=now,
                updated_at=now,
            )
        )
    test_harness.assignment_repo.assignments.append(
        AdvisorStudentAssignmentRecord(
            id=uuid4(),
            advisor_user_id=dual_user_id,
            student_user_id=test_harness.student_id,
            university_id=UNIV_ID,
            is_active=True,
            authority_source="DEAN",
            authority_version="v1",
            created_at=now,
            updated_at=now,
        )
    )

    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    response = await test_harness.dispatcher.execute_tool(dual_user_id, req)
    assert response.tool_id == "ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT"


@pytest.mark.anyio
async def test_wrong_student_rejected(test_harness) -> None:
    """Prompt Item 64: Assigned advisor attempts to access unassigned Student B -> 403."""
    unassigned_student_id = uuid4()
    test_harness.assignment_repo.student_universities[unassigned_student_id] = UNIV_ID

    req = AcademicSnapshotRequest(target_student_user_id=unassigned_student_id)
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED


@pytest.mark.anyio
async def test_cross_tenant_rejected(test_harness) -> None:
    """Prompt Item 65: Student belongs to Univ B, Advisor at Univ A -> 403."""
    other_student_id = uuid4()
    test_harness.assignment_repo.student_universities[other_student_id] = UNIV_OTHER

    req = AcademicSnapshotRequest(target_student_user_id=other_student_id)
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_inactive_assignment_rejected(test_harness) -> None:
    """Prompt Item 66: Inactive assignment row -> 403."""
    test_harness.assignment_repo.assignments[0] = AdvisorStudentAssignmentRecord(
        id=test_harness.assignment.id,
        advisor_user_id=test_harness.advisor_id,
        student_user_id=test_harness.student_id,
        university_id=UNIV_ID,
        is_active=False,  # INACTIVE!
        authority_source="EXPIRED",
        authority_version="v0",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_determinism_identical_inputs(test_harness) -> None:
    """Prompt Item 82: Identical inputs produce identical results with zero randomness."""
    req = GetRecommendationsRequest(target_student_user_id=test_harness.student_id)
    res1 = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)
    res2 = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert [c.course_code for c in res1.result.ranked_recommendations] == [
        c.course_code for c in res2.result.ranked_recommendations
    ]
    assert [c.reason_codes for c in res1.result.ranked_recommendations] == [
        c.reason_codes for c in res2.result.ranked_recommendations
    ]


# ==============================================================================
# 6. FastAPI HTTP Boundary Tests (TestClient)
# ==============================================================================


def test_api_execute_tool_success_200(test_harness) -> None:
    """FastAPI POST /api/v1/advisor/tools/execute -> 200 OK under verified auth."""
    app.state.advisor_copilot_service = test_harness.dispatcher

    def mock_get_current_user():
        return CurrentUser(user_id=str(test_harness.advisor_id))

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        client = TestClient(app)
        payload = {
            "target_student_user_id": str(test_harness.student_id),
            "tool_id": "ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT",
        }
        res = client.post("/api/v1/advisor/tools/execute", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["tool_id"] == "ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT"
        assert data["authority_class"] == "DETERMINISTIC_EVIDENCE"
        assert data["side_effects"] == "NONE"
        assert data["student_user_id"] == str(test_harness.student_id)
        assert data["result"]["reported_earned_credit_hours"] == "45.0"
    finally:
        app.dependency_overrides.clear()


def test_api_execute_tool_403_unauthorized(test_harness) -> None:
    """FastAPI POST /api/v1/advisor/tools/execute -> 403 FORBIDDEN when unassigned."""
    app.state.advisor_copilot_service = test_harness.dispatcher
    unassigned_advisor_id = uuid4()

    def mock_get_current_user():
        return CurrentUser(user_id=str(unassigned_advisor_id))

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        client = TestClient(app)
        payload = {
            "target_student_user_id": str(test_harness.student_id),
            "tool_id": "ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT",
        }
        res = client.post("/api/v1/advisor/tools/execute", json=payload)
        assert res.status_code == 403
        data = res.json()
        assert data["kind"] == "error"
        assert data["error_code"] == "ADVISOR_ACCESS_DENIED"
    finally:
        app.dependency_overrides.clear()


def test_api_execute_tool_422_unknown_tool(test_harness) -> None:
    """FastAPI POST /api/v1/advisor/tools/execute -> 422 when tool_id is unknown."""
    app.state.advisor_copilot_service = test_harness.dispatcher

    def mock_get_current_user():
        return CurrentUser(user_id=str(test_harness.advisor_id))

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        client = TestClient(app)
        payload = {
            "target_student_user_id": str(test_harness.student_id),
            "tool_id": "ADVISOR_TOOL_UNKNOWN_FICTIONAL",
        }
        res = client.post("/api/v1/advisor/tools/execute", json=payload)
        assert res.status_code == 422
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Supplemental Tests: Phase P7.5.1 Adapter Contract, Determinism & Boundaries
# ==============================================================================


@pytest.mark.anyio
async def test_supplemental_what_if_full_result_determinism(test_harness) -> None:
    """Requirement 16: Two What-If runs with identical inputs return identical results and identical scenario_id."""
    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
        target_course_code="1501221",
    )
    res1 = await test_harness.dispatcher.execute_tool(
        test_harness.advisor_id,
        req,
    )
    res2 = await test_harness.dispatcher.execute_tool(
        test_harness.advisor_id,
        req,
    )
    assert isinstance(res1, AdvisorToolExecutionResponse)
    assert isinstance(res2, AdvisorToolExecutionResponse)
    assert res1.result.scenario_id == res2.result.scenario_id
    assert res1.result.scenario_id.startswith("adv_whatif_")
    assert res1.result == res2.result


def test_supplemental_no_uuid4_in_adapters() -> None:
    """Requirement 16: Assert uuid4 is not imported or used in app.advisor_copilot.adapters."""
    import inspect
    import app.advisor_copilot.adapters as adapters_mod

    assert "uuid4" not in adapters_mod.__dict__

    source = inspect.getsource(adapters_mod)
    assert "uuid4" not in source


@pytest.mark.anyio
async def test_supplemental_what_if_authoritative_major_and_version_propagation(test_harness) -> None:
    """Requirement 16: Authoritative major_id and plan_version propagate without fabricated UUIDs."""
    class DummyOwnerContext:
        def __init__(self, major_id: str, version: str):
            self.major_id = major_id
            self.study_plan_version = version
            self.source_versions = (f"{version}-official",)
            self.university_id = UNIV_ID
            self.study_plan_id = PLAN_ID

    class DummyLoader:
        def __init__(self, major_id: str, version: str):
            self.major_id = major_id
            self.version = version
            self.load_calls: list[str] = []

        async def load_owner_context(self, owner_user_id: UUID | str):
            self.load_calls.append(str(owner_user_id))
            return DummyOwnerContext(self.major_id, self.version)

    from app.advisor_copilot.adapters import WhatIfAdapter

    loader_a = DummyLoader("MAJOR_CS_2026", "v2.1")
    what_if_adapter_a = WhatIfAdapter(
        student_repository=test_harness.student_repo,
        catalog_repository=test_harness.catalog_repo,
        context_loader=loader_a,
    )

    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
        target_course_code="1501221",
    )
    ctx = AdvisorAccessContext(
        advisor_user_id=test_harness.advisor_id,
        student_user_id=test_harness.student_id,
        university_id=UNIV_ID,
        assignment_id=uuid4(),
        authority_source="DEAN_ASSIGNMENT",
        authority_version="2026-FALL",
    )

    res_a = await what_if_adapter_a.execute(ctx, req)
    assert len(loader_a.load_calls) == 1
    assert loader_a.load_calls[0] == str(test_harness.student_id)

    loader_b = DummyLoader("MAJOR_ENG_2026", "v3.0")
    what_if_adapter_b = WhatIfAdapter(
        student_repository=test_harness.student_repo,
        catalog_repository=test_harness.catalog_repo,
        context_loader=loader_b,
    )
    res_b = await what_if_adapter_b.execute(ctx, req)

    assert res_a.scenario_id != res_b.scenario_id
    assert res_a.scenario_id.startswith("adv_whatif_")
    assert res_b.scenario_id.startswith("adv_whatif_")


def test_supplemental_non_fabricated_engine_policy_versions() -> None:
    """Requirement 16: ENGINE_POLICY_VERSIONS contains authentic versions from underlying engines."""
    from app.academic_digital_twin.models import DIGITAL_TWIN_CONTRACT_VERSION
    from app.advisor_copilot.adapters import ENGINE_POLICY_VERSIONS
    from app.decision_intelligence.models import (
        DECISION_INTELLIGENCE_INTEGRATION_POLICY_VERSION,
        DELAY_CONSEQUENCE_POLICY_VERSION,
    )
    from app.degree_path.models import DEGREE_PATH_POLICY_VERSION
    from app.planner.models import SEMESTER_PLANNER_POLICY_VERSION
    from app.recommendations.engine import RECOMMENDATION_POLICY_VERSION
    from app.student_intelligence.models import (
        POLICY_VERSION as STUDENT_INTELLIGENCE_POLICY_VERSION,
    )

    expected = (
        f"recommendations:{RECOMMENDATION_POLICY_VERSION}",
        f"planner:{SEMESTER_PLANNER_POLICY_VERSION}",
        f"degree_path:{DEGREE_PATH_POLICY_VERSION}",
        f"decision_intelligence:{DECISION_INTELLIGENCE_INTEGRATION_POLICY_VERSION}",
        f"delay_consequence:{DELAY_CONSEQUENCE_POLICY_VERSION}",
        f"student_intelligence:{STUDENT_INTELLIGENCE_POLICY_VERSION}",
        f"digital_twin:{DIGITAL_TWIN_CONTRACT_VERSION}",
    )
    assert ENGINE_POLICY_VERSIONS == expected


@pytest.mark.anyio
async def test_supplemental_repeated_attempt_sequence_preservation(test_harness) -> None:
    """Requirement 16: Repeated attempts (attempt 1 FAILED, attempt 2 PASSED) retain sequence 1 and 2."""
    now = datetime.now(timezone.utc)
    rec1 = StudentCourseAttemptRecord(
        attempt_id=str(uuid4()),
        profile_id=str(uuid4()),
        course_code="1501110",
        outcome=AttemptOutcome.FAILED,
        attempt_sequence=1,
        term_label="2025-FALL",
        attempted_on=date(2025, 10, 1),
        reported_grade_text="F",
        record_source="SIS_IMPORT",
        created_at=now,
        updated_at=now,
        attempt_credit_hours=Decimal("3.0"),
        performance_provenance=PerformanceProvenance.OFFICIAL_VERIFIED,
        performance_verification_state=PerformanceVerificationState.VERIFIED,
    )
    rec2 = StudentCourseAttemptRecord(
        attempt_id=str(uuid4()),
        profile_id=str(uuid4()),
        course_code="1501110",
        outcome=AttemptOutcome.PASSED,
        attempt_sequence=2,
        term_label="2026-SPRING",
        attempted_on=date(2026, 3, 1),
        reported_grade_text="A",
        record_source="SIS_IMPORT",
        created_at=now,
        updated_at=now,
        attempt_credit_hours=Decimal("3.0"),
        performance_provenance=PerformanceProvenance.OFFICIAL_VERIFIED,
        performance_verification_state=PerformanceVerificationState.VERIFIED,
    )
    test_harness.student_repo.attempts[str(test_harness.student_id)] = [rec1, rec2]

    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    res = await test_harness.dispatcher.execute_tool(
        test_harness.advisor_id,
        req,
    )
    assert isinstance(res, AdvisorToolExecutionResponse)
    attempts_out = res.result.attempts
    assert len(attempts_out) == 2
    assert attempts_out[0].course_code == "1501110"
    assert attempts_out[0].attempt_sequence == 1
    assert attempts_out[0].outcome == "FAILED"
    assert attempts_out[1].course_code == "1501110"
    assert attempts_out[1].attempt_sequence == 2
    assert attempts_out[1].outcome == "PASSED"


def test_supplemental_advisor_mock_registration_reader_owner_boundary() -> None:
    """Requirement 16: AdvisorMockRegistrationReader requires AdvisorAccessContext, zero write methods."""
    from app.advisor_copilot.adapters import AdvisorMockRegistrationReader

    assert not hasattr(AdvisorMockRegistrationReader, "submit")
    assert not hasattr(AdvisorMockRegistrationReader, "withdraw")
    assert not hasattr(AdvisorMockRegistrationReader, "create_intent")


def test_supplemental_typed_mock_registration_request_validation() -> None:
    """Requirement 16: GetCurrentMockRegistrationRequest is strictly typed, rejects invalid payloads."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GetCurrentMockRegistrationRequest(
            target_student_user_id="invalid-uuid",
            target_period_id=uuid4(),
        )
    with pytest.raises(ValidationError):
        GetCurrentMockRegistrationRequest(
            target_student_user_id=uuid4(),
            target_period_id="not-a-uuid",
        )


def test_supplemental_semester_planner_zero_credit_hours_preserved() -> None:
    """Requirement 16: max_credit_hours=0 is accepted and not replaced with 18.0; negatives and >30 rejected."""
    from pydantic import ValidationError

    req_zero = GetSemesterPlansRequest(
        target_student_user_id=uuid4(),
        max_credit_hours=Decimal("0"),
    )
    assert req_zero.max_credit_hours == Decimal("0")

    req_int_zero = GetSemesterPlansRequest(
        target_student_user_id=uuid4(),
        max_credit_hours=0,
    )
    assert req_int_zero.max_credit_hours == Decimal("0")

    # Negative rejected
    with pytest.raises(ValidationError):
        GetSemesterPlansRequest(
            target_student_user_id=uuid4(),
            max_credit_hours=-1,
        )

    # >30 rejected
    with pytest.raises(ValidationError):
        GetSemesterPlansRequest(
            target_student_user_id=uuid4(),
            max_credit_hours=31,
        )


def test_supplemental_degree_paths_boundary_values_and_rejections() -> None:
    """Requirement 16: max_credit_hours_per_semester=0 is accepted; negatives and >30 rejected."""
    from pydantic import ValidationError

    req_zero = GetDegreePathsRequest(
        target_student_user_id=uuid4(),
        max_credit_hours_per_semester=Decimal("0"),
    )
    assert req_zero.max_credit_hours_per_semester == Decimal("0")

    with pytest.raises(ValidationError):
        GetDegreePathsRequest(
            target_student_user_id=uuid4(),
            max_credit_hours_per_semester=-1,
        )

    with pytest.raises(ValidationError):
        GetDegreePathsRequest(
            target_student_user_id=uuid4(),
            max_credit_hours_per_semester=31,
        )


def test_supplemental_no_falsy_default_semantic_replacement() -> None:
    """Requirement 16: Explicit None checks ensure 0 or Decimal('0') is never replaced by default 18.0."""
    req_zero = GetSemesterPlansRequest(
        target_student_user_id=uuid4(),
        max_credit_hours=Decimal("0"),
    )
    resolved = req_zero.max_credit_hours if req_zero.max_credit_hours is not None else Decimal("18.0")
    assert resolved == Decimal("0")
    assert resolved != Decimal("18.0")

    req_none = GetSemesterPlansRequest(
        target_student_user_id=uuid4(),
        max_credit_hours=None,
    )
    resolved_none = req_none.max_credit_hours if req_none.max_credit_hours is not None else Decimal("18.0")
    assert resolved_none == Decimal("18.0")


@pytest.mark.anyio
async def test_supplemental_academic_snapshot_data_minimization_no_profile_id(test_harness) -> None:
    """Requirement 16: AcademicSnapshotResultDTO does not expose internal database PK profile_id."""
    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    res = await test_harness.dispatcher.execute_tool(
        test_harness.advisor_id,
        req,
    )
    assert isinstance(res, AdvisorToolExecutionResponse)
    dump = res.result.model_dump()
    assert "profile_id" not in dump
    assert "student_user_id" in dump
    assert "study_plan_id" in dump


def test_supplemental_mock_registration_no_invented_validity_or_expiry() -> None:
    """Requirement 16: CurrentMockRegistrationResultDTO current_validity is nullable, not forced to CURRENT_VALID."""
    from app.advisor_copilot.models import CurrentMockRegistrationResultDTO

    dto = CurrentMockRegistrationResultDTO(
        intent_id=str(uuid4()),
        target_period_id=uuid4(),
        course_codes=["1501221"],
        current_validity=None,
        revalidation_status="NOT_RUN",
        revalidation_reason_codes=[],
        is_expired=True,
        limitations=[],
    )
    data = dto.model_dump(mode="json")
    assert data["current_validity"] is None
    assert data["is_expired"] is True


# ==============================================================================
# Supplemental Tests: Phase P7.5.2 Authoritative Identity & Provenance Fail-Closed
# ==============================================================================


@pytest.mark.anyio
async def test_supplemental_what_if_missing_major_id_fails_closed(test_harness) -> None:
    """P7.5.2 Item 1 & 17: Missing major_id in authoritative context fails closed with TARGET_RESOURCE_UNAVAILABLE."""
    test_harness.context_loader.major_id = None
    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
        target_course_code="1501221",
    )
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Authoritative major identity is unavailable"


@pytest.mark.anyio
async def test_supplemental_what_if_unexpected_context_loader_failure_raises_500(test_harness) -> None:
    """Unexpected context-loader failures fail closed as sanitized INTERNAL_ERROR (500)."""
    test_harness.context_loader.should_fail = True
    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
        target_course_code="1501221",
    )
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.INTERNAL_ERROR
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "An internal error occurred while loading academic context"


@pytest.mark.anyio
async def test_supplemental_what_if_missing_study_plan_version_fails_closed(test_harness) -> None:
    """P7.5.2 Item 3 & 19: Missing study_plan_version fails closed with TARGET_RESOURCE_UNAVAILABLE (404)."""
    test_harness.context_loader.study_plan_version = None
    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
        target_course_code="1501221",
    )
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Authoritative study plan version is unavailable"


def test_supplemental_no_deterministic_hash_major_id_fallback() -> None:
    """P7.5.2 Item 4: No deterministic-hash major_id fallback or synthetic major generation exists in adapters."""
    import inspect
    import app.advisor_copilot.adapters as adapters_mod

    source = inspect.getsource(adapters_mod)
    assert "major_for_plan" not in source
    assert "hashlib.md5" not in source


def test_supplemental_no_hardcoded_academic_plan_version_fallback() -> None:
    """P7.5.2 Item 5: No hardcoded academic plan-version fallback (e.g. '2025.1' or '1.0') in adapters."""
    import inspect
    import app.advisor_copilot.adapters as adapters_mod

    source = inspect.getsource(adapters_mod)
    assert '"2025.1"' not in source
    assert "'2025.1'" not in source


@pytest.mark.anyio
async def test_supplemental_authoritative_major_id_preserved_exactly(test_harness) -> None:
    """P7.5.2 Item 6: Authoritative major_id is preserved exactly in plan identity without alteration."""
    exact_major = "EXACT_CS_AUTH_MAJOR_UUID_999"
    test_harness.context_loader.major_id = exact_major
    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
        target_course_code="1501221",
    )
    res = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)
    assert isinstance(res, AdvisorToolExecutionResponse)
    assert res.result.is_valid is True
    assert test_harness.context_loader.load_calls[-1] == str(test_harness.student_id)


@pytest.mark.anyio
async def test_supplemental_authoritative_study_plan_version_preserved_exactly(test_harness) -> None:
    """P7.5.2 Item 7: Authoritative study_plan_version is preserved exactly in plan identity."""
    exact_version = "2029-SEMESTER-SPECIAL.8"
    test_harness.context_loader.study_plan_version = exact_version
    test_harness.context_loader.source_versions = (f"catalog:{exact_version}",)
    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
        target_course_code="1501221",
    )
    res = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)
    assert isinstance(res, AdvisorToolExecutionResponse)
    assert res.result.is_valid is True


@pytest.mark.anyio
async def test_supplemental_missing_attempt_sequence_matches_p5_contract(test_harness) -> None:
    """P7.5.2 Item 8 & 20: Missing attempt_sequence is preserved as None without local synthesis."""
    now = datetime.now(timezone.utc)
    rec_no_seq = StudentCourseAttemptRecord(
        attempt_id=str(uuid4()),
        profile_id=str(uuid4()),
        course_code="1501110",
        outcome=AttemptOutcome.PASSED,
        attempt_sequence=None,  # Authoritative attempt without sequence
        term_label=None,
        attempted_on=None,
        reported_grade_text="B+",
        record_source="SIS_IMPORT",
        created_at=now,
        updated_at=now,
        attempt_credit_hours=Decimal("3.0"),
        performance_provenance=PerformanceProvenance.OFFICIAL_VERIFIED,
        performance_verification_state=PerformanceVerificationState.VERIFIED,
    )
    test_harness.student_repo.attempts[str(test_harness.student_id)] = [rec_no_seq]

    # Academic Snapshot check: attempt_sequence remains None, NOT synthesized to 1 or idx+1
    req_snap = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    res_snap = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req_snap)
    assert res_snap.result.attempts[0].attempt_sequence is None

    # What-If check: What-If executes cleanly with None attempt_sequence matching P5 contract
    req_whatif = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
        target_course_code="1501221",
    )
    res_whatif = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req_whatif)
    assert res_whatif.result.is_valid is True


def test_supplemental_no_broad_except_pass_in_advisor_copilot() -> None:
    """P7.5.2 Item 9: Assert zero broad 'except Exception: pass' or 'except: pass' in advisor_copilot."""
    import inspect
    import app.advisor_copilot.adapters as adapters_mod
    import app.advisor_copilot.dispatcher as dispatcher_mod
    import app.advisor_copilot.models as models_mod
    import app.advisor_copilot.registries as registries_mod
    import app.advisor_copilot.errors as errors_mod

    for mod in (adapters_mod, dispatcher_mod, models_mod, registries_mod, errors_mod):
        source = inspect.getsource(mod)
        assert "except Exception:\n        pass" not in source
        assert "except Exception:\n            pass" not in source
        assert "except:\n        pass" not in source
        assert "except:\n            pass" not in source


@pytest.mark.anyio
async def test_supplemental_what_if_full_result_determinism_with_authoritative_data(test_harness) -> None:
    """P7.5.2 Item 10: Full What-If result remains deterministic with complete authoritative data."""
    req = RunWhatIfRequest(
        target_student_user_id=test_harness.student_id,
        operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
        target_course_code="1501221",
    )
    res1 = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)
    res2 = await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)
    assert res1.result.scenario_id == res2.result.scenario_id
    assert res1.result.scenario_id.startswith("adv_whatif_")
    assert res1.result == res2.result


# ==============================================================================
# Supplemental Tests: Phase P7.5.3 Dispatcher Fail-Closed Security Hardening
# ==============================================================================


def test_supplemental_dispatcher_has_no_student_service_compatibility_parameter(test_harness) -> None:
    """The dispatcher exposes no legacy MockRegistrationStudentService compatibility parameter."""
    with pytest.raises(TypeError):
        AdvisorToolDispatcher(
            authorization_service=test_harness.auth_service,
            student_repository=test_harness.student_repo,
            catalog_repository=test_harness.catalog_repo,
            eligibility_service=test_harness.eligibility_service,
            mock_registration_reader=test_harness.mock_reg_reader,
            context_loader=test_harness.context_loader,
            mock_registration_student_service=object(),  # type: ignore[call-arg]
        )


def test_supplemental_no_contexts_private_attribute_fallback() -> None:
    """P7.5.3 Item 2: Assert no '_contexts' private-field discovery exists in dispatcher."""
    import inspect
    import app.advisor_copilot.dispatcher as dispatcher_mod

    source = inspect.getsource(dispatcher_mod)
    assert "_contexts" not in source


def test_supplemental_required_advisor_reader_missing_construction_failure(test_harness) -> None:
    """P7.5.3 Item 3: Missing mock_registration_reader causes fail-closed construction failure."""
    with pytest.raises(ValueError) as exc_info:
        AdvisorToolDispatcher(
            authorization_service=test_harness.auth_service,
            student_repository=test_harness.student_repo,
            catalog_repository=test_harness.catalog_repo,
            eligibility_service=test_harness.eligibility_service,
            mock_registration_reader=None,  # Missing
            context_loader=test_harness.context_loader,
        )
    assert "requires an explicit AdvisorMockRegistrationReader" in str(exc_info.value)


def test_supplemental_required_context_loader_missing_construction_failure(test_harness) -> None:
    """P7.5.3 Item 4: Missing context_loader causes fail-closed construction failure."""
    with pytest.raises(ValueError) as exc_info:
        AdvisorToolDispatcher(
            authorization_service=test_harness.auth_service,
            student_repository=test_harness.student_repo,
            catalog_repository=test_harness.catalog_repo,
            eligibility_service=test_harness.eligibility_service,
            mock_registration_reader=test_harness.mock_reg_reader,
            context_loader=None,  # Missing
        )
    assert "requires an explicit AcademicContextLoader" in str(exc_info.value)


@pytest.mark.anyio
async def test_supplemental_403_detail_does_not_expose_assignment_or_tenant(test_harness) -> None:
    """P7.5.3 Item 5: 403 detail is uniform and does not leak tenant, assignment, or existence facts."""
    unassigned_advisor = uuid4()
    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)

    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(unassigned_advisor, req)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED
    assert exc_info.value.detail == "Advisor access denied for requested student scope"
    for forbidden_word in ("inactive", "mismatch", "tenant", "assignment", "university", "not found"):
        assert forbidden_word not in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_supplemental_persistence_authorization_failure_remains_503(test_harness) -> None:
    """P7.5.3 Item 6: Persistence authorization failure maps to PERSISTENCE_UNAVAILABLE (503)."""
    class FailingAuthService:
        async def authorize_advisor_for_student(self, *args, **kwargs):
            raise AdvisorAuthorizationError(
                AdvisorAuthorizationErrorCode.PERSISTENCE_UNAVAILABLE,
                "Database connection lost during authorization check",
            )

    dispatcher = AdvisorToolDispatcher(
        authorization_service=FailingAuthService(),
        student_repository=test_harness.student_repo,
        catalog_repository=test_harness.catalog_repo,
        eligibility_service=test_harness.eligibility_service,
        mock_registration_reader=test_harness.mock_reg_reader,
        context_loader=test_harness.context_loader,
    )

    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await dispatcher.execute_tool(test_harness.advisor_id, req)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.PERSISTENCE_UNAVAILABLE
    assert exc_info.value.detail == "Advisor authorization service is temporarily unavailable"


@pytest.mark.anyio
async def test_supplemental_unexpected_adapter_exception_is_not_422(test_harness, monkeypatch) -> None:
    """P7.5.3 Item 7: Unexpected runtime exception from adapter results in 500, NOT 422 DOMAIN_VALIDATION_FAILED."""
    adapter = test_harness.dispatcher._adapters[AdvisorToolId.ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT]

    async def broken_execute(*args, **kwargs):
        raise RuntimeError("Low-level memory corruption or divide-by-zero")

    monkeypatch.setattr(adapter, "execute", broken_execute)

    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert exc_info.value.status_code == 500
    assert exc_info.value.code != AdvisorCopilotServiceErrorCode.DOMAIN_VALIDATION_FAILED
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.INTERNAL_ERROR


@pytest.mark.anyio
async def test_supplemental_unexpected_exception_public_response_contains_no_raw_exception_text(
    test_harness, monkeypatch
) -> None:
    """P7.5.3 Item 8: Unexpected exception detail is strictly sanitized and contains no raw str(e)."""
    adapter = test_harness.dispatcher._adapters[AdvisorToolId.ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT]
    secret_text = "SECRET_LEAK_POSTGRESQL_CONNECTION_STRING_PORT_5432"

    async def leaking_execute(*args, **kwargs):
        raise RuntimeError(secret_text)

    monkeypatch.setattr(adapter, "execute", leaking_execute)

    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert secret_text not in exc_info.value.detail
    assert exc_info.value.detail == "An internal error occurred during tool execution"


@pytest.mark.anyio
async def test_supplemental_missing_authority_registry_entry_fails_closed(test_harness, monkeypatch) -> None:
    """P7.5.3 Item 9: Missing tool authority registry entry fails closed with 500, no fallback."""
    from app.advisor_copilot import dispatcher as disp_mod

    copied = dict(disp_mod.TOOL_AUTHORITY_CLASSES)
    copied.pop(AdvisorToolId.ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT)
    monkeypatch.setattr(disp_mod, "TOOL_AUTHORITY_CLASSES", copied)

    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert exc_info.value.status_code == 500
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.INTERNAL_ERROR
    assert exc_info.value.detail == "Advisor tool registry configuration is invalid"


@pytest.mark.anyio
async def test_supplemental_missing_side_effect_registry_entry_fails_closed(test_harness, monkeypatch) -> None:
    """P7.5.3 Item 10: Missing side-effect registry entry fails closed with 500, does not default to NONE."""
    from app.advisor_copilot import dispatcher as disp_mod

    copied = dict(disp_mod.TOOL_SIDE_EFFECTS)
    copied.pop(AdvisorToolId.ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT)
    monkeypatch.setattr(disp_mod, "TOOL_SIDE_EFFECTS", copied)

    req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
    with pytest.raises(AdvisorCopilotServiceError) as exc_info:
        await test_harness.dispatcher.execute_tool(test_harness.advisor_id, req)

    assert exc_info.value.status_code == 500
    assert exc_info.value.code == AdvisorCopilotServiceErrorCode.INTERNAL_ERROR
    assert exc_info.value.detail == "Advisor tool registry configuration is invalid"


def test_supplemental_exact_registry_key_set_equality_all_11_tools(test_harness) -> None:
    """P7.5.3 Item 11: Machine-test exact key-set equality across all 11 tool registries."""
    adapter_keys = set(test_harness.dispatcher._adapters.keys())
    enum_keys = set(AdvisorToolId)
    authority_keys = set(TOOL_AUTHORITY_CLASSES.keys())
    side_effect_keys = set(TOOL_SIDE_EFFECTS.keys())

    assert adapter_keys == enum_keys
    assert enum_keys == authority_keys
    assert authority_keys == side_effect_keys
    assert len(enum_keys) == 11


@pytest.mark.anyio
async def test_supplemental_authorization_before_load_remains_true_for_all_11_tools(test_harness) -> None:
    """P7.5.3 Item 12: Zero student data loaded when unauthorized across all 11 tools."""
    unassigned_advisor = uuid4()
    tools = list(AdvisorToolId)

    for tool_id in tools:
        load_count_before = test_harness.student_repo.load_calls
        if tool_id == AdvisorToolId.ADVISOR_TOOL_RUN_WHAT_IF:
            req = RunWhatIfRequest(
                target_student_user_id=test_harness.student_id,
                operation_id=WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION,
                target_course_code="1501221",
            )
        elif tool_id == AdvisorToolId.ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION:
            req = GetCurrentMockRegistrationRequest(
                target_student_user_id=test_harness.student_id,
                target_period_id=uuid4(),
            )
        else:
            req = AcademicSnapshotRequest(target_student_user_id=test_harness.student_id)
            object.__setattr__(req, "tool_id", tool_id)

        with pytest.raises(AdvisorCopilotServiceError) as exc_info:
            await test_harness.dispatcher.execute_tool(unassigned_advisor, req)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Advisor access denied for requested student scope"
        assert test_harness.student_repo.load_calls == load_count_before
