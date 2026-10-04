"""Read-only adapters composing existing Morshidi engines for Advisor Copilot."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.academic_digital_twin.engine import evaluate_scenario
from app.academic_digital_twin.fingerprint import calculate_base_state_fingerprint
from app.academic_digital_twin.models import (
    DIGITAL_TWIN_CONTRACT_VERSION,
    AuthoritativeAcademicSnapshot,
    AuthoritativeAttempt,
    OperationId,
    PlanIdentity,
    PlanningConstraintBundle,
    ScenarioIdentity,
    ScenarioOperation,
)
from app.advisor_persistence.models import AdvisorAccessContext
from app.catalog.errors import CatalogIntegrityError, CatalogTransportError, StudyPlanNotFound
from app.catalog.repository import AcademicCatalogRepository
from app.decision_intelligence.delay import analyze_delay
from app.decision_intelligence.models import (
    DECISION_INTELLIGENCE_INTEGRATION_POLICY_VERSION,
    DELAY_CONSEQUENCE_POLICY_VERSION,
    DecisionMode,
    DelayConsequenceInput,
    SimulationProvenance as P4SimulationProvenance,
    SimulationStateKind,
)
from app.decision_intelligence.recommendation import integrate_recommendations
from app.degree_path.models import DEGREE_PATH_POLICY_VERSION, DegreePathConstraints
from app.core.academic_compute import AcademicComputeLimiter
from app.mock_registration.resolution import resolve_current_intents
from app.mock_registration_persistence.errors import (
    MockRegistrationPersistenceError,
    PersistenceFailureCode,
)
from app.mock_registration_persistence.models import (
    PersistedIntentRevision,
    PersistedTargetPeriod,
)
from app.mock_registration_service.context import AcademicContextLoader
from app.mock_registration_service.models import AcademicContextSnapshot
from app.mock_registration_service.revalidation import revalidate, stored_domain_record
from app.planner.engine import plan_semester
from app.planner.models import SEMESTER_PLANNER_POLICY_VERSION, PlannerConstraints
from app.progress.engine import calculate_academic_progress
from app.progress.models import CourseProgressState, RequirementType
from app.recommendations.engine import recommend_courses
from app.recommendations.models import RECOMMENDATION_POLICY_VERSION
from app.rules.models import CanTakeError, Decision
from app.services.eligibility import EligibilityService
from app.services.student import StudentService
from app.student.errors import (
    StudentProfileIntegrityError,
    StudentProfileNotFound,
    StudentProfileTransportError,
)
from app.student.repository import StudentAcademicRepository
from app.student_intelligence.engine import evaluate_student_intelligence
from app.student_intelligence.models import (
    POLICY_VERSION as STUDENT_INTELLIGENCE_POLICY_VERSION,
    StudentIntelligenceContext,
)

from app.advisor_copilot.errors import (
    AdvisorCopilotServiceError,
    AdvisorCopilotServiceErrorCode,
)
from app.advisor_copilot.models import (
    AcademicSnapshotRequest,
    AcademicSnapshotResultDTO,
    CapabilityResultDTO,
    CheckDelayConsequenceRequest,
    CheckEligibilityRequest,
    CurrentMockRegistrationResultDTO,
    DecisionFactorEvaluationDTO,
    DegreePathOptionDTO,
    DegreePathsResultDTO,
    DelayConsequenceResultDTO,
    EligibilityResultDTO,
    ExplainRecommendationDecisionRequest,
    ExplainRecommendationDecisionResultDTO,
    GetCurrentMockRegistrationRequest,
    GetDegreePathsRequest,
    GetRecommendationsRequest,
    GetSemesterPlansRequest,
    GetStudentIntelligenceRequest,
    MissingPrerequisiteGroupDTO,
    ModeledSemesterStepDTO,
    ProgressRequest,
    ProgressResultDTO,
    RecommendationsResultDTO,
    RecommendedCourseDTO,
    RelativeOrderChangeDTO,
    RequirementGroupProgressDTO,
    RunWhatIfRequest,
    SemesterPlanOptionDTO,
    SemesterPlansResultDTO,
    StudentAttemptSummaryDTO,
    StudentIntelligenceObservationDTO,
    StudentIntelligenceResultDTO,
    WhatIfDeltaDTO,
    WhatIfOperationId,
    WhatIfResultDTO,
)


ENGINE_POLICY_VERSIONS = (
    f"recommendations:{RECOMMENDATION_POLICY_VERSION}",
    f"planner:{SEMESTER_PLANNER_POLICY_VERSION}",
    f"degree_path:{DEGREE_PATH_POLICY_VERSION}",
    f"decision_intelligence:{DECISION_INTELLIGENCE_INTEGRATION_POLICY_VERSION}",
    f"delay_consequence:{DELAY_CONSEQUENCE_POLICY_VERSION}",
    f"student_intelligence:{STUDENT_INTELLIGENCE_POLICY_VERSION}",
    f"digital_twin:{DIGITAL_TWIN_CONTRACT_VERSION}",
)


def _deterministic_scenario_id(fingerprint: str, op: ScenarioOperation) -> str:
    op_payload = [op.operation_id, op.target_course_code or ""]
    if op.constraints:
        op_payload.extend([
            str(op.constraints.max_credit_hours),
            str(op.constraints.max_courses if op.constraints.max_courses is not None else ""),
            str(op.constraints.max_options),
            str(
                op.constraints.max_credit_hours_per_semester
                if op.constraints.max_credit_hours_per_semester is not None
                else ""
            ),
            str(
                op.constraints.max_courses_per_semester
                if op.constraints.max_courses_per_semester is not None
                else ""
            ),
            str(op.constraints.max_semesters_ahead),
            str(op.constraints.max_paths),
        ])
    canonical_repr = ":".join(op_payload)
    op_digest = hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()[:12]
    return f"adv_whatif_{fingerprint[:16]}_{op_digest}"



async def _load_authoritative_context(
    context_loader: AcademicContextLoader,
    student_user_id: UUID,
) -> AcademicContextSnapshot:
    """Load authoritative student context with finite, privacy-safe error mapping."""
    try:
        return await context_loader.load_owner_context(student_user_id)
    except AdvisorCopilotServiceError:
        raise
    except (StudentProfileNotFound, StudyPlanNotFound) as error:
        raise AdvisorCopilotServiceError(
            code=AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE,
            detail="Authoritative academic context was not found",
            status_code=404,
        ) from error
    except (StudentProfileTransportError, CatalogTransportError) as error:
        raise AdvisorCopilotServiceError(
            code=AdvisorCopilotServiceErrorCode.PERSISTENCE_UNAVAILABLE,
            detail="Authoritative academic context service is temporarily unavailable",
            status_code=503,
        ) from error
    except (StudentProfileIntegrityError, CatalogIntegrityError) as error:
        raise AdvisorCopilotServiceError(
            code=AdvisorCopilotServiceErrorCode.INTERNAL_ERROR,
            detail="Authoritative academic context failed integrity validation",
            status_code=500,
        ) from error
    except Exception as error:
        raise AdvisorCopilotServiceError(
            code=AdvisorCopilotServiceErrorCode.INTERNAL_ERROR,
            detail="An internal error occurred while loading academic context",
            status_code=500,
        ) from error


class BaseAdvisorAdapter:
    """Base class for read-only advisor copilot adapters."""

    def __init__(
        self,
        student_repository: StudentAcademicRepository,
        catalog_repository: AcademicCatalogRepository,
    ) -> None:
        self._student_repo = student_repository
        self._catalog_repo = catalog_repository


class AcademicSnapshotAdapter(BaseAdvisorAdapter):
    async def execute(
        self, context: AdvisorAccessContext, request: AcademicSnapshotRequest
    ) -> AcademicSnapshotResultDTO:
        state = await self._student_repo.load_student_academic_state(context.student_user_id)
        attempt_records = await self._student_repo.load_attempt_records(context.student_user_id)

        attempts_dto = [
            StudentAttemptSummaryDTO(
                course_code=att.course_code,
                outcome=att.outcome.value,
                attempt_sequence=att.attempt_sequence,
                attempted_on=str(att.attempted_on) if att.attempted_on else None,
                term_label=att.term_label,
                credit_hours=att.attempt_credit_hours,
            )
            for att in attempt_records
        ]

        return AcademicSnapshotResultDTO(
            student_user_id=context.student_user_id,
            study_plan_id=str(state.study_plan_id),
            reported_cumulative_gpa=state.reported_cumulative_gpa,
            reported_gpa_scale=state.reported_gpa_scale,
            reported_earned_credit_hours=state.reported_earned_credit_hours,
            total_attempts_count=len(attempts_dto),
            attempts=attempts_dto,
            limitations=[
                "Historical academic facts only; does not forecast future GPA or course outcomes.",
                "Student records are verified via authoritative institutional persistence.",
            ],
        )


class ProgressAdapter(BaseAdvisorAdapter):
    async def execute(
        self, context: AdvisorAccessContext, request: ProgressRequest
    ) -> ProgressResultDTO:
        state = await self._student_repo.load_student_academic_state(context.student_user_id)
        catalog = await self._catalog_repo.load_progress_catalog(state.study_plan_id)
        progress = calculate_academic_progress(
            catalog,
            state.attempts,
            reported_cumulative_gpa=state.reported_cumulative_gpa,
            reported_gpa_scale=state.reported_gpa_scale,
            reported_earned_credit_hours=state.reported_earned_credit_hours,
        )

        groups_dto = [
            RequirementGroupProgressDTO(
                group_id=str(g.group_id),
                group_name_en=g.name_en if g.name_en is not None else g.name_ar,
                group_name_ar=g.name_ar,
                required_credits=g.required_credits,
                completed_credits=g.credited_toward_requirement,
                remaining_credits=g.remaining_required_credits,
                completed_courses=[
                    c.course_code
                    for c in progress.courses
                    if c.requirement_group_id == g.group_id and c.state == CourseProgressState.COMPLETED
                ],
                remaining_courses=[
                    c.course_code
                    for c in progress.courses
                    if c.requirement_group_id == g.group_id
                    and c.state in (CourseProgressState.NOT_ATTEMPTED, CourseProgressState.ATTEMPTED_NOT_COMPLETED)
                ],
                in_progress_courses=[
                    c.course_code
                    for c in progress.courses
                    if c.requirement_group_id == g.group_id and c.state == CourseProgressState.IN_PROGRESS
                ],
            )
            for g in progress.requirement_groups
        ]

        zero_credit_completed = [
            c.course_code
            for c in progress.courses
            if c.credit_hours == Decimal("0.0") and c.state == CourseProgressState.COMPLETED
        ]
        zero_credit_remaining = [
            c.course_code
            for c in progress.courses
            if c.credit_hours == Decimal("0.0") and c.state != CourseProgressState.COMPLETED
        ]

        return ProgressResultDTO(
            study_plan_id=str(state.study_plan_id),
            total_required_credits=progress.plan_total_required_credits,
            total_completed_credits=progress.completed_plan_credits,
            total_remaining_credits=progress.remaining_plan_credits,
            requirement_groups=groups_dto,
            zero_credit_courses_completed=zero_credit_completed,
            zero_credit_courses_remaining=zero_credit_remaining,
            unresolved_courses=[],
            limitations=[
                "Progress calculations are derived strictly from verified catalog and student attempts.",
                "Completed credits do not constitute official degree clearance.",
            ],
        )


class EligibilityAdapter(BaseAdvisorAdapter):
    def __init__(
        self,
        student_repository: StudentAcademicRepository,
        catalog_repository: AcademicCatalogRepository,
        eligibility_service: EligibilityService,
    ) -> None:
        super().__init__(student_repository, catalog_repository)
        self._eligibility_service = eligibility_service

    async def execute(
        self, context: AdvisorAccessContext, request: CheckEligibilityRequest
    ) -> EligibilityResultDTO:
        state = await self._student_repo.load_student_academic_state(context.student_user_id)
        can_take = await self._eligibility_service.evaluate_can_take(
            UUID(state.study_plan_id), request.course_code, state.attempts
        )

        if isinstance(can_take, CanTakeError):
            return EligibilityResultDTO(
                course_code=request.course_code,
                decision="NOT_ELIGIBLE",
                is_eligible=False,
                is_passed=False,
                passed_note=None,
                missing_groups=[],
                review_reasons=[can_take.error_code.value],
                limitations=[
                    "Eligibility evaluates prerequisite rule satisfaction only; does not verify section seat availability.",
                ],
            )

        is_passed = can_take.target_attempt_state.has_passed_target
        is_eligible = can_take.decision == Decision.ELIGIBLE

        missing_groups_dto = [
            MissingPrerequisiteGroupDTO(
                group_id=str(mg.group_number),
                operator=mg.dependency_type.value,
                missing_course_codes=list(mg.non_passed_option_course_codes),
            )
            for mg in can_take.missing_dependency_groups
        ]

        review_reasons = [r.value for r in can_take.review_reasons]
        if can_take.decision == Decision.REVIEW_REQUIRED and not review_reasons:
            review_reasons.append("Course prerequisite structure contains source ambiguities or unresolved conflicts.")

        return EligibilityResultDTO(
            course_code=request.course_code,
            decision=can_take.decision.value,
            is_eligible=is_eligible,
            is_passed=is_passed,
            passed_note="Course has already been completed with passing grade" if is_passed else None,
            missing_groups=missing_groups_dto,
            review_reasons=review_reasons,
            limitations=[
                "Eligibility evaluates prerequisite rule satisfaction only; does not verify section seat availability.",
                "REVIEW_REQUIRED courses require human academic authority resolution.",
            ],
        )


class RecommendationsAdapter(BaseAdvisorAdapter):
    async def execute(
        self, context: AdvisorAccessContext, request: GetRecommendationsRequest
    ) -> RecommendationsResultDTO:
        state = await self._student_repo.load_student_academic_state(context.student_user_id)
        progress_catalog = await self._catalog_repo.load_progress_catalog(state.study_plan_id)
        eligibility_catalog = await self._catalog_repo.load_plan_eligibility_catalog(state.study_plan_id)

        baseline = recommend_courses(
            progress_catalog,
            eligibility_catalog,
            state.attempts,
            reported_cumulative_gpa=state.reported_cumulative_gpa,
            reported_gpa_scale=state.reported_gpa_scale,
            reported_earned_credit_hours=state.reported_earned_credit_hours,
        )

        final_candidates = baseline.ranked_recommendations

        if request.opt_in_readiness:
            provenance = P4SimulationProvenance(
                SimulationStateKind.AUTHORITATIVE,
                state_reference=f"adv_rec_{context.student_user_id}",
            )
            enhanced = integrate_recommendations(
                baseline,
                mode=DecisionMode.READINESS_AWARE,
                simulation_provenance=provenance,
            )
            final_candidates = [view.candidate for view in enhanced.ranked_candidates]

        if request.limit is not None:
            final_candidates = final_candidates[: request.limit]

        ranked_dto = [
            RecommendedCourseDTO(
                rank=idx + 1,
                course_code=cand.course_code,
                course_name_en=None,
                course_name_ar=cand.course_name_ar,
                credit_hours=cand.credit_hours,
                reason_codes=[r.value for r in cand.reason_codes],
                priority_tuple=list(cand.priority_tuple),
            )
            for idx, cand in enumerate(final_candidates)
        ]

        return RecommendationsResultDTO(
            study_plan_id=str(state.study_plan_id),
            ranked_recommendations=ranked_dto,
            review_required_courses=[r.course_code for r in baseline.review_required_courses],
            limitations=[
                "Course recommendations reflect auditable curriculum priorities; they do not replace human advising.",
                "Review-required courses are withheld from ranking until catalog ambiguities are resolved.",
            ],
        )


class SemesterPlansAdapter(BaseAdvisorAdapter):
    def __init__(self, student_repository, catalog_repository, academic_compute_limiter=None) -> None:
        super().__init__(student_repository, catalog_repository)
        self._academic_compute_limiter = academic_compute_limiter or AcademicComputeLimiter()

    async def execute(
        self, context: AdvisorAccessContext, request: GetSemesterPlansRequest
    ) -> SemesterPlansResultDTO:
        state = await self._student_repo.load_student_academic_state(context.student_user_id)
        progress_catalog = await self._catalog_repo.load_progress_catalog(state.study_plan_id)
        eligibility_catalog = await self._catalog_repo.load_plan_eligibility_catalog(state.study_plan_id)

        full_recommendations = recommend_courses(
            progress_catalog,
            eligibility_catalog,
            state.attempts,
            reported_cumulative_gpa=state.reported_cumulative_gpa,
            reported_gpa_scale=state.reported_gpa_scale,
            reported_earned_credit_hours=state.reported_earned_credit_hours,
        )

        constraints = PlannerConstraints(
            max_credit_hours=(
                request.max_credit_hours
                if request.max_credit_hours is not None
                else Decimal("18.0")
            ),
            max_courses=request.max_courses,
            max_options=request.max_options,
        )

        result = await self._academic_compute_limiter.run(
            lambda check_budget: plan_semester(
                progress_catalog,
                eligibility_catalog,
                state.attempts,
                full_recommendations,
                constraints,
                reported_cumulative_gpa=state.reported_cumulative_gpa,
                reported_gpa_scale=state.reported_gpa_scale,
                reported_earned_credit_hours=state.reported_earned_credit_hours,
                check_budget=check_budget,
            ),
        )

        options_dto = [
            SemesterPlanOptionDTO(
                option_index=opt.rank,
                course_codes=[c.course_code for c in opt.courses],
                total_credit_hours=opt.total_credit_hours,
                course_count=opt.total_courses,
                rank_score=None,
            )
            for opt in result.plan_options
        ]

        return SemesterPlansResultDTO(
            study_plan_id=str(state.study_plan_id),
            options=options_dto,
            limitations=[
                "Semester plan options are modeled candidate combinations; they do not guarantee timetable feasibility.",
                "Section scheduling and offering capacity must be verified during registration.",
            ],
        )


class DegreePathsAdapter(BaseAdvisorAdapter):
    def __init__(
        self,
        student_repository: StudentAcademicRepository,
        catalog_repository: AcademicCatalogRepository,
        academic_compute_limiter: AcademicComputeLimiter | None = None,
    ) -> None:
        super().__init__(student_repository, catalog_repository)
        self._degree_path_service = StudentService(
            student_repository, None, catalog_repository, academic_compute_limiter,  # type: ignore[arg-type]
        )

    async def execute(
        self, context: AdvisorAccessContext, request: GetDegreePathsRequest
    ) -> DegreePathsResultDTO:
        result = await self._degree_path_service.get_degree_paths(
            context.student_user_id,
            max_credit_hours_per_semester=(
                request.max_credit_hours_per_semester
                if request.max_credit_hours_per_semester is not None
                else Decimal("18.0")
            ),
            max_courses_per_semester=request.max_courses_per_semester,
            max_semesters_ahead=request.max_semesters_ahead,
            max_paths=request.max_paths,
        )

        paths_dto = []
        for path in result.paths:
            semesters_dto = [
                ModeledSemesterStepDTO(
                    semester_index=entry.semester_index,
                    course_codes=[c.course_code for c in entry.plan_option.courses],
                    credit_hours=entry.plan_option.total_credit_hours,
                )
                for entry in path.semesters
            ]
            period_count = len(path.semesters)
            paths_dto.append(
                DegreePathOptionDTO(
                    path_index=path.rank,
                    modeled_period_count=period_count,
                    semesters=semesters_dto,
                    completion_summary=f"Modeled path spans {period_count} academic registration periods",
                )
            )

        modeled_summary = (
            f"Modeled paths span {paths_dto[0].modeled_period_count} periods under current plan constraints"
            if paths_dto
            else "No feasible degree path completed within horizon constraints"
        )

        return DegreePathsResultDTO(
            study_plan_id=str(result.study_plan_id),
            paths=paths_dto,
            modeled_summary=modeled_summary,
            limitations=[
                "Degree path projections are forward-looking simulation sequences, NOT official graduation date guarantees.",
                "Future semester offerings, prerequisite policy changes, or academic standings may alter path progression.",
            ],
        )


class StudentIntelligenceAdapter(BaseAdvisorAdapter):
    async def execute(
        self, context: AdvisorAccessContext, request: GetStudentIntelligenceRequest
    ) -> StudentIntelligenceResultDTO:
        state = await self._student_repo.load_student_academic_state(context.student_user_id)
        attempt_records = await self._student_repo.load_attempt_records(context.student_user_id)
        progress_catalog = await self._catalog_repo.load_progress_catalog(state.study_plan_id)
        progress = calculate_academic_progress(
            progress_catalog,
            state.attempts,
            reported_cumulative_gpa=state.reported_cumulative_gpa,
            reported_gpa_scale=state.reported_gpa_scale,
            reported_earned_credit_hours=state.reported_earned_credit_hours,
        )

        required_group_ids = {
            g.group_id
            for g in progress_catalog.requirement_groups
            if g.requirement_type == RequirementType.REQUIRED
        }
        required_codes = frozenset(
            c.course_code
            for c in progress_catalog.plan_courses
            if c.requirement_group_id in required_group_ids
        )

        intel_context = StudentIntelligenceContext(
            attempts=attempt_records,
            progress=progress,
            required_course_codes=required_codes,
        )

        bundle = evaluate_student_intelligence(intel_context)

        def map_cap(cap: Any) -> CapabilityResultDTO:
            return CapabilityResultDTO(
                capability=cap.capability.value,
                status=cap.status.value,
                observations=[
                    StudentIntelligenceObservationDTO(
                        rule_id=obs.rule_id,
                        value=obs.value,
                        count=obs.count,
                        course_codes=list(obs.course_codes),
                    )
                    for obs in cap.observations
                ],
                signals=[
                    StudentIntelligenceObservationDTO(
                        rule_id=sig.rule_id,
                        value=sig.value,
                        count=sig.count,
                        course_codes=list(sig.course_codes),
                    )
                    for sig in cap.signals
                ],
                reason_codes=list(cap.reason_codes),
                limitations=list(cap.limitations),
            )

        return StudentIntelligenceResultDTO(
            policy_version=bundle.policy_version,
            performance=map_cap(bundle.performance),
            strengths=map_cap(bundle.strengths),
            difficulty=map_cap(bundle.difficulty),
            structural_risk=map_cap(bundle.structural_risk),
            predictive_risk=map_cap(bundle.predictive_risk),
            readiness=map_cap(bundle.readiness) if bundle.readiness else None,
            limitations=[
                "Observations are rule-based facts; no psychological or personality profiling is performed.",
                "Predictive failure/risk modeling is strictly blocked by external data policy.",
            ],
        )


class DelayConsequenceAdapter(BaseAdvisorAdapter):
    async def execute(
        self, context: AdvisorAccessContext, request: CheckDelayConsequenceRequest
    ) -> DelayConsequenceResultDTO:
        state = await self._student_repo.load_student_academic_state(context.student_user_id)
        progress_catalog = await self._catalog_repo.load_progress_catalog(state.study_plan_id)
        eligibility_catalog = await self._catalog_repo.load_plan_eligibility_catalog(state.study_plan_id)
        progress = calculate_academic_progress(
            progress_catalog,
            state.attempts,
            reported_cumulative_gpa=state.reported_cumulative_gpa,
            reported_gpa_scale=state.reported_gpa_scale,
            reported_earned_credit_hours=state.reported_earned_credit_hours,
        )

        delay_input = DelayConsequenceInput(
            target_course_code=request.course_code,
            study_plan_id=str(state.study_plan_id),
            student_attempts=state.attempts,
            simulation_provenance=P4SimulationProvenance(
                SimulationStateKind.AUTHORITATIVE,
                state_reference=f"adv_delay_{context.student_user_id}",
            ),
            progress_catalog=progress_catalog,
            eligibility_catalog=eligibility_catalog,
            current_progress=progress,
        )

        result = analyze_delay(delay_input)

        affected = [
            item.course_code
            for item in (*result.directly_affected_courses, *result.transitively_affected_courses)
        ]
        review_reasons = []
        if result.status.value == "REVIEW_REQUIRED":
            review_reasons.append("Course prerequisite structure contains source ambiguities or review requirements.")

        structural_facts = [
            f"Omission from next registration impacts {len(affected)} downstream dependencies"
            if affected
            else "No direct structural downstream dependencies impacted in active plan"
        ]

        return DelayConsequenceResultDTO(
            target_course_code=request.course_code,
            status=result.status.value,
            reasons=[r.value for r in result.reason_codes],
            affected_courses=affected,
            review_required_reasons=review_reasons,
            structural_facts=structural_facts,
            limitations=[
                "Consequences represent structural curriculum dependencies, not calendar graduation delay forecasts.",
                "Actual timing depends on departmental offering schedules and term capacities.",
            ],
        )


class WhatIfAdapter(BaseAdvisorAdapter):
    def __init__(
        self,
        student_repository: StudentAcademicRepository,
        catalog_repository: AcademicCatalogRepository,
        context_loader: AcademicContextLoader,
        academic_compute_limiter: AcademicComputeLimiter | None = None,
    ) -> None:
        super().__init__(student_repository, catalog_repository)
        self._context_loader = context_loader
        self._academic_compute_limiter = academic_compute_limiter or AcademicComputeLimiter()

    async def execute(
        self, context: AdvisorAccessContext, request: RunWhatIfRequest
    ) -> WhatIfResultDTO:
        # Validate that the operation is strictly one of the 3 accepted V1 operations
        if request.operation_id == WhatIfOperationId.TWIN_OP_MODEL_COURSE_COMPLETION:
            if not request.target_course_code:
                raise AdvisorCopilotServiceError(
                    code=AdvisorCopilotServiceErrorCode.TOOL_INPUT_INVALID,
                    detail="target_course_code is required for TWIN_OP_MODEL_COURSE_COMPLETION",
                    status_code=422,
                )
            op = ScenarioOperation(
                operation_id=OperationId.MODEL_COURSE_COMPLETION.value,
                target_course_code=request.target_course_code,
            )
        elif request.operation_id == WhatIfOperationId.TWIN_OP_OMIT_NEXT_PLAN_COURSE:
            if not request.target_course_code:
                raise AdvisorCopilotServiceError(
                    code=AdvisorCopilotServiceErrorCode.TOOL_INPUT_INVALID,
                    detail="target_course_code is required for TWIN_OP_OMIT_NEXT_PLAN_COURSE",
                    status_code=422,
                )
            op = ScenarioOperation(
                operation_id=OperationId.OMIT_NEXT_PLAN_COURSE.value,
                target_course_code=request.target_course_code,
            )
        elif request.operation_id == WhatIfOperationId.TWIN_OP_SET_PLANNING_CONSTRAINTS:
            bundle_input = request.constraints
            bundle = PlanningConstraintBundle(
                max_credit_hours=(
                    bundle_input.max_credit_hours
                    if (bundle_input and bundle_input.max_credit_hours is not None)
                    else Decimal("18.0")
                ),
                max_courses=bundle_input.max_courses if bundle_input else None,
                max_options=bundle_input.max_options if (bundle_input and bundle_input.max_options is not None) else 3,
                max_credit_hours_per_semester=(
                    bundle_input.max_credit_hours_per_semester
                    if (bundle_input and bundle_input.max_credit_hours_per_semester is not None)
                    else None
                ),
                max_courses_per_semester=bundle_input.max_courses_per_semester if bundle_input else None,
                max_paths=bundle_input.max_paths if (bundle_input and bundle_input.max_paths is not None) else 3,
                max_semesters_ahead=bundle_input.max_semesters_ahead if (bundle_input and bundle_input.max_semesters_ahead is not None) else 8,
            )
            op = ScenarioOperation(
                operation_id=OperationId.SET_PLANNING_CONSTRAINTS.value,
                constraints=bundle,
            )
        else:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.TOOL_INPUT_INVALID,
                detail=f"Unsupported What-If operation: {request.operation_id}",
                status_code=422,
            )

        state = await self._student_repo.load_student_academic_state(context.student_user_id)
        attempt_records = await self._student_repo.load_attempt_records(context.student_user_id)
        progress_catalog = await self._catalog_repo.load_progress_catalog(state.study_plan_id)
        eligibility_catalog = await self._catalog_repo.load_plan_eligibility_catalog(state.study_plan_id)
        progress = calculate_academic_progress(
            progress_catalog,
            state.attempts,
            reported_cumulative_gpa=state.reported_cumulative_gpa,
            reported_gpa_scale=state.reported_gpa_scale,
            reported_earned_credit_hours=state.reported_earned_credit_hours,
        )

        ctx_snapshot = await _load_authoritative_context(
            self._context_loader, context.student_user_id
        )

        if ctx_snapshot.university_id != context.university_id:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED,
                detail="Advisor access denied for requested student scope",
                status_code=403,
            )

        if not ctx_snapshot.major_id:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE,
                detail="Authoritative major identity is unavailable",
                status_code=404,
            )
        major_id_str = str(ctx_snapshot.major_id)

        if not ctx_snapshot.study_plan_version:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE,
                detail="Authoritative study plan version is unavailable",
                status_code=404,
            )
        plan_version_str = str(ctx_snapshot.study_plan_version)

        if not ctx_snapshot.source_versions:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE,
                detail="Authoritative source provenance is unavailable",
                status_code=404,
            )
        source_versions = tuple(str(v) for v in ctx_snapshot.source_versions)
        study_plan_id = str(ctx_snapshot.study_plan_id)

        plan_identity = PlanIdentity(
            university_id=str(context.university_id),
            major_id=major_id_str,
            study_plan_id=study_plan_id,
            plan_version=plan_version_str,
        )

        authoritative_attempts = tuple(
            AuthoritativeAttempt(
                course_code=att.course_code,
                outcome=att.outcome,
                attempt_sequence=att.attempt_sequence,
                provenance=(
                    att.performance_provenance.value
                    if hasattr(att, "performance_provenance") and att.performance_provenance
                    else "OFFICIAL_VERIFIED"
                ),
                verification_state=(
                    att.performance_verification_state.value
                    if hasattr(att, "performance_verification_state") and att.performance_verification_state
                    else "VERIFIED"
                ),
            )
            for att in attempt_records
        )

        snapshot = AuthoritativeAcademicSnapshot(
            owner_scope_id=str(context.student_user_id),
            plan_identity=plan_identity,
            attempts=authoritative_attempts,
            eligibility_catalog=eligibility_catalog,
            progress_catalog=progress_catalog,
            current_progress=progress,
            baseline_planner_constraints=PlannerConstraints(max_credit_hours=Decimal("18.0")),
            baseline_path_constraints=DegreePathConstraints(max_credit_hours_per_semester=Decimal("18.0")),
            source_versions=source_versions,
            engine_policy_versions=ENGINE_POLICY_VERSIONS,
        )

        fingerprint = calculate_base_state_fingerprint(snapshot)
        scenario_id = _deterministic_scenario_id(fingerprint, op)
        identity = ScenarioIdentity(
            scenario_id=scenario_id,
            base_state_fingerprint=fingerprint,
            operations=(op,),
        )

        result = await self._academic_compute_limiter.run(
            lambda check_budget: evaluate_scenario(
                snapshot, identity, check_budget=check_budget,
            ),
        )

        deltas_dto = [
            WhatIfDeltaDTO(
                delta_id=f"delta_{idx + 1}",
                delta_type=d.delta_type.value,
                description=f"{d.source_engine}: {d.target} changed from {d.base_value} to {d.modeled_value}",
                affected_courses=[d.target] if d.target else [],
            )
            for idx, d in enumerate(result.deltas)
        ]

        op_results_dto = [
            {"operation_id": o.operation_id, "applied": o.applied, "status": o.result_code}
            for o in result.operation_results
        ]

        is_valid = len(result.validation_issues) == 0 and result.lifecycle_status.value != "INVALID"

        return WhatIfResultDTO(
            scenario_id=scenario_id,
            operation_id=request.operation_id.value,
            is_valid=is_valid,
            status=result.lifecycle_status.value,
            deltas=deltas_dto,
            operation_results=op_results_dto,
            limitations=[
                "What-If scenarios are purely hypothetical and ephemeral; authoritative student state is UNCHANGED.",
                "Modeled completion or omission does not guarantee official registration or graduation clearance.",
            ],
        )


def _latest_persisted_intent(
    history: tuple[PersistedIntentRevision, ...],
    period: PersistedTargetPeriod,
) -> PersistedIntentRevision | None:
    if not history:
        return None
    resolution = resolve_current_intents(
        tuple(stored_domain_record(row, period) for row in history)
    )
    if not resolution.records:
        return None
    winner = max(resolution.records, key=lambda item: item.record.intent.revision)
    return next(row for row in history if row.revision == winner.record.intent.revision)


class AdvisorMockRegistrationReader:
    """Dedicated read-only advisor reader for the current Mock Registration intent."""

    def __init__(
        self,
        persistence: Any,
        context_loader: AcademicContextLoader,
    ) -> None:
        self._persistence = persistence
        self._context_loader = context_loader

    async def get_current_intent(
        self,
        context: AdvisorAccessContext,
        target_period_id: UUID,
    ) -> CurrentMockRegistrationResultDTO:
        snapshot = await _load_authoritative_context(
            self._context_loader, context.student_user_id
        )

        if snapshot.university_id != context.university_id:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED,
                detail="Advisor access denied for requested student scope",
                status_code=403,
            )

        try:
            period = await self._persistence.load_target_period(
                target_period_id, snapshot.university_id
            )
        except MockRegistrationPersistenceError as error:
            if error.code is PersistenceFailureCode.RESOURCE_NOT_FOUND:
                raise AdvisorCopilotServiceError(
                    code=AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE,
                    detail="Target planning period was not found",
                    status_code=404,
                ) from error
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.PERSISTENCE_UNAVAILABLE,
                detail="Mock Registration persistence is temporarily unavailable",
                status_code=503,
            ) from error

        try:
            history = await self._persistence.load_revision_history(
                owner_user_id=snapshot.owner_user_id,
                university_id=snapshot.university_id,
                major_id=snapshot.major_id,
                study_plan_id=snapshot.study_plan_id,
                study_plan_version=snapshot.study_plan_version,
                target_period_id=target_period_id,
            )
        except MockRegistrationPersistenceError as error:
            if error.code is PersistenceFailureCode.RESOURCE_NOT_FOUND:
                raise AdvisorCopilotServiceError(
                    code=AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE,
                    detail="Mock Registration intent history was not found",
                    status_code=404,
                ) from error
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.PERSISTENCE_UNAVAILABLE,
                detail="Mock Registration persistence is temporarily unavailable",
                status_code=503,
            ) from error

        row = _latest_persisted_intent(history, period)
        if row is None:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE,
                detail="No active Mock Registration intent exists for the requested period",
                status_code=404,
            )

        validation = revalidate(row, period, snapshot)

        return CurrentMockRegistrationResultDTO(
            intent_id=str(row.intent_id),
            target_period_id=row.target_period_id,
            course_codes=[course.course_code for course in row.courses],
            current_validity=(
                validation.current_validity.value
                if validation.current_validity is not None
                else None
            ),
            revalidation_status=validation.status.value,
            revalidation_reason_codes=[reason.value for reason in validation.reason_codes],
            is_expired=period.is_expired,
            limitations=[
                "Mock registration represents student declared intent; it does NOT constitute official course enrollment.",
                "Advisors have read-only access and cannot submit, alter, or withdraw student intent.",
            ],
        )


class CurrentMockRegistrationAdapter:
    def __init__(self, reader: AdvisorMockRegistrationReader) -> None:
        self._reader = reader

    async def execute(
        self,
        context: AdvisorAccessContext,
        request: GetCurrentMockRegistrationRequest,
    ) -> CurrentMockRegistrationResultDTO:
        return await self._reader.get_current_intent(
            context, request.target_period_id
        )


class ExplainRecommendationDecisionAdapter(BaseAdvisorAdapter):
    async def execute(
        self, context: AdvisorAccessContext, request: ExplainRecommendationDecisionRequest
    ) -> ExplainRecommendationDecisionResultDTO:
        state = await self._student_repo.load_student_academic_state(context.student_user_id)
        progress_catalog = await self._catalog_repo.load_progress_catalog(state.study_plan_id)
        eligibility_catalog = await self._catalog_repo.load_plan_eligibility_catalog(state.study_plan_id)

        baseline = recommend_courses(
            progress_catalog,
            eligibility_catalog,
            state.attempts,
            reported_cumulative_gpa=state.reported_cumulative_gpa,
            reported_gpa_scale=state.reported_gpa_scale,
            reported_earned_credit_hours=state.reported_earned_credit_hours,
        )

        decision_mode = (
            DecisionMode.READINESS_AWARE
            if request.mode == "READINESS_AWARE"
            else DecisionMode.STRUCTURAL_BASELINE
        )

        provenance = P4SimulationProvenance(
            SimulationStateKind.AUTHORITATIVE,
            state_reference=f"adv_trace_{context.student_user_id}",
        )

        enhanced = integrate_recommendations(
            baseline,
            mode=decision_mode,
            simulation_provenance=provenance,
        )

        trace = enhanced.trace

        applied_factors_dto = [
            DecisionFactorEvaluationDTO(
                factor_id=f.factor_id,
                classification=f.classification.value,
                action=f.action.value,
                reason=f.reason.value,
                ordering_value=f.ordering_value,
            )
            for f in trace.applied_factors
        ]

        ignored_factors_dto = [
            DecisionFactorEvaluationDTO(
                factor_id=f.factor_id,
                classification=f.classification.value,
                action=f.action.value,
                reason=f.reason.value,
                ordering_value=f.ordering_value,
            )
            for f in trace.ignored_factors
        ]

        order_changes_dto = [
            RelativeOrderChangeDTO(
                course_code=roc.course_code,
                baseline_rank=roc.baseline_rank,
                final_rank=roc.final_rank,
            )
            for roc in trace.changed_relative_orders
        ]

        return ExplainRecommendationDecisionResultDTO(
            decision_type=trace.decision_type,
            decision_mode=trace.decision_mode.value,
            baseline_order=list(trace.baseline_order),
            final_order=list(trace.final_order),
            applied_factors=applied_factors_dto,
            ignored_factors=ignored_factors_dto,
            changed_relative_orders=order_changes_dto,
            limitations=[
                "Decision trace is ephemerally recomputed from current verified facts; no persistent trace ID is used.",
                "Factors explain relative ordering decisions without assigning numerical student scores.",
            ],
        )
