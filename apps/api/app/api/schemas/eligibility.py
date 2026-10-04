"""Pydantic request and response models for the CAN TAKE HTTP contract."""

from __future__ import annotations

from typing import Annotated, Literal
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, Strict, field_validator

from app.rules.models import AttemptOutcome, Decision, DecisionReason, DependencyType, PrerequisiteLogicStatus

CourseCode = Annotated[str, Strict(), Field(min_length=1)]


class CourseAttemptInput(BaseModel):
    """A request-only student history fact; it is never persisted in this phase."""

    model_config = ConfigDict(extra="forbid")

    course_code: CourseCode
    outcome: AttemptOutcome

    @field_validator("course_code")
    @classmethod
    def require_nonblank_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("course_code must not be blank")
        return value


class CanTakeRequestBody(BaseModel):
    """Transport request for one study-plan target evaluation."""

    model_config = ConfigDict(extra="forbid")

    # Temporary API selector: the schema currently has no unique public plan key.
    study_plan_id: UUID
    target_course_code: CourseCode
    attempts: list[CourseAttemptInput] = Field(default_factory=list)

    @field_validator("target_course_code")
    @classmethod
    def require_nonblank_target_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target_course_code must not be blank")
        return value


class TargetAttemptStateResponse(BaseModel):
    has_passed_target: bool
    has_in_progress_target: bool


class DependencyGroupEvidenceResponse(BaseModel):
    group_number: int
    dependency_type: DependencyType
    option_course_codes: list[str]
    passed_option_course_codes: list[str]
    non_passed_option_course_codes: list[str]


class AcademicRuleTraceResponse(BaseModel):
    rule_id: str
    rule_version: str
    provenance: str
    required_credits: Decimal
    earned_completed_credits: Decimal | None
    result: str
    reason_ar: str
    reason_en: str


class CanTakeDecisionResponse(BaseModel):
    kind: Literal["decision"] = "decision"
    decision: Decision
    study_plan_id: str
    target_course_code: str
    prerequisite_logic_status: PrerequisiteLogicStatus
    target_attempt_state: TargetAttemptStateResponse
    satisfied_dependency_groups: list[DependencyGroupEvidenceResponse]
    missing_dependency_groups: list[DependencyGroupEvidenceResponse]
    reasons: list[DecisionReason]
    review_reasons: list[DecisionReason]
    raw_prerequisite_text: str | None
    target_name_ar: str | None
    target_name_en: str | None = None
    academic_rule_traces: list[AcademicRuleTraceResponse] = Field(default_factory=list)


class ApiErrorResponse(BaseModel):
    kind: Literal["error"] = "error"
    error_code: str
    detail: str
