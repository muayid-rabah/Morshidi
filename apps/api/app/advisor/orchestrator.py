"""Pure, read-only deterministic orchestration for the Morshidi advisor.

All authoritative data is injected in memory. This module performs no I/O,
contains no provider integration, and delegates every academic decision to the
existing Phase 5-9 engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from decimal import Decimal

from app.advisor.models import (
    AI_ADVISOR_POLICY_VERSION,
    AdvisorContractError,
    AdvisorEvidence,
    AdvisorIntent,
    AdvisorPayload,
    AdvisorTrace,
    AnswerAuthority,
    AuthoritativeSource,
    ClarificationReason,
    ClarificationRequest,
    CourseInformation,
    CourseResolution,
    DecisionReference,
    EntityResolutionStatus,
    NormalizedAdvisorRequest,
    OutOfScopeReason,
    PolicySource,
    PolicyVersionReference,
    ResolvedCourseReference,
    StructuredAdvisorResult,
)
from app.degree_path.engine import plan_degree_paths
from app.degree_path.models import (
    DegreePathConstraints,
    DegreePathOption,
    DegreePathResult,
    PathStatus,
)
from app.planner.engine import plan_semester
from app.planner.models import PlannerConstraints, SemesterPlanOption, SemesterPlannerResult
from app.progress.engine import calculate_academic_progress
from app.progress.models import AcademicProgress, AcademicProgressCatalog, CourseProgressState
from app.recommendations.engine import recommend_courses
from app.recommendations.models import (
    RecommendationCandidate,
    RecommendationResult,
)
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    CanTakeCatalog,
    CanTakeDecision,
    CanTakeError,
    CanTakeRequest,
    Decision,
    StudentCourseAttempt,
)


ComparisonResult = RecommendationResult | SemesterPlannerResult | DegreePathResult


@dataclass(frozen=True)
class AdvisorContext:
    """Preloaded authoritative inputs for one read-only orchestration call."""

    progress_catalog: AcademicProgressCatalog | None = None
    eligibility_catalog: CanTakeCatalog | None = None
    student_attempts: tuple[StudentCourseAttempt, ...] = ()
    reported_cumulative_gpa: Decimal | None = None
    reported_gpa_scale: Decimal | None = None
    reported_earned_credit_hours: Decimal | None = None
    comparison_result: ComparisonResult | None = None
    check_budget: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        if self.progress_catalog is not None and self.eligibility_catalog is not None:
            if (
                self.progress_catalog.study_plan.study_plan_id
                != self.eligibility_catalog.study_plan_id
            ):
                raise AdvisorContractError(
                    "AdvisorContext progress and eligibility catalogs must share a study plan"
                )
        if self.comparison_result is not None:
            context_plan_id = _context_study_plan_id(self)
            if context_plan_id is not None and self.comparison_result.study_plan_id != context_plan_id:
                raise AdvisorContractError(
                    "comparison_result must belong to the AdvisorContext study plan"
                )


def orchestrate_advisor_request(
    request: NormalizedAdvisorRequest,
    context: AdvisorContext,
) -> StructuredAdvisorResult:
    """Route a normalized request to preloaded Phase 5-9 academic inputs.

    The function is deterministic and read-only. It never fetches, persists, or
    mutates academic state and never generates natural-language advisor text.
    """

    if request.intent is AdvisorIntent.ACADEMIC_STATUS:
        return _progress_result(request, context)
    if request.intent is AdvisorIntent.COURSE_ELIGIBILITY:
        return _eligibility_result(request, context)
    if request.intent is AdvisorIntent.COURSE_RECOMMENDATIONS:
        return _recommendation_result(request, context)
    if request.intent is AdvisorIntent.REMAINING_REQUIREMENTS:
        return _progress_result(request, context, remaining_only=True)
    if request.intent is AdvisorIntent.SEMESTER_PLANNING:
        return _semester_result(request, context)
    if request.intent is AdvisorIntent.DEGREE_PATH_MODELING:
        return _degree_path_result(request, context)
    if request.intent is AdvisorIntent.OPTION_COMPARISON:
        return _option_comparison_result(request, context)
    if request.intent is AdvisorIntent.COURSE_INFORMATION:
        return _course_information_result(request, context)
    if request.intent in (AdvisorIntent.GENERAL_CHAT, AdvisorIntent.GENERAL_ACADEMIC_INFORMATION):
        return _general_information_result(request)
    if request.intent is AdvisorIntent.CLARIFICATION_REQUIRED:
        assert request.clarification_request is not None
        return _clarification_result(
            request.clarification_request,
            request.course_resolution,
        )
    if request.intent is AdvisorIntent.OUT_OF_SCOPE:
        assert request.out_of_scope_reason is not None
        return _out_of_scope_result(request.out_of_scope_reason)
    raise AdvisorContractError(f"Unsupported advisor intent: {request.intent!r}")


def _progress_result(
    request: NormalizedAdvisorRequest,
    context: AdvisorContext,
    *,
    remaining_only: bool = False,
) -> StructuredAdvisorResult:
    if context.progress_catalog is None:
        return _insufficient_result(request.intent, "progress-context-unavailable")
    progress = calculate_academic_progress(
        context.progress_catalog,
        context.student_attempts,
        reported_cumulative_gpa=context.reported_cumulative_gpa,
        reported_gpa_scale=context.reported_gpa_scale,
        reported_earned_credit_hours=context.reported_earned_credit_hours,
    )
    course_codes = ()
    if remaining_only:
        course_codes = tuple(
            course.course_code
            for course in progress.courses
            if course.state is not CourseProgressState.COMPLETED
        )
    evidence = AdvisorEvidence(
        source=AuthoritativeSource.PHASE6_PROGRESS,
        result_reference="AcademicProgress:remaining" if remaining_only else "AcademicProgress:status",
        course_codes=course_codes,
    )
    return _build_result(
        intent=request.intent,
        authority=AnswerAuthority.DETERMINISTIC,
        evidence=(evidence,),
        payload=progress,
    )


def _eligibility_result(
    request: NormalizedAdvisorRequest,
    context: AdvisorContext,
) -> StructuredAdvisorResult:
    course, early_result = _require_resolved_course(request)
    if early_result is not None:
        return early_result
    assert course is not None
    if context.eligibility_catalog is None:
        return _insufficient_result(
            request.intent,
            "eligibility-context-unavailable",
            request.course_resolution,
        )

    outcome = evaluate_can_take(
        context.eligibility_catalog,
        CanTakeRequest(
            study_plan_id=context.eligibility_catalog.study_plan_id,
            target_course_code=course.course_code,
            student_attempts=context.student_attempts,
        ),
    )
    if isinstance(outcome, CanTakeError):
        references = (
            DecisionReference(
                AuthoritativeSource.PHASE5_ELIGIBILITY,
                outcome.error_code.value,
            ),
        )
        evidence = AdvisorEvidence(
            AuthoritativeSource.PHASE5_ELIGIBILITY,
            f"CanTakeError:{course.course_code}",
            (course.course_code,),
            references,
        )
        return _build_result(
            intent=request.intent,
            authority=AnswerAuthority.INSUFFICIENT_CONTEXT,
            evidence=(evidence,),
            payload=outcome,
            course_resolution=request.course_resolution,
        )

    references = _eligibility_references(outcome)
    evidence = AdvisorEvidence(
        AuthoritativeSource.PHASE5_ELIGIBILITY,
        f"CanTakeDecision:{course.course_code}",
        (course.course_code,),
        references,
    )
    authority = (
        AnswerAuthority.REVIEW_REQUIRED
        if outcome.decision is Decision.REVIEW_REQUIRED
        else AnswerAuthority.DETERMINISTIC
    )
    return _build_result(
        intent=request.intent,
        authority=authority,
        evidence=(evidence,),
        payload=outcome,
        course_resolution=request.course_resolution,
    )


def _recommendation_result(
    request: NormalizedAdvisorRequest,
    context: AdvisorContext,
) -> StructuredAdvisorResult:
    missing = _require_planning_catalogs(request.intent, context)
    if missing is not None:
        return missing
    recommendations = _calculate_recommendations(context)
    evidence = _recommendation_evidence(recommendations)
    authority = (
        AnswerAuthority.REVIEW_REQUIRED
        if not recommendations.ranked_recommendations
        and bool(recommendations.review_required_courses)
        else AnswerAuthority.DETERMINISTIC
    )
    return _build_result(
        intent=request.intent,
        authority=authority,
        evidence=(evidence,),
        payload=recommendations,
        upstream_versions=(
            PolicyVersionReference(
                AuthoritativeSource.PHASE7_RECOMMENDATIONS,
                recommendations.recommendation_policy_version,
            ),
        ),
    )


def _semester_result(
    request: NormalizedAdvisorRequest,
    context: AdvisorContext,
) -> StructuredAdvisorResult:
    if not isinstance(request.planning_constraints, PlannerConstraints):
        return _clarification_result(
            ClarificationRequest(
                ClarificationReason.MISSING_REQUIRED_CONSTRAINT,
                "advisor.clarify.semester_constraints",
            )
        )
    missing = _require_planning_catalogs(request.intent, context)
    if missing is not None:
        return missing

    recommendations = _calculate_recommendations(context)
    assert context.progress_catalog is not None
    assert context.eligibility_catalog is not None
    planner_result = plan_semester(
        context.progress_catalog,
        context.eligibility_catalog,
        context.student_attempts,
        recommendations,
        request.planning_constraints,
        reported_cumulative_gpa=context.reported_cumulative_gpa,
        reported_gpa_scale=context.reported_gpa_scale,
        reported_earned_credit_hours=context.reported_earned_credit_hours,
        **({"check_budget": context.check_budget} if context.check_budget is not None else {}),
    )
    recommendation_evidence = _recommendation_evidence(recommendations)
    planner_evidence = _semester_evidence(planner_result)
    authority = (
        AnswerAuthority.REVIEW_REQUIRED
        if not planner_result.plan_options and bool(planner_result.review_required_courses)
        else AnswerAuthority.DETERMINISTIC
    )
    return _build_result(
        intent=request.intent,
        authority=authority,
        evidence=(recommendation_evidence, planner_evidence),
        payload=planner_result,
        planning_constraints=request.planning_constraints,
        upstream_versions=(
            PolicyVersionReference(
                AuthoritativeSource.PHASE7_RECOMMENDATIONS,
                recommendations.recommendation_policy_version,
            ),
            PolicyVersionReference(
                AuthoritativeSource.PHASE8_SEMESTER_PLANNER,
                planner_result.semester_planner_policy_version,
            ),
        ),
    )


def _degree_path_result(
    request: NormalizedAdvisorRequest,
    context: AdvisorContext,
) -> StructuredAdvisorResult:
    if not isinstance(request.planning_constraints, DegreePathConstraints):
        return _clarification_result(
            ClarificationRequest(
                ClarificationReason.MISSING_REQUIRED_CONSTRAINT,
                "advisor.clarify.degree_path_constraints",
            )
        )
    missing = _require_planning_catalogs(request.intent, context)
    if missing is not None:
        return missing
    assert context.progress_catalog is not None
    assert context.eligibility_catalog is not None
    result = plan_degree_paths(
        context.progress_catalog,
        context.eligibility_catalog,
        context.student_attempts,
        request.planning_constraints,
        reported_cumulative_gpa=context.reported_cumulative_gpa,
        reported_gpa_scale=context.reported_gpa_scale,
        reported_earned_credit_hours=context.reported_earned_credit_hours,
        **({"check_budget": context.check_budget} if context.check_budget is not None else {}),
    )
    evidence: list[AdvisorEvidence] = [_degree_path_evidence(result)]
    catalog_review_evidence = _review_status_evidence(result, context.eligibility_catalog)
    if catalog_review_evidence is not None:
        evidence.append(catalog_review_evidence)
    authority = (
        AnswerAuthority.REVIEW_REQUIRED
        if (
            result.paths
            and all(path.status is PathStatus.BLOCKED_BY_REVIEW_REQUIRED for path in result.paths)
        )
        or (not result.paths and bool(result.unresolved_review_required_courses))
        else AnswerAuthority.DETERMINISTIC
    )
    return _build_result(
        intent=request.intent,
        authority=authority,
        evidence=tuple(evidence),
        payload=result,
        planning_constraints=request.planning_constraints,
        upstream_versions=(
            PolicyVersionReference(
                AuthoritativeSource.PHASE9_DEGREE_PATH,
                result.degree_path_policy_version,
            ),
        ),
    )


def _option_comparison_result(
    request: NormalizedAdvisorRequest,
    context: AdvisorContext,
) -> StructuredAdvisorResult:
    if not request.option_references or context.comparison_result is None:
        return _clarification_result(
            ClarificationRequest(
                ClarificationReason.AMBIGUOUS_OPTION_REFERENCE,
                "advisor.clarify.option_reference",
            )
        )

    result = context.comparison_result
    if isinstance(result, RecommendationResult):
        options: tuple[RecommendationCandidate | SemesterPlanOption | DegreePathOption, ...] = (
            result.ranked_recommendations
        )
        evidence = _recommendation_evidence(result, selected_ranks=request.option_references)
        version = PolicyVersionReference(
            AuthoritativeSource.PHASE7_RECOMMENDATIONS,
            result.recommendation_policy_version,
        )
    elif isinstance(result, SemesterPlannerResult):
        options = result.plan_options
        evidence = _semester_evidence(result, selected_ranks=request.option_references)
        version = PolicyVersionReference(
            AuthoritativeSource.PHASE8_SEMESTER_PLANNER,
            result.semester_planner_policy_version,
        )
    else:
        options = result.paths
        evidence = _degree_path_evidence(result, selected_ranks=request.option_references)
        version = PolicyVersionReference(
            AuthoritativeSource.PHASE9_DEGREE_PATH,
            result.degree_path_policy_version,
        )

    options_by_rank = {option.rank: option for option in options}
    if any(rank not in options_by_rank for rank in request.option_references):
        return _clarification_result(
            ClarificationRequest(
                ClarificationReason.AMBIGUOUS_OPTION_REFERENCE,
                "advisor.clarify.option_reference",
            )
        )
    selected = tuple(options_by_rank[rank] for rank in request.option_references)
    return _build_result(
        intent=request.intent,
        authority=AnswerAuthority.DETERMINISTIC,
        evidence=(evidence,),
        payload=selected,
        option_references=request.option_references,
        upstream_versions=(version,),
    )


def _course_information_result(
    request: NormalizedAdvisorRequest,
    context: AdvisorContext,
) -> StructuredAdvisorResult:
    course, early_result = _require_resolved_course(request)
    if early_result is not None:
        return early_result
    assert course is not None
    if context.progress_catalog is None and context.eligibility_catalog is None:
        return _insufficient_result(
            request.intent,
            "catalog-context-unavailable",
            request.course_resolution,
        )

    plan_course = next(
        (
            item
            for item in (context.progress_catalog.plan_courses if context.progress_catalog else ())
            if item.course_code == course.course_code
        ),
        None,
    )
    group = next(
        (
            item
            for item in (context.progress_catalog.requirement_groups if context.progress_catalog else ())
            if plan_course is not None and item.group_id == plan_course.requirement_group_id
        ),
        None,
    )
    rule = next(
        (
            item
            for item in (context.eligibility_catalog.plan_courses if context.eligibility_catalog else ())
            if item.course_code == course.course_code
        ),
        None,
    )
    identity = next(
        (
            item
            for item in (context.eligibility_catalog.courses if context.eligibility_catalog else ())
            if item.course_code == course.course_code
        ),
        None,
    )
    information = CourseInformation(
        course_code=course.course_code,
        canonical_arabic_name=course.canonical_arabic_name,
        canonical_english_name=course.canonical_english_name,
        credit_hours=plan_course.credit_hours if plan_course else None,
        requirement_group_code=group.group_code if group else None,
        catalog_status=identity.catalog_status.value if identity else None,
        prerequisite_logic_status=rule.prerequisite_logic_status.value if rule else None,
        raw_prerequisite_text=rule.raw_prerequisite_text if rule else None,
    )
    references = ()
    if information.prerequisite_logic_status is not None:
        references = (
            DecisionReference(
                AuthoritativeSource.ACADEMIC_CATALOG,
                information.prerequisite_logic_status,
            ),
        )
    evidence = AdvisorEvidence(
        AuthoritativeSource.ACADEMIC_CATALOG,
        f"CourseInformation:{course.course_code}",
        (course.course_code,),
        references,
    )
    return _build_result(
        intent=request.intent,
        authority=AnswerAuthority.DETERMINISTIC,
        evidence=(evidence,),
        payload=information,
        course_resolution=request.course_resolution,
    )


def _general_information_result(request: NormalizedAdvisorRequest) -> StructuredAdvisorResult:
    return _build_result(
        intent=request.intent,
        authority=AnswerAuthority.GENERAL_INFORMATION,
        evidence=(),
        payload=None,
    )


def _require_resolved_course(
    request: NormalizedAdvisorRequest,
) -> tuple[ResolvedCourseReference | None, StructuredAdvisorResult | None]:
    resolution = request.course_resolution
    if resolution is None:
        return None, _clarification_result(
            ClarificationRequest(
                ClarificationReason.MISSING_COURSE,
                "advisor.clarify.missing_course",
            )
        )
    if resolution.status is EntityResolutionStatus.AMBIGUOUS:
        return None, _clarification_result(
            ClarificationRequest(
                ClarificationReason.AMBIGUOUS_COURSE,
                "advisor.clarify.ambiguous_course",
                resolution.candidate_course_codes,
            ),
            resolution,
            catalog_resolution=True,
        )
    if resolution.status is EntityResolutionStatus.NOT_FOUND:
        evidence = AdvisorEvidence(
            AuthoritativeSource.ACADEMIC_CATALOG,
            "CourseResolution:NOT_FOUND",
        )
        return None, _build_result(
            intent=request.intent,
            authority=AnswerAuthority.INSUFFICIENT_CONTEXT,
            evidence=(evidence,),
            payload=None,
            course_resolution=resolution,
        )
    assert resolution.resolved_course is not None
    return resolution.resolved_course, None


def _require_planning_catalogs(
    intent: AdvisorIntent,
    context: AdvisorContext,
) -> StructuredAdvisorResult | None:
    if context.progress_catalog is None or context.eligibility_catalog is None:
        return _insufficient_result(intent, "planning-context-unavailable")
    return None


def _calculate_recommendations(context: AdvisorContext) -> RecommendationResult:
    assert context.progress_catalog is not None
    assert context.eligibility_catalog is not None
    return recommend_courses(
        context.progress_catalog,
        context.eligibility_catalog,
        context.student_attempts,
        reported_cumulative_gpa=context.reported_cumulative_gpa,
        reported_gpa_scale=context.reported_gpa_scale,
        reported_earned_credit_hours=context.reported_earned_credit_hours,
    )


def _eligibility_references(result: CanTakeDecision) -> tuple[DecisionReference, ...]:
    codes = (
        result.decision.value,
        result.prerequisite_logic_status.value,
        *(reason.value for reason in result.reasons),
        *(reason.value for reason in result.review_reasons),
    )
    return tuple(
        DecisionReference(AuthoritativeSource.PHASE5_ELIGIBILITY, code)
        for code in codes
    )


def _recommendation_evidence(
    result: RecommendationResult,
    *,
    selected_ranks: tuple[int, ...] | None = None,
) -> AdvisorEvidence:
    selected = result.ranked_recommendations
    if selected_ranks is not None:
        ranks = set(selected_ranks)
        selected = tuple(item for item in selected if item.rank in ranks)
    codes = tuple(item.course_code for item in selected) + tuple(
        item.course_code for item in result.review_required_courses
    ) + result.excluded_in_progress
    reason_codes = tuple(
        reason.value for item in selected for reason in item.reason_codes
    ) + tuple(item.review_reason for item in result.review_required_courses)
    references = tuple(
        DecisionReference(AuthoritativeSource.PHASE7_RECOMMENDATIONS, code)
        for code in reason_codes
    )
    return AdvisorEvidence(
        AuthoritativeSource.PHASE7_RECOMMENDATIONS,
        "RecommendationResult",
        codes,
        references,
        result.recommendation_policy_version,
    )


def _semester_evidence(
    result: SemesterPlannerResult,
    *,
    selected_ranks: tuple[int, ...] | None = None,
) -> AdvisorEvidence:
    selected = result.plan_options
    if selected_ranks is not None:
        ranks = set(selected_ranks)
        selected = tuple(item for item in selected if item.rank in ranks)
    codes = tuple(
        course.course_code for option in selected for course in option.courses
    ) + result.review_required_courses + result.excluded_in_progress
    references = tuple(
        DecisionReference(AuthoritativeSource.PHASE8_SEMESTER_PLANNER, reason.value)
        for option in selected
        for reason in option.reason_codes
    )
    return AdvisorEvidence(
        AuthoritativeSource.PHASE8_SEMESTER_PLANNER,
        "SemesterPlannerResult",
        codes,
        references,
        result.semester_planner_policy_version,
    )


def _degree_path_evidence(
    result: DegreePathResult,
    *,
    selected_ranks: tuple[int, ...] | None = None,
) -> AdvisorEvidence:
    selected = result.paths
    if selected_ranks is not None:
        ranks = set(selected_ranks)
        selected = tuple(item for item in selected if item.rank in ranks)
    codes = tuple(
        course.course_code
        for path in selected
        for semester in path.semesters
        for course in semester.plan_option.courses
    ) + tuple(
        code for path in selected for code in path.remaining_required_course_codes
    ) + result.unresolved_review_required_courses + result.persisted_in_progress_courses
    reference_codes = tuple(path.status.value for path in selected) + tuple(
        reason.value for path in selected for reason in path.reason_codes
    ) + tuple(
        code for path in selected for code in path.unresolved_blocker_codes
    )
    references = tuple(
        DecisionReference(AuthoritativeSource.PHASE9_DEGREE_PATH, code)
        for code in reference_codes
    )
    return AdvisorEvidence(
        AuthoritativeSource.PHASE9_DEGREE_PATH,
        "DegreePathResult",
        codes,
        references,
        result.degree_path_policy_version,
    )


def _review_status_evidence(
    result: DegreePathResult,
    catalog: CanTakeCatalog,
) -> AdvisorEvidence | None:
    review_codes = set(result.unresolved_review_required_courses)
    statuses = tuple(
        rule.prerequisite_logic_status.value
        for rule in catalog.plan_courses
        if rule.course_code in review_codes
    )
    if not statuses:
        return None
    references = tuple(
        DecisionReference(AuthoritativeSource.ACADEMIC_CATALOG, status)
        for status in statuses
    )
    return AdvisorEvidence(
        AuthoritativeSource.ACADEMIC_CATALOG,
        "PrerequisiteLogicStatus:review-required",
        tuple(review_codes),
        references,
    )


def _clarification_result(
    clarification: ClarificationRequest,
    resolution: CourseResolution | None = None,
    *,
    catalog_resolution: bool = False,
) -> StructuredAdvisorResult:
    evidence: tuple[AdvisorEvidence, ...] = ()
    if catalog_resolution:
        evidence = (
            AdvisorEvidence(
                AuthoritativeSource.ACADEMIC_CATALOG,
                "CourseResolution:AMBIGUOUS",
                clarification.candidate_course_codes,
            ),
        )
    return _build_result(
        intent=AdvisorIntent.CLARIFICATION_REQUIRED,
        authority=AnswerAuthority.INSUFFICIENT_CONTEXT,
        evidence=evidence,
        payload=None,
        course_resolution=resolution,
        clarification=clarification,
    )


def _out_of_scope_result(reason: OutOfScopeReason) -> StructuredAdvisorResult:
    return _build_result(
        intent=AdvisorIntent.OUT_OF_SCOPE,
        authority=AnswerAuthority.INSUFFICIENT_CONTEXT,
        evidence=(),
        payload=None,
        out_of_scope_reason=reason,
    )


def _insufficient_result(
    intent: AdvisorIntent,
    result_reference: str,
    resolution: CourseResolution | None = None,
) -> StructuredAdvisorResult:
    # result_reference remains internal and deliberately is not presented as
    # authoritative evidence when the required source is unavailable.
    if not result_reference:
        raise AdvisorContractError("result_reference must not be empty")
    return _build_result(
        intent=intent,
        authority=AnswerAuthority.INSUFFICIENT_CONTEXT,
        evidence=(),
        payload=None,
        course_resolution=resolution,
    )


def _build_result(
    *,
    intent: AdvisorIntent,
    authority: AnswerAuthority,
    evidence: tuple[AdvisorEvidence, ...],
    payload: AdvisorPayload | None,
    course_resolution: CourseResolution | None = None,
    clarification: ClarificationRequest | None = None,
    out_of_scope_reason: OutOfScopeReason | None = None,
    planning_constraints: PlannerConstraints | DegreePathConstraints | None = None,
    option_references: tuple[int, ...] = (),
    upstream_versions: tuple[PolicyVersionReference, ...] = (),
) -> StructuredAdvisorResult:
    sources = tuple(item.source for item in evidence)
    course_codes = tuple(code for item in evidence for code in item.course_codes)
    decisions = tuple(
        reference for item in evidence for reference in item.decision_references
    )
    versions = (
        PolicyVersionReference(PolicySource.AI_ADVISOR, AI_ADVISOR_POLICY_VERSION),
        *upstream_versions,
    )
    trace = AdvisorTrace(
        advisor_intent=intent,
        answer_authority=authority,
        authoritative_sources_used=sources,
        course_codes=course_codes,
        decision_references=decisions,
        policy_versions=versions,
        planning_constraints=planning_constraints,
        option_references=option_references,
    )
    return StructuredAdvisorResult(
        intent=intent,
        authority=authority,
        trace=trace,
        course_resolution=course_resolution,
        evidence=evidence,
        clarification=clarification,
        out_of_scope_reason=out_of_scope_reason,
        authoritative_payload=payload,
    )


def _context_study_plan_id(context: AdvisorContext) -> str | None:
    if context.progress_catalog is not None:
        return context.progress_catalog.study_plan.study_plan_id
    if context.eligibility_catalog is not None:
        return context.eligibility_catalog.study_plan_id
    return None
