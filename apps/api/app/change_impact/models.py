"""Closed, immutable and provider-neutral WC-046 V1 contracts."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.rules.models import DependencyType


class ChangeType(str, Enum):
    PREREQUISITE_GROUP_CHANGE = "PREREQUISITE_GROUP_CHANGE"
    REQUIREMENT_GROUP_CREDIT_CHANGE = "REQUIREMENT_GROUP_CREDIT_CHANGE"
    COURSE_CREDIT_HOURS_CHANGE = "COURSE_CREDIT_HOURS_CHANGE"
    POLICY_VERSION_CHANGE = "POLICY_VERSION_CHANGE"


class ImpactStatus(str, Enum):
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNKNOWN = "UNKNOWN"


class ChangeAuthority(str, Enum):
    PROPOSED_ANALYST_CHANGE = "PROPOSED_ANALYST_CHANGE"


class ImpactBasis(str, Enum):
    HISTORICAL_BASIS = "HISTORICAL_BASIS"
    PROPOSED_BASIS = "PROPOSED_BASIS"
    CURRENT_RECOMPUTATION = "CURRENT_RECOMPUTATION"


class DecisionClass(str, Enum):
    ELIGIBILITY = "ELIGIBILITY"
    PROGRESS = "PROGRESS"
    RECOMMENDATIONS = "RECOMMENDATIONS"
    SEMESTER_PLANNER = "SEMESTER_PLANNER"
    DEGREE_PATH = "DEGREE_PATH"
    POLICY_CONSULTATION = "POLICY_CONSULTATION"


class ImpactLimitation(str, Enum):
    BASELINE_MISMATCH = "BASELINE_MISMATCH"
    IMPACT_FANOUT_LIMIT_EXCEEDED = "IMPACT_FANOUT_LIMIT_EXCEEDED"
    POLICY_CHANGE_NOT_MAPPED_TO_DETERMINISTIC_RULE = "POLICY_CHANGE_NOT_MAPPED_TO_DETERMINISTIC_RULE"
    RECOMPUTATION_INPUT_UNAVAILABLE = "RECOMPUTATION_INPUT_UNAVAILABLE"
    SOURCE_VERSION_UNVERIFIED = "SOURCE_VERSION_UNVERIFIED"
    SOURCE_CONFLICT_OR_UNRESOLVED = "SOURCE_CONFLICT_OR_UNRESOLVED"
    CHANGE_IMPACT_V1_EPHEMERAL_REPORT = "CHANGE_IMPACT_V1_EPHEMERAL_REPORT"


_CODE = re.compile(r"[A-Z0-9][A-Z0-9_.-]{0,49}\Z")


def canonical_code(value: str) -> str:
    result = value.strip().upper()
    if not _CODE.fullmatch(result):
        raise ValueError("invalid canonical code")
    return result


class _Delta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    old_version: str = Field(min_length=1, max_length=100)
    new_version: str = Field(min_length=1, max_length=100)
    provenance_reference: str = Field(min_length=1, max_length=200)

    @field_validator("old_version", "new_version", "provenance_reference")
    @classmethod
    def bounded_nonblank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or any(ord(char) < 32 for char in cleaned):
            raise ValueError("version and provenance must be nonblank printable text")
        return cleaned

    @model_validator(mode="after")
    def different_versions(self):
        if self.old_version == self.new_version:
            raise ValueError("old_version and new_version must differ")
        return self


class PrerequisiteGroupDelta(_Delta):
    change_type: Literal[ChangeType.PREREQUISITE_GROUP_CHANGE]
    study_plan_id: UUID
    target_course_code: str
    group_number: int = Field(ge=1, le=100)
    dependency_type: DependencyType
    old_option_course_codes: tuple[str, ...] = Field(min_length=1, max_length=30)
    new_option_course_codes: tuple[str, ...] = Field(min_length=1, max_length=30)

    @field_validator("target_course_code")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return canonical_code(value)

    @field_validator("old_option_course_codes", "new_option_course_codes")
    @classmethod
    def normalize_options(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(canonical_code(value) for value in values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate option course code")
        return tuple(sorted(normalized))


class RequirementGroupCreditDelta(_Delta):
    change_type: Literal[ChangeType.REQUIREMENT_GROUP_CREDIT_CHANGE]
    study_plan_id: UUID
    requirement_group_code: str
    old_required_credits: Decimal = Field(ge=0, le=300, allow_inf_nan=False)
    new_required_credits: Decimal = Field(ge=0, le=300, allow_inf_nan=False)

    @field_validator("requirement_group_code")
    @classmethod
    def normalize_group(cls, value: str) -> str:
        return canonical_code(value)


class CourseCreditHoursDelta(_Delta):
    change_type: Literal[ChangeType.COURSE_CREDIT_HOURS_CHANGE]
    study_plan_id: UUID
    course_code: str
    old_credit_hours: Decimal = Field(gt=0, le=30, allow_inf_nan=False)
    new_credit_hours: Decimal = Field(gt=0, le=30, allow_inf_nan=False)

    @field_validator("course_code")
    @classmethod
    def normalize_course(cls, value: str) -> str:
        return canonical_code(value)


class PolicyVersionDelta(_Delta):
    change_type: Literal[ChangeType.POLICY_VERSION_CHANGE]
    document_code: str
    affected_topic: str = Field(min_length=1, max_length=100)

    @field_validator("document_code")
    @classmethod
    def normalize_document(cls, value: str) -> str:
        return canonical_code(value)

    @field_validator("affected_topic")
    @classmethod
    def normalize_topic(cls, value: str) -> str:
        return canonical_code(value)


ChangeDelta = Annotated[
    Union[PrerequisiteGroupDelta, RequirementGroupCreditDelta, CourseCreditHoursDelta, PolicyVersionDelta],
    Field(discriminator="change_type"),
]


class AffectedFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    fact_type: str
    reference: str
    before: str | None = None
    after: str | None = None


class ImpactComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision_class: DecisionClass
    reference: str
    before: str
    after: str
    status: ImpactStatus
    basis_before: Literal[ImpactBasis.CURRENT_RECOMPUTATION] = ImpactBasis.CURRENT_RECOMPUTATION
    basis_after: Literal[ImpactBasis.PROPOSED_BASIS] = ImpactBasis.PROPOSED_BASIS


class ChangeImpactReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    change_id: str
    change_type: ChangeType
    change_authority: ChangeAuthority = ChangeAuthority.PROPOSED_ANALYST_CHANGE
    provenance_reference: str
    university_id: UUID
    study_plan_id: UUID | None
    old_version: str
    new_version: str
    impact_status: ImpactStatus
    affected_facts: tuple[AffectedFact, ...]
    affected_decision_types: tuple[DecisionClass, ...]
    structurally_affected_courses: tuple[str, ...]
    affected_requirement_groups: tuple[str, ...]
    comparisons: tuple[ImpactComparison, ...]
    requires_human_review: bool
    limitations: tuple[ImpactLimitation, ...]
    generated_at: datetime
    engine_version: Literal["wc046:v1"] = "wc046:v1"
    replay_status: Literal["NOT_REPLAYABLE"] = "NOT_REPLAYABLE"
    historical_basis: Literal["NOT_REWRITTEN"] = "NOT_REWRITTEN"
    audit_status: Literal["NOT_ATTEMPTED", "LEDGER_PERSISTED"] = "NOT_ATTEMPTED"
