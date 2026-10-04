from __future__ import annotations

from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CanTakeDecision,
    CanTakeError,
    CanTakeRequest,
    CourseCatalogStatus,
    CourseIdentity,
    Decision,
    DecisionReason,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    RequestErrorCode,
    StudentCourseAttempt,
)


PLAN_ID = "zu-ai-plan-12"
TARGET = "1501112"
PREREQUISITE = "1501110"


def attempt(course_code: str, outcome: AttemptOutcome) -> StudentCourseAttempt:
    return StudentCourseAttempt(course_code=course_code, outcome=outcome)


def group(number: int, *options: str) -> DependencyGroup:
    return DependencyGroup(number, DependencyType.PREREQUISITE, options)


def rule(
    code: str = TARGET,
    status: PrerequisiteLogicStatus = PrerequisiteLogicStatus.VERIFIED,
    groups: tuple[DependencyGroup, ...] = (group(1, PREREQUISITE),),
    raw: str | None = PREREQUISITE,
) -> PlanCourseRule:
    return PlanCourseRule(code, status, groups, raw, "اسم المادة")


def catalog(
    *plan_rules: PlanCourseRule,
    extra_courses: tuple[CourseIdentity, ...] = (),
    study_plan_id: str = PLAN_ID,
) -> CanTakeCatalog:
    plan_courses = plan_rules or (rule(),)
    identities = tuple(
        CourseIdentity(plan_rule.course_code, CourseCatalogStatus.KNOWN)
        for plan_rule in plan_courses
    )
    return CanTakeCatalog(study_plan_id, plan_courses, identities + extra_courses)


def request(
    target: str = TARGET,
    attempts: tuple[StudentCourseAttempt, ...] = (),
    study_plan_id: str = PLAN_ID,
) -> CanTakeRequest:
    return CanTakeRequest(study_plan_id, target, attempts)


def decision(result: CanTakeDecision | CanTakeError) -> CanTakeDecision:
    assert isinstance(result, CanTakeDecision)
    return result


def error(result: CanTakeDecision | CanTakeError) -> CanTakeError:
    assert isinstance(result, CanTakeError)
    return result


def test_not_applicable_is_eligible() -> None:
    result = decision(
        evaluate_can_take(
            catalog(rule(status=PrerequisiteLogicStatus.NOT_APPLICABLE, groups=(), raw=None)),
            request(),
        )
    )

    assert result.decision is Decision.ELIGIBLE
    assert result.reasons == (DecisionReason.NO_PREREQUISITES,)


def test_verified_single_prerequisite_passed_is_eligible() -> None:
    result = decision(evaluate_can_take(catalog(), request(attempts=(attempt(PREREQUISITE, AttemptOutcome.PASSED),))))

    assert result.decision is Decision.ELIGIBLE
    assert result.satisfied_dependency_groups[0].passed_option_course_codes == (PREREQUISITE,)


def test_verified_single_prerequisite_failed_is_not_eligible() -> None:
    result = decision(evaluate_can_take(catalog(), request(attempts=(attempt(PREREQUISITE, AttemptOutcome.FAILED),))))

    assert result.decision is Decision.NOT_ELIGIBLE
    assert result.missing_dependency_groups[0].option_course_codes == (PREREQUISITE,)


def test_verified_single_prerequisite_absent_is_not_eligible() -> None:
    assert decision(evaluate_can_take(catalog(), request())).decision is Decision.NOT_ELIGIBLE


def test_in_progress_prerequisite_does_not_satisfy() -> None:
    assert decision(
        evaluate_can_take(catalog(), request(attempts=(attempt(PREREQUISITE, AttemptOutcome.IN_PROGRESS),)))
    ).decision is Decision.NOT_ELIGIBLE


def test_withdrawn_prerequisite_does_not_satisfy() -> None:
    assert decision(
        evaluate_can_take(catalog(), request(attempts=(attempt(PREREQUISITE, AttemptOutcome.WITHDRAWN),)))
    ).decision is Decision.NOT_ELIGIBLE


def test_failed_then_passed_satisfies_prerequisite() -> None:
    result = decision(
        evaluate_can_take(
            catalog(),
            request(attempts=(attempt(PREREQUISITE, AttemptOutcome.FAILED), attempt(PREREQUISITE, AttemptOutcome.PASSED))),
        )
    )

    assert result.decision is Decision.ELIGIBLE


def test_passed_then_failed_still_satisfies_prerequisite() -> None:
    assert decision(
        evaluate_can_take(
            catalog(),
            request(attempts=(attempt(PREREQUISITE, AttemptOutcome.PASSED), attempt(PREREQUISITE, AttemptOutcome.FAILED))),
        )
    ).decision is Decision.ELIGIBLE


def test_duplicate_passed_attempts_have_stable_evidence() -> None:
    once = decision(evaluate_can_take(catalog(), request(attempts=(attempt(PREREQUISITE, AttemptOutcome.PASSED),))))
    twice = decision(
        evaluate_can_take(
            catalog(),
            request(attempts=(attempt(PREREQUISITE, AttemptOutcome.PASSED), attempt(PREREQUISITE, AttemptOutcome.PASSED))),
        )
    )

    assert once == twice


def test_unresolved_returns_review_required_without_parsing_raw_text() -> None:
    target = rule(status=PrerequisiteLogicStatus.UNRESOLVED, groups=(), raw="A,B")
    result = decision(evaluate_can_take(catalog(target), request(attempts=(attempt("A", AttemptOutcome.PASSED),))))

    assert result.decision is Decision.REVIEW_REQUIRED
    assert result.review_reasons == (DecisionReason.PREREQUISITE_LOGIC_UNRESOLVED,)


def test_source_conflict_returns_review_required_without_equivalency() -> None:
    target = rule(status=PrerequisiteLogicStatus.SOURCE_CONFLICT, groups=(), raw="0300103,1505311")
    result = decision(evaluate_can_take(catalog(target), request(attempts=(attempt("0300104", AttemptOutcome.PASSED),))))

    assert result.decision is Decision.REVIEW_REQUIRED
    assert result.review_reasons == (DecisionReason.PREREQUISITE_SOURCE_CONFLICT,)


def test_raw_prerequisite_text_does_not_override_verified_dependencies() -> None:
    target = rule(raw="some unrelated, raw, text")
    result = decision(evaluate_can_take(catalog(target), request(attempts=(attempt(PREREQUISITE, AttemptOutcome.PASSED),))))

    assert result.decision is Decision.ELIGIBLE
    assert result.raw_prerequisite_text == "some unrelated, raw, text"


def test_or_group_is_satisfied_by_one_option() -> None:
    target = rule(groups=(group(1, "A", "B"),), raw="A,B")
    result = decision(evaluate_can_take(catalog(target), request(attempts=(attempt("B", AttemptOutcome.PASSED),))))

    assert result.decision is Decision.ELIGIBLE
    assert result.satisfied_dependency_groups[0].passed_option_course_codes == ("B",)


def test_or_group_with_multiple_passed_options_has_no_duplicate_evidence() -> None:
    target = rule(groups=(group(1, "A", "B", "B"),))
    result = decision(
        evaluate_can_take(catalog(target), request(attempts=(attempt("A", AttemptOutcome.PASSED), attempt("B", AttemptOutcome.PASSED))))
    )

    assert result.decision is Decision.ELIGIBLE
    assert result.satisfied_dependency_groups[0].option_course_codes == ("A", "B")
    assert result.satisfied_dependency_groups[0].passed_option_course_codes == ("A", "B")


def test_or_group_with_no_passed_option_is_missing() -> None:
    target = rule(groups=(group(1, "A", "B"),))
    result = decision(evaluate_can_take(catalog(target), request()))

    assert result.decision is Decision.NOT_ELIGIBLE
    assert result.missing_dependency_groups[0].non_passed_option_course_codes == ("A", "B")


def test_multiple_and_groups_all_satisfied_is_eligible() -> None:
    target = rule(groups=(group(1, "A", "B"), group(2, "C")))
    result = decision(
        evaluate_can_take(catalog(target), request(attempts=(attempt("A", AttemptOutcome.PASSED), attempt("C", AttemptOutcome.PASSED))))
    )

    assert result.decision is Decision.ELIGIBLE


def test_multiple_and_groups_one_missing_is_not_eligible() -> None:
    target = rule(groups=(group(1, "A"), group(2, "B")))
    result = decision(evaluate_can_take(catalog(target), request(attempts=(attempt("A", AttemptOutcome.PASSED),))))

    assert result.decision is Decision.NOT_ELIGIBLE
    assert [item.group_number for item in result.missing_dependency_groups] == [2]


def test_multiple_and_groups_multiple_missing_are_returned_in_order() -> None:
    target = rule(groups=(group(3, "C"), group(1, "A"), group(2, "B")))
    result = decision(evaluate_can_take(catalog(target), request()))

    assert [item.group_number for item in result.missing_dependency_groups] == [1, 2, 3]


def test_referenced_only_prerequisite_can_satisfy_verified_rule() -> None:
    referenced = CourseIdentity("0300103", CourseCatalogStatus.REFERENCED_ONLY)
    target = rule(groups=(group(1, "0300103"),))
    result = decision(
        evaluate_can_take(catalog(target, extra_courses=(referenced,)), request(attempts=(attempt("0300103", AttemptOutcome.PASSED),)))
    )

    assert result.decision is Decision.ELIGIBLE


def test_no_implicit_0300103_to_0300104_equivalency() -> None:
    target = rule(groups=(group(1, "0300103"),))
    result = decision(evaluate_can_take(catalog(target), request(attempts=(attempt("0300104", AttemptOutcome.PASSED),))))

    assert result.decision is Decision.NOT_ELIGIBLE


def test_no_implicit_0301241_to_0301245_equivalency() -> None:
    target = rule(groups=(group(1, "0301241"),))
    result = decision(evaluate_can_take(catalog(target), request(attempts=(attempt("0301245", AttemptOutcome.PASSED),))))

    assert result.decision is Decision.NOT_ELIGIBLE


def test_target_already_passed_is_a_fact_not_a_registration_ruling() -> None:
    target = rule(status=PrerequisiteLogicStatus.NOT_APPLICABLE, groups=(), raw=None)
    result = decision(evaluate_can_take(catalog(target), request(attempts=(attempt(TARGET, AttemptOutcome.PASSED),))))

    assert result.decision is Decision.ELIGIBLE
    assert result.target_attempt_state.has_passed_target is True
    assert DecisionReason.TARGET_ALREADY_COMPLETED in result.reasons


def test_target_in_progress_is_surfaced_separately() -> None:
    target = rule(status=PrerequisiteLogicStatus.NOT_APPLICABLE, groups=(), raw=None)
    result = decision(evaluate_can_take(catalog(target), request(attempts=(attempt(TARGET, AttemptOutcome.IN_PROGRESS),))))

    assert result.decision is Decision.ELIGIBLE
    assert result.target_attempt_state.has_in_progress_target is True
    assert DecisionReason.TARGET_CURRENTLY_ENROLLED in result.reasons


def test_target_failed_only_does_not_imply_completion() -> None:
    target = rule(status=PrerequisiteLogicStatus.NOT_APPLICABLE, groups=(), raw=None)
    result = decision(evaluate_can_take(catalog(target), request(attempts=(attempt(TARGET, AttemptOutcome.FAILED),))))

    assert result.target_attempt_state.has_passed_target is False
    assert result.target_attempt_state.has_in_progress_target is False


def test_unrelated_history_does_not_change_decision() -> None:
    baseline = decision(evaluate_can_take(catalog(), request()))
    with_unrelated = decision(
        evaluate_can_take(catalog(), request(attempts=(attempt("9999999", AttemptOutcome.PASSED),)))
    )

    assert baseline == with_unrelated


def test_attempt_order_does_not_change_decision() -> None:
    first = decision(
        evaluate_can_take(catalog(), request(attempts=(attempt(PREREQUISITE, AttemptOutcome.FAILED), attempt(PREREQUISITE, AttemptOutcome.PASSED))))
    )
    second = decision(
        evaluate_can_take(catalog(), request(attempts=(attempt(PREREQUISITE, AttemptOutcome.PASSED), attempt(PREREQUISITE, AttemptOutcome.FAILED))))
    )

    assert first == second


def test_dependency_option_order_does_not_change_decision() -> None:
    first = rule(groups=(group(1, "A", "B"),))
    second = rule(groups=(group(1, "B", "A"),))
    attempts = (attempt("A", AttemptOutcome.PASSED),)

    assert decision(evaluate_can_take(catalog(first), request(attempts=attempts))) == decision(
        evaluate_can_take(catalog(second), request(attempts=attempts))
    )


def test_verified_target_without_dependency_groups_requires_review() -> None:
    result = decision(evaluate_can_take(catalog(rule(groups=())), request()))

    assert result.decision is Decision.REVIEW_REQUIRED
    assert result.review_reasons == (DecisionReason.VERIFIED_PREREQUISITE_MODEL_INCOMPLETE,)


def test_empty_dependency_group_requires_review() -> None:
    result = decision(evaluate_can_take(catalog(rule(groups=(group(1),))), request()))

    assert result.decision is Decision.REVIEW_REQUIRED


def test_duplicate_group_numbers_require_review() -> None:
    result = decision(evaluate_can_take(catalog(rule(groups=(group(1, "A"), group(1, "B")))), request()))

    assert result.decision is Decision.REVIEW_REQUIRED


def test_target_not_found_is_an_error() -> None:
    result = error(evaluate_can_take(catalog(), request(target="9999999")))

    assert result.error_code is RequestErrorCode.TARGET_NOT_FOUND


def test_referenced_only_target_not_in_plan_is_an_error() -> None:
    referenced = CourseIdentity("0300103", CourseCatalogStatus.REFERENCED_ONLY)
    result = error(evaluate_can_take(catalog(extra_courses=(referenced,)), request(target="0300103")))

    assert result.error_code is RequestErrorCode.TARGET_NOT_IN_STUDY_PLAN


def test_target_in_another_plan_is_not_in_this_plan_error() -> None:
    other = CourseIdentity("1509999", CourseCatalogStatus.KNOWN)
    result = error(evaluate_can_take(catalog(extra_courses=(other,)), request(target="1509999")))

    assert result.error_code is RequestErrorCode.TARGET_NOT_IN_STUDY_PLAN


def test_unknown_study_plan_is_an_error() -> None:
    result = error(evaluate_can_take(catalog(), request(study_plan_id="different-plan")))

    assert result.error_code is RequestErrorCode.STUDY_PLAN_NOT_FOUND


def test_empty_course_code_is_invalid_request() -> None:
    result = error(evaluate_can_take(catalog(), request(target="")))

    assert result.error_code is RequestErrorCode.INVALID_REQUEST


def test_empty_attempt_course_code_is_invalid_request() -> None:
    result = error(evaluate_can_take(catalog(), request(attempts=(attempt("", AttemptOutcome.PASSED),))))

    assert result.error_code is RequestErrorCode.INVALID_REQUEST


def test_real_plan_1501112_passed_1501110_is_eligible() -> None:
    target = PlanCourseRule("1501112", PrerequisiteLogicStatus.VERIFIED, (group(1, "1501110"),), "1501110")
    result = decision(evaluate_can_take(catalog(target), request(target="1501112", attempts=(attempt("1501110", AttemptOutcome.PASSED),))))

    assert result.decision is Decision.ELIGIBLE


def test_real_plan_1501112_failed_1501110_is_not_eligible() -> None:
    target = PlanCourseRule("1501112", PrerequisiteLogicStatus.VERIFIED, (group(1, "1501110"),), "1501110")
    result = decision(evaluate_can_take(catalog(target), request(target="1501112", attempts=(attempt("1501110", AttemptOutcome.FAILED),))))

    assert result.decision is Decision.NOT_ELIGIBLE


def test_real_plan_1505320_source_conflict_requires_review() -> None:
    target = PlanCourseRule("1505320", PrerequisiteLogicStatus.SOURCE_CONFLICT, (), "0300103,1505311")
    assert decision(evaluate_can_take(catalog(target), request(target="1505320"))).decision is Decision.REVIEW_REQUIRED


def test_real_plan_1505366_source_conflict_requires_review() -> None:
    target = PlanCourseRule("1505366", PrerequisiteLogicStatus.SOURCE_CONFLICT, (), "0301241,1505101")
    assert decision(evaluate_can_take(catalog(target), request(target="1505366"))).decision is Decision.REVIEW_REQUIRED


def test_real_plan_1505311_unresolved_requires_review() -> None:
    target = PlanCourseRule("1505311", PrerequisiteLogicStatus.UNRESOLVED, (), "1505101,1505201")
    assert decision(evaluate_can_take(catalog(target), request(target="1505311"))).decision is Decision.REVIEW_REQUIRED
