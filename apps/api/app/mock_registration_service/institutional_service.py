"""Authorized aggregate-only institutional demand application service."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

from app.catalog.errors import CatalogRepositoryError
from app.mock_registration.aggregation import aggregate_institutional_demand
from app.mock_registration.models import (
    AggregationLimits, AggregationScope, CoverageInput, DemandAggregationError,
    DemandAggregationInput, PrivacyConfiguration, ResolvedIntent, ResolutionDisposition,
    ValidationStatus,
)
from app.mock_registration.resolution import resolve_current_intents
from app.mock_registration_persistence.errors import MockRegistrationPersistenceError
from app.mock_registration_persistence.repository import SupabaseMockRegistrationRepository
from app.student.errors import StudentRepositoryError

from .context import AcademicContextLoader
from .errors import MockRegistrationServiceError, ServiceErrorCode
from .models import InstitutionalDemandResult, RevalidationStatus
from .revalidation import domain_period, revalidate, stored_domain_record


class InstitutionalDemandService:
    def __init__(self, persistence: SupabaseMockRegistrationRepository,
                 contexts: AcademicContextLoader, *, minimum_disclosure_group_size: int,
                 max_intents: int, max_catalog_courses: int) -> None:
        self._persistence = persistence
        self._contexts = contexts
        self._minimum = minimum_disclosure_group_size
        self._max_intents = max_intents
        self._max_catalog = max_catalog_courses

    async def demand(self, subject: str, *, university_id: UUID, target_period_id: UUID,
                     study_plan_id: UUID | None = None,
                     course_code: str | None = None) -> InstitutionalDemandResult:
        subject_id = UUID(subject)
        try:
            membership = await self._persistence.load_active_membership(
                subject_user_id=subject_id, university_id=university_id)
        except MockRegistrationPersistenceError as error:
            raise MockRegistrationServiceError(ServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED) from error
        if course_code is not None and study_plan_id is None:
            raise MockRegistrationServiceError(ServiceErrorCode.AGGREGATION_SCOPE_INVALID)
        try:
            period = await self._persistence.load_target_period(target_period_id, university_id)
            filter_facts = (await self._contexts.validate_plan_scope(study_plan_id, university_id)
                            if study_plan_id else ())
        except (MockRegistrationPersistenceError, CatalogRepositoryError) as error:
            raise MockRegistrationServiceError(ServiceErrorCode.AGGREGATION_SCOPE_INVALID) from error
        if membership.provider_namespace != period.provider_namespace:
            raise MockRegistrationServiceError(ServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED)
        if course_code and study_plan_id and course_code not in {item.course_code for item in filter_facts}:
            raise MockRegistrationServiceError(ServiceErrorCode.AGGREGATION_SCOPE_INVALID)
        try:
            candidates = await self._persistence.load_institution_period_candidates(
                university_id=university_id, target_period_id=target_period_id,
                study_plan_id=study_plan_id)
        except MockRegistrationPersistenceError as error:
            raise MockRegistrationServiceError(ServiceErrorCode.PERSISTENCE_UNAVAILABLE) from error
        stored = tuple(stored_domain_record(row, period) for row in candidates)
        resolved = resolve_current_intents(stored)
        rows_by_intent = {str(row.intent_id): row for row in candidates}
        included: list[ResolvedIntent] = []
        facts = {(
            item.major_id, item.study_plan_id, item.study_plan_version, item.course_code
        ): item for item in filter_facts}
        stale = False
        for item in resolved.current:
            row = rows_by_intent[item.record.intent.intent_id]
            try:
                snapshot = await self._contexts.load_owner_context(row.owner_user_id)
            except (StudentRepositoryError, CatalogRepositoryError):
                stale = True
                continue
            result = revalidate(row, period, snapshot)
            if result.status is RevalidationStatus.INCOMPLETE:
                stale = True
                continue
            if result.validated_intent is None or result.validated_intent.status is ValidationStatus.INVALID:
                continue
            record = result.validated_intent
            if course_code:
                if course_code not in record.canonical_course_codes:
                    continue
                record = replace(record, canonical_course_codes=(course_code,))
            included.append(ResolvedIntent(record, ResolutionDisposition.CURRENT))
            for fact in snapshot.plan_course_facts:
                facts[(fact.major_id, fact.study_plan_id, fact.study_plan_version, fact.course_code)] = fact
        scope = AggregationScope(str(university_id), study_plan_id=str(study_plan_id) if study_plan_id else None)
        try:
            demand = aggregate_institutional_demand(DemandAggregationInput(
                aggregation_scope=scope, target_period=domain_period(period),
                resolved_intents=tuple(included), normalized_plan_course_catalog=tuple(facts.values()),
                privacy_configuration=PrivacyConfiguration(self._minimum, "p6.5:1.0"),
                aggregation_limits=AggregationLimits(self._max_intents, self._max_catalog),
                coverage=CoverageInput(), include_review_metric=True,
                source_versions=(period.source_version,),
            ))
        except (DemandAggregationError, ValueError) as error:
            raise MockRegistrationServiceError(ServiceErrorCode.AGGREGATION_SCOPE_INVALID) from error
        return InstitutionalDemandResult(
            demand, RevalidationStatus.INCOMPLETE if stale else RevalidationStatus.COMPLETE,
            stale, datetime.now(timezone.utc), university_id, target_period_id,
            study_plan_id, course_code,
        )
