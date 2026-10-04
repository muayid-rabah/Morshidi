"""Finite validation for the three supported Digital Twin V1 operations."""

from __future__ import annotations

from collections import Counter

from app.academic_digital_twin.fingerprint import calculate_base_state_fingerprint
from app.academic_digital_twin.models import (
    AuthoritativeAcademicSnapshot,
    OperationId,
    ScenarioIdentity,
    ScenarioOperation,
    ScenarioStatus,
    ScenarioValidationIssue,
    ValidationCode,
)
from app.degree_path.models import DegreePathConstraintError
from app.planner.models import PlannerConstraintError
from app.progress.models import CourseProgressState, RequirementType
from app.rules.evaluator import evaluate_can_take
from app.rules.models import CanTakeDecision, CanTakeRequest, Decision

_STRUCTURAL = {
    OperationId.MODEL_COURSE_COMPLETION.value,
    OperationId.OMIT_NEXT_PLAN_COURSE.value,
}
_SUPPORTED = {item.value for item in OperationId}
_DEFERRED = {
    "TWIN_OP_PREFER_ELECTIVE_OPTION",
    "TWIN_OP_MODEL_COURSE_FAILURE",
    "TWIN_OP_MODEL_COURSE_WITHDRAWAL",
    "TWIN_OP_ASSUME_IN_PROGRESS_OUTCOME",
    "TWIN_OP_EXCLUDE_UNAVAILABLE_COURSE",
    "TWIN_OP_CHANGE_MAJOR",
    "TWIN_OP_CHANGE_PLAN_VERSION",
}
_FORBIDDEN = {
    "TWIN_OP_CREATE_EQUIVALENCY",
    "TWIN_OP_SET_GRADE_OR_GPA",
    "TWIN_OP_MUTATE_AUTHORITATIVE_RECORD",
    "TWIN_OP_FORCE_ELIGIBILITY",
    "TWIN_OP_OFFICIAL_REGISTER",
}


def canonical_operations(operations: tuple[ScenarioOperation, ...]) -> tuple[ScenarioOperation, ...]:
    order = {
        OperationId.SET_PLANNING_CONSTRAINTS.value: 0,
        OperationId.MODEL_COURSE_COMPLETION.value: 1,
        OperationId.OMIT_NEXT_PLAN_COURSE.value: 1,
    }
    return tuple(
        sorted(
            operations,
            key=lambda item: (
                order.get(item.operation_id, 9),
                item.operation_id,
                item.target_course_code or "",
            ),
        )
    )


def validate_scenario(
    snapshot: AuthoritativeAcademicSnapshot,
    identity: ScenarioIdentity,
) -> tuple[ScenarioStatus | None, tuple[ScenarioValidationIssue, ...]]:
    current_fingerprint = calculate_base_state_fingerprint(snapshot)
    if identity.base_state_fingerprint != current_fingerprint:
        return ScenarioStatus.STALE_BASE_STATE, (
            ScenarioValidationIssue(ValidationCode.STALE_BASE_STATE),
        )
    if (
        not identity.scenario_id.strip()
        or identity.scenario_contract_version != "1.0"
        or identity.scenario_version != 1
        or not snapshot.source_versions
        or not snapshot.engine_policy_versions
    ):
        return ScenarioStatus.INVALID, (
            ScenarioValidationIssue(ValidationCode.REQUIRED_CONTEXT_MISSING),
        )
    if (
        snapshot.plan_identity.study_plan_id != snapshot.eligibility_catalog.study_plan_id
        or snapshot.plan_identity.study_plan_id
        != snapshot.progress_catalog.study_plan.study_plan_id
        or snapshot.current_progress.study_plan_id != snapshot.plan_identity.study_plan_id
    ):
        return ScenarioStatus.INVALID, (
            ScenarioValidationIssue(ValidationCode.BASE_IDENTITY_MISMATCH),
        )
    if not identity.operations:
        return ScenarioStatus.INVALID, (
            ScenarioValidationIssue(ValidationCode.REQUIRED_CONTEXT_MISSING),
        )

    issues: list[ScenarioValidationIssue] = []
    counts = Counter(item.operation_id for item in identity.operations)
    if any(value > 1 for value in counts.values()):
        issues.append(ScenarioValidationIssue(ValidationCode.DUPLICATE_OPERATION))
    structural = [item for item in identity.operations if item.operation_id in _STRUCTURAL]
    if len(structural) > 1:
        code = (
            ValidationCode.CONFLICTING_OPERATIONS
            if len({item.operation_id for item in structural}) > 1
            else ValidationCode.TOO_MANY_STRUCTURAL_OPERATIONS
        )
        issues.append(ScenarioValidationIssue(code))
    if len(identity.operations) > 2:
        issues.append(ScenarioValidationIssue(ValidationCode.TOO_MANY_STRUCTURAL_OPERATIONS))

    review_required = False
    for operation in canonical_operations(identity.operations):
        if operation.operation_id in _DEFERRED:
            issues.append(_issue(ValidationCode.OPERATION_DEFERRED, operation))
        elif operation.operation_id in _FORBIDDEN:
            issues.append(_issue(ValidationCode.OPERATION_FORBIDDEN, operation))
        elif operation.operation_id not in _SUPPORTED:
            issues.append(_issue(ValidationCode.UNKNOWN_OPERATION, operation))
        elif operation.operation_id == OperationId.SET_PLANNING_CONSTRAINTS.value:
            _validate_constraints(operation, identity, issues)
        elif operation.operation_id == OperationId.MODEL_COURSE_COMPLETION.value:
            review = _validate_completion(snapshot, operation, issues)
            if review:
                review_required = True
        else:
            _validate_omission(snapshot, operation, issues)
    if issues:
        if review_required and all(
            issue.code is ValidationCode.TARGET_REVIEW_REQUIRED for issue in issues
        ):
            return ScenarioStatus.REVIEW_REQUIRED, tuple(_deduplicate(issues))
        return ScenarioStatus.INVALID, tuple(_deduplicate(issues))
    return None, ()


def _validate_constraints(operation, identity, issues) -> None:
    constraints = operation.constraints or identity.constraint_bundle
    if constraints is None:
        issues.append(_issue(ValidationCode.INVALID_CONSTRAINT, operation))
        return
    try:
        constraints.planner_constraints()
        constraints.path_constraints()
    except (PlannerConstraintError, DegreePathConstraintError, ValueError):
        issues.append(_issue(ValidationCode.INVALID_CONSTRAINT, operation))


def _validate_completion(snapshot, operation, issues) -> bool:
    target = (operation.target_course_code or "").strip()
    if not target:
        issues.append(_issue(ValidationCode.UNKNOWN_COURSE, operation))
        return False
    known = {item.course_code for item in snapshot.eligibility_catalog.courses}
    if target not in known:
        issues.append(_issue(ValidationCode.UNKNOWN_COURSE, operation))
        return False
    plan_courses = {item.course_code: item for item in snapshot.progress_catalog.plan_courses}
    plan_course = plan_courses.get(target)
    if plan_course is None:
        issues.append(_issue(ValidationCode.TARGET_NOT_PLAN_MEMBER, operation))
        return False
    progress = next((item for item in snapshot.current_progress.courses if item.course_code == target), None)
    if progress is None:
        issues.append(_issue(ValidationCode.REQUIRED_CONTEXT_MISSING, operation))
        return False
    if progress.state is CourseProgressState.COMPLETED:
        issues.append(_issue(ValidationCode.TARGET_ALREADY_COMPLETED, operation))
        return False
    if progress.state is CourseProgressState.IN_PROGRESS:
        issues.append(_issue(ValidationCode.TARGET_IN_PROGRESS, operation))
        return False
    decision = evaluate_can_take(
        snapshot.eligibility_catalog,
        CanTakeRequest(snapshot.plan_identity.study_plan_id, target, snapshot.engine_attempts),
    )
    if not isinstance(decision, CanTakeDecision):
        issues.append(_issue(ValidationCode.TARGET_NOT_PLAN_MEMBER, operation))
        return False
    if decision.decision is Decision.REVIEW_REQUIRED:
        issues.append(_issue(ValidationCode.TARGET_REVIEW_REQUIRED, operation))
        return True
    if decision.decision is not Decision.ELIGIBLE:
        issues.append(_issue(ValidationCode.TARGET_NOT_ELIGIBLE, operation))
        return False
    group = next(
        item
        for item in snapshot.progress_catalog.requirement_groups
        if item.group_id == plan_course.requirement_group_id
    )
    group_progress = next(
        item
        for item in snapshot.current_progress.requirement_groups
        if item.group_id == plan_course.requirement_group_id
    )
    if group.requirement_type is RequirementType.ELECTIVE and group_progress.is_satisfied:
        issues.append(_issue(ValidationCode.ELECTIVE_GROUP_ALREADY_SATISFIED, operation))
    return False


def _validate_omission(snapshot, operation, issues) -> None:
    target = (operation.target_course_code or "").strip()
    if not target:
        issues.append(_issue(ValidationCode.UNKNOWN_COURSE, operation))
        return
    known = {item.course_code for item in snapshot.eligibility_catalog.courses}
    if target not in known:
        issues.append(_issue(ValidationCode.UNKNOWN_COURSE, operation))
    elif target not in {item.course_code for item in snapshot.progress_catalog.plan_courses}:
        issues.append(_issue(ValidationCode.TARGET_NOT_PLAN_MEMBER, operation))


def _issue(code, operation):
    return ScenarioValidationIssue(code, operation.operation_id, operation.target_course_code)


def _deduplicate(issues):
    seen = set()
    result = []
    for issue in issues:
        key = (issue.code, issue.operation_id, issue.target_course_code)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result
