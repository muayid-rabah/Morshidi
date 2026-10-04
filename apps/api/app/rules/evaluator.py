"""Pure prerequisite eligibility evaluator; it has no I/O or framework dependency."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.rules.project_credits import (
    MIN_EARNED_CREDITS, RULE_ID, RULE_PROVENANCE, RULE_VERSION,
    credits_from_complete_rules, is_plan12_project,
)

from app.rules.models import (
    AttemptOutcome,
    AcademicRuleTrace,
    CanTakeCatalog,
    CanTakeDecision,
    CanTakeError,
    CanTakeRequest,
    Decision,
    DecisionReason,
    DependencyGroup,
    DependencyGroupEvidence,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    RequestErrorCode,
    StudentCourseAttempt,
    TargetAttemptState,
)

CanTakeResult = CanTakeDecision | CanTakeError


def evaluate_can_take(catalog: CanTakeCatalog, request: CanTakeRequest) -> CanTakeResult:
    """Apply verified prerequisites and any exact plan-scoped academic rule."""
    result = _evaluate_prerequisites(catalog, request)
    if not isinstance(result, CanTakeDecision) or not is_plan12_project(
        request.study_plan_id, request.target_course_code,
    ):
        return result
    earned = request.earned_completed_credits
    if earned is None:
        earned = credits_from_complete_rules(catalog, request.student_attempts)
    if earned is None:
        trace_result = "UNKNOWN"
        decision = Decision.REVIEW_REQUIRED if result.decision is Decision.ELIGIBLE else result.decision
        reason = DecisionReason.GRADUATION_PROJECT_CREDIT_EVIDENCE_UNKNOWN
    elif earned < MIN_EARNED_CREDITS:
        trace_result = "BLOCKED"
        decision = Decision.NOT_ELIGIBLE
        reason = DecisionReason.GRADUATION_PROJECT_MIN_EARNED_CREDITS
    else:
        trace_result = "SATISFIED"
        decision = result.decision  # 90 credits never bypasses prerequisites.
        reason = DecisionReason.GRADUATION_PROJECT_MIN_EARNED_CREDITS
    trace = AcademicRuleTrace(
        RULE_ID, RULE_VERSION, RULE_PROVENANCE, MIN_EARNED_CREDITS, earned,
        trace_result,
        "يتطلب مشروع الذكاء الاصطناعي إكمال 90 ساعة معتمدة بنجاح على الأقل.",
        "AI Project requires at least 90 successfully earned credit hours.",
    )
    return replace(result, decision=decision, reasons=(*result.reasons, reason),
                   review_reasons=(*result.review_reasons, reason)
                   if trace_result == "UNKNOWN" else result.review_reasons,
                   academic_rule_traces=(trace,))


def _evaluate_prerequisites(catalog: CanTakeCatalog, request: CanTakeRequest) -> CanTakeResult:
    """Evaluate only verified prerequisite eligibility for one plan-course target.

    Catalog resolution is deliberately external. This function does not parse raw
    prerequisite text, infer equivalencies, mutate input, or perform I/O.
    """

    invalid = _validate_request(request)
    if invalid is not None:
        return invalid
    if request.study_plan_id != catalog.study_plan_id:
        return _error(RequestErrorCode.STUDY_PLAN_NOT_FOUND, request)

    courses_by_code = {course.course_code: course for course in catalog.courses}
    if request.target_course_code not in courses_by_code:
        return _error(RequestErrorCode.TARGET_NOT_FOUND, request)

    plan_courses_by_code = {course.course_code: course for course in catalog.plan_courses}
    target = plan_courses_by_code.get(request.target_course_code)
    if target is None:
        return _error(RequestErrorCode.TARGET_NOT_IN_STUDY_PLAN, request)

    attempt_state = _target_attempt_state(target.course_code, request.student_attempts)
    target_reasons = _target_attempt_reasons(attempt_state)

    if target.prerequisite_logic_status is PrerequisiteLogicStatus.NOT_APPLICABLE:
        return _decision(
            target,
            request,
            attempt_state,
            reasons=(DecisionReason.NO_PREREQUISITES, *target_reasons),
            decision=Decision.ELIGIBLE,
        )
    if target.prerequisite_logic_status is PrerequisiteLogicStatus.UNRESOLVED:
        return _review(target, request, attempt_state, DecisionReason.PREREQUISITE_LOGIC_UNRESOLVED)
    if target.prerequisite_logic_status is PrerequisiteLogicStatus.SOURCE_CONFLICT:
        return _review(target, request, attempt_state, DecisionReason.PREREQUISITE_SOURCE_CONFLICT)

    prerequisite_groups = tuple(
        sorted(
            (
                group
                for group in target.dependency_groups
                if group.dependency_type is DependencyType.PREREQUISITE
            ),
            key=lambda group: group.group_number,
        )
    )
    if not _has_valid_prerequisite_groups(prerequisite_groups):
        return _review(
            target,
            request,
            attempt_state,
            DecisionReason.VERIFIED_PREREQUISITE_MODEL_INCOMPLETE,
        )

    passed_codes = {
        attempt.course_code
        for attempt in request.student_attempts
        if attempt.outcome is AttemptOutcome.PASSED
    }
    evidence = tuple(_group_evidence(group, passed_codes) for group in prerequisite_groups)
    satisfied = tuple(item for item in evidence if item.passed_option_course_codes)
    missing = tuple(item for item in evidence if not item.passed_option_course_codes)
    if missing:
        return _decision(
            target,
            request,
            attempt_state,
            decision=Decision.NOT_ELIGIBLE,
            reasons=(DecisionReason.MISSING_PREREQUISITE_GROUP, *target_reasons),
            satisfied=satisfied,
            missing=missing,
        )
    return _decision(
        target,
        request,
        attempt_state,
        decision=Decision.ELIGIBLE,
        reasons=(DecisionReason.PREREQUISITES_SATISFIED, *target_reasons),
        satisfied=satisfied,
    )


def _validate_request(request: CanTakeRequest) -> CanTakeError | None:
    if not request.study_plan_id or not request.target_course_code:
        return _error(RequestErrorCode.INVALID_REQUEST, request)
    if any(not attempt.course_code for attempt in request.student_attempts):
        return _error(RequestErrorCode.INVALID_REQUEST, request)
    credits = request.earned_completed_credits
    if credits is not None and (not isinstance(credits, Decimal) or not credits.is_finite() or credits < 0):
        return _error(RequestErrorCode.INVALID_REQUEST, request)
    return None


def _has_valid_prerequisite_groups(groups: tuple[DependencyGroup, ...]) -> bool:
    group_numbers = [group.group_number for group in groups]
    return bool(groups) and all(
        group.group_number > 0 and bool(group.option_course_codes) for group in groups
    ) and len(group_numbers) == len(set(group_numbers))


def _group_evidence(
    group: DependencyGroup, passed_codes: set[str]
) -> DependencyGroupEvidence:
    options = tuple(sorted(set(group.option_course_codes)))
    passed = tuple(code for code in options if code in passed_codes)
    non_passed = tuple(code for code in options if code not in passed_codes)
    return DependencyGroupEvidence(
        group_number=group.group_number,
        dependency_type=group.dependency_type,
        option_course_codes=options,
        passed_option_course_codes=passed,
        non_passed_option_course_codes=non_passed,
    )


def _target_attempt_state(
    target_course_code: str, attempts: tuple[StudentCourseAttempt, ...]
) -> TargetAttemptState:
    target_attempts = tuple(attempt for attempt in attempts if attempt.course_code == target_course_code)
    return TargetAttemptState(
        has_passed_target=any(attempt.outcome is AttemptOutcome.PASSED for attempt in target_attempts),
        has_in_progress_target=any(
            attempt.outcome is AttemptOutcome.IN_PROGRESS for attempt in target_attempts
        ),
    )


def _target_attempt_reasons(state: TargetAttemptState) -> tuple[DecisionReason, ...]:
    reasons: list[DecisionReason] = []
    if state.has_passed_target:
        reasons.append(DecisionReason.TARGET_ALREADY_COMPLETED)
    if state.has_in_progress_target:
        reasons.append(DecisionReason.TARGET_CURRENTLY_ENROLLED)
    return tuple(reasons)


def _review(
    target: PlanCourseRule,
    request: CanTakeRequest,
    attempt_state: TargetAttemptState,
    reason: DecisionReason,
) -> CanTakeDecision:
    return _decision(
        target,
        request,
        attempt_state,
        decision=Decision.REVIEW_REQUIRED,
        reasons=(reason, *_target_attempt_reasons(attempt_state)),
        review_reasons=(reason,),
    )


def _decision(
    target: PlanCourseRule,
    request: CanTakeRequest,
    attempt_state: TargetAttemptState,
    *,
    decision: Decision,
    reasons: tuple[DecisionReason, ...],
    satisfied: tuple[DependencyGroupEvidence, ...] = (),
    missing: tuple[DependencyGroupEvidence, ...] = (),
    review_reasons: tuple[DecisionReason, ...] = (),
) -> CanTakeDecision:
    return CanTakeDecision(
        kind="decision",
        decision=decision,
        study_plan_id=request.study_plan_id,
        target_course_code=target.course_code,
        prerequisite_logic_status=target.prerequisite_logic_status,
        target_attempt_state=attempt_state,
        satisfied_dependency_groups=satisfied,
        missing_dependency_groups=missing,
        reasons=reasons,
        review_reasons=review_reasons,
        raw_prerequisite_text=target.raw_prerequisite_text,
        target_name_ar=target.target_name_ar,
        target_name_en=target.target_name_en,
    )


def _error(error_code: RequestErrorCode, request: CanTakeRequest) -> CanTakeError:
    return CanTakeError(
        kind="error",
        error_code=error_code,
        study_plan_id=request.study_plan_id or None,
        target_course_code=request.target_course_code or None,
    )
