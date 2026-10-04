"""Pure contract tests for Phase 10.2 advisor domain models."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, asdict, fields
from pathlib import Path

import pytest

from app.advisor import (
    AI_ADVISOR_POLICY_VERSION,
    AdvisorContractError,
    AdvisorEvidence,
    AdvisorIntent,
    AdvisorTrace,
    AnswerAuthority,
    AuthoritativeSource,
    ClarificationReason,
    ClarificationRequest,
    CourseResolution,
    DecisionReference,
    EntityResolutionStatus,
    NormalizedAdvisorRequest,
    OutOfScopeReason,
    PolicyVersionReference,
    ResolvedCourseReference,
    StructuredAdvisorResult,
)
from app.degree_path.models import DegreePathConstraints
from app.planner.models import PlannerConstraints


def _course(code: str = "1501221") -> ResolvedCourseReference:
    return ResolvedCourseReference(
        course_code=code,
        canonical_arabic_name="تراكيب البيانات",
        canonical_english_name="Data Structures",
    )


def _phase5_evidence(*codes: str) -> AdvisorEvidence:
    references = tuple(
        DecisionReference(AuthoritativeSource.PHASE5_ELIGIBILITY, code)
        for code in codes
    )
    return AdvisorEvidence(
        source=AuthoritativeSource.PHASE5_ELIGIBILITY,
        result_reference="CanTakeDecision:1501221",
        course_codes=("1501221",),
        decision_references=references,
    )


def test_01_advisor_intent_exact_members() -> None:
    assert tuple(member.value for member in AdvisorIntent) == (
        "ACADEMIC_STATUS",
        "COURSE_ELIGIBILITY",
        "COURSE_RECOMMENDATIONS",
        "REMAINING_REQUIREMENTS",
        "SEMESTER_PLANNING",
        "DEGREE_PATH_MODELING",
        "OPTION_COMPARISON",
        "COURSE_INFORMATION",
        "GENERAL_ACADEMIC_INFORMATION",
        "GENERAL_CHAT",
        "CLARIFICATION_REQUIRED",
        "OUT_OF_SCOPE",
    )


def test_02_answer_authority_exact_members() -> None:
    assert tuple(member.value for member in AnswerAuthority) == (
        "DETERMINISTIC",
        "REVIEW_REQUIRED",
        "GENERAL_INFORMATION",
        "INSUFFICIENT_CONTEXT",
    )


def test_03_authoritative_source_exact_members() -> None:
    assert tuple(member.value for member in AuthoritativeSource) == (
        "ACADEMIC_CATALOG",
        "STUDENT_ACADEMIC_STATE",
        "PHASE5_ELIGIBILITY",
        "PHASE6_PROGRESS",
        "PHASE7_RECOMMENDATIONS",
        "PHASE8_SEMESTER_PLANNER",
        "PHASE9_DEGREE_PATH",
    )


def test_04_policy_version() -> None:
    assert AI_ADVISOR_POLICY_VERSION == "1.0"


def test_05_valid_resolved_course_reference() -> None:
    course = _course()
    assert course.course_code == "1501221"
    assert course.canonical_arabic_name == "تراكيب البيانات"


@pytest.mark.parametrize("code", ["", "   ", " 1501221"])
def test_06_empty_or_uncanonical_course_code_rejected(code: str) -> None:
    with pytest.raises(AdvisorContractError):
        ResolvedCourseReference(code, "تراكيب البيانات")


def test_07_ambiguous_resolution_is_explicit_and_sorted() -> None:
    resolution = CourseResolution(
        EntityResolutionStatus.AMBIGUOUS,
        candidate_course_codes=("1505320", "1505311", "1505320"),
    )
    assert resolution.resolved_course is None
    assert resolution.candidate_course_codes == ("1505311", "1505320")


def test_08_not_found_resolution_is_explicit() -> None:
    resolution = CourseResolution(EntityResolutionStatus.NOT_FOUND)
    assert resolution.resolved_course is None
    assert resolution.candidate_course_codes == ()


def test_09_resolved_status_requires_course() -> None:
    with pytest.raises(AdvisorContractError, match="requires resolved_course"):
        CourseResolution(EntityResolutionStatus.RESOLVED)


def test_10_deterministic_trace_ordering_and_duplicate_sources() -> None:
    trace = AdvisorTrace(
        advisor_intent=AdvisorIntent.COURSE_ELIGIBILITY,
        answer_authority=AnswerAuthority.DETERMINISTIC,
        authoritative_sources_used=(
            AuthoritativeSource.PHASE6_PROGRESS,
            AuthoritativeSource.PHASE5_ELIGIBILITY,
            AuthoritativeSource.PHASE6_PROGRESS,
            AuthoritativeSource.ACADEMIC_CATALOG,
        ),
        course_codes=("1505320", "1501221", "1505320"),
        decision_references=(
            DecisionReference(AuthoritativeSource.PHASE5_ELIGIBILITY, "PREREQUISITES_SATISFIED"),
            DecisionReference(AuthoritativeSource.PHASE5_ELIGIBILITY, "ELIGIBLE"),
            DecisionReference(AuthoritativeSource.PHASE5_ELIGIBILITY, "ELIGIBLE"),
        ),
    )
    assert trace.authoritative_sources_used == (
        AuthoritativeSource.ACADEMIC_CATALOG,
        AuthoritativeSource.PHASE5_ELIGIBILITY,
        AuthoritativeSource.PHASE6_PROGRESS,
    )
    assert trace.course_codes == ("1501221", "1505320")
    assert tuple(item.code for item in trace.decision_references) == (
        "ELIGIBLE",
        "PREREQUISITES_SATISFIED",
    )


def test_11_decision_reference_preserves_exact_upstream_value() -> None:
    reference = DecisionReference(
        AuthoritativeSource.PHASE5_ELIGIBILITY,
        "PREREQUISITE_SOURCE_CONFLICT",
    )
    assert reference.code == "PREREQUISITE_SOURCE_CONFLICT"


def test_12_source_specific_lowercase_status_is_not_reinterpreted() -> None:
    reference = DecisionReference(
        AuthoritativeSource.PHASE5_ELIGIBILITY,
        "source_conflict",
    )
    assert reference.code == "source_conflict"


def test_13_review_required_representation_retains_evidence() -> None:
    evidence = _phase5_evidence("REVIEW_REQUIRED", "PREREQUISITE_SOURCE_CONFLICT")
    trace = AdvisorTrace(
        AdvisorIntent.COURSE_ELIGIBILITY,
        AnswerAuthority.REVIEW_REQUIRED,
        authoritative_sources_used=(AuthoritativeSource.PHASE5_ELIGIBILITY,),
        course_codes=("1501221",),
        decision_references=evidence.decision_references,
    )
    result = StructuredAdvisorResult(
        intent=AdvisorIntent.COURSE_ELIGIBILITY,
        authority=AnswerAuthority.REVIEW_REQUIRED,
        trace=trace,
        course_resolution=CourseResolution(
            EntityResolutionStatus.RESOLVED,
            resolved_course=_course(),
        ),
        evidence=(evidence,),
    )
    assert result.authority is AnswerAuthority.REVIEW_REQUIRED
    assert tuple(item.code for item in result.evidence[0].decision_references) == (
        "PREREQUISITE_SOURCE_CONFLICT",
        "REVIEW_REQUIRED",
    )


def test_14_review_required_without_decision_evidence_rejected() -> None:
    evidence = _phase5_evidence()
    trace = AdvisorTrace(
        AdvisorIntent.COURSE_ELIGIBILITY,
        AnswerAuthority.REVIEW_REQUIRED,
        authoritative_sources_used=(AuthoritativeSource.PHASE5_ELIGIBILITY,),
    )
    with pytest.raises(AdvisorContractError, match="decision references"):
        StructuredAdvisorResult(
            AdvisorIntent.COURSE_ELIGIBILITY,
            AnswerAuthority.REVIEW_REQUIRED,
            trace,
            evidence=(evidence,),
        )


def test_15_insufficient_context_clarification_representation() -> None:
    clarification = ClarificationRequest(
        ClarificationReason.AMBIGUOUS_COURSE,
        "advisor.clarify.course",
        ("1505320", "1505311"),
    )
    trace = AdvisorTrace(
        AdvisorIntent.CLARIFICATION_REQUIRED,
        AnswerAuthority.INSUFFICIENT_CONTEXT,
    )
    result = StructuredAdvisorResult(
        AdvisorIntent.CLARIFICATION_REQUIRED,
        AnswerAuthority.INSUFFICIENT_CONTEXT,
        trace,
        course_resolution=CourseResolution(
            EntityResolutionStatus.AMBIGUOUS,
            candidate_course_codes=("1505311", "1505320"),
        ),
        clarification=clarification,
    )
    assert result.clarification is clarification


def test_16_clarification_candidate_codes_are_deterministic() -> None:
    clarification = ClarificationRequest(
        ClarificationReason.AMBIGUOUS_COURSE,
        "advisor.clarify.course",
        ("B", "A", "B"),
    )
    assert clarification.candidate_course_codes == ("A", "B")


def test_17_clarification_intent_requires_contract() -> None:
    trace = AdvisorTrace(
        AdvisorIntent.CLARIFICATION_REQUIRED,
        AnswerAuthority.INSUFFICIENT_CONTEXT,
    )
    with pytest.raises(AdvisorContractError, match="requires a clarification"):
        StructuredAdvisorResult(
            AdvisorIntent.CLARIFICATION_REQUIRED,
            AnswerAuthority.INSUFFICIENT_CONTEXT,
            trace,
        )


def test_18_general_information_has_no_deterministic_evidence() -> None:
    trace = AdvisorTrace(
        AdvisorIntent.GENERAL_ACADEMIC_INFORMATION,
        AnswerAuthority.GENERAL_INFORMATION,
    )
    result = StructuredAdvisorResult(
        AdvisorIntent.GENERAL_ACADEMIC_INFORMATION,
        AnswerAuthority.GENERAL_INFORMATION,
        trace,
    )
    assert result.evidence == ()
    assert result.trace.authoritative_sources_used == ()


def test_19_general_information_cannot_claim_sources() -> None:
    with pytest.raises(AdvisorContractError, match="GENERAL_INFORMATION"):
        AdvisorTrace(
            AdvisorIntent.GENERAL_ACADEMIC_INFORMATION,
            AnswerAuthority.GENERAL_INFORMATION,
            authoritative_sources_used=(AuthoritativeSource.PHASE6_PROGRESS,),
        )


def test_20_out_of_scope_representation() -> None:
    trace = AdvisorTrace(
        AdvisorIntent.OUT_OF_SCOPE,
        AnswerAuthority.INSUFFICIENT_CONTEXT,
    )
    result = StructuredAdvisorResult(
        AdvisorIntent.OUT_OF_SCOPE,
        AnswerAuthority.INSUFFICIENT_CONTEXT,
        trace,
        out_of_scope_reason=OutOfScopeReason.REQUIRES_OFFICIAL_AUTHORITY,
    )
    assert result.out_of_scope_reason is OutOfScopeReason.REQUIRES_OFFICIAL_AUTHORITY


def test_21_normalized_request_reuses_phase8_constraints() -> None:
    constraints = PlannerConstraints(max_credit_hours="15", max_courses=5)
    request = NormalizedAdvisorRequest(
        "شو بتنصحني أنزل؟",
        AdvisorIntent.SEMESTER_PLANNING,
        planning_constraints=constraints,
    )
    assert request.planning_constraints is constraints


def test_22_normalized_request_reuses_phase9_constraints() -> None:
    constraints = DegreePathConstraints(max_credit_hours_per_semester="15")
    request = NormalizedAdvisorRequest(
        "اعمللي خطة للمواد لحد ما أخلص",
        AdvisorIntent.DEGREE_PATH_MODELING,
        planning_constraints=constraints,
    )
    assert request.planning_constraints is constraints


def test_23_wrong_constraint_contract_rejected() -> None:
    with pytest.raises(AdvisorContractError, match="SEMESTER_PLANNING"):
        NormalizedAdvisorRequest(
            "هل أقدر آخذ المادة؟",
            AdvisorIntent.COURSE_ELIGIBILITY,
            planning_constraints=PlannerConstraints(max_credit_hours="15"),
        )


def test_24_policy_versions_are_sorted_and_tied_to_sources() -> None:
    trace = AdvisorTrace(
        AdvisorIntent.DEGREE_PATH_MODELING,
        AnswerAuthority.DETERMINISTIC,
        authoritative_sources_used=(
            AuthoritativeSource.PHASE9_DEGREE_PATH,
            AuthoritativeSource.PHASE8_SEMESTER_PLANNER,
        ),
        policy_versions=(
            PolicyVersionReference(AuthoritativeSource.PHASE9_DEGREE_PATH, "1.0"),
            PolicyVersionReference(AuthoritativeSource.PHASE8_SEMESTER_PLANNER, "1.0"),
        ),
    )
    assert tuple(item.source for item in trace.policy_versions) == (
        AuthoritativeSource.PHASE8_SEMESTER_PLANNER,
        AuthoritativeSource.PHASE9_DEGREE_PATH,
    )


def test_25_models_are_immutable() -> None:
    course = _course()
    with pytest.raises(FrozenInstanceError):
        course.course_code = "CHANGED"  # type: ignore[misc]


def test_26_identical_construction_serializes_stably() -> None:
    first = CourseResolution(
        EntityResolutionStatus.AMBIGUOUS,
        candidate_course_codes=("B", "A"),
    )
    second = CourseResolution(
        EntityResolutionStatus.AMBIGUOUS,
        candidate_course_codes=("A", "B", "A"),
    )
    assert asdict(first) == asdict(second)


def test_27_no_numeric_confidence_field() -> None:
    domain_models = (
        ResolvedCourseReference,
        CourseResolution,
        DecisionReference,
        PolicyVersionReference,
        AdvisorEvidence,
        ClarificationRequest,
        AdvisorTrace,
        NormalizedAdvisorRequest,
        StructuredAdvisorResult,
    )
    all_names = {field.name for model in domain_models for field in fields(model)}
    assert "confidence" not in all_names
    assert "confidence_score" not in all_names
    assert "confidence_percentage" not in all_names


def test_28_no_auth_owner_or_state_override_fields() -> None:
    request_fields = {field.name for field in fields(NormalizedAdvisorRequest)}
    forbidden = {
        "owner",
        "owner_user_id",
        "bearer_token",
        "supabase_token",
        "student_attempts",
        "gpa",
        "study_plan_id",
    }
    assert request_fields.isdisjoint(forbidden)


def test_29_evidence_has_no_arbitrary_blob_field() -> None:
    evidence_fields = {field.name for field in fields(AdvisorEvidence)}
    assert evidence_fields == {
        "source",
        "result_reference",
        "course_codes",
        "decision_references",
        "policy_version",
    }
    assert evidence_fields.isdisjoint({"payload", "data", "metadata", "raw", "blob"})


def test_30_evidence_decision_source_must_match() -> None:
    with pytest.raises(AdvisorContractError, match="must use the evidence source"):
        AdvisorEvidence(
            AuthoritativeSource.PHASE5_ELIGIBILITY,
            "CanTakeDecision:1501221",
            decision_references=(
                DecisionReference(AuthoritativeSource.PHASE9_DEGREE_PATH, "HORIZON_REACHED"),
            ),
        )


def test_31_deterministic_result_requires_evidence() -> None:
    trace = AdvisorTrace(
        AdvisorIntent.ACADEMIC_STATUS,
        AnswerAuthority.DETERMINISTIC,
        authoritative_sources_used=(AuthoritativeSource.PHASE6_PROGRESS,),
    )
    with pytest.raises(AdvisorContractError, match="requires authoritative evidence"):
        StructuredAdvisorResult(
            AdvisorIntent.ACADEMIC_STATUS,
            AnswerAuthority.DETERMINISTIC,
            trace,
        )


def test_32_trace_and_result_must_agree() -> None:
    trace = AdvisorTrace(
        AdvisorIntent.ACADEMIC_STATUS,
        AnswerAuthority.INSUFFICIENT_CONTEXT,
    )
    with pytest.raises(AdvisorContractError, match="trace intent"):
        StructuredAdvisorResult(
            AdvisorIntent.REMAINING_REQUIREMENTS,
            AnswerAuthority.INSUFFICIENT_CONTEXT,
            trace,
        )


def test_33_structural_import_boundary() -> None:
    advisor_dir = Path(__file__).parents[1] / "app" / "advisor"
    banned_roots = {
        "fastapi",
        "starlette",
        "httpx",
        "requests",
        "supabase",
    }
    banned_app_parts = {"api", "services", "repository", "supabase_repository", "core"}

    for path in sorted(advisor_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
                assert roots.isdisjoint(banned_roots), (path.name, roots)
            elif isinstance(node, ast.ImportFrom) and node.module:
                parts = set(node.module.split("."))
                assert node.module.split(".")[0] not in banned_roots, (path.name, node.module)
                assert parts.isdisjoint(banned_app_parts), (path.name, node.module)

