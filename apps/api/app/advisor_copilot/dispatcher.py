"""Deterministic Advisor Copilot dispatcher with strict P7.4 authorization."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.advisor_persistence.models import AdvisorAccessContext
from app.advisor_service.authorization import AdvisorAuthorizationService
from app.advisor_service.errors import AdvisorAuthorizationError, AdvisorAuthorizationErrorCode
from app.catalog.repository import AcademicCatalogRepository
from app.mock_registration_service.context import AcademicContextLoader
from app.services.eligibility import EligibilityService
from app.student.repository import StudentAcademicRepository
from app.core.academic_compute import AcademicComputeLimiter
from app.degree_path.models import DegreePathCapacityError, DegreePathComputationTimeout

from app.advisor_copilot.adapters import (
    AcademicSnapshotAdapter,
    AdvisorMockRegistrationReader,
    CurrentMockRegistrationAdapter,
    DegreePathsAdapter,
    DelayConsequenceAdapter,
    EligibilityAdapter,
    ExplainRecommendationDecisionAdapter,
    ProgressAdapter,
    RecommendationsAdapter,
    SemesterPlansAdapter,
    StudentIntelligenceAdapter,
    WhatIfAdapter,
)
from app.advisor_copilot.errors import (
    AdvisorCopilotServiceError,
    AdvisorCopilotServiceErrorCode,
)
from app.advisor_copilot.models import (
    AdvisorToolExecutionRequest,
    AdvisorToolExecutionResponse,
)
from app.advisor_copilot.registries import (
    TOOL_AUTHORITY_CLASSES,
    TOOL_SIDE_EFFECTS,
    AdvisorToolId,
)


class AdvisorAdapter(Protocol):
    """Internal read-only adapter protocol."""

    async def execute(
        self,
        context: AdvisorAccessContext,
        request: Any,
    ) -> Any: ...


class AdvisorToolDispatcher:
    """Closed, deterministic dispatcher for the 11 Advisor Copilot tools."""

    def __init__(
        self,
        authorization_service: AdvisorAuthorizationService,
        student_repository: StudentAcademicRepository,
        catalog_repository: AcademicCatalogRepository,
        eligibility_service: EligibilityService,
        mock_registration_reader: AdvisorMockRegistrationReader,
        context_loader: AcademicContextLoader,
        academic_compute_limiter: AcademicComputeLimiter | None = None,
    ) -> None:
        if mock_registration_reader is None:
            raise ValueError(
                "AdvisorToolDispatcher requires an explicit AdvisorMockRegistrationReader"
            )
        if context_loader is None:
            raise ValueError(
                "AdvisorToolDispatcher requires an explicit AcademicContextLoader"
            )

        self._auth_service = authorization_service
        academic_compute_limiter = academic_compute_limiter or AcademicComputeLimiter()
        self._adapters: dict[AdvisorToolId, AdvisorAdapter] = {
            AdvisorToolId.ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT: AcademicSnapshotAdapter(
                student_repository, catalog_repository
            ),
            AdvisorToolId.ADVISOR_TOOL_GET_PROGRESS: ProgressAdapter(
                student_repository, catalog_repository
            ),
            AdvisorToolId.ADVISOR_TOOL_CHECK_ELIGIBILITY: EligibilityAdapter(
                student_repository, catalog_repository, eligibility_service
            ),
            AdvisorToolId.ADVISOR_TOOL_GET_RECOMMENDATIONS: RecommendationsAdapter(
                student_repository, catalog_repository
            ),
            AdvisorToolId.ADVISOR_TOOL_GET_SEMESTER_PLANS: SemesterPlansAdapter(
                student_repository, catalog_repository, academic_compute_limiter
            ),
            AdvisorToolId.ADVISOR_TOOL_GET_DEGREE_PATHS: DegreePathsAdapter(
                student_repository, catalog_repository, academic_compute_limiter
            ),
            AdvisorToolId.ADVISOR_TOOL_GET_STUDENT_INTELLIGENCE: StudentIntelligenceAdapter(
                student_repository, catalog_repository
            ),
            AdvisorToolId.ADVISOR_TOOL_CHECK_DELAY_CONSEQUENCE: DelayConsequenceAdapter(
                student_repository, catalog_repository
            ),
            AdvisorToolId.ADVISOR_TOOL_RUN_WHAT_IF: WhatIfAdapter(
                student_repository, catalog_repository, context_loader=context_loader,
                academic_compute_limiter=academic_compute_limiter,
            ),
            AdvisorToolId.ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION: CurrentMockRegistrationAdapter(
                mock_registration_reader
            ),
            AdvisorToolId.ADVISOR_TOOL_EXPLAIN_RECOMMENDATION_DECISION: ExplainRecommendationDecisionAdapter(
                student_repository, catalog_repository
            ),
        }

    async def execute_tool(
        self,
        authenticated_advisor_id: UUID | str | None,
        request: AdvisorToolExecutionRequest,
    ) -> AdvisorToolExecutionResponse:
        try:
            auth_context = await self._auth_service.authorize_advisor_for_student(
                authenticated_advisor_id, request.target_student_user_id
            )
        except AdvisorAuthorizationError as error:
            if error.code == AdvisorAuthorizationErrorCode.AUTH_REQUIRED:
                raise AdvisorCopilotServiceError(
                    code=AdvisorCopilotServiceErrorCode.AUTH_REQUIRED,
                    detail="Authentication is required for advisor access",
                    status_code=401,
                ) from error
            if error.code == AdvisorAuthorizationErrorCode.PERSISTENCE_UNAVAILABLE:
                raise AdvisorCopilotServiceError(
                    code=AdvisorCopilotServiceErrorCode.PERSISTENCE_UNAVAILABLE,
                    detail="Advisor authorization service is temporarily unavailable",
                    status_code=503,
                ) from error
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED,
                detail="Advisor access denied for requested student scope",
                status_code=403,
            ) from error

        if auth_context.student_user_id != request.target_student_user_id:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED,
                detail="Advisor access denied for requested student scope",
                status_code=403,
            )

        tool_id = request.tool_id
        adapter = self._adapters.get(tool_id)
        if adapter is None:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.TOOL_NOT_FOUND,
                detail="Requested advisor tool was not found in registry",
                status_code=422,
            )

        try:
            result_dto = await adapter.execute(auth_context, request)
        except AdvisorCopilotServiceError:
            raise
        except DegreePathCapacityError as error:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.COMPUTE_CAPACITY_BUSY,
            ) from error
        except DegreePathComputationTimeout as error:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.COMPUTATION_TIMEOUT,
            ) from error
        except Exception as error:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.INTERNAL_ERROR,
                detail="An internal error occurred during tool execution",
                status_code=500,
            ) from error

        try:
            authority_class = TOOL_AUTHORITY_CLASSES[tool_id]
            side_effects = TOOL_SIDE_EFFECTS[tool_id]
        except KeyError as error:
            raise AdvisorCopilotServiceError(
                code=AdvisorCopilotServiceErrorCode.INTERNAL_ERROR,
                detail="Advisor tool registry configuration is invalid",
                status_code=500,
            ) from error

        return AdvisorToolExecutionResponse(
            tool_id=tool_id.value,
            authority_class=authority_class.value,
            student_user_id=auth_context.student_user_id,
            university_id=auth_context.university_id,
            side_effects=side_effects,
            result=result_dto,
        )


AdvisorCopilotService = AdvisorToolDispatcher
