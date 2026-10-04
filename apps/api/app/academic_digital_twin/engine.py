"""Pure orchestration for Academic Digital Twin and What-If V1."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from app.academic_digital_twin.deltas import delay_delta, extract_deltas
from app.academic_digital_twin.models import (
    DIGITAL_TWIN_CONTRACT_VERSION,
    AuthoritativeAcademicSnapshot,
    DigitalTwinEvaluationResult,
    EligibilityFact,
    EngineOutputs,
    ModeledCourseCompletion,
    OperationId,
    OperationResult,
    OperationResultCode,
    ScenarioContext,
    ScenarioIdentity,
    ScenarioStatus,
    SimulationProvenance,
    SimulationProvenanceClass,
    StateKind,
    StateSummary,
)
from app.academic_digital_twin.validation import canonical_operations, validate_scenario
from app.decision_intelligence.engine import (
    evaluate_delay_consequence,
    recommend_with_decision_intelligence,
)
from app.decision_intelligence.models import (
    DecisionMode,
    DelayConsequenceInput,
    SimulationProvenance as P4SimulationProvenance,
    SimulationStateKind,
)
from app.degree_path.engine import plan_degree_paths
from app.planner.engine import plan_semester
from app.progress.engine import calculate_academic_progress
from app.rules.evaluator import evaluate_can_take
from app.rules.models import CanTakeDecision, CanTakeRequest, Decision, StudentCourseAttempt

_LIMITATIONS = (
    "Modeled results are structural, ephemeral, and not authoritative academic records.",
    "No live offerings, timetable, seats, calendar duration, grades, GPA prediction, or registration authority is modeled.",
    "Modeled registration-set counts are not calendar semesters or graduation dates.",
    "Predictive academic risk remains BLOCKED_BY_EXTERNAL_DATA.",
)


def build_scenario_context(
    snapshot: AuthoritativeAcademicSnapshot,
    identity: ScenarioIdentity,
) -> ScenarioContext:
    operations = canonical_operations(identity.operations)
    provenance = SimulationProvenance(
        SimulationProvenanceClass.MODELED_OPERATION,
        identity.scenario_id,
        identity.base_state_fingerprint,
        tuple(item.operation_id for item in operations),
        tuple(sorted(snapshot.source_versions)),
        tuple(sorted(snapshot.engine_policy_versions)),
    )
    return ScenarioContext(snapshot, identity, operations, provenance)


def evaluate_scenario(
    snapshot: AuthoritativeAcademicSnapshot,
    identity: ScenarioIdentity,
    *,
    check_budget: Callable[[], None] | None = None,
) -> DigitalTwinEvaluationResult:
    """Validate atomically, then run unchanged domain engines over isolated tuples."""
    if check_budget is not None:
        check_budget()
    context = build_scenario_context(snapshot, identity)
    failure_status, issues = validate_scenario(snapshot, identity)
    base_summary = _summary(StateKind.AUTHORITATIVE_STATE, snapshot.current_progress, len(snapshot.attempts))
    if failure_status is not None:
        return _result(
            context,
            failure_status,
            base_summary,
            validation_issues=issues,
            missing_inputs=tuple(
                issue.code.value for issue in issues if issue.code.value.endswith("CONTEXT_MISSING")
            ),
        )

    attempts = snapshot.engine_attempts
    planner_constraints = snapshot.baseline_planner_constraints
    path_constraints = snapshot.baseline_path_constraints
    completion: ModeledCourseCompletion | None = None
    structural_operation = None
    operation_results: list[OperationResult] = []

    for operation in context.canonical_operations:
        if operation.operation_id == OperationId.SET_PLANNING_CONSTRAINTS.value:
            bundle = operation.constraints or identity.constraint_bundle
            assert bundle is not None
            planner_constraints = bundle.planner_constraints()
            path_constraints = bundle.path_constraints()
            operation_results.append(
                OperationResult(operation.operation_id, True, OperationResultCode.CONSTRAINTS_APPLIED.value)
            )
        else:
            structural_operation = operation

    base_outputs = _compute_outputs(
        snapshot,
        attempts,
        snapshot.baseline_planner_constraints,
        snapshot.baseline_path_constraints,
        identity.scenario_id,
        StateKind.AUTHORITATIVE_STATE,
        check_budget=check_budget,
    )

    if structural_operation and structural_operation.operation_id == OperationId.OMIT_NEXT_PLAN_COURSE.value:
        target = structural_operation.target_course_code or ""
        delay = evaluate_delay_consequence(
            DelayConsequenceInput(
                target,
                snapshot.plan_identity.study_plan_id,
                attempts,
                _p4_provenance(identity.scenario_id, identity.base_state_fingerprint, StateKind.MODELED_STATE),
                progress_catalog=snapshot.progress_catalog,
                eligibility_catalog=snapshot.eligibility_catalog,
                current_progress=snapshot.current_progress,
                source_versions=tuple(sorted(snapshot.source_versions)),
            )
        )
        operation_results.append(
            OperationResult(
                structural_operation.operation_id,
                True,
                OperationResultCode.DELAY_COMPOSED.value,
                target,
            )
        )
        delta = delay_delta("BASELINE", delay.status.value, target)
        modeled_summary = replace(base_summary, state_kind=StateKind.MODELED_STATE)
        return _result(
            context,
            ScenarioStatus.EVALUATED,
            base_summary,
            modeled_summary=modeled_summary,
            operation_results=tuple(operation_results),
            base_outputs=base_outputs,
            delay_consequence=delay,
            deltas=(delta,),
            decision_traces=("P4_DELAY_CONSEQUENCE_REUSED",),
        )

    if structural_operation:
        target = structural_operation.target_course_code or ""
        completion = ModeledCourseCompletion(target, identity.scenario_id)
        attempts = attempts + (StudentCourseAttempt(target, completion.outcome),)
        operation_results.append(
            OperationResult(
                structural_operation.operation_id,
                True,
                OperationResultCode.MODELED_COMPLETION_APPLIED.value,
                target,
            )
        )

    modeled_outputs = _compute_outputs(
        snapshot,
        attempts,
        planner_constraints,
        path_constraints,
        identity.scenario_id,
        StateKind.MODELED_STATE,
        check_budget=check_budget,
    )
    modeled_summary = _summary(StateKind.MODELED_STATE, modeled_outputs.progress, len(attempts))
    deltas = extract_deltas(base_outputs, modeled_outputs)
    return _result(
        context,
        ScenarioStatus.EVALUATED,
        base_summary,
        modeled_summary=modeled_summary,
        modeled_completion=completion,
        operation_results=tuple(operation_results),
        base_outputs=base_outputs,
        modeled_outputs=modeled_outputs,
        deltas=deltas,
        decision_traces=(
            "PHASE_5>PHASE_6>P3_AUTHORITATIVE_CONTEXT>PHASE_7>P4>PHASE_8>PHASE_9",
        ),
    )


def _compute_outputs(
    snapshot, attempts, planner_constraints, path_constraints, scenario_id, kind,
    *, check_budget: Callable[[], None] | None = None,
):
    if check_budget is not None:
        check_budget()
    progress = calculate_academic_progress(snapshot.progress_catalog, attempts)
    eligibility = []
    for course in sorted(snapshot.progress_catalog.plan_courses, key=lambda item: item.course_code):
        result = evaluate_can_take(
            snapshot.eligibility_catalog,
            CanTakeRequest(snapshot.plan_identity.study_plan_id, course.course_code, attempts),
        )
        if isinstance(result, CanTakeDecision):
            eligibility.append(EligibilityFact(course.course_code, result.decision))
    readiness = dict(snapshot.readiness_by_course)
    enhanced = recommend_with_decision_intelligence(
        snapshot.progress_catalog,
        snapshot.eligibility_catalog,
        attempts,
        mode=DecisionMode.READINESS_AWARE if readiness else DecisionMode.STRUCTURAL_BASELINE,
        readiness_by_course=readiness or None,
        simulation_provenance=_p4_provenance(
            scenario_id,
            calculate_reference(snapshot),
            kind,
        ),
    )
    recommendations = enhanced.baseline_result
    semester = plan_semester(
        snapshot.progress_catalog,
        snapshot.eligibility_catalog,
        attempts,
        recommendations,
        planner_constraints,
        check_budget=check_budget,
    )
    path = plan_degree_paths(
        snapshot.progress_catalog,
        snapshot.eligibility_catalog,
        attempts,
        path_constraints,
        check_budget=check_budget,
    )
    return EngineOutputs(
        tuple(eligibility),
        progress,
        recommendations,
        enhanced,
        semester,
        path,
        tuple(sorted(snapshot.structural_warnings)),
    )


def calculate_reference(snapshot):
    from app.academic_digital_twin.fingerprint import calculate_base_state_fingerprint

    return calculate_base_state_fingerprint(snapshot)


def _p4_provenance(scenario_id, base_reference, kind):
    if kind is StateKind.AUTHORITATIVE_STATE:
        return P4SimulationProvenance(SimulationStateKind.AUTHORITATIVE, base_reference)
    return P4SimulationProvenance(
        SimulationStateKind.SIMULATED,
        f"{base_reference}:scenario:{scenario_id}",
        parent_state_reference=base_reference,
        scenario_id=scenario_id,
    )


def _summary(kind, progress, attempt_count):
    return StateSummary(
        kind,
        progress.study_plan_id,
        progress.completed_plan_credits,
        progress.remaining_plan_credits,
        tuple(sorted(item.group_code for item in progress.requirement_groups if item.is_satisfied)),
        attempt_count,
    )


def _result(
    context,
    status,
    base_summary,
    *,
    modeled_summary=None,
    modeled_completion=None,
    operation_results=(),
    validation_issues=(),
    base_outputs=None,
    modeled_outputs=None,
    delay_consequence=None,
    deltas=(),
    decision_traces=(),
    warnings=(),
    missing_inputs=(),
):
    snapshot = context.authoritative_snapshot
    return DigitalTwinEvaluationResult(
        DIGITAL_TWIN_CONTRACT_VERSION,
        context.scenario_identity,
        status,
        snapshot.owner_scope_id,
        snapshot.plan_identity,
        base_summary,
        modeled_summary,
        modeled_completion,
        tuple(operation_results),
        tuple(validation_issues),
        base_outputs,
        modeled_outputs,
        delay_consequence,
        tuple(deltas),
        tuple(decision_traces),
        tuple(warnings),
        tuple(missing_inputs),
        _LIMITATIONS,
        tuple(sorted(snapshot.engine_policy_versions)),
        context.simulation_provenance,
    )
