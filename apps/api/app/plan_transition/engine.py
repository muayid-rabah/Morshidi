"""Pure, reversible modeled transition and major-transfer projection."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json

from .equivalency import decide_equivalency
from .models import (CompletedCourse, CreditLine, CreditStatus, EquivalencyRule,
                     EquivalencyStatus, GrandfatheringAction, PlanVersion,
                     TransitionResult, TransitionRule)


class TransitionIntegrityError(ValueError):
    """Cross-scope or internally inconsistent modeled inputs."""


def _fingerprint(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, default=str,
                             ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def evaluate_transition(
    source: PlanVersion, target: PlanVersion, completed: tuple[CompletedCourse, ...],
    equivalencies: tuple[EquivalencyRule, ...],
    transitions: tuple[TransitionRule, ...], on: date,
) -> TransitionResult:
    """No writes, no recommendation, no implicit equivalence or grandfathering."""
    if source.identity.institution_id != target.identity.institution_id:
        raise TransitionIntegrityError("Cross-institution modeled transition is not authorized")
    if source.identity.key == target.identity.key:
        raise TransitionIntegrityError("Source and target must be different versions")
    if not (target.identity.effective_from <= on and
            (target.identity.effective_to is None or on <= target.identity.effective_to)):
        raise TransitionIntegrityError("Target version is not effective on comparison date")
    if len({c.identity.key for c in source.courses}) != len(source.courses) or len({c.identity.key for c in target.courses}) != len(target.courses):
        raise TransitionIntegrityError("Duplicate plan-course identity")
    if any(a.source_plan_key != source.identity.key or
           a.identity.institution_id != source.identity.institution_id for a in completed):
        raise TransitionIntegrityError("Completed record is outside source plan")
    source_courses = {c.identity.key: c for c in source.courses}
    target_courses = {c.identity.key: c for c in target.courses}
    if any(a.identity.key not in source_courses or a.credits < 0 for a in completed):
        raise TransitionIntegrityError("Completed record not in source plan")
    if len({a.identity.key for a in completed}) != len(completed):
        raise TransitionIntegrityError("Duplicate completed course")
    target_groups = {g.group_id: g for g in target.groups}
    source_groups = {g.group_id: g for g in source.groups}
    if len(target_groups) != len(target.groups) or len(source_groups) != len(source.groups):
        raise TransitionIntegrityError("Duplicate requirement group")
    active_rules = tuple(r for r in transitions if r.source_plan_key == source.identity.key
                         and r.target_plan_key == target.identity.key and r.effective_from <= on
                         and (r.effective_to is None or on <= r.effective_to))
    group_rules: dict[str, list[TransitionRule]] = {}
    for rule in active_rules:
        group_rules.setdefault(rule.group_id, []).append(rule)
    lines: list[CreditLine] = []
    used_targets: set[tuple[str, str]] = set()
    group_credit_left = {g.group_id: g.required_credits for g in target.groups}
    for attempt in sorted(completed, key=lambda x: x.identity.key):
        old = source_courses[attempt.identity.key]
        candidates = []
        for new in target.courses:
            if new.identity.key == attempt.identity.key:
                candidates.append((new, CreditStatus.UNCHANGED, (), ()))
            else:
                decision = decide_equivalency(old.identity, new.identity, source.identity,
                                               target.identity, on, equivalencies)
                if decision.status is EquivalencyStatus.EQUIVALENT:
                    candidates.append((new, CreditStatus.EQUIVALENT, decision.rule_ids, decision.evidence))
                elif decision.status is EquivalencyStatus.CONFLICT:
                    candidates.append((new, CreditStatus.REVIEW_REQUIRED, decision.rule_ids, decision.evidence))
        matches = [c for c in candidates if c[1] in {CreditStatus.UNCHANGED, CreditStatus.EQUIVALENT}]
        if len(matches) != 1 or len(candidates) != 1 or matches[0][0].identity.key in used_targets:
            ids = tuple(sorted({rid for _, _, rule_ids, _ in candidates for rid in rule_ids}))
            evidence = tuple(e for _, _, _, entries in candidates for e in entries)
            lines.append(CreditLine(old.identity.course_id, None,
                                    CreditStatus.REVIEW_REQUIRED if candidates else CreditStatus.UNRESOLVED,
                                    Decimal(0), attempt.credits, ids,
                                    "Ambiguous/contested mapping" if candidates else "No exact approved mapping",
                                    evidence))
            continue
        new, status, ids, evidence = matches[0]
        rules = group_rules.get(new.group_id, [])
        if len(rules) > 1 or (rules and rules[0].action is GrandfatheringAction.MANUAL_REVIEW_REQUIRED):
            lines.append(CreditLine(old.identity.course_id, new.identity.course_id,
                                    CreditStatus.REVIEW_REQUIRED, Decimal(0), attempt.credits,
                                    ids + tuple(r.rule_id for r in rules), "Grandfathering review required", evidence))
            continue
        if rules and rules[0].action is GrandfatheringAction.KEEP_SOURCE_REQUIREMENT and old.group_id != new.group_id:
            # A source-only requirement cannot silently satisfy a target group.
            lines.append(CreditLine(old.identity.course_id, new.identity.course_id,
                                    CreditStatus.REVIEW_REQUIRED, Decimal(0), attempt.credits,
                                    ids + (rules[0].rule_id,), "Source requirement needs registrar review", evidence))
            continue
        if rules and rules[0].action is GrandfatheringAction.ALLOW_EQUIVALENT_REQUIREMENT and status is not CreditStatus.EQUIVALENT:
            lines.append(CreditLine(old.identity.course_id, new.identity.course_id,
                                    CreditStatus.REVIEW_REQUIRED, Decimal(0), attempt.credits,
                                    ids + (rules[0].rule_id,), "Equivalent requirement rule not satisfied", evidence))
            continue
        if new.group_id not in group_credit_left:
            raise TransitionIntegrityError("Target course references missing requirement group")
        recognized = min(attempt.credits, new.credits, group_credit_left[new.group_id])
        group_credit_left[new.group_id] -= recognized
        used_targets.add(new.identity.key)
        lines.append(CreditLine(old.identity.course_id, new.identity.course_id,
                                status if old.group_id == new.group_id else CreditStatus.RECOGNIZED,
                                recognized, attempt.credits - recognized,
                                ids + ((rules[0].rule_id,) if rules else ()),
                                "Modeled target credit; not official recognition", evidence))
    new_requirements = tuple(sorted(c.identity.course_id for c in target.courses
                                    if c.identity.key not in used_targets))
    removed = tuple(sorted(c.identity.course_id for c in source.courses
                           if c.identity.key not in target_courses))
    lines.extend(CreditLine(None, course_id, CreditStatus.NEW_REQUIREMENT,
                            Decimal(0), Decimal(0), (), "Target-plan requirement not satisfied")
                 for course_id in new_requirements)
    lines.extend(CreditLine(course_id, None, CreditStatus.REMOVED_REQUIREMENT,
                            Decimal(0), Decimal(0), (), "Source-plan course absent from target version")
                 for course_id in removed)
    changed_groups = tuple(sorted(g for g in source_groups.keys() & target_groups.keys()
                                  if source_groups[g].required_credits != target_groups[g].required_credits))
    changed_prerequisites = tuple(sorted(c.identity.course_id for c in source.courses
                                         if c.identity.key in target_courses and
                                         c.prerequisites != target_courses[c.identity.key].prerequisites))
    recognized_total = sum((x.recognized_credits for x in lines), Decimal(0))
    unresolved_total = sum((x.unresolved_credits for x in lines), Decimal(0))
    remaining = max(Decimal(0), sum((g.required_credits for g in target.groups), Decimal(0)) - recognized_total)
    payload = {"source": source.identity.key, "source_fingerprint": source.content_fingerprint,
               "target": target.identity.key, "target_fingerprint": target.content_fingerprint,
               "on": on.isoformat(), "lines": [asdict(x) for x in lines],
               "new": new_requirements, "removed": removed,
               "changed_groups": changed_groups, "changed_prerequisites": changed_prerequisites}
    return TransitionResult(source.identity.key, target.identity.key, tuple(lines),
                            recognized_total, unresolved_total, remaining, new_requirements,
                            removed, changed_groups, changed_prerequisites, _fingerprint(payload))


def project_major_transfer(
    source: PlanVersion, target: PlanVersion, completed: tuple[CompletedCourse, ...],
    equivalencies: tuple[EquivalencyRule, ...], transitions: tuple[TransitionRule, ...],
    on: date,
) -> TransitionResult:
    if source.identity.major_id == target.identity.major_id:
        raise TransitionIntegrityError("Use plan transition for the same major")
    return evaluate_transition(source, target, completed, equivalencies, transitions, on)
