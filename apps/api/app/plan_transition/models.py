"""Immutable, institution/major/plan/version-scoped P12 input contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


@dataclass(frozen=True)
class PlanIdentity:
    institution_id: str
    program_id: str
    major_id: str
    plan_id: str
    version_id: str
    effective_from: date
    effective_to: date | None
    source_version: str

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (self.institution_id, self.program_id, self.major_id,
                self.plan_id, self.version_id)


@dataclass(frozen=True)
class CourseIdentity:
    institution_id: str
    course_id: str
    code: str  # Display only; never an equivalency key.

    @property
    def key(self) -> tuple[str, str]:
        return self.institution_id, self.course_id


@dataclass(frozen=True)
class PlanCourse:
    identity: CourseIdentity
    group_id: str
    credits: Decimal
    prerequisites: tuple[str, ...] = ()  # Course IDs within this version only.


@dataclass(frozen=True)
class RequirementGroup:
    group_id: str
    required_credits: Decimal


@dataclass(frozen=True)
class StagedRule:
    rule_id: str
    source_course_id: str
    target_course_id: str
    source_plan_key: tuple[str, str, str, str, str]
    target_plan_key: tuple[str, str, str, str, str]
    effective_from: date
    effective_to: date | None
    authority: str
    provenance: str
    version: str
    status: str


@dataclass(frozen=True)
class PlanVersion:
    identity: PlanIdentity
    groups: tuple[RequirementGroup, ...]
    courses: tuple[PlanCourse, ...]
    source_fingerprint: str
    content_fingerprint: str
    source: str
    schema_version: str = "P12_PLAN_V1"
    synthetic: bool = True
    staged_rules: tuple[StagedRule, ...] = ()


@dataclass(frozen=True)
class CompletedCourse:
    identity: CourseIdentity
    credits: Decimal
    source_plan_key: tuple[str, str, str, str, str]


class EquivalencyStatus(str, Enum):
    EQUIVALENT = "EQUIVALENT"
    NOT_EQUIVALENT = "NOT_EQUIVALENT"
    UNRESOLVED = "UNRESOLVED"
    CONFLICT = "CONFLICT"
    EXPIRED = "EXPIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class EquivalencyRule:
    rule_id: str
    source_course: CourseIdentity
    target_course: CourseIdentity
    source_plan_key: tuple[str, str, str, str, str]
    target_plan_key: tuple[str, str, str, str, str]
    effective_from: date
    effective_to: date | None
    authority: str
    version: str
    status: str  # APPROVED or DENIED; drafts never grant credit.
    provenance: str


@dataclass(frozen=True)
class EquivalencyDecision:
    status: EquivalencyStatus
    rule_ids: tuple[str, ...]
    reason: str
    evidence: tuple[RuleEvidence, ...] = ()


@dataclass(frozen=True)
class RuleEvidence:
    rule_id: str
    rule_version: str
    effective_from: date
    effective_to: date | None
    source_plan_key: tuple[str, str, str, str, str]
    target_plan_key: tuple[str, str, str, str, str]
    authority: str
    provenance: str
    status: str


class GrandfatheringAction(str, Enum):
    KEEP_SOURCE_REQUIREMENT = "KEEP_SOURCE_REQUIREMENT"
    USE_TARGET_REQUIREMENT = "USE_TARGET_REQUIREMENT"
    ALLOW_EQUIVALENT_REQUIREMENT = "ALLOW_EQUIVALENT_REQUIREMENT"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


@dataclass(frozen=True)
class TransitionRule:
    rule_id: str
    source_plan_key: tuple[str, str, str, str, str]
    target_plan_key: tuple[str, str, str, str, str]
    group_id: str
    action: GrandfatheringAction
    effective_from: date
    effective_to: date | None
    provenance: str


class CreditStatus(str, Enum):
    UNCHANGED = "UNCHANGED"
    RECOGNIZED = "RECOGNIZED"
    NEW_REQUIREMENT = "NEW_REQUIREMENT"
    REMOVED_REQUIREMENT = "REMOVED_REQUIREMENT"
    EQUIVALENT = "EQUIVALENT"
    UNRESOLVED = "UNRESOLVED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class CreditLine:
    source_course_id: str | None
    target_course_id: str | None
    status: CreditStatus
    recognized_credits: Decimal
    unresolved_credits: Decimal
    rule_ids: tuple[str, ...] = ()
    explanation: str = ""
    rule_evidence: tuple[RuleEvidence, ...] = ()


@dataclass(frozen=True)
class TransitionResult:
    source_plan_key: tuple[str, str, str, str, str]
    target_plan_key: tuple[str, str, str, str, str]
    lines: tuple[CreditLine, ...]
    recognized_credits: Decimal
    unresolved_credits: Decimal
    remaining_target_credits: Decimal
    new_requirements: tuple[str, ...]
    removed_requirements: tuple[str, ...]
    changed_groups: tuple[str, ...]
    changed_prerequisites: tuple[str, ...]
    fingerprint: str
    label: str = "MODELED_UNOFFICIAL_NO_WRITE"
