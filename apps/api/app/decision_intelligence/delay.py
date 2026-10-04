"""Pure deterministic Delay Consequence engine (contract version 1.0)."""

from __future__ import annotations

from collections import deque
from decimal import Decimal

from app.decision_intelligence.models import (
    DELAY_CONSEQUENCE_POLICY_VERSION,
    AffectedCourse,
    DegreePathComparison,
    DelayConsequenceInput,
    DelayConsequenceResult,
    DelayEvidence,
    DelayEvidenceType,
    DelayReason,
    DelayStatus,
    ProgressImpact,
    RequirementImpact,
)
from app.degree_path.models import DegreePathOption, DegreePathResult, PathStatus
from app.progress.engine import calculate_academic_progress
from app.progress.models import (
    AcademicProgress,
    CourseProgressState,
    RequirementType,
)
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    AttemptOutcome,
    CanTakeDecision,
    CanTakeRequest,
    Decision,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)

_LIMITATIONS = (
    "Consequences are structural modeled differences, not graduation-date or calendar predictions.",
    "Course offerings, capacity, timetable, and real registration timing are not modeled.",
    "Phase 9 comparison preserves bounded-search limitations and makes no global-optimality claim.",
)


def analyze_delay(data: DelayConsequenceInput) -> DelayConsequenceResult:
    """Analyze one target without I/O, persistence, mutation, or rule duplication."""
    missing = _missing_context(data)
    if missing:
        return _result(
            data,
            status=DelayStatus.INSUFFICIENT_DATA,
            reasons=(DelayReason.DELAY_CONTEXT_INSUFFICIENT,),
            missing_inputs=missing,
        )

    assert data.progress_catalog is not None
    assert data.eligibility_catalog is not None
    assert data.current_progress is not None
    progress_catalog = data.progress_catalog
    eligibility_catalog = data.eligibility_catalog

    plan_courses = {item.course_code: item for item in progress_catalog.plan_courses}
    rules = {item.course_code: item for item in eligibility_catalog.plan_courses}
    identities = {item.course_code: item for item in eligibility_catalog.courses}
    target_meta = plan_courses.get(data.target_course_code)
    target_rule = rules.get(data.target_course_code)
    if target_meta is None or target_rule is None:
        identity = identities.get(data.target_course_code)
        target_kind = identity.catalog_status.value if identity is not None else "UNKNOWN"
        return _result(
            data,
            status=DelayStatus.INSUFFICIENT_DATA,
            reasons=(DelayReason.DELAY_CONTEXT_INSUFFICIENT,),
            missing_inputs=(f"TARGET_NOT_PLAN_MEMBER:{target_kind}",),
        )

    target_progress = next(
        (item for item in data.current_progress.courses if item.course_code == data.target_course_code),
        None,
    )
    if target_progress is None:
        return _result(
            data,
            status=DelayStatus.INSUFFICIENT_DATA,
            reasons=(DelayReason.DELAY_CONTEXT_INSUFFICIENT,),
            missing_inputs=("TARGET_PROGRESS",),
        )
    if target_progress.state is CourseProgressState.COMPLETED:
        return _result(
            data,
            status=DelayStatus.NO_MODELED_STRUCTURAL_IMPACT,
            reasons=(DelayReason.DELAY_TARGET_ALREADY_COMPLETED,),
            current_target_state=target_progress.state.value,
        )
    if target_progress.state is CourseProgressState.IN_PROGRESS:
        return _result(
            data,
            status=DelayStatus.REVIEW_REQUIRED,
            reasons=(DelayReason.DELAY_TARGET_IN_PROGRESS_UNRESOLVED,),
            current_target_state=target_progress.state.value,
        )
    if target_rule.prerequisite_logic_status in {
        PrerequisiteLogicStatus.UNRESOLVED,
        PrerequisiteLogicStatus.SOURCE_CONFLICT,
    }:
        return _result(
            data,
            status=DelayStatus.REVIEW_REQUIRED,
            reasons=(DelayReason.DELAY_RULE_REVIEW_REQUIRED,),
            current_target_state=target_progress.state.value,
            evidence=(
                DelayEvidence(
                    DelayEvidenceType.TARGET_COURSE,
                    target_rule.prerequisite_logic_status.value,
                    (data.target_course_code,),
                ),
            ),
        )

    baseline_attempts = data.student_attempts + (
        StudentCourseAttempt(data.target_course_code, AttemptOutcome.PASSED),
    )
    delayed_attempts = data.student_attempts

    direct, material_review, dependency_evidence = _direct_impacts(
        data,
        baseline_attempts,
        delayed_attempts,
        rules,
        plan_courses,
    )
    transitive = _transitive_impacts(
        data.target_course_code,
        direct,
        rules,
        plan_courses,
        data.student_attempts,
        progress_catalog,
    )

    baseline_progress = calculate_academic_progress(progress_catalog, baseline_attempts)
    delayed_progress = calculate_academic_progress(progress_catalog, delayed_attempts)
    elective_substitute = False
    target_group = next(
        group
        for group in progress_catalog.requirement_groups
        if group.group_id == target_meta.requirement_group_id
    )
    if target_group.requirement_type is RequirementType.ELECTIVE:
        substitute_progress = _best_elective_substitute_progress(
            data,
            baseline_progress,
            target_meta.requirement_group_id,
            target_meta.course_code,
        )
        if substitute_progress is not None:
            delayed_progress = substitute_progress
            elective_substitute = True

    requirement_impacts = _requirement_impacts(baseline_progress, delayed_progress)
    progress_impact = _progress_impact(baseline_progress, delayed_progress, requirement_impacts)
    path_comparison = compare_degree_path_results(
        data.baseline_path_result,
        data.delayed_path_result,
    )

    reasons: set[DelayReason] = set()
    if direct:
        reasons.add(DelayReason.DELAY_DIRECT_DEPENDENCY_AFFECTED)
    if transitive:
        reasons.add(DelayReason.DELAY_TRANSITIVE_DEPENDENCY_AFFECTED)
    if requirement_impacts:
        reasons.add(DelayReason.DELAY_REQUIREMENT_PROGRESS_AFFECTED)
    if progress_impact is not None and progress_impact.modeled_completed_credit_delta != 0:
        reasons.add(DelayReason.DELAY_MODELED_CREDIT_PROGRESS_AFFECTED)
    if elective_substitute:
        reasons.add(DelayReason.DELAY_ELECTIVE_SUBSTITUTE_AVAILABLE)
    if path_comparison is not None:
        if _path_changed(path_comparison):
            reasons.add(DelayReason.DELAY_MODELED_PATH_CHANGED)
        else:
            reasons.add(DelayReason.DELAY_MODELED_PATH_UNCHANGED)
    if material_review:
        reasons.add(DelayReason.DELAY_RULE_REVIEW_REQUIRED)

    has_impact = bool(
        direct
        or transitive
        or requirement_impacts
        or (progress_impact is not None and progress_impact.modeled_completed_credit_delta != 0)
        or (path_comparison is not None and _path_changed(path_comparison))
    )
    if material_review:
        status = DelayStatus.REVIEW_REQUIRED
    elif has_impact:
        status = DelayStatus.MODELED_STRUCTURAL_IMPACT
    else:
        status = DelayStatus.NO_MODELED_STRUCTURAL_IMPACT
        reasons.add(DelayReason.DELAY_NO_MODELED_STRUCTURAL_IMPACT)

    evidence = list(dependency_evidence)
    evidence.append(
        DelayEvidence(
            DelayEvidenceType.TARGET_COURSE,
            "PLAN_TARGET",
            (data.target_course_code,),
        )
    )
    evidence.extend(
        DelayEvidence(
            DelayEvidenceType.REQUIREMENT_GROUP,
            item.requirement_group_code,
            (data.target_course_code,),
        )
        for item in requirement_impacts
    )
    evidence.extend(
        DelayEvidence(
            DelayEvidenceType.AFFECTED_COURSE,
            f"depth:{item.minimum_dependency_depth}",
            item.evidence_path,
        )
        for item in (*direct, *transitive)
    )
    if progress_impact is not None:
        evidence.append(
            DelayEvidence(
                DelayEvidenceType.PROGRESS_DELTA,
                str(progress_impact.modeled_completed_credit_delta),
                (data.target_course_code,),
            )
        )
    if path_comparison is not None:
        evidence.append(
            DelayEvidence(
                DelayEvidenceType.DEGREE_PATH_COMPARISON,
                "BASELINE_VS_DELAYED",
                (data.target_course_code,),
            )
        )

    return _result(
        data,
        status=status,
        reasons=_canonical_reasons(reasons),
        current_target_state=target_progress.state.value,
        direct=direct,
        transitive=transitive,
        requirement_impacts=requirement_impacts,
        progress_impact=progress_impact,
        path_comparison=path_comparison,
        evidence=tuple(sorted(evidence, key=_evidence_key)),
    )


def compare_degree_path_results(
    baseline: DegreePathResult | None,
    delayed: DegreePathResult | None,
) -> DegreePathComparison | None:
    """Compare results from two unchanged Phase 9 runs over explicit snapshots."""
    if baseline is None or delayed is None:
        return None
    if baseline.study_plan_id != delayed.study_plan_id:
        raise ValueError("Degree path comparison requires the same study plan")
    baseline_path = baseline.paths[0] if baseline.paths else None
    delayed_path = delayed.paths[0] if delayed.paths else None
    baseline_blockers = set(baseline_path.unresolved_blocker_codes if baseline_path else ())
    delayed_blockers = set(delayed_path.unresolved_blocker_codes if delayed_path else ())

    set_delta: int | None = None
    if (
        baseline_path is not None
        and delayed_path is not None
        and baseline_path.status is PathStatus.MODELED_COMPLETE
        and delayed_path.status is PathStatus.MODELED_COMPLETE
    ):
        set_delta = delayed_path.semester_count - baseline_path.semester_count

    credit_delta: Decimal | None = None
    if baseline_path is not None and delayed_path is not None:
        credit_delta = (
            delayed_path.final_completed_plan_credits
            - baseline_path.final_completed_plan_credits
        )

    return DegreePathComparison(
        baseline_path_rank=baseline_path.rank if baseline_path else None,
        delayed_path_rank=delayed_path.rank if delayed_path else None,
        modeled_registration_set_count_delta=set_delta,
        modeled_completed_credit_delta=credit_delta,
        introduced_blocker_codes=tuple(sorted(delayed_blockers - baseline_blockers)),
        removed_blocker_codes=tuple(sorted(baseline_blockers - delayed_blockers)),
        baseline_termination_status=baseline_path.status.value if baseline_path else None,
        delayed_termination_status=delayed_path.status.value if delayed_path else None,
        canonical_path_changed=(
            _canonical_path(baseline_path) != _canonical_path(delayed_path)
        ),
    )


def _missing_context(data: DelayConsequenceInput) -> tuple[str, ...]:
    missing: list[str] = []
    if not data.target_course_code.strip():
        missing.append("TARGET_COURSE_CODE")
    if not data.study_plan_id.strip():
        missing.append("STUDY_PLAN_ID")
    if data.progress_catalog is None:
        missing.append("PROGRESS_CATALOG")
    if data.eligibility_catalog is None:
        missing.append("ELIGIBILITY_CATALOG")
    if data.current_progress is None:
        missing.append("CURRENT_PROGRESS")
    if not data.source_versions:
        missing.append("SOURCE_VERSIONS")
    if data.progress_catalog is not None and data.progress_catalog.study_plan.study_plan_id != data.study_plan_id:
        missing.append("PROGRESS_PLAN_MISMATCH")
    if data.eligibility_catalog is not None and data.eligibility_catalog.study_plan_id != data.study_plan_id:
        missing.append("ELIGIBILITY_PLAN_MISMATCH")
    if data.current_progress is not None and data.current_progress.study_plan_id != data.study_plan_id:
        missing.append("CURRENT_PROGRESS_PLAN_MISMATCH")
    return tuple(sorted(missing))


def _direct_impacts(data, baseline_attempts, delayed_attempts, rules, plan_courses):
    direct: list[AffectedCourse] = []
    material_review = False
    evidence: list[DelayEvidence] = []
    for code in sorted(rules):
        if code == data.target_course_code:
            continue
        rule = rules[code]
        relevant_groups = tuple(
            group
            for group in rule.dependency_groups
            if data.target_course_code in group.option_course_codes
        )
        if not relevant_groups:
            continue
        if rule.prerequisite_logic_status in {
            PrerequisiteLogicStatus.UNRESOLVED,
            PrerequisiteLogicStatus.SOURCE_CONFLICT,
        }:
            material_review = True
            continue
        baseline_decision = evaluate_can_take(
            data.eligibility_catalog,
            CanTakeRequest(data.study_plan_id, code, baseline_attempts),
        )
        delayed_decision = evaluate_can_take(
            data.eligibility_catalog,
            CanTakeRequest(data.study_plan_id, code, delayed_attempts),
        )
        if not isinstance(baseline_decision, CanTakeDecision) or not isinstance(
            delayed_decision, CanTakeDecision
        ):
            continue
        if baseline_decision.decision is Decision.REVIEW_REQUIRED or delayed_decision.decision is Decision.REVIEW_REQUIRED:
            material_review = True
            continue
        if baseline_decision.decision is Decision.ELIGIBLE and delayed_decision.decision is not Decision.ELIGIBLE:
            direct.append(_affected(code, 1, (data.target_course_code, code), plan_courses, data.progress_catalog))
            for group in relevant_groups:
                evidence.append(
                    DelayEvidence(
                        DelayEvidenceType.DEPENDENCY_GROUP,
                        f"{code}:{group.group_number}",
                        tuple(sorted(group.option_course_codes)),
                    )
                )
                evidence.extend(
                    DelayEvidence(
                        DelayEvidenceType.DEPENDENCY_OPTION,
                        f"{code}:{group.group_number}:{option}",
                        (option, code),
                    )
                    for option in sorted(group.option_course_codes)
                )
    return tuple(direct), material_review, tuple(evidence)


def _transitive_impacts(target, direct, rules, plan_courses, attempts, progress_catalog):
    passed = {item.course_code for item in attempts if item.outcome is AttemptOutcome.PASSED}
    unavailable = {target, *(item.course_code for item in direct)}
    paths = {item.course_code: item.evidence_path for item in direct}
    queue = deque(sorted(item.course_code for item in direct))
    transitive: dict[str, AffectedCourse] = {}
    while queue:
        parent = queue.popleft()
        parent_path = paths[parent]
        for code in sorted(rules):
            if code in unavailable:
                continue
            rule = rules[code]
            if rule.prerequisite_logic_status is not PrerequisiteLogicStatus.VERIFIED:
                continue
            affected_group = False
            for group in rule.dependency_groups:
                options = set(group.option_course_codes)
                if parent not in options or options & passed:
                    continue
                if options and options <= unavailable:
                    affected_group = True
                    break
            if not affected_group:
                continue
            path = parent_path + (code,)
            unavailable.add(code)
            paths[code] = path
            transitive[code] = _affected(
                code, len(path) - 1, path, plan_courses, progress_catalog
            )
            queue.append(code)
    return tuple(sorted(transitive.values(), key=lambda item: (item.minimum_dependency_depth, item.course_code)))


def _affected(code, depth, path, plan_courses, progress_catalog):
    meta = plan_courses.get(code)
    requirement_type = None
    if meta is not None and progress_catalog is not None:
        group = next(
            (item for item in progress_catalog.requirement_groups if item.group_id == meta.requirement_group_id),
            None,
        )
        requirement_type = group.requirement_type.value if group is not None else None
    return AffectedCourse(code, depth, path, meta is not None, requirement_type)


def _best_elective_substitute_progress(data, baseline_progress, group_id, target_code):
    assert data.progress_catalog is not None and data.eligibility_catalog is not None
    baseline_group = next(item for item in baseline_progress.requirement_groups if item.group_id == group_id)
    current_states = {item.course_code: item.state for item in data.current_progress.courses}
    candidates: list[AcademicProgress] = []
    for course in sorted(data.progress_catalog.plan_courses, key=lambda item: item.course_code):
        if course.requirement_group_id != group_id or course.course_code == target_code:
            continue
        if current_states.get(course.course_code) in {CourseProgressState.COMPLETED, CourseProgressState.IN_PROGRESS}:
            continue
        decision = evaluate_can_take(
            data.eligibility_catalog,
            CanTakeRequest(data.study_plan_id, course.course_code, data.student_attempts),
        )
        if not isinstance(decision, CanTakeDecision) or decision.decision is not Decision.ELIGIBLE:
            continue
        progress = calculate_academic_progress(
            data.progress_catalog,
            data.student_attempts + (StudentCourseAttempt(course.course_code, AttemptOutcome.PASSED),),
        )
        group = next(item for item in progress.requirement_groups if item.group_id == group_id)
        if (
            group.is_satisfied == baseline_group.is_satisfied
            and group.remaining_required_credits <= baseline_group.remaining_required_credits
        ):
            candidates.append(progress)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda progress: next(
            item.remaining_required_credits
            for item in progress.requirement_groups
            if item.group_id == group_id
        ),
    )


def _requirement_impacts(baseline: AcademicProgress, delayed: AcademicProgress):
    delayed_by_id = {item.group_id: item for item in delayed.requirement_groups}
    impacts: list[RequirementImpact] = []
    for before in baseline.requirement_groups:
        after = delayed_by_id[before.group_id]
        if (
            before.is_satisfied != after.is_satisfied
            or before.remaining_required_credits != after.remaining_required_credits
        ):
            impacts.append(
                RequirementImpact(
                    before.group_code,
                    before.is_satisfied,
                    after.is_satisfied,
                    before.remaining_required_credits,
                    after.remaining_required_credits,
                )
            )
    return tuple(sorted(impacts, key=lambda item: item.requirement_group_code))


def _progress_impact(baseline, delayed, requirement_impacts):
    return ProgressImpact(
        baseline_completed_plan_credits=baseline.completed_plan_credits,
        delayed_completed_plan_credits=delayed.completed_plan_credits,
        modeled_completed_credit_delta=(
            delayed.completed_plan_credits - baseline.completed_plan_credits
        ),
        baseline_remaining_plan_credits=baseline.remaining_plan_credits,
        delayed_remaining_plan_credits=delayed.remaining_plan_credits,
        affected_requirement_group_codes=tuple(
            item.requirement_group_code for item in requirement_impacts
        ),
    )


def _canonical_path(path: DegreePathOption | None) -> tuple[tuple[str, ...], ...]:
    if path is None:
        return ()
    return tuple(
        tuple(course.course_code for course in semester.plan_option.courses)
        for semester in path.semesters
    )


def _path_changed(comparison: DegreePathComparison) -> bool:
    return any(
        (
            comparison.modeled_registration_set_count_delta not in {None, 0},
            comparison.modeled_completed_credit_delta not in {None, Decimal("0")},
            bool(comparison.introduced_blocker_codes),
            bool(comparison.removed_blocker_codes),
            comparison.baseline_termination_status != comparison.delayed_termination_status,
            comparison.canonical_path_changed,
        )
    )


def _canonical_reasons(reasons) -> tuple[DelayReason, ...]:
    values = set(reasons)
    return tuple(reason for reason in DelayReason if reason in values)


def _evidence_key(item: DelayEvidence):
    return (item.evidence_type.value, item.identifier, item.course_codes)


def _result(
    data,
    *,
    status,
    reasons,
    current_target_state=None,
    direct=(),
    transitive=(),
    requirement_impacts=(),
    progress_impact=None,
    path_comparison=None,
    evidence=(),
    missing_inputs=(),
):
    return DelayConsequenceResult(
        contract_version=DELAY_CONSEQUENCE_POLICY_VERSION,
        status=status,
        target_course_code=data.target_course_code,
        current_target_state=current_target_state,
        baseline_scenario_reference=f"{data.simulation_provenance.state_reference}:baseline",
        delayed_scenario_reference=f"{data.simulation_provenance.state_reference}:delay:{data.target_course_code}",
        directly_affected_courses=tuple(direct),
        transitively_affected_courses=tuple(transitive),
        requirement_impacts=tuple(requirement_impacts),
        progress_impact=progress_impact,
        degree_path_comparison=path_comparison,
        reason_codes=_canonical_reasons(reasons),
        evidence=tuple(evidence),
        missing_inputs=tuple(missing_inputs),
        limitations=_LIMITATIONS,
        source_and_policy_versions=tuple(
            sorted(
                {
                    *data.source_versions,
                    f"DELAY_CONSEQUENCE:{DELAY_CONSEQUENCE_POLICY_VERSION}",
                }
            )
        ),
        simulation_provenance=data.simulation_provenance,
    )
