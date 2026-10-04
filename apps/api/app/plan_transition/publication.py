"""Pure content-addressed publication registry and deterministic version comparison."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .ingestion import LocalPublication
from .models import PlanVersion


@dataclass(frozen=True)
class ModeledVersionRegistry:
    """Immutable local selection state; rollback changes only the active pointer."""

    publications: tuple[LocalPublication, ...] = ()
    active_key: tuple[str, str, str, str, str] | None = None

    def add(self, publication: LocalPublication) -> ModeledVersionRegistry:
        if publication.plan.identity.key in {p.plan.identity.key for p in self.publications}:
            raise ValueError("Published version identity already exists; create a new version")
        if any(p.plan.content_fingerprint == publication.plan.content_fingerprint
               for p in self.publications):
            raise ValueError("Academic content already published under another version")
        return ModeledVersionRegistry(self.publications + (publication,), self.active_key)

    def activate(self, key: tuple[str, str, str, str, str]) -> ModeledVersionRegistry:
        if key not in {p.plan.identity.key for p in self.publications}:
            raise ValueError("Only a published immutable version can be activated")
        return ModeledVersionRegistry(self.publications, key)

    @property
    def active(self) -> LocalPublication | None:
        return next((p for p in self.publications if p.plan.identity.key == self.active_key), None)


class ReconciliationStatus(str, Enum):
    ADDED_COURSE = "ADDED_COURSE"
    REMOVED_COURSE = "REMOVED_COURSE"
    CHANGED_CREDITS = "CHANGED_CREDITS"
    CHANGED_REQUIREMENT_GROUP = "CHANGED_REQUIREMENT_GROUP"
    CHANGED_PREREQUISITE = "CHANGED_PREREQUISITE"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True)
class ReconciliationLine:
    course_id: str
    changes: tuple[ReconciliationStatus, ...]


@dataclass(frozen=True)
class Reconciliation:
    source_key: tuple[str, str, str, str, str]
    target_key: tuple[str, str, str, str, str]
    lines: tuple[ReconciliationLine, ...]
    source_changed: bool
    source_fingerprints: tuple[str, str]
    content_fingerprints: tuple[str, str]
    warnings: tuple[str, ...]


def reconcile_versions(source: PlanVersion, target: PlanVersion) -> Reconciliation:
    if source.identity.key[:4] != target.identity.key[:4]:
        raise ValueError("Reconciliation requires versions of the same institution/program/major/plan")
    old = {c.identity.key: c for c in source.courses}
    new = {c.identity.key: c for c in target.courses}
    if len(old) != len(source.courses) or len(new) != len(target.courses):
        raise ValueError("Duplicate course identity")
    lines: list[ReconciliationLine] = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        if a is None:
            changes = (ReconciliationStatus.ADDED_COURSE,)
        elif b is None:
            changes = (ReconciliationStatus.REMOVED_COURSE,)
        else:
            collected: list[ReconciliationStatus] = []
            if a.credits != b.credits:
                collected.append(ReconciliationStatus.CHANGED_CREDITS)
            if a.group_id != b.group_id:
                collected.append(ReconciliationStatus.CHANGED_REQUIREMENT_GROUP)
            if set(a.prerequisites) != set(b.prerequisites):
                collected.append(ReconciliationStatus.CHANGED_PREREQUISITE)
            changes = tuple(collected) or (ReconciliationStatus.UNCHANGED,)
        lines.append(ReconciliationLine(key[1], changes))
    warnings = ("SOURCE_CHANGED_REQUIRES_REVIEW",) if source.source_fingerprint != target.source_fingerprint else ()
    return Reconciliation(source.identity.key, target.identity.key, tuple(lines),
                          bool(warnings), (source.source_fingerprint, target.source_fingerprint),
                          (source.content_fingerprint, target.content_fingerprint), warnings)
