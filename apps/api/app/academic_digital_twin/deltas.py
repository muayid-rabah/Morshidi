"""Closed-registry deterministic delta extraction."""

from __future__ import annotations

from app.academic_digital_twin.models import DeltaType, EngineOutputs, TwinDelta


def extract_deltas(base: EngineOutputs, modeled: EngineOutputs) -> tuple[TwinDelta, ...]:
    deltas: list[TwinDelta] = []
    base_eligibility = {item.course_code: item.decision.value for item in base.eligibility}
    modeled_eligibility = {item.course_code: item.decision.value for item in modeled.eligibility}
    for code in sorted(base_eligibility.keys() | modeled_eligibility.keys()):
        before = base_eligibility.get(code, "MISSING")
        after = modeled_eligibility.get(code, "MISSING")
        if before == after:
            continue
        if after == "ELIGIBLE":
            deltas.append(_delta(DeltaType.NEWLY_MODELED_ELIGIBLE, "Phase 5", code, before, after))
            deltas.append(_delta(DeltaType.NEWLY_MODELED_UNLOCKED, "Phase 5", code, before, after))
        if before == "ELIGIBLE" and after != "ELIGIBLE":
            deltas.append(_delta(DeltaType.NO_LONGER_MODELED_ELIGIBLE, "Phase 5", code, before, after))
            deltas.append(_delta(DeltaType.NEWLY_MODELED_BLOCKED, "Phase 5", code, before, after))
        if "REVIEW_REQUIRED" in {before, after}:
            deltas.append(_delta(DeltaType.REVIEW_STATE_CHANGE, "Phase 5", code, before, after))

    base_groups = {item.group_code: item for item in base.progress.requirement_groups}
    modeled_groups = {item.group_code: item for item in modeled.progress.requirement_groups}
    for code in sorted(base_groups.keys() & modeled_groups.keys()):
        before = base_groups[code]
        after = modeled_groups[code]
        if not before.is_satisfied and after.is_satisfied:
            deltas.append(
                _delta(DeltaType.NEWLY_MODELED_COMPLETED_REQUIREMENT, "Phase 6", code, "false", "true")
            )
        if before.is_satisfied and not after.is_satisfied:
            deltas.append(
                _delta(DeltaType.NO_LONGER_MODELED_SATISFIED_REQUIREMENT, "Phase 6", code, "true", "false")
            )
    if base.progress.completed_plan_credits != modeled.progress.completed_plan_credits:
        deltas.append(
            _delta(
                DeltaType.COMPLETED_PLAN_CREDIT_DELTA,
                "Phase 6",
                "PLAN",
                str(base.progress.completed_plan_credits),
                str(modeled.progress.completed_plan_credits),
            )
        )
    if base.progress.remaining_plan_credits != modeled.progress.remaining_plan_credits:
        deltas.append(
            _delta(
                DeltaType.REMAINING_PLAN_CREDIT_DELTA,
                "Phase 6",
                "PLAN",
                str(base.progress.remaining_plan_credits),
                str(modeled.progress.remaining_plan_credits),
            )
        )

    base_recs = tuple(item.course_code for item in base.recommendations.ranked_recommendations)
    modeled_recs = tuple(item.course_code for item in modeled.recommendations.ranked_recommendations)
    if set(base_recs) != set(modeled_recs):
        deltas.append(
            _delta(DeltaType.RECOMMENDATION_MEMBERSHIP_CHANGE, "Phase 7/P4", "RECOMMENDATIONS", _csv(base_recs), _csv(modeled_recs))
        )
    elif base_recs != modeled_recs:
        deltas.append(
            _delta(DeltaType.RECOMMENDATION_ORDER_CHANGE, "Phase 7/P4", "RECOMMENDATIONS", _csv(base_recs), _csv(modeled_recs))
        )

    base_plan = _plan_signature(base.semester_plan)
    modeled_plan = _plan_signature(modeled.semester_plan)
    if base_plan != modeled_plan:
        deltas.append(_delta(DeltaType.MODELED_PLAN_CHANGE, "Phase 8", "PRIMARY_PLAN", base_plan, modeled_plan))

    base_path = _path_signature(base.degree_path)
    modeled_path = _path_signature(modeled.degree_path)
    if base_path != modeled_path:
        deltas.append(_delta(DeltaType.MODELED_PATH_CHANGE, "Phase 9/P4", "PRIMARY_PATH", base_path, modeled_path))
    base_count = _registration_set_count(base.degree_path)
    modeled_count = _registration_set_count(modeled.degree_path)
    if base_count is not None and modeled_count is not None and base_count != modeled_count:
        deltas.append(
            _delta(
                DeltaType.MODELED_REGISTRATION_SET_COUNT_DELTA,
                "Phase 9/P4",
                "PRIMARY_PATH",
                str(base_count),
                str(modeled_count),
            )
        )

    if base.structural_warnings != modeled.structural_warnings:
        deltas.append(
            _delta(
                DeltaType.STRUCTURAL_WARNING_CHANGE,
                "P3/P4",
                "WARNINGS",
                _csv(base.structural_warnings),
                _csv(modeled.structural_warnings),
            )
        )
    return _canonical(deltas)


def delay_delta(base_value: str, modeled_value: str, target: str) -> TwinDelta:
    return _delta(DeltaType.DELAY_CONSEQUENCE_CHANGE, "P4 Delay", target, base_value, modeled_value)


def _delta(delta_type, source, target, before, after):
    return TwinDelta(delta_type, source, target, before, after)


def _csv(values) -> str:
    return "|".join(str(value) for value in values)


def _plan_signature(result) -> str:
    return ";".join(
        ",".join(course.course_code for course in option.courses)
        for option in result.plan_options
    )


def _path_signature(result) -> str:
    if not result.paths:
        return ""
    path = result.paths[0]
    return ";".join(
        ",".join(course.course_code for course in semester.plan_option.courses)
        for semester in path.semesters
    ) + f"|{path.status.value}|{'/'.join(path.unresolved_blocker_codes)}"


def _registration_set_count(result) -> int | None:
    if not result.paths or result.paths[0].status.value != "MODELED_COMPLETE":
        return None
    return result.paths[0].semester_count


def _canonical(deltas):
    order = {item: index for index, item in enumerate(DeltaType)}
    return tuple(sorted(deltas, key=lambda item: (order[item.delta_type], item.target)))

