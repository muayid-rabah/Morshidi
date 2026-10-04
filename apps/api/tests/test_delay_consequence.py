"""P4.2 Delay Consequence policy matrix and boundary tests."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from time import perf_counter

import pytest

from app.decision_intelligence.delay import analyze_delay, compare_degree_path_results
from app.decision_intelligence.models import (
    DegreePathRunContext,
    DelayConsequenceInput,
    DelayReason,
    DelayEvidenceType,
    DelayStatus,
    SimulationProvenance,
    SimulationStateKind,
)
from app.degree_path.models import (
    DegreePathConstraints,
    DegreePathOption,
    DegreePathResult,
    ModeledSemesterEntry,
    PathStatus,
)
from app.planner.models import PlanReasonCode, PlannedCourseEntry, SemesterPlanOption
from app.progress.engine import calculate_academic_progress
from app.progress.models import (
    AcademicProgressCatalog,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CourseCatalogStatus,
    CourseIdentity,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)

PLAN = "synthetic-plan"
PROVENANCE = SimulationProvenance(SimulationStateKind.AUTHORITATIVE, "synthetic-v1")


def _group(
    group_id="required",
    code="SYNTHETIC_REQUIRED",
    kind=RequirementType.REQUIRED,
    credits="3",
    order=1,
):
    return ProgressRequirementGroup(
        group_id, PLAN, code, "مصطنع", "Synthetic", "major", kind, Decimal(credits), order
    )


def _course(code, group_id="required", credits="3", order=1):
    return ProgressPlanCourse(
        f"pc-{code}", PLAN, group_id, code, CourseCatalogStatus.KNOWN,
        Decimal(credits), order,
    )


def _na(code):
    return PlanCourseRule(code, PrerequisiteLogicStatus.NOT_APPLICABLE)


def _dep(code, *groups, status=PrerequisiteLogicStatus.VERIFIED):
    dependencies = tuple(
        DependencyGroup(index + 1, DependencyType.PREREQUISITE, tuple(options))
        for index, options in enumerate(groups)
    )
    return PlanCourseRule(code, status, dependencies, "synthetic")


def _catalogs(groups, courses, rules, extra_identities=()):
    total = sum((group.required_credit_hours for group in groups), Decimal("0"))
    progress = AcademicProgressCatalog(
        ProgressStudyPlan(PLAN, total), tuple(groups), tuple(courses)
    )
    identities = {item.course_code: item for item in extra_identities}
    for course in courses:
        identities.setdefault(course.course_code, CourseIdentity(course.course_code, course.catalog_status))
    for rule in rules:
        identities.setdefault(rule.course_code, CourseIdentity(rule.course_code, CourseCatalogStatus.KNOWN))
        for dependency_group in rule.dependency_groups:
            for option in dependency_group.option_course_codes:
                identities.setdefault(option, CourseIdentity(option, CourseCatalogStatus.REFERENCED_ONLY))
    eligibility = CanTakeCatalog(PLAN, tuple(rules), tuple(identities.values()))
    return progress, eligibility


def _input(target, groups, courses, rules, attempts=(), *, extra_identities=(), source_versions=("synthetic:v1",), **kwargs):
    progress_catalog, eligibility_catalog = _catalogs(
        groups, courses, rules, extra_identities
    )
    current = calculate_academic_progress(progress_catalog, tuple(attempts))
    return DelayConsequenceInput(
        target_course_code=target,
        study_plan_id=PLAN,
        student_attempts=tuple(attempts),
        simulation_provenance=PROVENANCE,
        progress_catalog=progress_catalog,
        eligibility_catalog=eligibility_catalog,
        current_progress=current,
        source_versions=source_versions,
        **kwargs,
    )


def _required_chain(*codes, credits=None):
    credits = credits or {code: "3" for code in codes}
    group = _group(credits=str(sum(Decimal(credits[code]) for code in codes)))
    courses = tuple(_course(code, credits=credits[code], order=index + 1) for index, code in enumerate(codes))
    rules = [_na(codes[0])]
    rules.extend(_dep(code, (codes[index - 1],)) for index, code in enumerate(codes[1:], 1))
    return (group,), courses, tuple(rules)


def _reason_values(result):
    return {item.value for item in result.reason_codes}


def test_t01_mandatory_course_with_direct_dependent():
    groups, courses, rules = _required_chain("A", "B")
    result = analyze_delay(_input("A", groups, courses, rules))
    assert result.status is DelayStatus.MODELED_STRUCTURAL_IMPACT
    assert tuple(item.course_code for item in result.directly_affected_courses) == ("B",)
    assert DelayReason.DELAY_DIRECT_DEPENDENCY_AFFECTED in result.reason_codes
    assert {
        DelayEvidenceType.DEPENDENCY_GROUP,
        DelayEvidenceType.DEPENDENCY_OPTION,
        DelayEvidenceType.AFFECTED_COURSE,
    } <= {item.evidence_type for item in result.evidence}


def test_t02_multilevel_dependency_reports_canonical_depth_and_path():
    groups, courses, rules = _required_chain("A", "B", "C")
    result = analyze_delay(_input("A", groups, courses, rules))
    assert result.directly_affected_courses[0].evidence_path == ("A", "B")
    assert result.transitively_affected_courses[0].course_code == "C"
    assert result.transitively_affected_courses[0].minimum_dependency_depth == 2
    assert result.transitively_affected_courses[0].evidence_path == ("A", "B", "C")


def test_t03_elective_substitute_preserves_requirement_progress():
    group = _group("elective", "SYNTHETIC_ELECTIVE", RequirementType.ELECTIVE, "3")
    courses = (_course("A", "elective", order=1), _course("X", "elective", order=2))
    rules = (_na("A"), _na("X"))
    result = analyze_delay(_input("A", (group,), courses, rules))
    assert result.status is DelayStatus.NO_MODELED_STRUCTURAL_IMPACT
    assert result.requirement_impacts == ()
    assert DelayReason.DELAY_ELECTIVE_SUBSTITUTE_AVAILABLE in result.reason_codes


def test_t04_elective_without_substitute_has_requirement_and_credit_impact():
    group = _group("elective", "SYNTHETIC_ELECTIVE", RequirementType.ELECTIVE, "3")
    result = analyze_delay(_input("A", (group,), (_course("A", "elective"),), (_na("A"),)))
    assert result.status is DelayStatus.MODELED_STRUCTURAL_IMPACT
    assert result.requirement_impacts
    assert result.progress_impact.modeled_completed_credit_delta == Decimal("-3")


def test_t05_zero_credit_required_course_remains_structurally_significant():
    group = _group(credits="0")
    courses = (_course("A", credits="0"),)
    result = analyze_delay(_input("A", (group,), courses, (_na("A"),)))
    assert result.status is DelayStatus.MODELED_STRUCTURAL_IMPACT
    assert result.requirement_impacts
    assert result.progress_impact.modeled_completed_credit_delta == 0


def test_t06_referenced_only_course_is_evidence_not_progress():
    group = _group(credits="3")
    courses = (_course("A"),)
    rules = (_dep("A", ("R",)),)
    attempts = (StudentCourseAttempt("R", AttemptOutcome.PASSED),)
    data = _input(
        "A", (group,), courses, rules, attempts,
        extra_identities=(CourseIdentity("R", CourseCatalogStatus.REFERENCED_ONLY),),
    )
    result = analyze_delay(data)
    assert all(item.requirement_group_code != "R" for item in result.requirement_impacts)
    assert all(item.course_code != "R" for item in data.current_progress.courses)


def test_t07_referenced_only_target_is_insufficient_not_promoted_to_plan():
    group = _group(credits="3")
    data = _input(
        "R", (group,), (_course("A"),), (_na("A"),),
        extra_identities=(CourseIdentity("R", CourseCatalogStatus.REFERENCED_ONLY),),
    )
    result = analyze_delay(data)
    assert result.status is DelayStatus.INSUFFICIENT_DATA
    assert result.missing_inputs == ("TARGET_NOT_PLAN_MEMBER:referenced_only",)


def test_t08_no_dependency_and_satisfied_elective_group_has_no_impact():
    group = _group("elective", "SYNTHETIC_ELECTIVE", RequirementType.ELECTIVE, "3")
    courses = (_course("DONE", "elective"), _course("A", "elective", order=2))
    attempts = (StudentCourseAttempt("DONE", AttemptOutcome.PASSED),)
    result = analyze_delay(_input("A", (group,), courses, (_na("DONE"), _na("A")), attempts))
    assert result.status is DelayStatus.NO_MODELED_STRUCTURAL_IMPACT
    assert DelayReason.DELAY_NO_MODELED_STRUCTURAL_IMPACT in result.reason_codes


@pytest.mark.parametrize(
    "status",
    [PrerequisiteLogicStatus.SOURCE_CONFLICT, PrerequisiteLogicStatus.UNRESOLVED],
    ids=["T09-source-conflict", "T10-unresolved"],
)
def test_t09_t10_material_ambiguous_downstream_rule_requires_review(status):
    group = _group(credits="6")
    courses = (_course("A"), _course("B", order=2))
    rules = (_na("A"), _dep("B", ("A",), status=status))
    result = analyze_delay(_input("A", (group,), courses, rules))
    assert result.status is DelayStatus.REVIEW_REQUIRED
    assert result.directly_affected_courses == ()
    assert result.reason_codes == (DelayReason.DELAY_REQUIREMENT_PROGRESS_AFFECTED, DelayReason.DELAY_MODELED_CREDIT_PROGRESS_AFFECTED, DelayReason.DELAY_RULE_REVIEW_REQUIRED)


def _path_result(*, semesters=0, status=PathStatus.MODELED_COMPLETE, blockers=(), code="A", credits="3"):
    semester_entries = ()
    if semesters:
        course = PlannedCourseEntry(code, None, None, Decimal(credits), "SYNTHETIC_REQUIRED", "required", 1, False, 1)
        option = SemesterPlanOption(
            1, (course,), Decimal(credits), 1, 1, 0, Decimal(credits), (), 0, (), 0, 1,
            (1, 0, Decimal(credits), 0, Decimal(credits), 1, (code,)),
            (PlanReasonCode.CONTAINS_MANDATORY_COURSES,),
        )
        semester_entries = tuple(
            ModeledSemesterEntry(index + 1, option, Decimal(credits), Decimal("0"), ())
            for index in range(semesters)
        )
    path = DegreePathOption(
        1, status, semester_entries, semesters, semesters, Decimal(credits) * semesters,
        Decimal(credits) * semesters, Decimal(credits) * semesters, Decimal("0"),
        0, (), (), tuple(blockers), semesters,
        (-1, semesters, Decimal("0"), 0, len(blockers), semesters, ()), (),
    )
    return DegreePathResult(
        PLAN, "1.0", "MODELED_DEGREE_PATH_ONLY", DegreePathConstraints(Decimal("12")),
        (path,), Decimal("0"), Decimal("3"), 0, 1,
    )


def test_t11_identical_path_results_are_unchanged():
    baseline = _path_result(semesters=1)
    comparison = compare_degree_path_results(baseline, baseline)
    assert comparison.modeled_registration_set_count_delta == 0
    assert comparison.canonical_path_changed is False

    group = _group("elective", "SYNTHETIC_ELECTIVE", RequirementType.ELECTIVE, "3")
    courses = (_course("DONE", "elective"), _course("A", "elective", order=2))
    attempts = (StudentCourseAttempt("DONE", AttemptOutcome.PASSED),)
    result = analyze_delay(
        _input(
            "A", (group,), courses, (_na("DONE"), _na("A")), attempts,
            baseline_path_result=baseline, delayed_path_result=baseline,
        )
    )
    assert DelayReason.DELAY_MODELED_PATH_UNCHANGED in result.reason_codes


def test_t12_path_count_termination_blocker_and_canonical_changes_are_typed():
    baseline = _path_result(semesters=1, code="A")
    delayed = _path_result(
        semesters=2,
        status=PathStatus.BLOCKED_BY_REVIEW_REQUIRED,
        blockers=("REVIEW_REQUIRED_BLOCKER",),
        code="B",
    )
    comparison = compare_degree_path_results(baseline, delayed)
    assert comparison.modeled_registration_set_count_delta is None
    assert comparison.canonical_path_changed
    assert comparison.introduced_blocker_codes == ("REVIEW_REQUIRED_BLOCKER",)
    assert comparison.delayed_termination_status == "BLOCKED_BY_REVIEW_REQUIRED"

    groups, courses, rules = _required_chain("A")
    result = analyze_delay(
        _input(
            "A", groups, courses, rules,
            baseline_path_result=baseline, delayed_path_result=delayed,
        )
    )
    assert DelayReason.DELAY_MODELED_PATH_CHANGED in result.reason_codes


def test_t13_in_progress_target_requires_review_without_mutation():
    groups, courses, rules = _required_chain("A")
    attempts = (StudentCourseAttempt("A", AttemptOutcome.IN_PROGRESS),)
    result = analyze_delay(_input("A", groups, courses, rules, attempts))
    assert result.status is DelayStatus.REVIEW_REQUIRED
    assert result.reason_codes == (DelayReason.DELAY_TARGET_IN_PROGRESS_UNRESOLVED,)
    assert attempts[0].outcome is AttemptOutcome.IN_PROGRESS


def test_t14_passed_target_is_no_impact_without_history_rewrite():
    groups, courses, rules = _required_chain("A")
    attempts = (StudentCourseAttempt("A", AttemptOutcome.PASSED),)
    result = analyze_delay(_input("A", groups, courses, rules, attempts))
    assert result.status is DelayStatus.NO_MODELED_STRUCTURAL_IMPACT
    assert result.reason_codes == (DelayReason.DELAY_TARGET_ALREADY_COMPLETED,)


def test_t15_no_attempt_history_still_supports_structural_analysis():
    groups, courses, rules = _required_chain("A", "B")
    result = analyze_delay(_input("A", groups, courses, rules))
    assert result.directly_affected_courses
    assert result.current_target_state == "NOT_ATTEMPTED"


@pytest.mark.parametrize(
    "field",
    ["progress_catalog", "eligibility_catalog", "current_progress", "source_versions"],
    ids=["T16-progress", "T16-eligibility", "T16-current", "T16-versions"],
)
def test_t16_partial_context_returns_explicit_insufficient_data(field):
    groups, courses, rules = _required_chain("A")
    data = _input("A", groups, courses, rules)
    value = () if field == "source_versions" else None
    result = analyze_delay(replace(data, **{field: value}))
    assert result.status is DelayStatus.INSUFFICIENT_DATA
    assert result.reason_codes == (DelayReason.DELAY_CONTEXT_INSUFFICIENT,)
    assert result.missing_inputs


def test_t17_absent_optional_phase9_context_preserves_structural_result():
    groups, courses, rules = _required_chain("A", "B")
    result = analyze_delay(_input("A", groups, courses, rules))
    assert result.degree_path_comparison is None
    assert result.status is DelayStatus.MODELED_STRUCTURAL_IMPACT


def test_t18_satisfied_or_alternative_prevents_direct_impact():
    group = _group(credits="9")
    courses = (_course("A"), _course("X", order=2), _course("B", order=3))
    rules = (_na("A"), _na("X"), _dep("B", ("A", "X")))
    attempts = (StudentCourseAttempt("X", AttemptOutcome.PASSED),)
    result = analyze_delay(_input("A", (group,), courses, rules, attempts))
    assert result.directly_affected_courses == ()


def test_t19_unsatisfied_second_and_group_prevents_false_direct_transition():
    group = _group(credits="9")
    courses = (_course("A"), _course("X", order=2), _course("B", order=3))
    rules = (_na("A"), _na("X"), _dep("B", ("A",), ("X",)))
    result = analyze_delay(_input("A", (group,), courses, rules))
    assert result.directly_affected_courses == ()


def test_t20_input_permutations_are_deterministic_and_canonical():
    groups, courses, rules = _required_chain("A", "B", "C")
    forward = analyze_delay(_input("A", groups, courses, rules))
    reverse = analyze_delay(_input("A", groups, tuple(reversed(courses)), tuple(reversed(rules))))
    assert forward == reverse


def test_t21_current_progress_is_unchanged_while_modeled_delta_is_separate():
    groups, courses, rules = _required_chain("A")
    data = _input("A", groups, courses, rules)
    before = data.current_progress
    result = analyze_delay(data)
    assert data.current_progress == before
    assert data.current_progress.completed_plan_credits == 0
    assert result.progress_impact.baseline_completed_plan_credits == 3


def test_t22_plan_isolation_rejects_mismatched_context():
    groups, courses, rules = _required_chain("A")
    data = _input("A", groups, courses, rules)
    wrong = replace(data, study_plan_id="other-plan")
    result = analyze_delay(wrong)
    assert result.status is DelayStatus.INSUFFICIENT_DATA
    assert "PROGRESS_PLAN_MISMATCH" in result.missing_inputs


def test_or_without_satisfied_substitute_creates_direct_impact():
    group = _group(credits="9")
    courses = (_course("A"), _course("X", order=2), _course("B", order=3))
    rules = (_na("A"), _na("X"), _dep("B", ("A", "X")))
    result = analyze_delay(_input("A", (group,), courses, rules))
    assert tuple(item.course_code for item in result.directly_affected_courses) == ("B",)


def test_multiple_direct_dependents_and_cycle_safety_are_canonical():
    group = _group(credits="9")
    courses = (_course("A"), _course("B", order=2), _course("C", order=3))
    rules = (_dep("A", ("C",)), _dep("B", ("A",)), _dep("C", ("A",)))
    result = analyze_delay(_input("A", (group,), courses, rules))
    assert tuple(item.course_code for item in result.directly_affected_courses) == ("B", "C")
    assert len({item.course_code for item in result.transitively_affected_courses}) == len(result.transitively_affected_courses)


def test_delay_traversal_performance_is_bounded_for_synthetic_chain():
    count = 120
    codes = tuple(f"SYN{index:03d}" for index in range(count))
    groups, courses, rules = _required_chain(*codes)
    started = perf_counter()
    result = analyze_delay(_input(codes[0], groups, courses, rules))
    duration = perf_counter() - started
    assert len(result.transitively_affected_courses) == count - 2
    assert duration < 2.0


def test_all_and_only_twelve_delay_reason_codes_exist():
    assert len(DelayReason) == 12
    assert {item.value for item in DelayReason} == {
        "DELAY_TARGET_ALREADY_COMPLETED", "DELAY_TARGET_IN_PROGRESS_UNRESOLVED",
        "DELAY_NO_MODELED_STRUCTURAL_IMPACT", "DELAY_DIRECT_DEPENDENCY_AFFECTED",
        "DELAY_TRANSITIVE_DEPENDENCY_AFFECTED", "DELAY_REQUIREMENT_PROGRESS_AFFECTED",
        "DELAY_MODELED_CREDIT_PROGRESS_AFFECTED", "DELAY_MODELED_PATH_CHANGED",
        "DELAY_MODELED_PATH_UNCHANGED", "DELAY_ELECTIVE_SUBSTITUTE_AVAILABLE",
        "DELAY_RULE_REVIEW_REQUIRED", "DELAY_CONTEXT_INSUFFICIENT",
    }


def test_decision_intelligence_package_has_no_io_framework_imports():
    from pathlib import Path

    package = Path(__file__).parents[1] / "app" / "decision_intelligence"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    for forbidden in ("fastapi", "starlette", "supabase", "httpx", "openai", "sqlalchemy"):
        assert forbidden not in source.lower()
