"""Bounded structural critical-chain calculation over verified plan prerequisites.

Only unfinished required plan courses and mandatory single-option PREREQUISITE
edges participate. OR alternatives, electives, corequisites, unresolved rules,
and calendar/offerings are deliberately excluded. All ties on the globally
longest remaining chain are marked; no time-to-graduation claim is made.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from app.catalog.errors import CatalogIntegrityError
from app.progress.models import AcademicProgress, AcademicProgressCatalog, CourseProgressState, RequirementType
from app.rules.models import CanTakeCatalog, DependencyType, PrerequisiteLogicStatus

CRITICAL_PATH_POLICY_VERSION = "P9_REQUIRED_PREREQUISITE_CHAIN_V1"
CRITICAL_PATH_REASON = "MAXIMAL_UNFINISHED_REQUIRED_PREREQUISITE_CHAIN"


@dataclass(frozen=True)
class CriticalPathEvidence:
    is_critical: bool
    reason_code: str | None
    chain_length: int
    downstream_required_codes: tuple[str, ...]
    evidence_chain: tuple[str, ...]


def calculate_structural_critical_path(
    progress_catalog: AcademicProgressCatalog,
    eligibility_catalog: CanTakeCatalog,
    progress: AcademicProgress,
) -> dict[str, CriticalPathEvidence]:
    """Bounded DAG traversal; cycles fail closed rather than inventing rank."""
    required_groups = {group.group_id for group in progress_catalog.requirement_groups
                       if group.requirement_type is RequirementType.REQUIRED}
    candidates = {course.course_code for course in progress.courses
                  if course.requirement_group_id in required_groups
                  and course.state is not CourseProgressState.COMPLETED}
    downstream: dict[str, set[str]] = {code: set() for code in candidates}
    upstream: dict[str, set[str]] = {code: set() for code in candidates}
    for rule in eligibility_catalog.plan_courses:
        if rule.course_code not in candidates or rule.prerequisite_logic_status is not PrerequisiteLogicStatus.VERIFIED:
            continue
        for group in rule.dependency_groups:
            if group.dependency_type is not DependencyType.PREREQUISITE or len(group.option_course_codes) != 1:
                continue
            prerequisite = group.option_course_codes[0]
            if prerequisite in candidates:
                downstream[prerequisite].add(rule.course_code)
                upstream[rule.course_code].add(prerequisite)

    queue = deque(sorted(code for code in candidates if not upstream[code]))
    indegree = {code: len(parents) for code, parents in upstream.items()}
    order: list[str] = []
    while queue:
        code = queue.popleft()
        order.append(code)
        for child in sorted(downstream[code]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(order) != len(candidates):
        raise CatalogIntegrityError("Verified required prerequisite graph contains a cycle")

    before = {code: 0 for code in candidates}
    after = {code: 0 for code in candidates}
    for code in order:
        for child in downstream[code]:
            before[child] = max(before[child], before[code] + 1)
    for code in reversed(order):
        for child in downstream[code]:
            after[code] = max(after[code], after[child] + 1)
    longest = max(before.values(), default=0)

    result = {}
    for code in candidates:
        critical = longest > 0 and before[code] + after[code] == longest
        chain = [code]
        cursor = code
        while before[cursor] > 0:
            cursor = min(parent for parent in upstream[cursor] if before[parent] == before[cursor] - 1)
            chain.insert(0, cursor)
        cursor = code
        while downstream[cursor] and after[cursor] > 0:
            cursor = min(child for child in downstream[cursor] if after[child] == after[cursor] - 1)
            chain.append(cursor)
        seen = set()
        pending = list(downstream[code])
        while pending:
            child = pending.pop()
            if child not in seen:
                seen.add(child)
                pending.extend(downstream[child])
        result[code] = CriticalPathEvidence(
            critical, CRITICAL_PATH_REASON if critical else None,
            longest if critical else 0, tuple(sorted(seen)) if critical else (),
            tuple(chain) if critical else (),
        )
    return result
