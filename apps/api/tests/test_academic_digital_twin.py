"""P5.2 Academic Digital Twin V1 contract, orchestration, and matrix tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from decimal import Decimal
from pathlib import Path
from time import perf_counter

import pytest

from app.academic_digital_twin.comparison import (
    compare_baseline_to_scenario,
    compare_scenarios,
)
from app.academic_digital_twin.deltas import delay_delta, extract_deltas
from app.academic_digital_twin.engine import evaluate_scenario
from app.degree_path.models import DegreePathComputationTimeout
from app.academic_digital_twin.fingerprint import calculate_base_state_fingerprint
from app.academic_digital_twin.models import (
    AuthoritativeAcademicSnapshot,
    AuthoritativeAttempt,
    DeltaType,
    EligibilityFact,
    ModeledCourseCompletion,
    OperationId,
    PlanIdentity,
    PlanningConstraintBundle,
    ScenarioIdentity,
    ScenarioOperation,
    ScenarioStatus,
    SimulationProvenanceClass,
    StateKind,
    ValidationCode,
)
from app.degree_path.models import DegreePathConstraints
from app.planner.models import PlannerConstraints
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
    Decision,
    PlanCourseRule,
    PrerequisiteLogicStatus,
)

PLAN = "sandbox-plan-v1"


def _group(group_id, code, kind, credits, order):
    return ProgressRequirementGroup(
        group_id,
        PLAN,
        code,
        f"Arabic {code}",
        code,
        "major",
        kind,
        Decimal(credits),
        order,
    )


def _course(code, group, credits="3", order=1, status=CourseCatalogStatus.KNOWN):
    return ProgressPlanCourse(f"pc-{code}", PLAN, group, code, status, Decimal(credits), order)


def _rule(code, prereq=None, status=PrerequisiteLogicStatus.NOT_APPLICABLE):
    groups = ()
    if prereq is not None:
        groups = (DependencyGroup(1, DependencyType.PREREQUISITE, (prereq,)),)
    return PlanCourseRule(code, status, groups, prereq, f"Arabic {code}")


def _snapshot(*attempts, conflict=False, plan=PLAN):
    groups = (
        _group("required", "REQUIRED", RequirementType.REQUIRED, "6", 1),
        _group("zero", "ZERO", RequirementType.REQUIRED, "0", 2),
        _group("elective", "ELECTIVE", RequirementType.ELECTIVE, "3", 3),
    )
    courses = (
        _course("A", "required", order=1),
        _course("B", "required", order=2),
        _course("Z", "zero", credits="0", order=3),
        _course("E1", "elective", order=4),
        _course("E2", "elective", order=5),
    )
    rules = (
        _rule("A"),
        _rule("B", "A", PrerequisiteLogicStatus.SOURCE_CONFLICT if conflict else PrerequisiteLogicStatus.VERIFIED),
        _rule("Z"),
        _rule("E1"),
        _rule("E2"),
    )
    progress_catalog = AcademicProgressCatalog(
        ProgressStudyPlan(PLAN, Decimal("9")), groups, courses
    )
    eligibility_catalog = CanTakeCatalog(
        PLAN,
        rules,
        tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in ("A", "B", "Z", "E1", "E2"))
        + (CourseIdentity("REF", CourseCatalogStatus.REFERENCED_ONLY),),
    )
    authoritative_attempts = tuple(
        AuthoritativeAttempt(code, outcome, index + 1, "SYNTHETIC_VERIFIED", "VERIFIED")
        for index, (code, outcome) in enumerate(attempts)
    )
    engine_attempts = tuple(item.as_engine_attempt() for item in authoritative_attempts)
    current = calculate_academic_progress(progress_catalog, engine_attempts)
    return AuthoritativeAcademicSnapshot(
        "owner-1",
        PlanIdentity("sandbox-university", "sandbox-major", plan, "2026-v1"),
        authoritative_attempts,
        eligibility_catalog,
        progress_catalog,
        current,
        PlannerConstraints(Decimal("6"), 2, 3),
        DegreePathConstraints(Decimal("6"), 2, 6, 2),
        ("sandbox-catalog:v1",),
        ("PHASE5:1.0", "PHASE6:1.0", "PHASE7:1.0", "PHASE8:1.0", "PHASE9:1.0", "P3:1.0", "P4:1.0"),
    )


def _identity(snapshot, *operations, scenario="scenario-1", fingerprint=None):
    return ScenarioIdentity(
        scenario,
        fingerprint or calculate_base_state_fingerprint(snapshot),
        tuple(operations),
    )


def _completion(code):
    return ScenarioOperation(OperationId.MODEL_COURSE_COMPLETION.value, code)


def _codes(result):
    return {item.code for item in result.validation_issues}


def test_supported_operation_status_and_delta_registries_are_locked():
    assert len(OperationId) == 3
    assert len(ScenarioStatus) == 5
    assert len(DeltaType) == 16


def test_valid_completion_uses_separate_modeled_pass_and_recomputes():
    snapshot = _snapshot()
    original = deepcopy(snapshot)
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion("A")))
    assert result.lifecycle_status is ScenarioStatus.EVALUATED
    assert isinstance(result.modeled_completion, ModeledCourseCompletion)
    assert result.modeled_completion.provenance is SimulationProvenanceClass.MODELED_OPERATION
    assert result.modeled_completion.outcome is AttemptOutcome.PASSED
    assert result.base_state_summary.state_kind is StateKind.AUTHORITATIVE_STATE
    assert result.modeled_state_summary.state_kind is StateKind.MODELED_STATE
    assert result.base_outputs is not None and result.modeled_outputs is not None
    assert snapshot == original
    assert snapshot.attempts == ()


def test_what_if_propagates_bounded_degree_path_cancellation() -> None:
    snapshot = _snapshot()
    calls = 0

    def check_budget() -> None:
        nonlocal calls
        calls += 1
        if calls >= 4:
            raise DegreePathComputationTimeout("expired")

    with pytest.raises(DegreePathComputationTimeout):
        evaluate_scenario(snapshot, _identity(snapshot, _completion("A")), check_budget=check_budget)
    assert calls >= 4


def test_elective_with_remaining_need_is_supported():
    snapshot = _snapshot()
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion("E1")))
    assert result.lifecycle_status is ScenarioStatus.EVALUATED
    assert result.modeled_completion.course_code == "E1"


def test_t51_satisfied_elective_group_is_invalid_without_application_or_recompute():
    snapshot = _snapshot(("E1", AttemptOutcome.PASSED))
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion("E2")))
    assert result.lifecycle_status is ScenarioStatus.INVALID
    assert _codes(result) == {ValidationCode.ELECTIVE_GROUP_ALREADY_SATISFIED}
    assert result.modeled_completion is None
    assert result.operation_results == ()
    assert result.base_outputs is None and result.modeled_outputs is None
    assert result.deltas == ()
    assert result.modeled_state_summary is None


@pytest.mark.parametrize(
    ("attempt", "code"),
    [
        (("A", AttemptOutcome.PASSED), ValidationCode.TARGET_ALREADY_COMPLETED),
        (("A", AttemptOutcome.IN_PROGRESS), ValidationCode.TARGET_IN_PROGRESS),
    ],
)
def test_protected_target_states_are_rejected(attempt, code):
    snapshot = _snapshot(attempt)
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion("A")))
    assert result.lifecycle_status is ScenarioStatus.INVALID
    assert code in _codes(result)


@pytest.mark.parametrize(
    ("target", "code"),
    [("UNKNOWN", ValidationCode.UNKNOWN_COURSE), ("REF", ValidationCode.TARGET_NOT_PLAN_MEMBER)],
)
def test_unknown_and_referenced_only_targets_are_rejected(target, code):
    snapshot = _snapshot()
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion(target)))
    assert result.lifecycle_status is ScenarioStatus.INVALID
    assert code in _codes(result)


def test_source_conflict_returns_review_required_without_modeled_pass():
    snapshot = _snapshot(conflict=True)
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion("B")))
    assert result.lifecycle_status is ScenarioStatus.REVIEW_REQUIRED
    assert _codes(result) == {ValidationCode.TARGET_REVIEW_REQUIRED}
    assert result.modeled_completion is None
    assert result.deltas == ()


def test_zero_credit_completion_can_change_structure_without_credit_delta():
    snapshot = _snapshot()
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion("Z")))
    assert result.lifecycle_status is ScenarioStatus.EVALUATED
    assert result.base_state_summary.completed_plan_credits == result.modeled_state_summary.completed_plan_credits
    assert DeltaType.COMPLETED_PLAN_CREDIT_DELTA not in {item.delta_type for item in result.deltas}
    assert DeltaType.NEWLY_MODELED_COMPLETED_REQUIREMENT in {item.delta_type for item in result.deltas}


def test_failed_history_is_preserved_and_not_reclassified_as_real_pass():
    snapshot = _snapshot(("A", AttemptOutcome.FAILED), ("A", AttemptOutcome.FAILED))
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion("A")))
    assert [item.outcome for item in snapshot.attempts] == [AttemptOutcome.FAILED, AttemptOutcome.FAILED]
    assert result.modeled_completion.outcome is AttemptOutcome.PASSED
    assert len(snapshot.attempts) == 2


def test_planning_constraint_operation_reuses_validated_phase8_and_phase9_types():
    snapshot = _snapshot()
    bundle = PlanningConstraintBundle(Decimal("3"), 1, 2, Decimal("3"), 1, 4, 2)
    operation = ScenarioOperation(OperationId.SET_PLANNING_CONSTRAINTS.value, constraints=bundle)
    result = evaluate_scenario(snapshot, _identity(snapshot, operation))
    assert result.lifecycle_status is ScenarioStatus.EVALUATED
    assert result.modeled_outputs.semester_plan.constraints.max_credit_hours == Decimal("3")
    assert result.modeled_outputs.degree_path.constraints.max_semesters_ahead == 4


def test_invalid_constraints_are_not_clamped_and_apply_nothing():
    snapshot = _snapshot()
    bundle = PlanningConstraintBundle(Decimal("30.01"))
    operation = ScenarioOperation(OperationId.SET_PLANNING_CONSTRAINTS.value, constraints=bundle)
    result = evaluate_scenario(snapshot, _identity(snapshot, operation))
    assert result.lifecycle_status is ScenarioStatus.INVALID
    assert _codes(result) == {ValidationCode.INVALID_CONSTRAINT}
    assert result.base_outputs is None and result.modeled_outputs is None


def test_one_constraint_and_one_structural_operation_use_canonical_order():
    snapshot = _snapshot()
    constraints = ScenarioOperation(
        OperationId.SET_PLANNING_CONSTRAINTS.value,
        constraints=PlanningConstraintBundle(Decimal("3"), 1, 1),
    )
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion("A"), constraints))
    assert result.lifecycle_status is ScenarioStatus.EVALUATED
    assert [item.operation_id for item in result.operation_results] == [
        OperationId.SET_PLANNING_CONSTRAINTS.value,
        OperationId.MODEL_COURSE_COMPLETION.value,
    ]


@pytest.mark.parametrize(
    ("operations", "code"),
    [
        ((), ValidationCode.REQUIRED_CONTEXT_MISSING),
        ((_completion("A"), _completion("A")), ValidationCode.DUPLICATE_OPERATION),
        (
            (_completion("A"), ScenarioOperation(OperationId.OMIT_NEXT_PLAN_COURSE.value, "B")),
            ValidationCode.CONFLICTING_OPERATIONS,
        ),
    ],
)
def test_atomic_operation_set_rejection(operations, code):
    snapshot = _snapshot()
    result = evaluate_scenario(snapshot, _identity(snapshot, *operations))
    assert result.lifecycle_status is ScenarioStatus.INVALID
    assert code in _codes(result)
    assert result.operation_results == ()


@pytest.mark.parametrize(
    ("operation_id", "code"),
    [
        ("TWIN_OP_MODEL_COURSE_FAILURE", ValidationCode.OPERATION_DEFERRED),
        ("TWIN_OP_SET_GRADE_OR_GPA", ValidationCode.OPERATION_FORBIDDEN),
        ("TWIN_OP_NOT_REGISTERED", ValidationCode.UNKNOWN_OPERATION),
    ],
)
def test_closed_operation_registry(operation_id, code):
    snapshot = _snapshot()
    operation = ScenarioOperation(operation_id, "A")
    result = evaluate_scenario(snapshot, _identity(snapshot, operation))
    assert result.lifecycle_status is ScenarioStatus.INVALID
    assert code in _codes(result)


def test_stale_fingerprint_stops_before_execution():
    snapshot = _snapshot()
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion("A"), fingerprint="0" * 64))
    assert result.lifecycle_status is ScenarioStatus.STALE_BASE_STATE
    assert _codes(result) == {ValidationCode.STALE_BASE_STATE}
    assert result.base_outputs is None


def test_fingerprint_is_order_independent_and_privacy_minimized():
    snapshot = _snapshot(("E1", AttemptOutcome.FAILED), ("A", AttemptOutcome.PASSED))
    reordered = replace(
        snapshot,
        attempts=tuple(reversed(snapshot.attempts)),
        eligibility_catalog=replace(
            snapshot.eligibility_catalog,
            plan_courses=tuple(reversed(snapshot.eligibility_catalog.plan_courses)),
            courses=tuple(reversed(snapshot.eligibility_catalog.courses)),
        ),
        progress_catalog=replace(
            snapshot.progress_catalog,
            requirement_groups=tuple(reversed(snapshot.progress_catalog.requirement_groups)),
            plan_courses=tuple(reversed(snapshot.progress_catalog.plan_courses)),
        ),
    )
    assert calculate_base_state_fingerprint(snapshot) == calculate_base_state_fingerprint(reordered)
    assert calculate_base_state_fingerprint(snapshot) == calculate_base_state_fingerprint(
        replace(snapshot, owner_scope_id="other-owner")
    )
    assert not {"name", "email", "phone", "raw_grade"} & {item.name for item in fields(AuthoritativeAcademicSnapshot)}


def test_decision_relevant_changes_change_fingerprint():
    snapshot = _snapshot()
    changed = _snapshot(("A", AttemptOutcome.PASSED))
    assert calculate_base_state_fingerprint(snapshot) != calculate_base_state_fingerprint(changed)
    changed_versions = replace(snapshot, source_versions=("sandbox-catalog:v2",))
    assert calculate_base_state_fingerprint(snapshot) != calculate_base_state_fingerprint(changed_versions)


def test_same_contract_runs_on_a_second_normalized_plan_without_identifier_leakage():
    first = _snapshot()
    second_id = "second-sandbox-plan"
    progress_catalog = replace(
        first.progress_catalog,
        study_plan=replace(first.progress_catalog.study_plan, study_plan_id=second_id),
        requirement_groups=tuple(
            replace(item, study_plan_id=second_id)
            for item in first.progress_catalog.requirement_groups
        ),
        plan_courses=tuple(
            replace(item, study_plan_id=second_id) for item in first.progress_catalog.plan_courses
        ),
    )
    second = replace(
        first,
        plan_identity=replace(first.plan_identity, study_plan_id=second_id),
        eligibility_catalog=replace(first.eligibility_catalog, study_plan_id=second_id),
        progress_catalog=progress_catalog,
        current_progress=calculate_academic_progress(progress_catalog, ()),
    )
    first_result = evaluate_scenario(first, _identity(first, _completion("A"), scenario="first"))
    second_result = evaluate_scenario(second, _identity(second, _completion("A"), scenario="second"))
    assert first_result.lifecycle_status is second_result.lifecycle_status is ScenarioStatus.EVALUATED
    assert first_result.plan_identity.study_plan_id != second_result.plan_identity.study_plan_id
    assert first_result.scenario_identity.base_state_fingerprint != second_result.scenario_identity.base_state_fingerprint


def test_large_dependency_graph_orchestration_remains_within_inherited_bounds():
    codes = tuple(f"C{index:02d}" for index in range(12))
    group = _group("large-required", "LARGE_REQUIRED", RequirementType.REQUIRED, "36", 1)
    courses = tuple(_course(code, "large-required", order=index + 1) for index, code in enumerate(codes))
    rules = (_rule(codes[0]),) + tuple(
        _rule(code, codes[index - 1], PrerequisiteLogicStatus.VERIFIED)
        for index, code in enumerate(codes[1:], 1)
    )
    progress_catalog = AcademicProgressCatalog(
        ProgressStudyPlan(PLAN, Decimal("36")), (group,), courses
    )
    eligibility_catalog = CanTakeCatalog(
        PLAN,
        rules,
        tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in codes),
    )
    snapshot = AuthoritativeAcademicSnapshot(
        "synthetic-large-owner",
        PlanIdentity("sandbox-university", "large-major", PLAN, "large-v1"),
        (),
        eligibility_catalog,
        progress_catalog,
        calculate_academic_progress(progress_catalog, ()),
        PlannerConstraints(Decimal("3"), 1, 3),
        DegreePathConstraints(Decimal("3"), 1, 16, 2),
        ("synthetic-large:v1",),
        ("PHASE5:1.0", "PHASE6:1.0", "PHASE7:1.0", "PHASE8:1.0", "PHASE9:1.0", "P4:1.0"),
    )
    started = perf_counter()
    result = evaluate_scenario(snapshot, _identity(snapshot, _completion(codes[0]), scenario="large"))
    elapsed = perf_counter() - started
    assert result.lifecycle_status is ScenarioStatus.EVALUATED
    assert result.modeled_outputs.degree_path.total_parent_states_expanded <= 48
    assert elapsed < 3


def test_omit_operation_composes_existing_p4_delay_result():
    snapshot = _snapshot()
    operation = ScenarioOperation(OperationId.OMIT_NEXT_PLAN_COURSE.value, "A")
    result = evaluate_scenario(snapshot, _identity(snapshot, operation))
    assert result.lifecycle_status is ScenarioStatus.EVALUATED
    assert result.delay_consequence is not None
    assert result.delay_consequence.contract_version == "1.0"
    assert result.deltas[0].delta_type is DeltaType.DELAY_CONSEQUENCE_CHANGE


def test_baseline_and_same_base_scenario_comparisons_are_factual():
    snapshot = _snapshot()
    left = evaluate_scenario(snapshot, _identity(snapshot, _completion("A"), scenario="left"))
    right = evaluate_scenario(snapshot, _identity(snapshot, _completion("E1"), scenario="right"))
    baseline = compare_baseline_to_scenario(left)
    comparison = compare_scenarios(left, right)
    assert baseline.left_scenario_reference == "BASELINE"
    assert comparison.left_scenario_reference == "left"
    assert comparison.right_scenario_reference == "right"
    assert not hasattr(comparison, "score")
    assert not hasattr(comparison, "winner")


def test_comparison_rejects_different_base_owner_or_invalid_result():
    snapshot = _snapshot()
    left = evaluate_scenario(snapshot, _identity(snapshot, _completion("A"), scenario="left"))
    other = _snapshot(("E1", AttemptOutcome.FAILED))
    right = evaluate_scenario(other, _identity(other, _completion("A"), scenario="right"))
    with pytest.raises(ValueError, match="base-state fingerprint"):
        compare_scenarios(left, right)
    foreign = replace(left, owner_scope_id="foreign-owner")
    with pytest.raises(ValueError, match="owner scope"):
        compare_scenarios(left, foreign)
    invalid = evaluate_scenario(snapshot, _identity(snapshot, _completion("UNKNOWN")))
    with pytest.raises(ValueError, match="not comparable"):
        compare_baseline_to_scenario(invalid)


def test_identical_runs_and_reordered_inputs_are_deterministic():
    snapshot = _snapshot()
    identity = _identity(snapshot, _completion("A"))
    first = evaluate_scenario(snapshot, identity)
    assert all(evaluate_scenario(snapshot, identity) == first for _ in range(4))
    reordered = replace(
        snapshot,
        eligibility_catalog=replace(
            snapshot.eligibility_catalog,
            plan_courses=tuple(reversed(snapshot.eligibility_catalog.plan_courses)),
            courses=tuple(reversed(snapshot.eligibility_catalog.courses)),
        ),
        progress_catalog=replace(
            snapshot.progress_catalog,
            requirement_groups=tuple(reversed(snapshot.progress_catalog.requirement_groups)),
            plan_courses=tuple(reversed(snapshot.progress_catalog.plan_courses)),
        ),
    )
    reordered = replace(
        reordered,
        current_progress=calculate_academic_progress(reordered.progress_catalog, reordered.engine_attempts),
    )
    reordered_result = evaluate_scenario(reordered, _identity(reordered, _completion("A")))
    assert reordered_result.deltas == first.deltas
    assert reordered_result.modeled_state_summary == first.modeled_state_summary


def test_package_has_no_io_framework_or_persistence_dependency():
    package = Path(__file__).parents[1] / "app" / "academic_digital_twin"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    for forbidden in ("fastapi", "supabase", "httpx", "sqlalchemy", "openai"):
        assert forbidden not in source.lower()


def test_all_16_delta_types_have_positive_absence_and_canonical_coverage():
    snapshot = _snapshot()
    evaluated = evaluate_scenario(snapshot, _identity(snapshot, _completion("A")))
    base = evaluated.base_outputs
    assert base is not None
    observed = {delay_delta("BASELINE", "MODELED_STRUCTURAL_IMPACT", "A").delta_type}

    def record(modeled):
        values = extract_deltas(base, modeled)
        order = {item: index for index, item in enumerate(DeltaType)}
        assert list(values) == sorted(values, key=lambda item: (order[item.delta_type], item.target))
        observed.update(item.delta_type for item in values)

    eligibility = {item.course_code: item for item in base.eligibility}
    record(replace(base, eligibility=tuple(
        EligibilityFact(item.course_code, Decision.ELIGIBLE) if item.course_code == "B" else item
        for item in base.eligibility
    )))
    record(replace(base, eligibility=tuple(
        EligibilityFact(item.course_code, Decision.NOT_ELIGIBLE) if item.course_code == "A" else item
        for item in base.eligibility
    )))
    record(replace(base, eligibility=tuple(
        EligibilityFact(item.course_code, Decision.REVIEW_REQUIRED) if item.course_code == "A" else item
        for item in base.eligibility
    )))

    group = base.progress.requirement_groups[0]
    satisfied_group = replace(group, is_satisfied=True)
    record(replace(base, progress=replace(
        base.progress,
        requirement_groups=(satisfied_group, *base.progress.requirement_groups[1:]),
        completed_plan_credits=base.progress.completed_plan_credits + Decimal("3"),
        remaining_plan_credits=base.progress.remaining_plan_credits - Decimal("3"),
    )))
    reverse_base = replace(base, progress=replace(
        base.progress,
        requirement_groups=(satisfied_group, *base.progress.requirement_groups[1:]),
    ))
    reverse_values = extract_deltas(reverse_base, base)
    observed.update(item.delta_type for item in reverse_values)

    recommendations = base.recommendations.ranked_recommendations
    assert len(recommendations) >= 2
    record(replace(base, recommendations=replace(
        base.recommendations, ranked_recommendations=recommendations[:-1]
    )))
    record(replace(base, recommendations=replace(
        base.recommendations, ranked_recommendations=tuple(reversed(recommendations))
    )))
    record(replace(base, semester_plan=replace(base.semester_plan, plan_options=())))
    record(replace(base, degree_path=replace(base.degree_path, paths=())))
    if base.degree_path.paths and base.degree_path.paths[0].status.value == "MODELED_COMPLETE":
        changed_path = replace(
            base.degree_path.paths[0], semester_count=base.degree_path.paths[0].semester_count + 1
        )
        record(replace(base, degree_path=replace(base.degree_path, paths=(changed_path,))))
    else:
        completed = evaluated.modeled_outputs.degree_path.paths[0]
        completed = replace(completed, status=type(completed.status).MODELED_COMPLETE)
        completed_base = replace(base, degree_path=replace(base.degree_path, paths=(completed,)))
        changed = replace(completed, semester_count=completed.semester_count + 1)
        values = extract_deltas(completed_base, replace(completed_base, degree_path=replace(completed_base.degree_path, paths=(changed,))))
        observed.update(item.delta_type for item in values)
    record(replace(base, structural_warnings=("STRUCTURAL_WARNING",)))

    assert extract_deltas(base, base) == ()
    assert observed == set(DeltaType)


def test_committed_matrix_has_all_51_stable_ids():
    matrix = Path(__file__).parents[2] / ".." / "docs" / "digital-twin-test-matrix.md"
    text = matrix.resolve().read_text(encoding="utf-8")
    ids = [f"TWIN-T{number:02d}" for number in range(1, 52)]
    assert all(f"`{item}`" in text for item in ids)
    assert text.count("| `TWIN-T") == 51
