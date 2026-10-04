"""Exact Plan 12 AI Project rule; no display-name or reported-credit trust."""

from decimal import Decimal

import pytest

from app.api.routes.eligibility import _decision_response
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    AttemptOutcome, CanTakeCatalog, CanTakeDecision, CanTakeRequest,
    CourseCatalogStatus, CourseIdentity, Decision, DependencyGroup,
    DependencyType, PlanCourseRule, PrerequisiteLogicStatus, StudentCourseAttempt,
)
from app.rules.project_credits import PLAN12_ID, PROJECT_CODES, RULE_ID
from app.progress.models import (AcademicProgressCatalog, ProgressPlanCourse,
                                 ProgressRequirementGroup, ProgressStudyPlan, RequirementType)
from app.recommendations.engine import recommend_courses


def catalog(*, complete=False):
    return CanTakeCatalog(
        PLAN12_ID,
        (PlanCourseRule("1505467", PrerequisiteLogicStatus.NOT_APPLICABLE,
                        credit_hours=Decimal("3")),
         PlanCourseRule("1505468", PrerequisiteLogicStatus.VERIFIED,
                        (DependencyGroup(1, DependencyType.PREREQUISITE,
                                         ("1505467",)),), credit_hours=Decimal("3")),
         PlanCourseRule("OTHER", PrerequisiteLogicStatus.NOT_APPLICABLE,
                        credit_hours=Decimal("90"))),
        tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN)
              for code in ("1505467", "1505468", "OTHER")),
        complete_plan_credits=complete,
    )


@pytest.mark.parametrize("credits,expected", [
    ("89", Decision.NOT_ELIGIBLE), ("89.99", Decision.NOT_ELIGIBLE),
    ("90", Decision.ELIGIBLE), ("91", Decision.ELIGIBLE),
])
def test_project_one_earned_credit_boundary(credits, expected):
    result = evaluate_can_take(catalog(), CanTakeRequest(
        PLAN12_ID, "1505467", (), Decimal(credits)))
    assert isinstance(result, CanTakeDecision) and result.decision is expected
    trace = result.academic_rule_traces[0]
    assert trace.rule_id == RULE_ID and trace.required_credits == Decimal(90)
    assert trace.earned_completed_credits == Decimal(credits)
    assert trace.rule_version and trace.provenance and trace.reason_ar and trace.reason_en
    assert _decision_response(result).academic_rule_traces[0].result == (
        "BLOCKED" if expected is Decision.NOT_ELIGIBLE else "SATISFIED")


def test_project_two_keeps_separate_prerequisite_at_90():
    blocked = evaluate_can_take(catalog(), CanTakeRequest(
        PLAN12_ID, "1505468", (), Decimal("90")))
    assert isinstance(blocked, CanTakeDecision) and blocked.decision is Decision.NOT_ELIGIBLE
    assert blocked.missing_dependency_groups
    passed = (StudentCourseAttempt("1505467", AttemptOutcome.PASSED),)
    eligible = evaluate_can_take(catalog(), CanTakeRequest(
        PLAN12_ID, "1505468", passed, Decimal("90")))
    assert isinstance(eligible, CanTakeDecision) and eligible.decision is Decision.ELIGIBLE


def test_only_passed_plan_course_credits_count_when_snapshot_complete():
    attempts = (StudentCourseAttempt("OTHER", AttemptOutcome.FAILED),
                StudentCourseAttempt("OTHER", AttemptOutcome.IN_PROGRESS),
                StudentCourseAttempt("OTHER", AttemptOutcome.WITHDRAWN))
    blocked = evaluate_can_take(catalog(complete=True), CanTakeRequest(PLAN12_ID, "1505467", attempts))
    assert isinstance(blocked, CanTakeDecision) and blocked.decision is Decision.NOT_ELIGIBLE
    assert blocked.academic_rule_traces[0].earned_completed_credits == 0
    passed = evaluate_can_take(catalog(complete=True), CanTakeRequest(
        PLAN12_ID, "1505467", attempts + (StudentCourseAttempt("OTHER", AttemptOutcome.PASSED),)))
    assert isinstance(passed, CanTakeDecision) and passed.decision is Decision.ELIGIBLE


def test_incomplete_credit_evidence_fails_closed_and_scope_is_exact():
    unknown = evaluate_can_take(catalog(), CanTakeRequest(PLAN12_ID, "1505467", ()))
    assert isinstance(unknown, CanTakeDecision) and unknown.decision is Decision.REVIEW_REQUIRED
    assert unknown.academic_rule_traces[0].result == "UNKNOWN"
    other_plan = CanTakeCatalog("other-plan", catalog().plan_courses, catalog().courses)
    unaffected = evaluate_can_take(other_plan, CanTakeRequest("other-plan", "1505467", ()))
    assert isinstance(unaffected, CanTakeDecision) and unaffected.decision is Decision.ELIGIBLE
    assert not unaffected.academic_rule_traces
    assert PROJECT_CODES == {"1505467", "1505468"}


def test_project_credit_gate_precedes_eligible_only_recommendation_ranking():
    group = ProgressRequirementGroup("group", PLAN12_ID, "MAJOR_REQUIRED", "Required",
                                     "Required", "major", RequirementType.REQUIRED,
                                     Decimal("96"), 1)
    progress_catalog = AcademicProgressCatalog(
        ProgressStudyPlan(PLAN12_ID, Decimal("96")), (group,),
        tuple(ProgressPlanCourse(f"pc-{code}", PLAN12_ID, "group", code,
                                 CourseCatalogStatus.KNOWN, Decimal(hours), index)
              for index, (code, hours) in enumerate((
                  ("OTHER", "90"), ("1505467", "3"), ("1505468", "3")), 1)),
    )
    before = recommend_courses(progress_catalog, catalog(complete=True), ())
    before_codes = {item.course_code for item in before.ranked_recommendations}
    assert "1505467" not in before_codes and "1505468" not in before_codes
    after = recommend_courses(progress_catalog, catalog(complete=True),
                              (StudentCourseAttempt("OTHER", AttemptOutcome.PASSED),))
    after_codes = {item.course_code for item in after.ranked_recommendations}
    assert "1505467" in after_codes and "1505468" not in after_codes
