"""Minimal HTTP contracts for the authenticated read-only advisor."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, Strict, field_validator

from app.advisor.models import (
    AI_ADVISOR_POLICY_VERSION,
    AdvisorIntent,
    AnswerAuthority,
    AuthoritativeSource,
    CourseInformation,
    EntityResolutionStatus,
    OutOfScopeReason,
    StructuredAdvisorResult,
)
from app.advisor.explanation import ExplanationLanguage, ExplanationStatus
from app.degree_path.models import DegreePathResult, PathReasonCode, PathStatus
from app.planner.models import PlanReasonCode, SemesterPlannerResult
from app.progress.models import AcademicProgress, CourseProgressState, RequirementType
from app.recommendations.models import RecommendationReason, RecommendationResult
from app.rules.models import (
    CanTakeDecision,
    CanTakeError,
    Decision,
    DecisionReason,
    DependencyType,
    PrerequisiteLogicStatus,
)


ADVISOR_MESSAGE_MAX_LENGTH = 4000


class AdvisorRequest(BaseModel):
    """Message-only request; every provider and academic control is forbidden."""

    model_config = ConfigDict(extra="forbid")

    message: Annotated[
        str,
        Strict(),
        Field(min_length=1, max_length=ADVISOR_MESSAGE_MAX_LENGTH),
    ]

    @field_validator("message")
    @classmethod
    def trim_and_require_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class ResolvedCourseResponse(BaseModel):
    course_code: str
    canonical_arabic_name: str
    canonical_english_name: str | None


class CourseResolutionResponse(BaseModel):
    status: EntityResolutionStatus
    resolved_course: ResolvedCourseResponse | None
    candidate_course_codes: list[str]


class ClarificationResponse(BaseModel):
    reason: str
    message_key: str
    candidate_course_codes: list[str]


class DecisionReferenceResponse(BaseModel):
    source: AuthoritativeSource
    code: str


class PolicyVersionResponse(BaseModel):
    source: str
    version: str


class AdvisorEvidenceResponse(BaseModel):
    source: AuthoritativeSource
    course_codes: list[str]
    decision_references: list[DecisionReferenceResponse]
    policy_version: str | None


class AdvisorTraceResponse(BaseModel):
    authoritative_sources: list[AuthoritativeSource]
    course_codes: list[str]
    decision_references: list[DecisionReferenceResponse]
    policy_versions: list[PolicyVersionResponse]
    option_references: list[int]


class TargetAttemptStateResponse(BaseModel):
    has_passed_target: bool
    has_in_progress_target: bool


class DependencyGroupResponse(BaseModel):
    group_number: int
    dependency_type: DependencyType
    option_course_codes: list[str]
    passed_option_course_codes: list[str]
    non_passed_option_course_codes: list[str]


class EligibilityAdvisorPayload(BaseModel):
    kind: Literal["eligibility"] = "eligibility"
    decision: Decision
    target_course_code: str
    target_name_ar: str | None
    prerequisite_logic_status: PrerequisiteLogicStatus
    target_attempt_state: TargetAttemptStateResponse
    satisfied_dependency_groups: list[DependencyGroupResponse]
    missing_dependency_groups: list[DependencyGroupResponse]
    reasons: list[DecisionReason]
    review_reasons: list[DecisionReason]


class AcademicRequestErrorAdvisorPayload(BaseModel):
    kind: Literal["academic_request_error"] = "academic_request_error"
    error_code: str
    target_course_code: str | None


class ProgressGroupResponse(BaseModel):
    group_code: str
    name_ar: str
    name_en: str | None
    requirement_type: RequirementType
    required_credits: Decimal
    completed_listed_credits: Decimal
    remaining_required_credits: Decimal
    is_satisfied: bool


class ProgressCourseResponse(BaseModel):
    course_code: str
    credit_hours: Decimal
    requirement_group_code: str
    state: CourseProgressState


class ProgressAdvisorPayload(BaseModel):
    kind: Literal["progress"] = "progress"
    plan_total_required_credits: Decimal
    completed_plan_credits: Decimal
    in_progress_plan_credits: Decimal
    remaining_plan_credits: Decimal
    all_modeled_plan_requirements_satisfied: bool
    requirement_groups: list[ProgressGroupResponse]
    courses: list[ProgressCourseResponse]


class RecommendationCandidateResponse(BaseModel):
    rank: int
    course_code: str
    course_name_ar: str | None
    credit_hours: Decimal
    requirement_group_code: str
    eligibility_decision: str
    reason_codes: list[RecommendationReason]
    newly_eligible_course_codes: list[str]
    previously_attempted: bool


class RecommendationReviewResponse(BaseModel):
    course_code: str
    course_name_ar: str | None
    review_reason: str


class RecommendationsAdvisorPayload(BaseModel):
    kind: Literal["recommendations"] = "recommendations"
    policy_version: str
    ranked_courses: list[RecommendationCandidateResponse]
    review_required_courses: list[RecommendationReviewResponse]
    excluded_in_progress: list[str]


class PlannedCourseResponse(BaseModel):
    course_code: str
    course_name_ar: str | None
    course_name_en: str | None
    credit_hours: Decimal
    requirement_group_code: str


class SemesterOptionResponse(BaseModel):
    rank: int
    courses: list[PlannedCourseResponse]
    total_credit_hours: Decimal
    reason_codes: list[PlanReasonCode]
    newly_satisfied_requirement_group_codes: list[str]
    newly_eligible_course_codes: list[str]


class SemesterPlansAdvisorPayload(BaseModel):
    kind: Literal["semester_plans"] = "semester_plans"
    policy_version: str
    planning_scope: str
    max_credit_hours: Decimal
    max_courses: int | None
    max_options: int
    options: list[SemesterOptionResponse]
    review_required_courses: list[str]
    excluded_in_progress: list[str]


class ModeledSemesterResponse(BaseModel):
    semester_index: int
    courses: list[PlannedCourseResponse]
    total_credit_hours: Decimal
    completed_plan_credits_after: Decimal
    remaining_plan_credits_after: Decimal


class DegreePathOptionResponse(BaseModel):
    rank: int
    status: PathStatus
    semesters: list[ModeledSemesterResponse]
    remaining_required_course_codes: list[str]
    unresolved_blocker_codes: list[str]
    reason_codes: list[PathReasonCode]


class DegreePathsAdvisorPayload(BaseModel):
    kind: Literal["degree_paths"] = "degree_paths"
    policy_version: str
    planning_scope: str
    max_credit_hours_per_semester: Decimal
    max_courses_per_semester: int | None
    max_semesters_ahead: int
    max_paths: int
    paths: list[DegreePathOptionResponse]
    unresolved_review_required_courses: list[str]
    persisted_in_progress_courses: list[str]


class CourseInformationAdvisorPayload(BaseModel):
    kind: Literal["course_information"] = "course_information"
    course_code: str
    canonical_arabic_name: str
    canonical_english_name: str | None
    credit_hours: Decimal | None
    requirement_group_code: str | None
    catalog_status: str | None
    prerequisite_logic_status: str | None
    raw_prerequisite_text: str | None


AdvisorPayloadResponse = Annotated[
    EligibilityAdvisorPayload
    | AcademicRequestErrorAdvisorPayload
    | ProgressAdvisorPayload
    | RecommendationsAdvisorPayload
    | SemesterPlansAdvisorPayload
    | DegreePathsAdvisorPayload
    | CourseInformationAdvisorPayload,
    Field(discriminator="kind"),
]


class AdvisorResponse(BaseModel):
    policy_version: str
    intent: AdvisorIntent
    answer_authority: AnswerAuthority
    course_resolution: CourseResolutionResponse | None
    clarification: ClarificationResponse | None
    out_of_scope_reason: OutOfScopeReason | None
    evidence: list[AdvisorEvidenceResponse]
    trace: AdvisorTraceResponse
    result: AdvisorPayloadResponse | None
    explanation: str | None
    explanation_status: ExplanationStatus
    explanation_language: ExplanationLanguage | None

    @classmethod
    def from_domain(
        cls,
        domain: StructuredAdvisorResult,
        *,
        explanation: str | None = None,
        explanation_status: ExplanationStatus = ExplanationStatus.UNAVAILABLE,
        explanation_language: ExplanationLanguage | None = None,
    ) -> "AdvisorResponse":
        resolution = None
        if domain.course_resolution is not None:
            resolved = domain.course_resolution.resolved_course
            resolution = CourseResolutionResponse(
                status=domain.course_resolution.status,
                resolved_course=(
                    ResolvedCourseResponse.model_validate(resolved, from_attributes=True)
                    if resolved is not None
                    else None
                ),
                candidate_course_codes=list(domain.course_resolution.candidate_course_codes),
            )
        clarification = None
        if domain.clarification is not None:
            clarification = ClarificationResponse(
                reason=domain.clarification.reason.value,
                message_key=domain.clarification.message_key,
                candidate_course_codes=list(domain.clarification.candidate_course_codes),
            )
        return cls(
            policy_version=AI_ADVISOR_POLICY_VERSION,
            intent=domain.intent,
            answer_authority=domain.authority,
            course_resolution=resolution,
            clarification=clarification,
            out_of_scope_reason=domain.out_of_scope_reason,
            evidence=[
                AdvisorEvidenceResponse(
                    source=item.source,
                    course_codes=list(item.course_codes),
                    decision_references=[
                        DecisionReferenceResponse(source=ref.source, code=ref.code)
                        for ref in item.decision_references
                    ],
                    policy_version=item.policy_version,
                )
                for item in domain.evidence
            ],
            trace=AdvisorTraceResponse(
                authoritative_sources=list(domain.trace.authoritative_sources_used),
                course_codes=list(domain.trace.course_codes),
                decision_references=[
                    DecisionReferenceResponse(source=ref.source, code=ref.code)
                    for ref in domain.trace.decision_references
                ],
                policy_versions=[
                    PolicyVersionResponse(source=ref.source.value, version=ref.version)
                    for ref in domain.trace.policy_versions
                ],
                option_references=list(domain.trace.option_references),
            ),
            result=_payload_response(domain.authoritative_payload),
            explanation=explanation,
            explanation_status=explanation_status,
            explanation_language=explanation_language,
        )


def _payload_response(payload: object) -> AdvisorPayloadResponse | None:
    if payload is None:
        return None
    if isinstance(payload, CanTakeDecision):
        return EligibilityAdvisorPayload(
            decision=payload.decision,
            target_course_code=payload.target_course_code,
            target_name_ar=payload.target_name_ar,
            prerequisite_logic_status=payload.prerequisite_logic_status,
            target_attempt_state=TargetAttemptStateResponse.model_validate(
                payload.target_attempt_state,
                from_attributes=True,
            ),
            satisfied_dependency_groups=[
                DependencyGroupResponse.model_validate(item, from_attributes=True)
                for item in payload.satisfied_dependency_groups
            ],
            missing_dependency_groups=[
                DependencyGroupResponse.model_validate(item, from_attributes=True)
                for item in payload.missing_dependency_groups
            ],
            reasons=list(payload.reasons),
            review_reasons=list(payload.review_reasons),
        )
    if isinstance(payload, CanTakeError):
        return AcademicRequestErrorAdvisorPayload(
            error_code=payload.error_code.value,
            target_course_code=payload.target_course_code,
        )
    if isinstance(payload, AcademicProgress):
        return ProgressAdvisorPayload(
            plan_total_required_credits=payload.plan_total_required_credits,
            completed_plan_credits=payload.completed_plan_credits,
            in_progress_plan_credits=payload.in_progress_plan_credits,
            remaining_plan_credits=payload.remaining_plan_credits,
            all_modeled_plan_requirements_satisfied=payload.all_modeled_plan_requirements_satisfied,
            requirement_groups=[
                ProgressGroupResponse.model_validate(item, from_attributes=True)
                for item in payload.requirement_groups
            ],
            courses=[
                ProgressCourseResponse.model_validate(item, from_attributes=True)
                for item in payload.courses
            ],
        )
    if isinstance(payload, RecommendationResult):
        return RecommendationsAdvisorPayload(
            policy_version=payload.recommendation_policy_version,
            ranked_courses=[
                RecommendationCandidateResponse.model_validate(item, from_attributes=True)
                for item in payload.ranked_recommendations
            ],
            review_required_courses=[
                RecommendationReviewResponse.model_validate(item, from_attributes=True)
                for item in payload.review_required_courses
            ],
            excluded_in_progress=list(payload.excluded_in_progress),
        )
    if isinstance(payload, SemesterPlannerResult):
        return SemesterPlansAdvisorPayload(
            policy_version=payload.semester_planner_policy_version,
            planning_scope=payload.planning_scope,
            max_credit_hours=payload.constraints.max_credit_hours,
            max_courses=payload.constraints.max_courses,
            max_options=payload.constraints.max_options,
            options=[
                SemesterOptionResponse(
                    rank=option.rank,
                    courses=[
                        PlannedCourseResponse.model_validate(course, from_attributes=True)
                        for course in option.courses
                    ],
                    total_credit_hours=option.total_credit_hours,
                    reason_codes=list(option.reason_codes),
                    newly_satisfied_requirement_group_codes=list(
                        option.newly_satisfied_requirement_group_codes
                    ),
                    newly_eligible_course_codes=list(option.newly_eligible_course_codes),
                )
                for option in payload.plan_options
            ],
            review_required_courses=list(payload.review_required_courses),
            excluded_in_progress=list(payload.excluded_in_progress),
        )
    if isinstance(payload, DegreePathResult):
        return DegreePathsAdvisorPayload(
            policy_version=payload.degree_path_policy_version,
            planning_scope=payload.planning_scope,
            max_credit_hours_per_semester=payload.constraints.max_credit_hours_per_semester,
            max_courses_per_semester=payload.constraints.max_courses_per_semester,
            max_semesters_ahead=payload.constraints.max_semesters_ahead,
            max_paths=payload.constraints.max_paths,
            paths=[
                DegreePathOptionResponse(
                    rank=path.rank,
                    status=path.status,
                    semesters=[
                        ModeledSemesterResponse(
                            semester_index=semester.semester_index,
                            courses=[
                                PlannedCourseResponse.model_validate(course, from_attributes=True)
                                for course in semester.plan_option.courses
                            ],
                            total_credit_hours=semester.plan_option.total_credit_hours,
                            completed_plan_credits_after=semester.completed_plan_credits_after,
                            remaining_plan_credits_after=semester.remaining_plan_credits_after,
                        )
                        for semester in path.semesters
                    ],
                    remaining_required_course_codes=list(path.remaining_required_course_codes),
                    unresolved_blocker_codes=list(path.unresolved_blocker_codes),
                    reason_codes=list(path.reason_codes),
                )
                for path in payload.paths
            ],
            unresolved_review_required_courses=list(payload.unresolved_review_required_courses),
            persisted_in_progress_courses=list(payload.persisted_in_progress_courses),
        )
    if isinstance(payload, CourseInformation):
        return CourseInformationAdvisorPayload.model_validate(
            {"kind": "course_information", **_attributes(payload)}
        )
    raise ValueError("Unsupported advisor payload type")


def _attributes(value: object) -> dict[str, object]:
    return dict(vars(value))
