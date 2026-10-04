"""Exact effective-dated equivalency; no title/code similarity or transitive inference."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from .models import (CourseIdentity, EquivalencyDecision, EquivalencyRule,
                     EquivalencyStatus, PlanIdentity, RuleEvidence)


class EquivalencyRuleProvider(Protocol):
    async def rules_for(self, source: PlanIdentity, target: PlanIdentity) -> tuple[EquivalencyRule, ...]: ...


def _decision(status: EquivalencyStatus, rules: tuple[EquivalencyRule, ...], reason: str) -> EquivalencyDecision:
    ordered = tuple(sorted(rules, key=lambda r: r.rule_id))
    return EquivalencyDecision(status, tuple(r.rule_id for r in ordered), reason,
                               tuple(RuleEvidence(r.rule_id, r.version, r.effective_from,
                                                  r.effective_to, r.source_plan_key,
                                                  r.target_plan_key, r.authority,
                                                  r.provenance, r.status) for r in ordered))


def decide_equivalency(
    source: CourseIdentity, target: CourseIdentity,
    source_plan: PlanIdentity, target_plan: PlanIdentity,
    on: date, rules: tuple[EquivalencyRule, ...],
) -> EquivalencyDecision:
    if source.institution_id != source_plan.institution_id or target.institution_id != target_plan.institution_id:
        return _decision(EquivalencyStatus.NOT_APPLICABLE, (), "Course/plan institution mismatch")
    scoped = tuple(r for r in rules if r.source_plan_key == source_plan.key
                   and r.target_plan_key == target_plan.key)
    exact = tuple(r for r in scoped if r.source_course.key == source.key
                  and r.target_course.key == target.key)
    if not exact and any(r.source_course.key == source.key and r.target_course.key == target.key
                         for r in rules):
        return _decision(EquivalencyStatus.NOT_APPLICABLE,
                         tuple(r for r in rules if r.source_course.key == source.key and r.target_course.key == target.key),
                         "Rule belongs to another plan/version")
    active = tuple(r for r in exact if r.effective_from <= on
                   and (r.effective_to is None or on <= r.effective_to))
    approved_scoped = tuple(r for r in scoped if r.status == "APPROVED"
                            and r.effective_from <= on
                            and (r.effective_to is None or on <= r.effective_to))
    alternatives = {r.target_course.key for r in approved_scoped
                    if r.source_course.key == source.key}
    if len(alternatives) > 1:
        return _decision(EquivalencyStatus.CONFLICT,
                         tuple(r for r in approved_scoped if r.source_course.key == source.key),
                         "Conflicting approved targets")
    graph: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for rule in approved_scoped:
        graph.setdefault(rule.source_course.key, set()).add(rule.target_course.key)
    frontier = list(graph.get(target.key, ()))
    visited: set[tuple[str, str]] = set()
    while frontier:
        node = frontier.pop()
        if node == source.key:
            return _decision(EquivalencyStatus.CONFLICT, approved_scoped,
                             "Cycle in approved equivalency rules")
        if node not in visited:
            visited.add(node)
            frontier.extend(graph.get(node, ()))
    if len(active) > 1:
        return _decision(EquivalencyStatus.CONFLICT, active, "Overlapping exact rules")
    if active:
        rule = active[0]
        if not rule.authority.strip() or not rule.provenance.strip() or not rule.version.strip():
            return _decision(EquivalencyStatus.UNRESOLVED, (rule,), "Missing rule authority")
        if rule.status == "APPROVED":
            return _decision(EquivalencyStatus.EQUIVALENT, (rule,), "Approved exact rule")
        if rule.status == "DENIED":
            return _decision(EquivalencyStatus.NOT_EQUIVALENT, (rule,), "Explicit denial")
        return _decision(EquivalencyStatus.UNRESOLVED, (rule,), "Rule not approved")
    if exact:
        return _decision(EquivalencyStatus.EXPIRED, exact, "No rule effective on date")
    # A -> B and B -> C does not grant A -> C. Cycles also remain unresolved.
    edges = {(r.source_course.key, r.target_course.key) for r in approved_scoped}
    if any(a == source.key for a, _ in edges) or any(b == target.key for _, b in edges):
        return _decision(EquivalencyStatus.UNRESOLVED,
                         tuple(r for r in approved_scoped if r.source_course.key == source.key or r.target_course.key == target.key),
                         "No direct rule; chain or alternative requires review")
    return _decision(EquivalencyStatus.UNRESOLVED, (), "No exact rule")
