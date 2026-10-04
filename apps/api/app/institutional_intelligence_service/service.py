"""Authorized Institutional Intelligence Application Service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.catalog.errors import CatalogRepositoryError, StudyPlanNotFound
from app.catalog.repository import AcademicCatalogRepository
from app.institutional_intelligence.engine import evaluate_institutional_intelligence
from app.institutional_intelligence.models import InstitutionalIntelligenceInput
from app.mock_registration_persistence.errors import MockRegistrationPersistenceError, PersistenceFailureCode
from app.mock_registration_persistence.models import InstitutionalMembershipRecord
from app.mock_registration_persistence.repository import SupabaseMockRegistrationRepository
from app.mock_registration_service.context import AcademicContextLoader
from app.mock_registration_service.errors import MockRegistrationServiceError
from app.mock_registration_service.institutional_service import InstitutionalDemandService

from .errors import InstitutionalIntelligenceServiceError, InstitutionalIntelligenceServiceErrorCode
from .mapping import map_institutional_intelligence_response
from .models import InstitutionalIntelligenceResponse
from .providers import CapacityFactProvider, NullCapacityFactProvider, NullOfferingFactProvider, OfferingFactProvider


class InstitutionalIntelligenceService:
    """Coordinates authentication, authorization, tenant isolation, and fact resolution for Institutional Intelligence."""

    def __init__(
        self,
        persistence: SupabaseMockRegistrationRepository,
        contexts: AcademicContextLoader,
        catalog_repository: AcademicCatalogRepository,
        demand_service: InstitutionalDemandService,
        offering_provider: OfferingFactProvider | None = None,
        capacity_provider: CapacityFactProvider | None = None,
    ) -> None:
        self._persistence = persistence
        self._contexts = contexts
        self._catalog = catalog_repository
        self._demand_service = demand_service
        self._offering_provider = offering_provider or NullOfferingFactProvider()
        self._capacity_provider = capacity_provider or NullCapacityFactProvider()

    async def _resolve_authorized_membership(
        self,
        subject_id: UUID,
        requested_university_id: UUID | None,
    ) -> InstitutionalMembershipRecord:
        """Enforces authorization BEFORE any sensitive institutional loads occur.

        The client NEVER dictates authority; server-side active membership is mandatory.
        """
        if requested_university_id is not None:
            try:
                return await self._persistence.load_active_membership(
                    subject_user_id=subject_id,
                    university_id=requested_university_id,
                    role="INSTITUTIONAL_ANALYST",
                )
            except MockRegistrationPersistenceError as error:
                raise InstitutionalIntelligenceServiceError(
                    InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED
                ) from error

        # When university_id is not supplied in query, discover through active analyst memberships
        if hasattr(self._persistence, "load_active_memberships_for_user"):
            try:
                memberships = await self._persistence.load_active_memberships_for_user(
                    subject_user_id=subject_id,
                    role="INSTITUTIONAL_ANALYST",
                )
            except MockRegistrationPersistenceError as error:
                raise InstitutionalIntelligenceServiceError(
                    InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED
                ) from error
            if not memberships:
                raise InstitutionalIntelligenceServiceError(
                    InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED
                )
            if len(memberships) == 1:
                return memberships[0]
            # Multiple active memberships exist and caller did not specify which tenant
            raise InstitutionalIntelligenceServiceError(
                InstitutionalIntelligenceServiceErrorCode.AGGREGATION_SCOPE_INVALID,
                "Multiple active institutional memberships exist; specify university_id",
            )

        raise InstitutionalIntelligenceServiceError(
            InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED
        )

    async def authorize_analyst_university(
        self, subject: str | UUID, university_id: UUID | None = None,
    ) -> UUID:
        """Expose the existing membership predicate to bounded metric consumers."""
        membership = await self._resolve_authorized_membership(UUID(str(subject)), university_id)
        return membership.university_id

    async def evaluate(
        self,
        subject: str | UUID,
        *,
        target_period_id: UUID,
        study_plan_id: UUID,
        course_code: str,
        university_id: UUID | None = None,
        computed_at: datetime | None = None,
        deterministic_trace_id: str | None = None,
    ) -> InstitutionalIntelligenceResponse:
        """Evaluates institutional intelligence for a course within an authorized tenant scope."""
        subject_id = UUID(str(subject))

        # ---------------------------------------------------------------------
        # 1. Authorization Must Occur BEFORE Sensitive Loads
        # ---------------------------------------------------------------------
        membership = await self._resolve_authorized_membership(subject_id, university_id)
        effective_university_id = membership.university_id

        # ---------------------------------------------------------------------
        # 2. Tenant-Scoped Scope Resolution (Target Period, Study Plan, Course)
        # ---------------------------------------------------------------------
        try:
            period = await self._persistence.load_target_period(target_period_id, effective_university_id)
        except MockRegistrationPersistenceError as error:
            if error.code is PersistenceFailureCode.RESOURCE_NOT_FOUND:
                raise InstitutionalIntelligenceServiceError(
                    InstitutionalIntelligenceServiceErrorCode.TARGET_PERIOD_UNAVAILABLE
                ) from error
            raise InstitutionalIntelligenceServiceError(
                InstitutionalIntelligenceServiceErrorCode.PERSISTENCE_UNAVAILABLE
            ) from error

        if membership.provider_namespace != period.provider_namespace:
            raise InstitutionalIntelligenceServiceError(
                InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED
            )

        try:
            await self._contexts.validate_plan_scope(study_plan_id, effective_university_id)
        except (CatalogRepositoryError, MockRegistrationPersistenceError, StudyPlanNotFound, ValueError) as error:
            raise InstitutionalIntelligenceServiceError(
                InstitutionalIntelligenceServiceErrorCode.STUDY_PLAN_UNAVAILABLE
            ) from error

        # ---------------------------------------------------------------------
        # 3. Load Academic Structure & Prerequisite Graph
        # ---------------------------------------------------------------------
        try:
            progress_catalog = await self._catalog.load_progress_catalog(study_plan_id)
            eligibility_catalog = await self._catalog.load_plan_eligibility_catalog(study_plan_id)
        except (CatalogRepositoryError, Exception) as error:
            raise InstitutionalIntelligenceServiceError(
                InstitutionalIntelligenceServiceErrorCode.STUDY_PLAN_UNAVAILABLE
            ) from error

        plan_course_codes = {c.course_code for c in progress_catalog.plan_courses}
        all_known_codes = {c.course_code for c in eligibility_catalog.courses} | plan_course_codes
        if course_code not in all_known_codes:
            raise InstitutionalIntelligenceServiceError(
                InstitutionalIntelligenceServiceErrorCode.COURSE_UNAVAILABLE
            )

        # ---------------------------------------------------------------------
        # 4. In-Process P6 Demand Loading
        # ---------------------------------------------------------------------
        demand_aggregation = None
        if course_code in plan_course_codes:
            try:
                p6_res = await self._demand_service.demand(
                    str(subject_id),
                    university_id=effective_university_id,
                    target_period_id=target_period_id,
                    study_plan_id=study_plan_id,
                    course_code=course_code,
                )
                demand_aggregation = p6_res.demand
            except MockRegistrationServiceError as error:
                raise InstitutionalIntelligenceServiceError(
                    InstitutionalIntelligenceServiceErrorCode.AGGREGATION_SCOPE_INVALID
                ) from error
            except Exception as error:
                raise InstitutionalIntelligenceServiceError(
                    InstitutionalIntelligenceServiceErrorCode.PERSISTENCE_UNAVAILABLE
                ) from error

        # ---------------------------------------------------------------------
        # 5. External Fact Loading (Offering & Capacity via Providers)
        # ---------------------------------------------------------------------
        offering_fact = await self._offering_provider.get_offering_fact(
            university_id=str(effective_university_id),
            period_key=period.period_key,
            course_code=course_code,
            study_plan_id=str(study_plan_id),
        )
        capacity_fact = await self._capacity_provider.get_capacity_fact(
            university_id=str(effective_university_id),
            period_key=period.period_key,
            course_code=course_code,
            study_plan_id=str(study_plan_id),
        )

        # ---------------------------------------------------------------------
        # 6. Call Pure Domain P7.2 Engine
        # ---------------------------------------------------------------------
        now = computed_at or datetime.now(timezone.utc)
        domain_input = InstitutionalIntelligenceInput(
            university_id=str(effective_university_id),
            target_period_key=period.period_key,
            course_code=course_code,
            catalog=progress_catalog,
            can_take_catalog=eligibility_catalog,
            study_plan_id=str(study_plan_id),
            demand_result=demand_aggregation,
            offering_fact=offering_fact,
            capacity_fact=capacity_fact,
            computed_at=now.isoformat(),
            deterministic_trace_id=deterministic_trace_id,
        )

        try:
            domain_result = evaluate_institutional_intelligence(domain_input)
        except (ValueError, TypeError) as error:
            raise InstitutionalIntelligenceServiceError(
                InstitutionalIntelligenceServiceErrorCode.AGGREGATION_SCOPE_INVALID,
                detail=str(error),
            ) from error

        # ---------------------------------------------------------------------
        # 7. Map to Allowlisted Response DTO
        # ---------------------------------------------------------------------
        return map_institutional_intelligence_response(
            domain_result,
            university_id=effective_university_id,
            target_period_id=target_period_id,
            study_plan_id=study_plan_id,
            generated_at=now,
        )
