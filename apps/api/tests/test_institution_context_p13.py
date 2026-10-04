"""Tiny, in-memory two-institution P13 conformance; no sandbox/database state."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.auth import CurrentUser, get_current_user
from app.institution_context import (CapabilityState, InstitutionConfig,
                                     InstitutionContext, InstitutionProviderRegistry,
                                     ProviderBinding, ProviderUnavailable)
from app.main import app
from app.advisor.models import ResolvedCourseReference
from app.degree_path.engine import plan_degree_paths
from app.degree_path.models import DegreePathConstraints
from app.planner.engine import plan_semester
from app.planner.models import PlannerConstraints
from app.progress.engine import calculate_academic_progress
from app.progress.models import (AcademicProgressCatalog, ProgressPlanCourse,
                                 ProgressRequirementGroup, ProgressStudyPlan,
                                 RequirementType)
from app.roadmap.engine import build_roadmap
from app.roadmap.fingerprint import academic_input_fingerprint
from app.roadmap.report import build_report_snapshot
from app.recommendations.engine import recommend_courses
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (AttemptOutcome, CanTakeCatalog, CanTakeRequest,
                              CourseCatalogStatus, CourseIdentity, Decision,
                              DependencyGroup, DependencyType, PlanCourseRule,
                              PrerequisiteLogicStatus, StudentCourseAttempt)

A = "10000000-0000-0000-0000-00000000000a"
B = "10000000-0000-0000-0000-00000000000b"
OWNER = "10000000-0000-0000-0000-000000000111"


def config(institution_id: str, *, key: str, theme: str = "sand",
           offering: CapabilityState = CapabilityState.ENABLED) -> InstitutionConfig:
    context = InstitutionContext(institution_id, key, f"Institution {key}", "ACTIVE",
                                 "JO" if institution_id == A else "GB", "ar" if institution_id == A else "en",
                                 ("ar", "en") if institution_id == A else ("en",),
                                 "Asia/Amman" if institution_id == A else "Europe/London",
                                 "academic-v1", "branding-v1", "v1")
    capabilities = {"offerings": offering, "policy_rag": CapabilityState.ENABLED,
                    "career_intelligence": CapabilityState.ENABLED,
                    "plan_transition": CapabilityState.MODELED_ONLY}
    bindings = {kind: ProviderBinding(f"{key}-{kind}", institution_id)
                for kind in ("offerings", "policy", "career", "transition")}
    return InstitutionConfig(context, capabilities, bindings, theme, "local-conformance", "v1")


class TinyAdapter:
    def __init__(self, institution_id: str, result: str):
        self.institution_id = institution_id
        self.result = result

    def read(self, code: str, plan_id: str) -> str:
        assert (code, plan_id) == ("CS101", "PLAN-2026")
        return self.result


def registry(configs: tuple[InstitutionConfig, ...] | None = None) -> InstitutionProviderRegistry:
    configs = configs or (config(A, key="a"), config(B, key="b", theme="indigo"))
    adapters = {(c.context.institution_id, binding.provider_key):
                TinyAdapter(c.context.institution_id, f"{c.context.institution_key}-{kind}")
                for c in configs for kind, binding in c.provider_bindings.items()}
    return InstitutionProviderRegistry(configs, adapters)


def test_two_institutions_identical_visible_ids_and_a_b_a_stability():
    items = registry()
    for kind in ("offerings", "policy", "career", "transition"):
        assert [items.resolve(tenant).require(kind).read("CS101", "PLAN-2026")
                for tenant in (A, B, A)] == [f"a-{kind}", f"b-{kind}", f"a-{kind}"]
    a, b = items.resolve(A), items.resolve(B)
    assert a.cache_key("PLAN-2026", "CS101") != b.cache_key("PLAN-2026", "CS101")
    assert a.config.fingerprint != b.config.fingerprint
    assert a.config.context.timezone != b.config.context.timezone
    assert a.config.theme_key != b.config.theme_key
    assert a.config.context.default_locale != b.config.context.default_locale


def _academic_inputs(institution_id: str):
    """Same visible plan/course IDs; different scoped catalogs and owner attempts."""
    credits = Decimal(3 if institution_id == A else 4)
    group = ProgressRequirementGroup("core", "PLAN-2026", "CORE", "Core", "Core",
                                     "major", RequirementType.REQUIRED, credits * 2, 1)
    progress = AcademicProgressCatalog(
        ProgressStudyPlan("PLAN-2026", credits * 2), (group,),
        tuple(ProgressPlanCourse(code, "PLAN-2026", "core", code,
                                 CourseCatalogStatus.KNOWN, credits, index)
              for index, code in enumerate(("CS100", "CS101"))))
    prerequisite = (DependencyGroup(1, DependencyType.PREREQUISITE, ("CS100",)),)
    rules = CanTakeCatalog("PLAN-2026", (
        PlanCourseRule("CS100", PrerequisiteLogicStatus.NOT_APPLICABLE),
        PlanCourseRule("CS101", PrerequisiteLogicStatus.VERIFIED, prerequisite)
        if institution_id == A else PlanCourseRule("CS101", PrerequisiteLogicStatus.NOT_APPLICABLE)),
        (CourseIdentity("CS100", CourseCatalogStatus.KNOWN),
         CourseIdentity("CS101", CourseCatalogStatus.KNOWN)))
    attempts = (StudentCourseAttempt("CS100", AttemptOutcome.PASSED),) if institution_id == B else ()
    names = (ResolvedCourseReference("CS100", "CS100"),
             ResolvedCourseReference("CS101", "CS101"))
    return progress, rules, names, attempts


def _academic_snapshot(institution_id: str):
    progress, rules, names, attempts = _academic_inputs(institution_id)
    decision = evaluate_can_take(rules, CanTakeRequest("PLAN-2026", "CS101", attempts))
    completed = calculate_academic_progress(progress, attempts)
    roadmap = build_roadmap(progress, rules, names, attempts, institution_id=institution_id,
                            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    return decision.decision, completed.completed_plan_credits, roadmap.snapshot_fingerprint, len(roadmap.edges)


def test_existing_deterministic_engines_are_reused_for_two_institutions():
    items = registry()
    results = [_academic_snapshot(items.resolve(tenant).config.context.institution_id)
               for tenant in (A, B, A)]
    assert results[0] == results[2]
    assert results[0][0] is Decision.NOT_ELIGIBLE
    assert results[1][0] is Decision.ELIGIBLE
    assert results[0][1] == 0 and results[1][1] == 4
    assert results[0][2] != results[1][2]
    assert results[0][3] == 1 and results[1][3] == 0


def test_identical_academic_inputs_have_distinct_institution_roadmap_and_report_identity():
    inputs = _academic_inputs(A)
    a = academic_input_fingerprint(*inputs, None, institution_id=A)
    b = academic_input_fingerprint(*inputs, None, institution_id=B)
    assert a != b
    assert a == academic_input_fingerprint(*inputs, None, institution_id=A)
    reports = [build_report_snapshot(build_roadmap(*inputs, institution_id=tenant))
               for tenant in (A, B, A)]
    assert reports[0].content_fingerprint != reports[1].content_fingerprint
    assert reports[0].content_fingerprint == reports[2].content_fingerprint
    with pytest.raises(ValueError, match="institution identity"):
        academic_input_fingerprint(*inputs, None, institution_id="")


def test_planner_degree_path_and_report_follow_same_tenant_catalog_a_b_a():
    def project(tenant: str):
        progress, rules, names, attempts = _academic_inputs(tenant)
        recommendations = recommend_courses(progress, rules, attempts)
        planner = plan_semester(progress, rules, attempts, recommendations,
                                PlannerConstraints(Decimal(4), max_courses=1, max_options=2))
        degree = plan_degree_paths(progress, rules, attempts,
                                   DegreePathConstraints(Decimal(4), max_courses_per_semester=1,
                                                         max_semesters_ahead=2, max_paths=1))
        report = build_report_snapshot(build_roadmap(
            progress, rules, names, attempts, institution_id=tenant,
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        return (recommendations, planner, degree, report.content_fingerprint)

    first, second, again = (project(tenant) for tenant in (A, B, A))
    assert first == again
    assert first[1] != second[1]
    assert first[2] != second[2]
    assert first[3] != second[3]


def test_unavailable_provider_never_falls_back_and_failure_is_isolated():
    configs = (config(A, key="a", offering=CapabilityState.UNAVAILABLE), config(B, key="b"))
    items = registry(configs)
    with pytest.raises(ProviderUnavailable):
        items.resolve("unknown")
    # An unavailable capability is not an authorization grant, even if an adapter exists.
    with pytest.raises(ProviderUnavailable):
        items.resolve(A).require("offerings")
    assert items.resolve(B).require("offerings").read("CS101", "PLAN-2026") == "b-offerings"
    failed = TinyAdapter(A, "a-offerings")
    failed.read = lambda *_: (_ for _ in ()).throw(RuntimeError("A outage"))
    enabled_configs = (config(A, key="a"), config(B, key="b"))
    adapters = {(c.context.institution_id, binding.provider_key):
                (failed if c.context.institution_id == A and kind == "offerings" else
                 TinyAdapter(c.context.institution_id, f"{c.context.institution_key}-{kind}"))
                for c in enabled_configs for kind, binding in c.provider_bindings.items()}
    items = InstitutionProviderRegistry(enabled_configs, adapters)
    with pytest.raises(RuntimeError, match="A outage"):
        items.resolve(A).require("offerings").read("CS101", "PLAN-2026")
    assert items.resolve(B).require("offerings").read("CS101", "PLAN-2026") == "b-offerings"


def test_invalid_config_and_binding_fail_closed():
    a = config(A, key="a")
    assert a.fingerprint == config(A, key="a").fingerprint
    assert a.fingerprint != config(A, key="a", theme="indigo").fingerprint
    with pytest.raises(ValueError, match="Duplicate"):
        registry((a, config(B, key="a")))
    with pytest.raises(ValueError, match="Unknown provider binding"):
        InstitutionProviderRegistry((a,), {})
    with pytest.raises(ValueError, match="cross-tenant"):
        replace(a, provider_bindings={"offerings": ProviderBinding("other", B)})
    with pytest.raises(ValueError, match="Unsupported locale"):
        replace(a.context, default_locale="fr")
    with pytest.raises(ValueError, match="timezone"):
        replace(a.context, timezone="Not/AZone")
    with pytest.raises(ValueError, match="branding"):
        replace(a, theme_key="<script>alert(1)</script>")
    with pytest.raises(ValueError, match="requires"):
        replace(a, provider_bindings={})
    inactive = replace(a, context=replace(a.context, status="INACTIVE"))
    with pytest.raises(ProviderUnavailable):
        registry((inactive,)).resolve(A)
    assert "provider_bindings" not in a.public_view()
    assert "secret" not in str(a.public_view()).lower()
    with pytest.raises(TypeError):
        a.capabilities["offerings"] = CapabilityState.UNAVAILABLE


class StudentStub:
    def __init__(self):
        self.owner_calls = []

    async def resolve_student_university_id(self, owner: str) -> str:
        self.owner_calls.append(owner)
        return A


def test_current_institution_uses_authenticated_owner_not_request_identity():
    original_service = getattr(app.state, "student_service", None)
    original_registry = getattr(app.state, "institution_registry", None)
    student = StudentStub()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    try:
        with TestClient(app) as client:
            app.state.student_service = student
            app.state.institution_registry = registry()
            response = client.get(f"/api/v1/me/institution-context?institution_id={B}")
            assert response.status_code == 200
            assert response.json()["institution_id"] == A
            assert response.headers["cache-control"] == "private, no-store"
            assert student.owner_calls == [OWNER]
            app.state.institution_registry = None
            assert client.get("/api/v1/me/institution-context").status_code == 503
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.state.student_service = original_service
        app.state.institution_registry = original_registry


def test_current_institution_requires_authentication():
    with TestClient(app) as client:
        assert client.get("/api/v1/me/institution-context").status_code == 401
