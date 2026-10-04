"""WC-046 pure domain and no-mutation regression evidence."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from app.change_impact.engine import evaluate_change_impact, fingerprint
from app.change_impact.models import (
    ChangeDelta, ChangeType, CourseCreditHoursDelta, ImpactLimitation,
    ImpactStatus, PolicyVersionDelta, PrerequisiteGroupDelta,
    RequirementGroupCreditDelta,
)
from app.progress.models import (
    AcademicProgressCatalog, ProgressPlanCourse, ProgressRequirementGroup,
    ProgressStudyPlan, RequirementType,
)
from app.rules.models import (
    AttemptOutcome, CanTakeCatalog, CourseCatalogStatus, CourseIdentity,
    DependencyGroup, DependencyType, PlanCourseRule, PrerequisiteLogicStatus,
    StudentCourseAttempt,
)


PLAN = UUID("10000000-0000-0000-0000-000000000005")
TENANT = UUID("10000000-0000-0000-0000-000000000001")
GROUP = "10000000-0000-0000-0000-000000000011"


def _prerequisite_catalog(extra: int = 0) -> CanTakeCatalog:
    codes = ("A101", "B101", "C101", "TARGET", "NEXT", *(f"D{i:03}" for i in range(extra)))
    rules = [PlanCourseRule(code, PrerequisiteLogicStatus.NOT_APPLICABLE) for code in codes[:3]]
    rules.extend((
        PlanCourseRule("TARGET", PrerequisiteLogicStatus.VERIFIED,
                       (DependencyGroup(1, DependencyType.PREREQUISITE, ("A101",)),
                        DependencyGroup(2, DependencyType.PREREQUISITE, ("C101",)))),
        PlanCourseRule("NEXT", PrerequisiteLogicStatus.VERIFIED,
                       (DependencyGroup(1, DependencyType.PREREQUISITE, ("TARGET",)),)),
    ))
    rules.extend(PlanCourseRule(f"D{i:03}", PrerequisiteLogicStatus.VERIFIED,
                                (DependencyGroup(1, DependencyType.PREREQUISITE,
                                                 ("TARGET",)),)) for i in range(extra))
    return CanTakeCatalog(str(PLAN), tuple(rules), tuple(
        CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in codes))


def _progress_catalog() -> AcademicProgressCatalog:
    return AcademicProgressCatalog(
        ProgressStudyPlan(str(PLAN), Decimal("12")),
        (ProgressRequirementGroup(GROUP, str(PLAN), "MAJOR", "Major", None,
                                  "major", RequirementType.ELECTIVE, Decimal("6"), 1),),
        (ProgressPlanCourse("pc-1", str(PLAN), GROUP, "A101", CourseCatalogStatus.KNOWN,
                            Decimal("3"), 1),
         ProgressPlanCourse("pc-2", str(PLAN), GROUP, "B101", CourseCatalogStatus.KNOWN,
                            Decimal("3"), 2)),
    )


def _pre(**changes) -> PrerequisiteGroupDelta:
    values = dict(change_type=ChangeType.PREREQUISITE_GROUP_CHANGE, study_plan_id=PLAN,
                  target_course_code="TARGET", group_number=1,
                  dependency_type=DependencyType.PREREQUISITE,
                  old_option_course_codes=("A101",), new_option_course_codes=("B101",),
                  old_version="v1", new_version="v2", provenance_reference="proposal-1")
    values.update(changes)
    return PrerequisiteGroupDelta(**values)


def _req(**changes) -> RequirementGroupCreditDelta:
    values = dict(change_type=ChangeType.REQUIREMENT_GROUP_CREDIT_CHANGE,
                  study_plan_id=PLAN, requirement_group_code="MAJOR",
                  old_required_credits=Decimal("6"), new_required_credits=Decimal("9"),
                  old_version="v1", new_version="v2", provenance_reference="proposal-1")
    values.update(changes)
    return RequirementGroupCreditDelta(**values)


def _credit(**changes) -> CourseCreditHoursDelta:
    values = dict(change_type=ChangeType.COURSE_CREDIT_HOURS_CHANGE,
                  study_plan_id=PLAN, course_code="A101", old_credit_hours=Decimal("3"),
                  new_credit_hours=Decimal("4"), old_version="v1", new_version="v2",
                  provenance_reference="proposal-1")
    values.update(changes)
    return CourseCreditHoursDelta(**values)


def _policy() -> PolicyVersionDelta:
    return PolicyVersionDelta(change_type=ChangeType.POLICY_VERSION_CHANGE,
                              document_code="POLICY-A", affected_topic="admissions",
                              old_version="v1", new_version="v2",
                              provenance_reference="proposal-1")


def test_prerequisite_replace_preserves_baseline_and_uses_existing_eligibility() -> None:
    catalog = _prerequisite_catalog()
    prior = repr(catalog)
    attempts = (StudentCourseAttempt("A101", AttemptOutcome.PASSED),
                StudentCourseAttempt("C101", AttemptOutcome.PASSED))
    report = evaluate_change_impact(_pre(), university_id=TENANT,
                                    eligibility_catalog=catalog, student_attempts=attempts)
    assert report.impact_status is ImpactStatus.CHANGED
    assert report.structurally_affected_courses == ("NEXT", "TARGET")
    target = next(item for item in report.comparisons if item.reference == "TARGET")
    assert (target.before, target.after) == ("ELIGIBLE", "NOT_ELIGIBLE")
    assert repr(catalog) == prior
    assert report.requires_human_review


def test_prerequisite_added_option_respects_or_group_and_second_and_group() -> None:
    catalog = _prerequisite_catalog()
    report = evaluate_change_impact(_pre(new_option_course_codes=("A101", "B101")),
                                    university_id=TENANT, eligibility_catalog=catalog,
                                    student_attempts=(StudentCourseAttempt("B101", AttemptOutcome.PASSED),))
    target = next(item for item in report.comparisons if item.reference == "TARGET")
    assert target.before == "NOT_ELIGIBLE"
    assert target.after == "NOT_ELIGIBLE"  # the separate C101 AND group remains missing


def test_prerequisite_remove_option_and_unchanged_result() -> None:
    catalog = _prerequisite_catalog()
    added = _pre(old_option_course_codes=("A101", "B101"), new_option_course_codes=("A101",))
    altered_rule = replace(catalog.plan_courses[3], dependency_groups=(
        DependencyGroup(1, DependencyType.PREREQUISITE, ("A101", "B101")),
        catalog.plan_courses[3].dependency_groups[1],
    ))
    altered = replace(catalog, plan_courses=(*catalog.plan_courses[:3], altered_rule,
                                              *catalog.plan_courses[4:]))
    result = evaluate_change_impact(added, university_id=TENANT, eligibility_catalog=altered)
    assert result.impact_status is ImpactStatus.CHANGED
    same = evaluate_change_impact(_pre(new_option_course_codes=("A101",)),
                                  university_id=TENANT, eligibility_catalog=catalog)
    assert same.impact_status is ImpactStatus.UNCHANGED


@pytest.mark.parametrize("delta", [
    _pre(old_option_course_codes=("B101",)),
    _req(old_required_credits=Decimal("5")),
    _credit(old_credit_hours=Decimal("5")),
])
def test_baseline_mismatch_fails_closed(delta) -> None:
    report = evaluate_change_impact(delta, university_id=TENANT,
                                    eligibility_catalog=_prerequisite_catalog(),
                                    progress_catalog=_progress_catalog())
    assert report.impact_status is ImpactStatus.REVIEW_REQUIRED
    assert ImpactLimitation.BASELINE_MISMATCH in report.limitations
    assert not report.comparisons


def test_fanout_limit_is_review_not_truncation() -> None:
    report = evaluate_change_impact(_pre(), university_id=TENANT,
                                    eligibility_catalog=_prerequisite_catalog(extra=5),
                                    max_affected_courses=3)
    assert report.impact_status is ImpactStatus.REVIEW_REQUIRED
    assert ImpactLimitation.IMPACT_FANOUT_LIMIT_EXCEEDED in report.limitations
    assert not report.structurally_affected_courses


@pytest.mark.parametrize(("new", "before", "after"), [
    ("9", "3", "6"), ("3", "3", "0"),
])
def test_requirement_credit_change_recomputes_group_progress(new, before, after) -> None:
    catalog = _progress_catalog()
    original = repr(catalog)
    report = evaluate_change_impact(_req(new_required_credits=Decimal(new)),
                                    university_id=TENANT, progress_catalog=catalog,
                                    student_attempts=(StudentCourseAttempt("A101", AttemptOutcome.PASSED),))
    comparison = next(item for item in report.comparisons
                      if item.reference == "group:MAJOR:remaining_credits")
    assert (comparison.before, comparison.after) == (before, after)
    assert repr(catalog) == original


@pytest.mark.parametrize(("new", "after"), [("4", "4"), ("2", "2")])
def test_course_credit_change_recomputes_completed_progress(new, after) -> None:
    report = evaluate_change_impact(_credit(new_credit_hours=Decimal(new)),
                                    university_id=TENANT, progress_catalog=_progress_catalog(),
                                    student_attempts=(StudentCourseAttempt("A101", AttemptOutcome.PASSED),))
    comparison = next(item for item in report.comparisons
                      if item.reference == "completed_plan_credits")
    assert comparison.before == "3" and comparison.after == after


def test_policy_change_does_not_invent_academic_rule_effect() -> None:
    report = evaluate_change_impact(_policy(), university_id=TENANT)
    assert report.impact_status is ImpactStatus.REVIEW_REQUIRED
    assert report.affected_decision_types == ("POLICY_CONSULTATION",)
    assert not report.structurally_affected_courses
    assert not report.comparisons
    assert ImpactLimitation.POLICY_CHANGE_NOT_MAPPED_TO_DETERMINISTIC_RULE in report.limitations


def test_stable_fingerprint_and_ordering() -> None:
    first = _pre(new_option_course_codes=("B101", "A101"))
    second = _pre(new_option_course_codes=("A101", "B101"))
    assert fingerprint(first, university_id=TENANT) == fingerprint(second, university_id=TENANT)
    assert fingerprint(first, university_id=TENANT) == fingerprint(
        _pre(new_option_course_codes=("A101", "B101"),
             provenance_reference="different-proposal"), university_id=TENANT)
    assert fingerprint(first, university_id=TENANT) != fingerprint(_pre(), university_id=TENANT)
    assert fingerprint(first, university_id=TENANT) != fingerprint(
        first, university_id=UUID("10000000-0000-0000-0000-000000000002"))
    assert evaluate_change_impact(first, university_id=TENANT,
                                  eligibility_catalog=_prerequisite_catalog()).structurally_affected_courses == (
                                      "NEXT", "TARGET")


def test_provenance_is_not_echoed_into_analyst_report() -> None:
    marker = "sensitive-client-supplied-label"
    report = evaluate_change_impact(_pre(provenance_reference=marker), university_id=TENANT,
                                    eligibility_catalog=_prerequisite_catalog())
    assert marker not in report.model_dump_json()
    assert report.provenance_reference.startswith("sha256:")


def test_closed_input_registry_validation_and_bounds() -> None:
    adapter = TypeAdapter(ChangeDelta)
    with pytest.raises(ValidationError):
        adapter.validate_python({**_pre().model_dump(), "change_type": "ARBITRARY"})
    with pytest.raises(ValidationError):
        _pre(old_version="v1", new_version="v1")
    with pytest.raises(ValidationError):
        _pre(new_option_course_codes=("B101", "B101"))
    with pytest.raises(ValidationError):
        _credit(new_credit_hours=Decimal("NaN"))
    with pytest.raises(ValueError):
        evaluate_change_impact(_pre(), university_id=TENANT,
                               eligibility_catalog=_prerequisite_catalog(), max_affected_courses=101)
