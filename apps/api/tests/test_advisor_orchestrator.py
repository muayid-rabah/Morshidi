"""Pure regression tests for Phase 10.3 deterministic advisor orchestration."""

from __future__ import annotations

import ast
from dataclasses import asdict, fields
from decimal import Decimal
from pathlib import Path

import pytest

import app.advisor.orchestrator as orchestration
from app.advisor import (
    AI_ADVISOR_POLICY_VERSION,
    AdvisorContext,
    AdvisorContractError,
    AdvisorIntent,
    AnswerAuthority,
    AuthoritativeSource,
    ClarificationReason,
    ClarificationRequest,
    CourseInformation,
    CourseResolution,
    EntityResolutionStatus,
    NormalizedAdvisorRequest,
    OutOfScopeReason,
    PolicySource,
    ResolvedCourseReference,
    orchestrate_advisor_request,
)
from app.degree_path.models import DegreePathConstraints, DegreePathResult, PathStatus
from app.planner.models import PlannerConstraints, SemesterPlannerResult
from app.progress.models import (
    AcademicProgress,
    AcademicProgressCatalog,
    CourseProgressState,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.recommendations.models import RecommendationResult
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CanTakeDecision,
    CourseCatalogStatus,
    CourseIdentity,
    Decision,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)


PLAN = "10000000-0000-0000-0000-000000000001"
GROUP = "20000000-0000-0000-0000-000000000001"


def _group() -> ProgressRequirementGroup:
    return ProgressRequirementGroup(
        group_id=GROUP,
        study_plan_id=PLAN,
        group_code="MAJOR_REQUIRED",
        name_ar="متطلبات التخصص الإجبارية",
        name_en="Major Required",
        scope="major",
        requirement_type=RequirementType.REQUIRED,
        required_credit_hours=Decimal("15"),
        display_order=1,
    )


def _plan_course(code: str, credits: str, order: int) -> ProgressPlanCourse:
    return ProgressPlanCourse(
        plan_course_id=f"pc-{code}",
        study_plan_id=PLAN,
        requirement_group_id=GROUP,
        course_code=code,
        catalog_status=CourseCatalogStatus.KNOWN,
        credit_hours=Decimal(credits),
        display_order=order,
    )


def _rule(
    code: str,
    status: PrerequisiteLogicStatus,
    name: str,
    prereq: str | None = None,
    raw: str | None = None,
) -> PlanCourseRule:
    groups = ()
    if status is PrerequisiteLogicStatus.VERIFIED and prereq is not None:
        groups = (
            DependencyGroup(1, DependencyType.PREREQUISITE, (prereq,)),
        )
    return PlanCourseRule(
        course_code=code,
        prerequisite_logic_status=status,
        dependency_groups=groups,
        raw_prerequisite_text=raw,
        target_name_ar=name,
    )


def _context(
    attempts: tuple[StudentCourseAttempt, ...] = (),
    *,
    comparison_result: RecommendationResult | SemesterPlannerResult | DegreePathResult | None = None,
) -> AdvisorContext:
    course_specs = (
        ("0300153", "أساسيات تكنولوجيا المعلومات", "3", 1),
        ("1502000", "مادة مستقلة", "3", 2),
        ("1501110", "برمجة الحاسوب (1)", "3", 3),
        ("1505311", "تعلم الالة", "3", 4),
        ("1505320", "تعلم الآلة المتقدم", "3", 5),
    )
    progress_catalog = AcademicProgressCatalog(
        study_plan=ProgressStudyPlan(PLAN, Decimal("15")),
        requirement_groups=(_group(),),
        plan_courses=tuple(
            _plan_course(code, credits, order)
            for code, _, credits, order in course_specs
        ),
    )
    rules = (
        _rule("0300153", PrerequisiteLogicStatus.NOT_APPLICABLE, course_specs[0][1]),
        _rule("1502000", PrerequisiteLogicStatus.NOT_APPLICABLE, course_specs[1][1]),
        _rule("1501110", PrerequisiteLogicStatus.VERIFIED, course_specs[2][1], "0300153"),
        _rule(
            "1505311",
            PrerequisiteLogicStatus.UNRESOLVED,
            course_specs[3][1],
            raw="1505101,1505201",
        ),
        _rule(
            "1505320",
            PrerequisiteLogicStatus.SOURCE_CONFLICT,
            course_specs[4][1],
            raw="0300103,1505311",
        ),
    )
    identities = tuple(
        CourseIdentity(code, CourseCatalogStatus.KNOWN)
        for code, _, _, _ in course_specs
    ) + (CourseIdentity("0300103", CourseCatalogStatus.REFERENCED_ONLY),)
    return AdvisorContext(
        progress_catalog=progress_catalog,
        eligibility_catalog=CanTakeCatalog(PLAN, rules, identities),
        student_attempts=attempts,
        comparison_result=comparison_result,
    )


def _resolved(code: str, name: str) -> CourseResolution:
    return CourseResolution(
        EntityResolutionStatus.RESOLVED,
        ResolvedCourseReference(code, name),
    )


def _request(
    intent: AdvisorIntent,
    *,
    course: CourseResolution | None = None,
    constraints: PlannerConstraints | DegreePathConstraints | None = None,
    options: tuple[int, ...] = (),
) -> NormalizedAdvisorRequest:
    return NormalizedAdvisorRequest(
        user_message="طلب تجريبي",
        intent=intent,
        course_resolution=course,
        planning_constraints=constraints,
        option_references=options,
    )


def test_01_academic_status_routes_to_phase6(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    real = orchestration.calculate_academic_progress

    def spy(*args: object, **kwargs: object) -> AcademicProgress:
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(orchestration, "calculate_academic_progress", spy)
    result = orchestrate_advisor_request(_request(AdvisorIntent.ACADEMIC_STATUS), _context())
    assert calls == 1
    assert isinstance(result.authoritative_payload, AcademicProgress)
    assert result.authority is AnswerAuthority.DETERMINISTIC


def test_02_remaining_requirements_routes_to_phase6(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    real = orchestration.calculate_academic_progress

    def spy(*args: object, **kwargs: object) -> AcademicProgress:
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(orchestration, "calculate_academic_progress", spy)
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.REMAINING_REQUIREMENTS),
        _context(),
    )
    assert calls == 1
    assert result.trace.course_codes == (
        "0300153",
        "1501110",
        "1502000",
        "1505311",
        "1505320",
    )


def test_03_eligible_course_is_deterministic() -> None:
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.COURSE_ELIGIBILITY,
            course=_resolved("0300153", "أساسيات تكنولوجيا المعلومات"),
        ),
        _context(),
    )
    assert result.authority is AnswerAuthority.DETERMINISTIC
    assert isinstance(result.authoritative_payload, CanTakeDecision)
    assert result.authoritative_payload.decision is Decision.ELIGIBLE


def test_04_missing_prerequisite_preserves_not_eligible_evidence() -> None:
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.COURSE_ELIGIBILITY,
            course=_resolved("1501110", "برمجة الحاسوب (1)"),
        ),
        _context(),
    )
    payload = result.authoritative_payload
    assert isinstance(payload, CanTakeDecision)
    assert payload.decision is Decision.NOT_ELIGIBLE
    assert "MISSING_PREREQUISITE_GROUP" in {
        reference.code for reference in result.trace.decision_references
    }


@pytest.mark.parametrize(
    ("code", "name", "status", "reason"),
    [
        ("1505311", "تعلم الالة", "unresolved", "PREREQUISITE_LOGIC_UNRESOLVED"),
        ("1505320", "تعلم الآلة المتقدم", "source_conflict", "PREREQUISITE_SOURCE_CONFLICT"),
    ],
)
def test_05_06_review_required_states_remain_distinct(
    code: str,
    name: str,
    status: str,
    reason: str,
) -> None:
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.COURSE_ELIGIBILITY, course=_resolved(code, name)),
        _context(),
    )
    assert result.authority is AnswerAuthority.REVIEW_REQUIRED
    refs = {reference.code for reference in result.trace.decision_references}
    assert status in refs
    assert reason in refs
    assert "REVIEW_REQUIRED" in refs


def test_07_recommendations_preserve_phase7_ordering() -> None:
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.COURSE_RECOMMENDATIONS),
        _context(),
    )
    payload = result.authoritative_payload
    assert isinstance(payload, RecommendationResult)
    assert tuple(item.rank for item in payload.ranked_recommendations) == tuple(
        range(1, len(payload.ranked_recommendations) + 1)
    )
    assert tuple(item.course_code for item in payload.ranked_recommendations) == (
        "0300153",
        "1502000",
    )


def test_08_recommendations_preserve_reason_codes() -> None:
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.COURSE_RECOMMENDATIONS),
        _context(),
    )
    payload = result.authoritative_payload
    assert isinstance(payload, RecommendationResult)
    upstream = {
        reason.value
        for candidate in payload.ranked_recommendations
        for reason in candidate.reason_codes
    }
    trace_codes = {reference.code for reference in result.trace.decision_references}
    assert upstream.issubset(trace_codes)


def test_09_semester_planner_preserves_selected_course_ordering() -> None:
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.SEMESTER_PLANNING,
            constraints=PlannerConstraints("6", max_courses=2, max_options=3),
        ),
        _context(),
    )
    payload = result.authoritative_payload
    assert isinstance(payload, SemesterPlannerResult)
    assert payload.plan_options
    first_codes = tuple(course.course_code for course in payload.plan_options[0].courses)
    assert first_codes == ("0300153", "1502000")


def test_10_semester_planner_preserves_reason_codes() -> None:
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.SEMESTER_PLANNING,
            constraints=PlannerConstraints("6", max_options=2),
        ),
        _context(),
    )
    payload = result.authoritative_payload
    assert isinstance(payload, SemesterPlannerResult)
    upstream = {reason.value for option in payload.plan_options for reason in option.reason_codes}
    trace_codes = {reference.code for reference in result.trace.decision_references}
    assert upstream.issubset(trace_codes)


def test_11_degree_path_preserves_status_blockers_and_reasons() -> None:
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.DEGREE_PATH_MODELING,
            constraints=DegreePathConstraints("6", max_semesters_ahead=4, max_paths=3),
        ),
        _context(),
    )
    payload = result.authoritative_payload
    assert isinstance(payload, DegreePathResult)
    assert payload.paths
    trace_codes = {reference.code for reference in result.trace.decision_references}
    for path in payload.paths:
        assert path.status.value in trace_codes
        assert set(path.unresolved_blocker_codes).issubset(trace_codes)
        assert {reason.value for reason in path.reason_codes}.issubset(trace_codes)


def test_12_modeled_future_trace_has_phase9_policy_and_source() -> None:
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.DEGREE_PATH_MODELING,
            constraints=DegreePathConstraints("6", max_semesters_ahead=2),
        ),
        _context(),
    )
    assert AuthoritativeSource.PHASE9_DEGREE_PATH in result.trace.authoritative_sources_used
    assert any(
        version.source is AuthoritativeSource.PHASE9_DEGREE_PATH
        and version.version == "1.0"
        for version in result.trace.policy_versions
    )


def test_13_ambiguous_course_returns_clarification_without_engine_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("eligibility engine must not be called")

    monkeypatch.setattr(orchestration, "evaluate_can_take", fail)
    resolution = CourseResolution(
        EntityResolutionStatus.AMBIGUOUS,
        candidate_course_codes=("1505311", "1505320"),
    )
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.COURSE_ELIGIBILITY, course=resolution),
        _context(),
    )
    assert result.intent is AdvisorIntent.CLARIFICATION_REQUIRED
    assert result.authority is AnswerAuthority.INSUFFICIENT_CONTEXT
    assert result.clarification is not None
    assert result.clarification.reason is ClarificationReason.AMBIGUOUS_COURSE


def test_14_not_found_course_returns_insufficient_context() -> None:
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.COURSE_ELIGIBILITY,
            course=CourseResolution(EntityResolutionStatus.NOT_FOUND),
        ),
        _context(),
    )
    assert result.intent is AdvisorIntent.COURSE_ELIGIBILITY
    assert result.authority is AnswerAuthority.INSUFFICIENT_CONTEXT
    assert result.authoritative_payload is None


def test_15_explicit_clarification_intent_returns_contract() -> None:
    clarification = ClarificationRequest(
        ClarificationReason.AMBIGUOUS_INTENT,
        "advisor.clarify.intent",
    )
    request = NormalizedAdvisorRequest(
        "شو بتنصحني أنزل؟",
        AdvisorIntent.CLARIFICATION_REQUIRED,
        clarification_request=clarification,
    )
    result = orchestrate_advisor_request(request, AdvisorContext())
    assert result.clarification is clarification
    assert result.authority is AnswerAuthority.INSUFFICIENT_CONTEXT


def test_16_out_of_scope_returns_structured_non_answer() -> None:
    request = NormalizedAdvisorRequest(
        "سجلني بالمواد",
        AdvisorIntent.OUT_OF_SCOPE,
        out_of_scope_reason=OutOfScopeReason.UNSUPPORTED_CAPABILITY,
    )
    result = orchestrate_advisor_request(request, AdvisorContext())
    assert result.out_of_scope_reason is OutOfScopeReason.UNSUPPORTED_CAPABILITY
    assert result.authoritative_payload is None


def test_17_general_information_has_general_authority_and_no_source() -> None:
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.GENERAL_ACADEMIC_INFORMATION),
        AdvisorContext(),
    )
    assert result.authority is AnswerAuthority.GENERAL_INFORMATION
    assert result.trace.authoritative_sources_used == ()
    assert result.evidence == ()


def test_18_option_comparison_uses_existing_options_without_new_score() -> None:
    recommendation_result = orchestrate_advisor_request(
        _request(AdvisorIntent.COURSE_RECOMMENDATIONS),
        _context(),
    ).authoritative_payload
    assert isinstance(recommendation_result, RecommendationResult)
    context = _context(comparison_result=recommendation_result)
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.OPTION_COMPARISON, options=(2, 1)),
        context,
    )
    payload = result.authoritative_payload
    assert isinstance(payload, tuple)
    assert tuple(option.rank for option in payload) == (1, 2)
    assert all("advisor_score" not in {field.name for field in fields(option)} for option in payload)


def test_19_invalid_option_reference_requires_clarification() -> None:
    recommendation_result = orchestrate_advisor_request(
        _request(AdvisorIntent.COURSE_RECOMMENDATIONS),
        _context(),
    ).authoritative_payload
    assert isinstance(recommendation_result, RecommendationResult)
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.OPTION_COMPARISON, options=(99,)),
        _context(comparison_result=recommendation_result),
    )
    assert result.intent is AdvisorIntent.CLARIFICATION_REQUIRED
    assert result.clarification is not None
    assert result.clarification.reason is ClarificationReason.AMBIGUOUS_OPTION_REFERENCE


def test_20_course_information_uses_catalog_facts_without_parsing_raw_text() -> None:
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.COURSE_INFORMATION,
            course=_resolved("1505320", "تعلم الآلة المتقدم"),
        ),
        _context(),
    )
    payload = result.authoritative_payload
    assert isinstance(payload, CourseInformation)
    assert payload.credit_hours == Decimal("3")
    assert payload.prerequisite_logic_status == "source_conflict"
    assert payload.raw_prerequisite_text == "0300103,1505311"


def test_21_referenced_only_course_information_is_safe() -> None:
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.COURSE_INFORMATION,
            course=_resolved("0300103", "الإحصاء والاحتمالات"),
        ),
        _context(),
    )
    payload = result.authoritative_payload
    assert isinstance(payload, CourseInformation)
    assert payload.catalog_status == "referenced_only"
    assert payload.credit_hours is None


def test_22_trace_and_evidence_ordering_are_deterministic() -> None:
    first = orchestrate_advisor_request(
        _request(
            AdvisorIntent.SEMESTER_PLANNING,
            constraints=PlannerConstraints("6", max_options=3),
        ),
        _context(),
    )
    assert first.trace.authoritative_sources_used == (
        AuthoritativeSource.PHASE7_RECOMMENDATIONS,
        AuthoritativeSource.PHASE8_SEMESTER_PLANNER,
    )
    assert tuple(evidence.source for evidence in first.evidence) == (
        AuthoritativeSource.PHASE7_RECOMMENDATIONS,
        AuthoritativeSource.PHASE8_SEMESTER_PLANNER,
    )


def test_23_identical_input_produces_identical_result() -> None:
    request = _request(
        AdvisorIntent.DEGREE_PATH_MODELING,
        constraints=DegreePathConstraints("6", max_semesters_ahead=3),
    )
    context = _context()
    assert orchestrate_advisor_request(request, context) == orchestrate_advisor_request(
        request,
        context,
    )


def test_24_no_timestamps_or_random_ids_in_orchestration_contract() -> None:
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.ACADEMIC_STATUS),
        _context(),
    )
    serialized = repr(asdict(result)).lower()
    assert "timestamp" not in serialized
    assert "created_at" not in serialized
    assert "uuid" not in serialized


def test_25_no_token_owner_or_state_override_field() -> None:
    names = {field.name for field in fields(NormalizedAdvisorRequest)}
    assert names.isdisjoint(
        {
            "owner",
            "owner_user_id",
            "token",
            "bearer_token",
            "student_attempts",
            "gpa",
            "study_plan_id",
            "eligibility_decision",
            "recommendation_ranks",
            "planner_result",
        }
    )


def test_26_read_only_inputs_remain_unchanged() -> None:
    context = _context()
    request = _request(
        AdvisorIntent.SEMESTER_PLANNING,
        constraints=PlannerConstraints("6", max_options=3),
    )
    before_context = repr(context)
    before_request = repr(request)
    orchestrate_advisor_request(request, context)
    assert repr(context) == before_context
    assert repr(request) == before_request


def test_27_phase5_to_9_domain_inputs_unchanged_after_degree_path() -> None:
    context = _context()
    attempts_before = context.student_attempts
    progress_before = context.progress_catalog
    eligibility_before = context.eligibility_catalog
    orchestrate_advisor_request(
        _request(
            AdvisorIntent.DEGREE_PATH_MODELING,
            constraints=DegreePathConstraints("6", max_semesters_ahead=3),
        ),
        context,
    )
    assert context.student_attempts == attempts_before
    assert context.progress_catalog == progress_before
    assert context.eligibility_catalog == eligibility_before


def test_28_in_progress_does_not_become_passed() -> None:
    attempts = (StudentCourseAttempt("0300153", AttemptOutcome.IN_PROGRESS),)
    context = _context(attempts)
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.COURSE_ELIGIBILITY,
            course=_resolved("1501110", "برمجة الحاسوب (1)"),
        ),
        context,
    )
    payload = result.authoritative_payload
    assert isinstance(payload, CanTakeDecision)
    assert payload.decision is Decision.NOT_ELIGIBLE
    assert context.student_attempts == attempts
    assert context.student_attempts[0].outcome is AttemptOutcome.IN_PROGRESS


def test_29_raw_prerequisite_text_is_not_parsed() -> None:
    result = orchestrate_advisor_request(
        _request(
            AdvisorIntent.COURSE_ELIGIBILITY,
            course=_resolved("1505320", "تعلم الآلة المتقدم"),
        ),
        _context(),
    )
    payload = result.authoritative_payload
    assert isinstance(payload, CanTakeDecision)
    assert payload.decision is Decision.REVIEW_REQUIRED
    assert payload.raw_prerequisite_text == "0300103,1505311"
    assert payload.satisfied_dependency_groups == ()
    assert payload.missing_dependency_groups == ()


@pytest.mark.parametrize(
    "intent",
    [
        AdvisorIntent.ACADEMIC_STATUS,
        AdvisorIntent.COURSE_RECOMMENDATIONS,
        AdvisorIntent.REMAINING_REQUIREMENTS,
    ],
)
def test_30_missing_authoritative_context_does_not_fabricate(intent: AdvisorIntent) -> None:
    result = orchestrate_advisor_request(_request(intent), AdvisorContext())
    assert result.authority is AnswerAuthority.INSUFFICIENT_CONTEXT
    assert result.authoritative_payload is None
    assert result.evidence == ()


def test_31_missing_course_is_structured_clarification() -> None:
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.COURSE_ELIGIBILITY),
        _context(),
    )
    assert result.intent is AdvisorIntent.CLARIFICATION_REQUIRED
    assert result.clarification is not None
    assert result.clarification.reason is ClarificationReason.MISSING_COURSE


def test_32_missing_planning_constraints_is_structured_clarification() -> None:
    # Construct without the Phase 10.2 constraint validator being violated: None
    # is a valid normalized absence and is handled as a normal user-flow result.
    result = orchestrate_advisor_request(
        _request(AdvisorIntent.SEMESTER_PLANNING),
        _context(),
    )
    assert result.intent is AdvisorIntent.CLARIFICATION_REQUIRED
    assert result.clarification is not None
    assert result.clarification.reason is ClarificationReason.MISSING_REQUIRED_CONSTRAINT


def test_33_invalid_normalized_request_raises_domain_contract_error() -> None:
    with pytest.raises(AdvisorContractError):
        NormalizedAdvisorRequest(" ", AdvisorIntent.ACADEMIC_STATUS)


def test_34_advisor_policy_version_is_always_in_trace() -> None:
    requests_and_contexts = (
        (_request(AdvisorIntent.ACADEMIC_STATUS), _context()),
        (_request(AdvisorIntent.GENERAL_ACADEMIC_INFORMATION), AdvisorContext()),
        (
            NormalizedAdvisorRequest(
                "غير مدعوم",
                AdvisorIntent.OUT_OF_SCOPE,
                out_of_scope_reason=OutOfScopeReason.UNSUPPORTED_CAPABILITY,
            ),
            AdvisorContext(),
        ),
    )
    for request, context in requests_and_contexts:
        result = orchestrate_advisor_request(request, context)
        assert any(
            version.source is PolicySource.AI_ADVISOR
            and version.version == AI_ADVISOR_POLICY_VERSION
            for version in result.trace.policy_versions
        )


def test_35_context_rejects_mismatched_catalogs() -> None:
    context = _context()
    assert context.eligibility_catalog is not None
    mismatched = CanTakeCatalog(
        "different-plan",
        context.eligibility_catalog.plan_courses,
        context.eligibility_catalog.courses,
    )
    with pytest.raises(AdvisorContractError, match="share a study plan"):
        AdvisorContext(context.progress_catalog, mismatched)


def test_36_orchestrator_structural_security_boundary() -> None:
    path = Path(orchestration.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    banned_roots = {"fastapi", "starlette", "httpx", "requests", "supabase"}
    banned_app_parts = {
        "api",
        "services",
        "repository",
        "supabase_repository",
        "core",
        "config",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".")[0] for alias in node.names}
            assert roots.isdisjoint(banned_roots), roots
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = set(node.module.split("."))
            assert node.module.split(".")[0] not in banned_roots, node.module
            assert parts.isdisjoint(banned_app_parts), node.module


def test_37_all_phase_engines_are_reused_by_exact_function_name() -> None:
    source = Path(orchestration.__file__).read_text(encoding="utf-8")
    for name in (
        "evaluate_can_take",
        "calculate_academic_progress",
        "recommend_courses",
        "plan_semester",
        "plan_degree_paths",
    ):
        assert f"{name}(" in source

