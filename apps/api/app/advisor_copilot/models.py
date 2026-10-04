"""Typed tool-specific input contracts and allowlisted response models for Advisor Copilot."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field

from app.advisor_copilot.registries import AdvisorToolId, ToolAuthorityClass


# ==============================================================================
# What-If Allowed Operation Contracts
# ==============================================================================


class WhatIfOperationId(str, Enum):
    """The exact three permitted What-If scenario operations."""

    TWIN_OP_MODEL_COURSE_COMPLETION = "TWIN_OP_MODEL_COURSE_COMPLETION"
    TWIN_OP_OMIT_NEXT_PLAN_COURSE = "TWIN_OP_OMIT_NEXT_PLAN_COURSE"
    TWIN_OP_SET_PLANNING_CONSTRAINTS = "TWIN_OP_SET_PLANNING_CONSTRAINTS"


class PlanningConstraintBundleInput(BaseModel):
    """Input parameters for adjusting planning constraints in What-If scenarios."""

    max_credit_hours: Decimal | None = Field(default=None, ge=1)
    max_credit_hours: Decimal | None = Field(default=None, ge=0, le=30)
    max_credit_hours_per_semester: Decimal | None = Field(default=None, ge=0, le=30)
    max_courses: int | None = Field(default=None, ge=1)
    max_courses_per_semester: int | None = Field(default=None, ge=1)
    max_options: int = Field(default=3, ge=1, le=10)
    max_paths: int = Field(default=3, ge=1, le=5)
    max_semesters_ahead: int = Field(default=8, ge=1, le=16)


# ==============================================================================
# Tool-Specific Request Models (Discriminated Union on tool_id)
# ==============================================================================


class BaseToolRequest(BaseModel):
    target_student_user_id: UUID
    tool_id: AdvisorToolId


class AcademicSnapshotRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT] = (
        AdvisorToolId.ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT
    )


class ProgressRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_GET_PROGRESS] = (
        AdvisorToolId.ADVISOR_TOOL_GET_PROGRESS
    )


class CheckEligibilityRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_CHECK_ELIGIBILITY] = (
        AdvisorToolId.ADVISOR_TOOL_CHECK_ELIGIBILITY
    )
    course_code: str = Field(min_length=1, max_length=50)


class GetRecommendationsRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_GET_RECOMMENDATIONS] = (
        AdvisorToolId.ADVISOR_TOOL_GET_RECOMMENDATIONS
    )
    opt_in_readiness: bool = False
    limit: int | None = Field(default=None, ge=1)


class GetSemesterPlansRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_GET_SEMESTER_PLANS] = (
        AdvisorToolId.ADVISOR_TOOL_GET_SEMESTER_PLANS
    )
    max_options: int = Field(default=3, ge=1, le=10)
    max_credit_hours: Decimal | None = Field(default=None, ge=1)
    max_credit_hours: Decimal | None = Field(default=None, ge=0, le=30)
    max_courses: int | None = Field(default=None, ge=1)


class GetDegreePathsRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_GET_DEGREE_PATHS] = (
        AdvisorToolId.ADVISOR_TOOL_GET_DEGREE_PATHS
    )
    max_paths: int = Field(default=3, ge=1, le=5)
    max_credit_hours_per_semester: Decimal | None = Field(default=None, ge=1)
    max_credit_hours_per_semester: Decimal | None = Field(default=None, ge=0, le=30)
    max_courses_per_semester: int | None = Field(default=None, ge=1)
    max_semesters_ahead: int = Field(default=8, ge=1, le=16)


class GetStudentIntelligenceRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_GET_STUDENT_INTELLIGENCE] = (
        AdvisorToolId.ADVISOR_TOOL_GET_STUDENT_INTELLIGENCE
    )


class CheckDelayConsequenceRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_CHECK_DELAY_CONSEQUENCE] = (
        AdvisorToolId.ADVISOR_TOOL_CHECK_DELAY_CONSEQUENCE
    )
    course_code: str = Field(min_length=1, max_length=50)


class RunWhatIfRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_RUN_WHAT_IF] = (
        AdvisorToolId.ADVISOR_TOOL_RUN_WHAT_IF
    )
    operation_id: WhatIfOperationId
    target_course_code: str | None = None
    constraints: PlanningConstraintBundleInput | None = None


class GetCurrentMockRegistrationRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION] = (
        AdvisorToolId.ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION
    )
    target_period_id: UUID


class ExplainRecommendationDecisionRequest(BaseToolRequest):
    tool_id: Literal[AdvisorToolId.ADVISOR_TOOL_EXPLAIN_RECOMMENDATION_DECISION] = (
        AdvisorToolId.ADVISOR_TOOL_EXPLAIN_RECOMMENDATION_DECISION
    )
    mode: str = Field(default="READINESS_AWARE")


AdvisorToolExecutionRequest = Annotated[
    Union[
        AcademicSnapshotRequest,
        ProgressRequest,
        CheckEligibilityRequest,
        GetRecommendationsRequest,
        GetSemesterPlansRequest,
        GetDegreePathsRequest,
        GetStudentIntelligenceRequest,
        CheckDelayConsequenceRequest,
        RunWhatIfRequest,
        GetCurrentMockRegistrationRequest,
        ExplainRecommendationDecisionRequest,
    ],
    Field(discriminator="tool_id"),
]


# ==============================================================================
# Allowlisted Response DTOs
# ==============================================================================


class StudentAttemptSummaryDTO(BaseModel):
    course_code: str
    outcome: str
    attempt_sequence: int | None = None
    attempted_on: str | None = None
    term_label: str | None = None
    credit_hours: Decimal | None = None


class AcademicSnapshotResultDTO(BaseModel):
    student_user_id: UUID
    study_plan_id: str
    reported_cumulative_gpa: Decimal | None = None
    reported_gpa_scale: Decimal | None = None
    reported_earned_credit_hours: Decimal | None = None
    total_attempts_count: int
    attempts: list[StudentAttemptSummaryDTO]
    limitations: list[str]


class RequirementGroupProgressDTO(BaseModel):
    group_id: str
    group_name_en: str | None = None
    group_name_ar: str | None = None
    required_credits: Decimal
    completed_credits: Decimal
    remaining_credits: Decimal
    completed_courses: list[str]
    remaining_courses: list[str]
    in_progress_courses: list[str]


class ProgressResultDTO(BaseModel):
    study_plan_id: str
    total_required_credits: Decimal
    total_completed_credits: Decimal
    total_remaining_credits: Decimal
    requirement_groups: list[RequirementGroupProgressDTO]
    zero_credit_courses_completed: list[str]
    zero_credit_courses_remaining: list[str]
    unresolved_courses: list[str]
    limitations: list[str]


class MissingPrerequisiteGroupDTO(BaseModel):
    group_id: str
    operator: str
    missing_course_codes: list[str]


class EligibilityResultDTO(BaseModel):
    course_code: str
    decision: str  # ELIGIBLE, NOT_ELIGIBLE, REVIEW_REQUIRED
    is_eligible: bool
    is_passed: bool
    passed_note: str | None = None
    missing_groups: list[MissingPrerequisiteGroupDTO]
    review_reasons: list[str]
    limitations: list[str]


class RecommendedCourseDTO(BaseModel):
    rank: int
    course_code: str
    course_name_en: str | None = None
    course_name_ar: str | None = None
    credit_hours: Decimal
    reason_codes: list[str]
    priority_tuple: list[Any]


class RecommendationsResultDTO(BaseModel):
    study_plan_id: str
    ranked_recommendations: list[RecommendedCourseDTO]
    review_required_courses: list[str]
    limitations: list[str]


class SemesterPlanOptionDTO(BaseModel):
    option_index: int
    course_codes: list[str]
    total_credit_hours: Decimal
    course_count: int
    rank_score: Decimal | None = None


class SemesterPlansResultDTO(BaseModel):
    study_plan_id: str
    options: list[SemesterPlanOptionDTO]
    limitations: list[str]


class ModeledSemesterStepDTO(BaseModel):
    semester_index: int
    course_codes: list[str]
    credit_hours: Decimal


class DegreePathOptionDTO(BaseModel):
    path_index: int
    modeled_period_count: int
    semesters: list[ModeledSemesterStepDTO]
    completion_summary: str


class DegreePathsResultDTO(BaseModel):
    study_plan_id: str
    paths: list[DegreePathOptionDTO]
    modeled_summary: str  # e.g., "Modeled path spans N periods"
    limitations: list[str]


class StudentIntelligenceObservationDTO(BaseModel):
    rule_id: str
    value: str
    count: int | None = None
    course_codes: list[str] = []


class CapabilityResultDTO(BaseModel):
    capability: str
    status: str
    observations: list[StudentIntelligenceObservationDTO]
    signals: list[StudentIntelligenceObservationDTO]
    reason_codes: list[str]
    limitations: list[str]


class StudentIntelligenceResultDTO(BaseModel):
    policy_version: str
    performance: CapabilityResultDTO
    strengths: CapabilityResultDTO
    difficulty: CapabilityResultDTO
    structural_risk: CapabilityResultDTO
    predictive_risk: CapabilityResultDTO  # Strictly BLOCKED_BY_EXTERNAL_DATA
    readiness: CapabilityResultDTO | None = None
    limitations: list[str]


class DelayConsequenceResultDTO(BaseModel):
    target_course_code: str
    status: str  # NO_MODELED_STRUCTURAL_IMPACT, MODELED_STRUCTURAL_IMPACT, REVIEW_REQUIRED
    reasons: list[str]
    affected_courses: list[str]
    review_required_reasons: list[str]
    structural_facts: list[str]
    limitations: list[str]


class WhatIfDeltaDTO(BaseModel):
    delta_id: str
    delta_type: str
    description: str
    affected_courses: list[str]


class WhatIfResultDTO(BaseModel):
    scenario_id: str
    operation_id: str
    is_valid: bool
    status: str
    deltas: list[WhatIfDeltaDTO]
    operation_results: list[dict[str, Any]]
    limitations: list[str]


class CurrentMockRegistrationResultDTO(BaseModel):
    intent_id: str
    target_period_id: UUID
    course_codes: list[str]
    current_validity: str
    current_validity: str | None = None
    revalidation_status: str
    revalidation_reason_codes: list[str]
    is_expired: bool
    limitations: list[str]


class DecisionFactorEvaluationDTO(BaseModel):
    factor_id: str
    classification: str
    action: str
    reason: str
    ordering_value: int | None = None


class RelativeOrderChangeDTO(BaseModel):
    course_code: str
    baseline_rank: int
    final_rank: int


class ExplainRecommendationDecisionResultDTO(BaseModel):
    decision_type: str
    decision_mode: str
    baseline_order: list[str]
    final_order: list[str]
    applied_factors: list[DecisionFactorEvaluationDTO]
    ignored_factors: list[DecisionFactorEvaluationDTO]
    changed_relative_orders: list[RelativeOrderChangeDTO]
    limitations: list[str]


class AdvisorToolExecutionResponse(BaseModel):
    """Unified allowlisted response envelope for all Advisor Copilot tool executions."""

    tool_id: str
    authority_class: str
    student_user_id: UUID
    university_id: UUID
    side_effects: str = "NONE"
    result: Any
