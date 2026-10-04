"""Prerequisite graph structural analysis and sound AND/OR necessity logic."""

from __future__ import annotations

from collections import deque

from app.progress.models import AcademicProgressCatalog, RequirementType
from app.rules.models import CanTakeCatalog, PlanCourseRule, PrerequisiteLogicStatus

from .registries import StructuralGatewayStatus, StructuralMandatoryRole


def get_direct_downstream_courses(
    candidate_code: str,
    can_take_catalog: CanTakeCatalog,
) -> list[str]:
    """Returns a stably sorted unique list of courses that directly depend on candidate_code."""
    downstream: set[str] = set()
    for rule in can_take_catalog.plan_courses:
        for group in rule.dependency_groups:
            if candidate_code in group.option_course_codes:
                downstream.add(rule.course_code)
                break
    return sorted(downstream)


def get_transitive_downstream_courses(
    candidate_code: str,
    can_take_catalog: CanTakeCatalog,
) -> list[str]:
    """Returns a stably sorted unique list of courses reachable from candidate_code via prerequisite edges.

    Cycle-safe via BFS.
    """
    # Build forward adjacency: prerequisite -> set of dependent courses
    adjacency: dict[str, set[str]] = {}
    for rule in can_take_catalog.plan_courses:
        dep_code = rule.course_code
        for group in rule.dependency_groups:
            for opt in group.option_course_codes:
                adjacency.setdefault(opt, set()).add(dep_code)

    visited: set[str] = set()
    queue: deque[str] = deque(sorted(adjacency.get(candidate_code, set())))

    while queue:
        curr = queue.popleft()
        if curr not in visited and curr != candidate_code:
            visited.add(curr)
            for nxt in sorted(adjacency.get(curr, set())):
                if nxt not in visited and nxt != candidate_code:
                    queue.append(nxt)

    return sorted(visited)


def get_transitive_upstream_courses(
    candidate_code: str,
    can_take_catalog: CanTakeCatalog,
) -> list[str]:
    """Returns a stably sorted unique list of all upstream prerequisites of candidate_code."""
    rule_map: dict[str, PlanCourseRule] = {
        r.course_code: r for r in can_take_catalog.plan_courses
    }
    visited: set[str] = set()
    queue: deque[str] = deque()

    curr_rule = rule_map.get(candidate_code)
    if curr_rule:
        for group in curr_rule.dependency_groups:
            for opt in group.option_course_codes:
                queue.append(opt)

    while queue:
        curr = queue.popleft()
        if curr not in visited:
            visited.add(curr)
            r = rule_map.get(curr)
            if r:
                for group in r.dependency_groups:
                    for opt in group.option_course_codes:
                        if opt not in visited:
                            queue.append(opt)

    return sorted(visited)


def detect_candidate_cycle(
    candidate_code: str,
    can_take_catalog: CanTakeCatalog,
) -> bool:
    """Detects whether candidate_code is part of a dependency cycle."""
    rule_map: dict[str, PlanCourseRule] = {
        r.course_code: r for r in can_take_catalog.plan_courses
    }
    curr_rule = rule_map.get(candidate_code)
    if not curr_rule:
        return False

    visited: set[str] = set()
    queue: deque[str] = deque()

    for group in curr_rule.dependency_groups:
        for opt in group.option_course_codes:
            if opt == candidate_code:
                return True
            queue.append(opt)

    while queue:
        curr = queue.popleft()
        if curr == candidate_code:
            return True
        if curr not in visited:
            visited.add(curr)
            r = rule_map.get(curr)
            if r:
                for group in r.dependency_groups:
                    for opt in group.option_course_codes:
                        if opt == candidate_code:
                            return True
                        if opt not in visited:
                            queue.append(opt)

    return False


def get_individually_mandatory_courses(catalog: AcademicProgressCatalog) -> set[str]:
    """Derives the set of individually mandatory courses from the authoritative study plan.

    A course is individually mandatory if and only if its parent requirement group
    has requirement_type == RequirementType.REQUIRED.
    """
    req_group_ids = {
        g.group_id for g in catalog.requirement_groups if g.requirement_type is RequirementType.REQUIRED
    }
    return {
        c.course_code for c in catalog.plan_courses if c.requirement_group_id in req_group_ids
    }


def is_course_individually_mandatory(
    course_code: str,
    catalog: AcademicProgressCatalog,
) -> bool:
    """Returns True if the course is individually mandatory under the study plan."""
    mandatory_courses = get_individually_mandatory_courses(catalog)
    return course_code in mandatory_courses


def evaluate_mandatory_role(
    course_code: str,
    catalog: AcademicProgressCatalog,
) -> StructuralMandatoryRole | None:
    """Returns the StructuralMandatoryRole of the course in the study plan, or None if not in plan."""
    plan_course = next((c for c in catalog.plan_courses if c.course_code == course_code), None)
    if plan_course is None:
        return None
    req_group_ids = {
        g.group_id for g in catalog.requirement_groups if g.requirement_type is RequirementType.REQUIRED
    }
    if plan_course.requirement_group_id in req_group_ids:
        return StructuralMandatoryRole.MANDATORY_REQUIRED
    return StructuralMandatoryRole.CHOICE_ELECTIVE


def compute_must_prerequisites(
    target_code: str,
    rule_map: dict[str, PlanCourseRule],
    memo: dict[str, set[str]],
    visiting: set[str],
    detected_cycles: set[str],
) -> set[str]:
    """Computes the set of indispensable prerequisites Must(target_code).

    Formula:
        Must(T) = UNION_{G in T.groups} INTERSECTION_{O in G.options} ({O} UNION Must(O))
    """
    if target_code in memo:
        return memo[target_code]

    if target_code in visiting:
        detected_cycles.add(target_code)
        return set()

    visiting.add(target_code)
    rule = rule_map.get(target_code)

    if rule is None or not rule.dependency_groups:
        visiting.remove(target_code)
        memo[target_code] = set()
        return set()

    must_set: set[str] = set()

    for group in rule.dependency_groups:
        if not group.option_course_codes:
            continue

        group_indispensable: set[str] | None = None
        for option_code in group.option_course_codes:
            option_must = compute_must_prerequisites(
                option_code,
                rule_map,
                memo,
                visiting,
                detected_cycles,
            )
            option_branch = {option_code} | option_must

            if group_indispensable is None:
                group_indispensable = set(option_branch)
            else:
                group_indispensable &= option_branch

        if group_indispensable:
            must_set |= group_indispensable

    visiting.remove(target_code)
    memo[target_code] = must_set
    return must_set


def evaluate_candidate_necessity(
    candidate_code: str,
    target_code: str,
    rule_map: dict[str, PlanCourseRule],
    memo: dict[str, str],
    visiting: set[str],
    detected_cycles: set[str],
) -> str:
    """Evaluates whether candidate_code is indispensable to target_code under 3-valued logic.

    Returns:
        "MUST": target_code definitely requires candidate_code across all verified alternatives.
        "BYPASSABLE": target_code has a verified bypass that does not require candidate_code.
        "UNKNOWN": target_code cannot be resolved decisively due to source conflicts or cycles
                   that could alter whether candidate_code is indispensable.
    """
    if target_code == candidate_code:
        return "MUST"

    if target_code in memo:
        return memo[target_code]

    if target_code in visiting:
        detected_cycles.add(target_code)
        return "UNKNOWN"

    visiting.add(target_code)
    rule = rule_map.get(target_code)

    if rule is None:
        visiting.remove(target_code)
        memo[target_code] = "BYPASSABLE"
        return "BYPASSABLE"

    if rule.prerequisite_logic_status in (
        PrerequisiteLogicStatus.UNRESOLVED,
        PrerequisiteLogicStatus.SOURCE_CONFLICT,
    ):
        visiting.remove(target_code)
        memo[target_code] = "UNKNOWN"
        return "UNKNOWN"

    if not rule.dependency_groups:
        visiting.remove(target_code)
        memo[target_code] = "BYPASSABLE"
        return "BYPASSABLE"

    has_unknown_group = False
    is_must_for_any_group = False

    for group in rule.dependency_groups:
        if not group.option_course_codes:
            continue

        group_has_bypass = False
        all_options_must = True
        # Evaluate this OR dependency group under 3-valued logic:
        # - If ANY option is BYPASSABLE => group = BYPASSABLE (verified bypass found)
        # - Else if ALL options are MUST => group = MUST (candidate unavoidable across all options)
        # - Else => group = UNKNOWN (unresolved conflict on an option with no verified bypass)
        any_bypass = False
        all_must = True

        for opt_code in group.option_course_codes:
            opt_res = evaluate_candidate_necessity(
                candidate_code,
                opt_code,
                rule_map,
                memo,
                visiting,
                detected_cycles,
            )
            if opt_res == "BYPASSABLE":
                group_has_bypass = True
                any_bypass = True
                break
            if opt_res != "MUST":
                all_must = False

        if any_bypass:
            group_eval = "BYPASSABLE"
        elif all_must:
            group_eval = "MUST"
        else:
            group_eval = "UNKNOWN"

        # Conjunctive (AND) aggregation across all required dependency groups:
        # - If ANY group is MUST => target necessity is MUST
        # - Else if ANY group is UNKNOWN => target necessity is UNKNOWN
        # - Else (all groups BYPASSABLE) => target necessity is BYPASSABLE
        if group_eval == "MUST":
            is_must_for_any_group = True
            break
        elif group_eval == "UNKNOWN":
            has_unknown_group = True

    visiting.remove(target_code)

    if is_must_for_any_group:
        result = "MUST"
    elif has_unknown_group:
        result = "UNKNOWN"
    else:
        result = "BYPASSABLE"

    memo[target_code] = result
    return result


def evaluate_structural_gateway(
    candidate_code: str,
    catalog: AcademicProgressCatalog,
    can_take_catalog: CanTakeCatalog,
) -> tuple[StructuralGatewayStatus, list[str], list[str]]:
    """Evaluates the structural gateway status of candidate_code.

    Returns:
        (
            gateway_status,
            gated_mandatory_courses,
            limitations_or_conflicts,
        )
    """
    rule_map: dict[str, PlanCourseRule] = {
        r.course_code: r for r in can_take_catalog.plan_courses
    }

    # 1. Candidate's own rule check for source conflict
    cand_rule = rule_map.get(candidate_code)
    if cand_rule is not None and cand_rule.prerequisite_logic_status in (
        PrerequisiteLogicStatus.UNRESOLVED,
        PrerequisiteLogicStatus.SOURCE_CONFLICT,
    ):
        return (
            StructuralGatewayStatus.REVIEW_REQUIRED,
            [],
            [f"Prerequisite source conflict on candidate course {candidate_code}"],
        )

    # 2. Cycle detection on candidate
    if detect_candidate_cycle(candidate_code, can_take_catalog):
        return (
            StructuralGatewayStatus.REVIEW_REQUIRED,
            [],
            [f"Candidate course {candidate_code} is involved in a prerequisite dependency cycle"],
        )

    # 3. Transitive downstream reachability
    transitive_downstream = get_transitive_downstream_courses(candidate_code, can_take_catalog)
    if not transitive_downstream:
        return (StructuralGatewayStatus.NON_GATEWAY, [], [])

    # 4. Filter individually mandatory degree targets in transitive downstream
    # (A candidate cannot gate itself)
    mandatory_targets = get_individually_mandatory_courses(catalog)
    relevant_mandatory_targets = sorted(
        t for t in mandatory_targets if t in transitive_downstream and t != candidate_code
    )

    if not relevant_mandatory_targets:
        # Downstream dependencies exist, but none are individually mandatory degree courses
        return (StructuralGatewayStatus.NON_GATEWAY, [], [])

    # 5. Outcome-sensitive necessity evaluation across mandatory targets
    memo: dict[str, str] = {}
    detected_cycles: set[str] = set()
    gated_mandatory_courses: list[str] = []
    has_unknown_mandatory = False
    limitations: list[str] = []

    for target in relevant_mandatory_targets:
        nec = evaluate_candidate_necessity(
            candidate_code=candidate_code,
            target_code=target,
            rule_map=rule_map,
            memo=memo,
            visiting=set(),
            detected_cycles=detected_cycles,
        )
        if nec == "MUST":
            gated_mandatory_courses.append(target)
        elif nec == "UNKNOWN":
            has_unknown_mandatory = True
            limitations.append(
                f"Outcome-relevant prerequisite conflict or cycle on path to mandatory course {target}"
            )

    if detected_cycles:
        limitations.append(f"Prerequisite cycle detected involving {sorted(detected_cycles)}")

    if gated_mandatory_courses:
        return (
            StructuralGatewayStatus.STRUCTURAL_GATEWAY,
            gated_mandatory_courses,
            limitations,
        )

    if has_unknown_mandatory or detected_cycles:
        return (
            StructuralGatewayStatus.REVIEW_REQUIRED,
            [],
            limitations,
        )

    return (StructuralGatewayStatus.NON_GATEWAY, [], [])
