"""Local structured import staging; no database write or production publication path."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping

from .models import (CourseIdentity, PlanCourse, PlanIdentity, PlanVersion,
                     RequirementGroup, StagedRule)


class IngestionState(str, Enum):
    RECEIVED = "RECEIVED"
    NORMALIZED = "NORMALIZED"
    VALID = "VALID"
    INVALID = "INVALID"
    QUARANTINED = "QUARANTINED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"


@dataclass(frozen=True)
class ImportPreview:
    state: IngestionState
    plan_key: tuple[str, str, str, str, str] | None
    source: str
    source_fingerprint: str
    content_fingerprint: str | None
    course_count: int
    group_count: int
    total_credits: Decimal
    prerequisite_edges: int
    unresolved_references: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    plan: PlanVersion | None


def _digest(value: Any, *, modeled: bool = False) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                           default=str if modeled else None,
                           ensure_ascii=True, allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")
    return value.strip()


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be a finite nonnegative decimal") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a finite nonnegative decimal")
    return result


def _date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(_text(value, field))
    except ValueError:
        raise ValueError(f"{field} must be an ISO date") from None


def stage_structured_import(document: Mapping[str, Any], *, source: str,
                            existing_keys: frozenset[tuple[str, str, str, str, str]] = frozenset(),
                            existing_versions: tuple[PlanIdentity, ...] = ()) -> ImportPreview:
    """Validate an isolated JSON-like record; invalid data is wholly quarantined."""
    errors: list[str] = []
    warnings: list[str] = []
    unresolved: list[str] = []
    identity: PlanIdentity | None = None
    groups: list[RequirementGroup] = []
    courses: list[PlanCourse] = []
    staged_rules: list[StagedRule] = []
    source_name = source.strip()
    try:
        source_hash = _digest(document)
    except (TypeError, ValueError):
        source_hash = "UNAVAILABLE"
        errors.append("Malformed source metadata")
    if not source_name:
        errors.append("Missing source provenance")
    if document.get("schema_version") != "P12_PLAN_V1":
        errors.append("Unsupported schema version")
    try:
        raw = document["identity"]
        if not isinstance(raw, Mapping):
            raise ValueError("Malformed plan identity")
        identity = PlanIdentity(
            _text(raw.get("institution_id"), "institution_id"),
            _text(raw.get("program_id"), "program_id"),
            _text(raw.get("major_id"), "major_id"),
            _text(raw.get("plan_id"), "plan_id"),
            _text(raw.get("version_id"), "version_id"),
            _date(raw.get("effective_from"), "effective_from"),
            _date(raw["effective_to"], "effective_to") if raw.get("effective_to") else None,
            _text(raw.get("source_version"), "source_version"),
        )
        if identity.effective_to is not None and identity.effective_to < identity.effective_from:
            errors.append("Conflicting effective dates")
        if identity.key in existing_keys:
            errors.append("Duplicate plan version")
        for earlier in existing_versions:
            if earlier.key == identity.key:
                errors.append("Duplicate plan version")
            elif earlier.key[:4] == identity.key[:4] and (
                earlier.effective_to is None or identity.effective_from <= earlier.effective_to
            ) and (identity.effective_to is None or earlier.effective_from <= identity.effective_to):
                errors.append("Conflicting effective dates across plan versions")
    except (KeyError, ValueError, TypeError) as exc:
        errors.append(str(exc))
    raw_groups = document.get("groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        errors.append("Missing requirement groups")
        raw_groups = []
    for index, raw in enumerate(raw_groups):
        try:
            if not isinstance(raw, Mapping):
                raise ValueError("Malformed requirement group")
            groups.append(RequirementGroup(_text(raw.get("group_id"), "group_id"),
                                           _decimal(raw.get("required_credits"), "required_credits")))
        except ValueError as exc:
            errors.append(f"group[{index}]: {exc}")
    if len({g.group_id for g in groups}) != len(groups):
        errors.append("Duplicate requirement group")
    raw_courses = document.get("courses")
    if not isinstance(raw_courses, list):
        errors.append("Missing courses")
        raw_courses = []
    for index, raw in enumerate(raw_courses):
        try:
            if not isinstance(raw, Mapping) or identity is None:
                raise ValueError("Malformed course or plan identity")
            prereqs = raw.get("prerequisites", [])
            if not isinstance(prereqs, list) or any(not isinstance(p, str) or not p.strip() for p in prereqs):
                raise ValueError("Malformed prerequisite IDs")
            courses.append(PlanCourse(
                CourseIdentity(identity.institution_id, _text(raw.get("course_id"), "course_id"),
                               _text(raw.get("code"), "code")),
                _text(raw.get("group_id"), "group_id"),
                _decimal(raw.get("credits"), "credits"), tuple(prereqs)))
        except ValueError as exc:
            errors.append(f"course[{index}]: {exc}")
    ids = [c.identity.course_id for c in courses]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate course identity")
    raw_rules = document.get("equivalency_rules", [])
    if not isinstance(raw_rules, list):
        errors.append("Malformed equivalency rules")
        raw_rules = []
    rule_ids: list[str] = []
    for index, raw_rule in enumerate(raw_rules):
        try:
            if not isinstance(raw_rule, Mapping):
                raise ValueError("Malformed equivalency rule")
            rule_id = _text(raw_rule.get("rule_id"), "rule_id")
            rule_ids.append(rule_id)
            authority = _text(raw_rule.get("authority"), "authority")
            provenance = _text(raw_rule.get("provenance"), "provenance")
            start = _date(raw_rule.get("effective_from"), "rule effective_from")
            end = _date(raw_rule["effective_to"], "rule effective_to") if raw_rule.get("effective_to") else None
            if end is not None and end < start:
                raise ValueError("Conflicting rule effective dates")
            source_key_raw = raw_rule.get("source_plan_key")
            target_key_raw = raw_rule.get("target_plan_key")
            if not isinstance(source_key_raw, (list, tuple)) or not isinstance(target_key_raw, (list, tuple)):
                raise ValueError("Malformed rule plan/version scope")
            source_key = tuple(source_key_raw)
            target_key = tuple(target_key_raw)
            if len(source_key) != 5 or len(target_key) != 5 or any(not isinstance(v, str) or not v.strip() for v in source_key + target_key):
                raise ValueError("Malformed rule plan/version scope")
            if identity is None or target_key != identity.key:
                raise ValueError("Rule target must match imported plan/version")
            status = _text(raw_rule.get("status"), "status")
            if status not in {"APPROVED", "DENIED", "DRAFT"}:
                raise ValueError("Unsupported rule status")
            staged_rules.append(StagedRule(rule_id,
                                           _text(raw_rule.get("source_course_id"), "source_course_id"),
                                           _text(raw_rule.get("target_course_id"), "target_course_id"),
                                           source_key, target_key, start, end, authority,
                                           provenance, _text(raw_rule.get("version"), "version"), status))
        except ValueError as exc:
            errors.append(f"equivalency_rule[{index}]: {exc}")
    if len(rule_ids) != len(set(rule_ids)):
        errors.append("Duplicate equivalency rule")
    for staged_rule in staged_rules:
        if staged_rule.target_course_id not in ids:
            errors.append("Rule target references nonexistent course")
    group_ids = {g.group_id for g in groups}
    for course in courses:
        if course.group_id not in group_ids:
            errors.append(f"Unknown requirement group: {course.group_id}")
        for dependency in course.prerequisites:
            if dependency not in ids:
                unresolved.append(dependency)
    if unresolved:
        errors.append("Prerequisite references nonexistent course")
    graph = {c.identity.course_id: c.prerequisites for c in courses}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(course_id: str) -> bool:
        if course_id in visiting:
            return True
        if course_id in visited:
            return False
        visiting.add(course_id)
        for dep in graph.get(course_id, ()):
            if visit(dep):
                return True
        visiting.remove(course_id)
        visited.add(course_id)
        return False

    if any(visit(course_id) for course_id in graph):
        errors.append("Prerequisite cycle")
    required = sum((g.required_credits for g in groups), Decimal(0))
    if required == 0:
        warnings.append("Zero required credits")
    if courses and sum((c.credits for c in courses), Decimal(0)) < required:
        errors.append("Listed course credits below required group totals")
    content_hash = None
    plan = None
    if identity is not None and not errors:
        content_hash = _digest({
            "identity": asdict(identity),
            "groups": [asdict(g) for g in sorted(groups, key=lambda g: g.group_id)],
            "courses": [{**asdict(c), "prerequisites": sorted(c.prerequisites)}
                        for c in sorted(courses, key=lambda c: c.identity.course_id)],
            "rules": [asdict(r) for r in sorted(staged_rules, key=lambda r: r.rule_id)],
            "schema_version": "P12_PLAN_V1"}, modeled=True)
        plan = PlanVersion(identity, tuple(groups), tuple(courses), source_hash,
                           content_hash, source_name, staged_rules=tuple(staged_rules))
    return ImportPreview(IngestionState.QUARANTINED if errors else IngestionState.READY_FOR_REVIEW,
                         identity.key if identity else None, source_name, source_hash,
                         content_hash, len(courses), len(groups), required,
                         sum(len(c.prerequisites) for c in courses), tuple(sorted(set(unresolved))),
                         tuple(errors), tuple(warnings), plan)


@dataclass(frozen=True)
class ModeledApproval:
    actor_id: str
    role: str
    authority: str
    approved_on: date


def approve_local_version(preview: ImportPreview, approval: ModeledApproval) -> PlanVersion:
    """Pure local gate only; no production registrar role or persistence is wired."""
    if preview.state is not IngestionState.READY_FOR_REVIEW or preview.plan is None:
        raise ValueError("Only a complete validated preview may be approved")
    if approval.role != "MODELED_CURRICULUM_ADMIN" or not approval.actor_id.strip() or not approval.authority.strip():
        raise PermissionError("Modeled curriculum-admin approval required")
    return preview.plan


@dataclass(frozen=True)
class LocalPublication:
    state: IngestionState
    plan: PlanVersion
    approved_by: str
    approved_on: date
    authority: str


def publish_local_version(preview: ImportPreview, approval: ModeledApproval) -> LocalPublication:
    """Explicit modeled publication value; caller must persist separately, if ever authorized."""
    plan = approve_local_version(preview, approval)
    return LocalPublication(IngestionState.PUBLISHED, plan, approval.actor_id,
                            approval.approved_on, approval.authority)
