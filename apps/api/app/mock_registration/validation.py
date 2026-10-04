"""Atomic Phase 5/6-backed validation of explicit Mock Registration intent."""

from __future__ import annotations

from decimal import Decimal

from app.progress.models import CourseProgressState, RequirementType
from app.rules.evaluator import evaluate_can_take
from app.rules.models import CanTakeDecision, CanTakeRequest, Decision

from .canonicalization import canonicalize_course_codes, duplicate_course_codes
from .fingerprint import calculate_intent_fingerprint
from .models import (
    MAX_INTENT_COURSES,
    MAX_INTENT_CREDITS,
    CourseValidationResult,
    IntentLifecycle,
    MockRegistrationContext,
    RegistrationIntent,
    TargetPeriodClass,
    ValidatedIntent,
    ValidationStatus,
)
from .registries import ReasonCode

ZERO = Decimal("0")


def validate_registration_intent(
    intent: RegistrationIntent, context: MockRegistrationContext
) -> ValidatedIntent:
    canonical = canonicalize_course_codes(intent.course_codes)
    fingerprint = calculate_intent_fingerprint(intent)
    issues: list[ReasonCode] = []

    if (
        intent.contract_version != "1.0"
        or not intent.intent_id.strip()
        or not intent.owner_scope_id.strip()
        or intent.owner_scope_id != context.owner_scope_id
    ):
        issues.append(ReasonCode.MOCK_REG_REQUIRED_CONTEXT_MISSING)
    if not isinstance(intent.revision, int) or isinstance(intent.revision, bool) or intent.revision < 1:
        issues.append(ReasonCode.MOCK_REG_INVALID_REVISION)
    if (
        not intent.university_id.strip()
        or not intent.major_id.strip()
        or not intent.study_plan_id.strip()
        or intent.university_id != context.university_id
        or intent.major_id != context.major_id
        or intent.study_plan_id != context.study_plan_id
    ):
        issues.append(ReasonCode.MOCK_REG_INVALID_PLAN_IDENTITY)
    if (
        not intent.study_plan_version.strip()
        or intent.study_plan_version != context.study_plan_version
    ):
        issues.append(ReasonCode.MOCK_REG_INVALID_PLAN_VERSION)
    if not _valid_period(intent, context):
        issues.append(ReasonCode.MOCK_REG_INVALID_TARGET_PERIOD)
    if not intent.source_version.strip():
        issues.append(ReasonCode.MOCK_REG_REQUIRED_CONTEXT_MISSING)
    if not hasattr(intent.source_class, "value"):
        issues.append(ReasonCode.MOCK_REG_REQUIRED_CONTEXT_MISSING)

    if intent.lifecycle_status is IntentLifecycle.SUBMITTED:
        if not canonical:
            issues.append(ReasonCode.MOCK_REG_EMPTY_COURSE_SET)
    elif intent.lifecycle_status is IntentLifecycle.WITHDRAWN:
        if canonical:
            issues.append(ReasonCode.MOCK_REG_INVALID_LIFECYCLE)
    elif intent.lifecycle_status is IntentLifecycle.EXPIRED:
        pass
    else:  # defensive if a caller bypasses the enum at runtime
        issues.append(ReasonCode.MOCK_REG_INVALID_LIFECYCLE)

    duplicates = duplicate_course_codes(intent.course_codes)
    if duplicates:
        issues.append(ReasonCode.MOCK_REG_DUPLICATE_COURSE)
    if len(canonical) > MAX_INTENT_COURSES:
        issues.append(ReasonCode.MOCK_REG_COURSE_LIMIT_EXCEEDED)

    context_ready = bool(
        context.source_versions
        and context.engine_policy_versions
        and context.current_progress.study_plan_id == context.study_plan_id
        and context.progress_catalog.study_plan.study_plan_id == context.study_plan_id
        and context.eligibility_catalog.study_plan_id == context.study_plan_id
    )
    if not context_ready:
        issues.append(ReasonCode.MOCK_REG_REQUIRED_CONTEXT_MISSING)

    blocking_context_codes = {
        ReasonCode.MOCK_REG_REQUIRED_CONTEXT_MISSING,
        ReasonCode.MOCK_REG_INVALID_PLAN_IDENTITY,
        ReasonCode.MOCK_REG_INVALID_PLAN_VERSION,
        ReasonCode.MOCK_REG_INVALID_TARGET_PERIOD,
        ReasonCode.MOCK_REG_INVALID_REVISION,
        ReasonCode.MOCK_REG_INVALID_LIFECYCLE,
        ReasonCode.MOCK_REG_EMPTY_COURSE_SET,
        ReasonCode.MOCK_REG_COURSE_LIMIT_EXCEEDED,
    }
    course_results: tuple[CourseValidationResult, ...] = ()
    declared_credits = ZERO
    if intent.lifecycle_status is IntentLifecycle.SUBMITTED and not (set(issues) & blocking_context_codes):
        course_results = tuple(
            _validate_course(code, context, code in duplicates) for code in canonical
        )
        declared_credits = sum(
            (item.credit_hours or ZERO for item in course_results), ZERO
        )
        if declared_credits > MAX_INTENT_CREDITS:
            issues.append(ReasonCode.MOCK_REG_CREDIT_LIMIT_EXCEEDED)
        for item in course_results:
            issues.extend(item.reason_codes)

    reasons = _ordered_reasons(issues)
    status = _status(reasons, course_results)
    return ValidatedIntent(
        intent=intent,
        canonical_course_codes=canonical,
        content_fingerprint=fingerprint,
        status=status,
        reason_codes=reasons,
        course_results=course_results,
        declared_credit_load=declared_credits,
        source_engine_policy_versions=tuple(sorted(context.engine_policy_versions)),
        limitations=(
            "Non-binding declared intent; not enrollment, approval, reservation, or offering guarantee.",
            "The 10-course and 30.00-credit limits are Morshidi safety bounds, not institutional rules.",
        ),
    )


def _valid_period(intent: RegistrationIntent, context: MockRegistrationContext) -> bool:
    period = intent.target_period
    allowed = context.allowed_target_period
    if (
        not period.period_key.strip()
        or not period.source_version.strip()
        or period.university_id != intent.university_id
        or period != allowed
    ):
        return False
    if period.period_class is TargetPeriodClass.OFFICIAL_PERIOD_REFERENCE:
        return period.verified_provider_source
    return not period.verified_provider_source


def _validate_course(code, context: MockRegistrationContext, duplicate: bool) -> CourseValidationResult:
    reasons: list[ReasonCode] = []
    known = {item.course_code for item in context.eligibility_catalog.courses}
    plan_courses = {item.course_code: item for item in context.progress_catalog.plan_courses}
    if duplicate:
        reasons.append(ReasonCode.MOCK_REG_DUPLICATE_COURSE)
    if code not in known:
        reasons.append(ReasonCode.MOCK_REG_UNKNOWN_COURSE)
        return _course_result(code, reasons)
    plan_course = plan_courses.get(code)
    if plan_course is None:
        reasons.append(ReasonCode.MOCK_REG_TARGET_NOT_PLAN_MEMBER)
        return _course_result(code, reasons)
    progress = next((item for item in context.current_progress.courses if item.course_code == code), None)
    if progress is None:
        reasons.append(ReasonCode.MOCK_REG_REQUIRED_CONTEXT_MISSING)
        return _course_result(code, reasons, plan_course=plan_course)
    if progress.state is CourseProgressState.COMPLETED:
        reasons.append(ReasonCode.MOCK_REG_TARGET_ALREADY_COMPLETED)
    if progress.state is CourseProgressState.IN_PROGRESS:
        reasons.append(ReasonCode.MOCK_REG_TARGET_IN_PROGRESS)
    decision = evaluate_can_take(
        context.eligibility_catalog,
        CanTakeRequest(context.study_plan_id, code, context.student_attempts),
    )
    phase5 = decision.decision if isinstance(decision, CanTakeDecision) else None
    phase5_reasons = (
        tuple(item.value for item in decision.reasons) if isinstance(decision, CanTakeDecision) else ()
    )
    if not isinstance(decision, CanTakeDecision):
        reasons.append(ReasonCode.MOCK_REG_TARGET_NOT_PLAN_MEMBER)
    elif decision.decision is Decision.NOT_ELIGIBLE:
        reasons.append(ReasonCode.MOCK_REG_TARGET_NOT_ELIGIBLE)
    elif decision.decision is Decision.REVIEW_REQUIRED:
        reasons.append(ReasonCode.MOCK_REG_ELIGIBILITY_REVIEW_REQUIRED)
    group = next(
        (item for item in context.progress_catalog.requirement_groups if item.group_id == plan_course.requirement_group_id),
        None,
    )
    group_progress = next(
        (item for item in context.current_progress.requirement_groups if item.group_id == plan_course.requirement_group_id),
        None,
    )
    if group is None or group_progress is None:
        reasons.append(ReasonCode.MOCK_REG_REQUIRED_CONTEXT_MISSING)
    elif (
        group.requirement_type is RequirementType.ELECTIVE
        and group_progress.is_satisfied
        and decision is not None
        and isinstance(decision, CanTakeDecision)
        and decision.decision is Decision.ELIGIBLE
    ):
        reasons.append(ReasonCode.MOCK_REG_ELECTIVE_GROUP_ALREADY_SATISFIED)
    return _course_result(
        code,
        reasons,
        plan_course=plan_course,
        phase5=phase5,
        phase5_reasons=phase5_reasons,
        group_code=group.group_code if group else None,
    )


def _course_result(
    code,
    reasons,
    *,
    plan_course=None,
    phase5=None,
    phase5_reasons=(),
    group_code=None,
):
    ordered = _ordered_reasons(reasons)
    status = (
        ValidationStatus.REVIEW_REQUIRED
        if ordered == (ReasonCode.MOCK_REG_ELIGIBILITY_REVIEW_REQUIRED,)
        else ValidationStatus.INVALID if ordered else ValidationStatus.VALID
    )
    return CourseValidationResult(
        course_code=code,
        status=status,
        reason_codes=ordered,
        phase5_decision=phase5,
        phase5_reasons=phase5_reasons,
        requirement_group_id=plan_course.requirement_group_id if plan_course else None,
        requirement_group_code=group_code,
        credit_hours=plan_course.credit_hours if plan_course else None,
        limitations=("Validated against current authoritative state; same-intent courses do not co-satisfy prerequisites.",),
    )


def _ordered_reasons(values):
    present = set(values)
    return tuple(code for code in ReasonCode if code in present)


def _status(reasons, course_results):
    review = ReasonCode.MOCK_REG_ELIGIBILITY_REVIEW_REQUIRED
    invalid_reasons = tuple(item for item in reasons if item is not review)
    if invalid_reasons or any(item.status is ValidationStatus.INVALID for item in course_results):
        return ValidationStatus.INVALID
    if review in reasons or any(item.status is ValidationStatus.REVIEW_REQUIRED for item in course_results):
        return ValidationStatus.REVIEW_REQUIRED
    return ValidationStatus.VALID
