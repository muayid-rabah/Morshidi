"""Authorized WC-046 orchestration and required, fail-closed audit sidecar."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from app.advisor_service.authorization import AdvisorAuthorizationService
from app.advisor_service.errors import AdvisorAuthorizationError, AdvisorAuthorizationErrorCode
from app.catalog.errors import CatalogIntegrityError, CatalogRepositoryError, CatalogTransportError
from app.catalog.repository import AcademicCatalogRepository
from app.catalog.display import CourseDisplayIdentity
from app.decision_trace import (
    ActorClass, DecisionStatus, DecisionType, EvidenceReference, IntegrityStatus,
    ProvenanceClass, RedactionProfile, ReplayStatus, SubjectScopeType,
    create_canonical_ledger_entry, materiality_for, verify_integrity_hash,
)
from app.decision_trace_persistence.errors import DecisionTraceErrorCode, DecisionTracePersistenceError
from app.decision_trace_persistence.repository import SupabaseDecisionTraceRepository
from app.mock_registration_persistence.errors import (
    MockRegistrationPersistenceError, PersistenceFailureCode,
)
from app.mock_registration_persistence.repository import SupabaseMockRegistrationRepository
from app.mock_registration_service.context import AcademicContextLoader
from app.student.errors import (
    StudentProfileIntegrityError, StudentProfileTransportError, StudentRepositoryError,
)

from .engine import evaluate_change_impact
from .models import (
    ChangeDelta, ChangeImpactReport, CourseCreditHoursDelta, PolicyVersionDelta,
    PrerequisiteGroupDelta, RequirementGroupCreditDelta,
)


class ImpactServiceCode(str, Enum):
    ACCESS_DENIED = "ACCESS_DENIED"
    SCOPE_UNAVAILABLE = "SCOPE_UNAVAILABLE"
    IMPACT_SERVICE_UNAVAILABLE = "IMPACT_SERVICE_UNAVAILABLE"
    AUDIT_PERSISTENCE_UNAVAILABLE = "AUDIT_PERSISTENCE_UNAVAILABLE"


class ImpactServiceError(RuntimeError):
    def __init__(self, code: ImpactServiceCode):
        super().__init__(code.value)
        self.code = code


class ChangeImpactService:
    def __init__(
        self, memberships: SupabaseMockRegistrationRepository,
        advisor_authorization: AdvisorAuthorizationService,
        contexts: AcademicContextLoader,
        catalog: AcademicCatalogRepository,
        ledger: SupabaseDecisionTraceRepository,
    ) -> None:
        self._memberships = memberships
        self._advisor_authorization = advisor_authorization
        self._contexts = contexts
        self._catalog = catalog
        self._ledger = ledger

    async def available_analyst_universities(self, actor_user_id: str) -> tuple[UUID, ...]:
        """Membership-only projection for the focused institutional page."""
        try:
            rows = await self._memberships.load_active_memberships_for_user(
                subject_user_id=UUID(actor_user_id), role="INSTITUTIONAL_ANALYST")
        except MockRegistrationPersistenceError as error:
            raise ImpactServiceError(_membership_failure_code(error)) from error
        if not rows:
            raise ImpactServiceError(ImpactServiceCode.ACCESS_DENIED)
        return tuple(sorted({row.university_id for row in rows}))

    async def course_identities(self, actor_user_id: str, university_id: UUID
                                ) -> tuple[CourseDisplayIdentity, ...]:
        if university_id not in await self.available_analyst_universities(actor_user_id):
            raise ImpactServiceError(ImpactServiceCode.ACCESS_DENIED)
        try:
            return await self._catalog.load_university_course_identities(university_id)
        except CatalogRepositoryError as error:
            raise ImpactServiceError(ImpactServiceCode.IMPACT_SERVICE_UNAVAILABLE) from error

    async def evaluate_institutional(
        self, actor_user_id: str, delta: ChangeDelta, *, university_id: UUID | None = None,
    ) -> ChangeImpactReport:
        actor = UUID(actor_user_id)
        try:
            if university_id is None:
                memberships = await self._memberships.load_active_memberships_for_user(
                    subject_user_id=actor, role="INSTITUTIONAL_ANALYST")
                if len(memberships) != 1:
                    raise ImpactServiceError(ImpactServiceCode.ACCESS_DENIED)
                authorized_university = memberships[0].university_id
            else:
                membership = await self._memberships.load_active_membership(
                    subject_user_id=actor, university_id=university_id,
                    role="INSTITUTIONAL_ANALYST")
                authorized_university = membership.university_id
        except MockRegistrationPersistenceError as error:
            raise ImpactServiceError(_membership_failure_code(error)) from error
        report, source_versions = await self._evaluate_scoped(delta, authorized_university)
        return await self._audit(report, actor, ActorClass.INSTITUTIONAL_ANALYST,
                                 None, source_versions)

    async def evaluate_advisor(
        self, actor_user_id: str, student_user_id: UUID, delta: ChangeDelta,
    ) -> ChangeImpactReport:
        actor = UUID(actor_user_id)
        try:
            authorized = await self._advisor_authorization.authorize_advisor_for_student(
                actor, student_user_id)
        except AdvisorAuthorizationError as error:
            code = (ImpactServiceCode.IMPACT_SERVICE_UNAVAILABLE
                    if error.code is AdvisorAuthorizationErrorCode.PERSISTENCE_UNAVAILABLE
                    else ImpactServiceCode.ACCESS_DENIED)
            raise ImpactServiceError(code) from error
        try:
            snapshot = await self._contexts.load_owner_context(student_user_id)
        except (StudentProfileTransportError, StudentProfileIntegrityError,
                CatalogTransportError, CatalogIntegrityError) as error:
            raise ImpactServiceError(ImpactServiceCode.IMPACT_SERVICE_UNAVAILABLE) from error
        except (StudentRepositoryError, CatalogRepositoryError, ValueError) as error:
            raise ImpactServiceError(ImpactServiceCode.SCOPE_UNAVAILABLE) from error
        if snapshot.university_id != authorized.university_id:
            raise ImpactServiceError(ImpactServiceCode.ACCESS_DENIED)
        if not isinstance(delta, PolicyVersionDelta) and str(delta.study_plan_id) != str(snapshot.study_plan_id):
            raise ImpactServiceError(ImpactServiceCode.SCOPE_UNAVAILABLE)
        _require_target_exists(delta, snapshot.eligibility_catalog, snapshot.progress_catalog)
        report = evaluate_change_impact(
            delta, university_id=authorized.university_id,
            eligibility_catalog=snapshot.eligibility_catalog,
            progress_catalog=snapshot.progress_catalog,
            student_attempts=snapshot.student_attempts,
            reported_cumulative_gpa=snapshot.current_progress.reported_cumulative_gpa,
            reported_gpa_scale=snapshot.current_progress.reported_gpa_scale,
            reported_earned_credit_hours=snapshot.current_progress.reported_earned_credit_hours,
        )
        return await self._audit(report, actor, ActorClass.ACADEMIC_ADVISOR,
                                 student_user_id,
                                 _relevant_source_versions(delta, snapshot.study_plan_version,
                                                           snapshot.plan_course_facts))

    async def _evaluate_scoped(
        self, delta: ChangeDelta, university_id: UUID,
    ) -> tuple[ChangeImpactReport, tuple[str, ...]]:
        if isinstance(delta, PolicyVersionDelta):
            return evaluate_change_impact(delta, university_id=university_id), ()
        try:
            scope_facts = await self._contexts.validate_plan_scope(delta.study_plan_id, university_id)
            if delta.change_type.value == "PREREQUISITE_GROUP_CHANGE":
                eligibility = await self._catalog.load_plan_eligibility_catalog(delta.study_plan_id)
                progress = None
            else:
                eligibility = None
                progress = await self._catalog.load_progress_catalog(delta.study_plan_id)
        except (CatalogTransportError, CatalogIntegrityError) as error:
            raise ImpactServiceError(ImpactServiceCode.IMPACT_SERVICE_UNAVAILABLE) from error
        except (CatalogRepositoryError, MockRegistrationPersistenceError, ValueError) as error:
            raise ImpactServiceError(ImpactServiceCode.SCOPE_UNAVAILABLE) from error
        _require_target_exists(delta, eligibility, progress)
        report = evaluate_change_impact(delta, university_id=university_id,
                                        eligibility_catalog=eligibility, progress_catalog=progress)
        plan_version = scope_facts[0].study_plan_version if scope_facts else None
        return report, _relevant_source_versions(delta, plan_version, scope_facts)

    async def _audit(
        self, report: ChangeImpactReport, actor: UUID, actor_class: ActorClass,
        student_user_id: UUID | None, source_versions: tuple[str, ...],
    ) -> ChangeImpactReport:
        if student_user_id is not None:
            scope_type = SubjectScopeType.STUDENT_INDIVIDUAL
            scope_id = str(student_user_id)
            redaction = RedactionProfile.ADVISOR_SAFE
        elif report.study_plan_id is not None:
            scope_type = SubjectScopeType.CURRICULAR_PROGRAM
            scope_id = str(report.study_plan_id)
            redaction = RedactionProfile.AGGREGATE_ANALYST
        else:
            scope_type = SubjectScopeType.POLICY_DOCUMENT
            scope_id = next(fact.reference for fact in report.affected_facts)
            redaction = RedactionProfile.AGGREGATE_ANALYST
        outcome = _report_fingerprint(report)
        identity = hashlib.sha256(
            f"{actor_class.value}:{actor}:{scope_type.value}:{scope_id}:{outcome}".encode()
        ).hexdigest()
        evidence = [
            EvidenceReference("WC046_DELTA", report.change_id, "wc046:v1"),
            EvidenceReference("WC046_OLD_VERSION", report.change_id, report.old_version),
            EvidenceReference("WC046_NEW_VERSION", report.change_id, report.new_version),
        ]
        if report.study_plan_id is not None:
            evidence.append(EvidenceReference("STUDY_PLAN", str(report.study_plan_id), "wc046:v1"))
        for code in report.structurally_affected_courses[:100]:
            evidence.append(EvidenceReference("AFFECTED_COURSE", code, report.new_version))
        entry = create_canonical_ledger_entry(
            ledger_entry_id=identity,
            decision_type=DecisionType.CHANGE_IMPACT_EVALUATION,
            materiality_class=materiality_for(DecisionType.CHANGE_IMPACT_EVALUATION),
            actor_class=actor_class, actor_id=str(actor),
            subject_scope_type=scope_type, subject_scope_id=scope_id,
            university_id=str(report.university_id),
            student_user_id=str(student_user_id) if student_user_id else None,
            source_engine="P8_CHANGE_IMPACT_ENGINE", source_engine_version="wc046:v1",
            policy_version="wc046:v1", source_versions=tuple(sorted(set((report.old_version,
                report.new_version, *source_versions)))), input_state_reference=report.change_id,
            scenario_id=None,
            decision_status=(DecisionStatus.FLAGGED_REVIEW if report.requires_human_review
                             else DecisionStatus.VALIDATED),
            outcome_reference=f"WC046_IMPACT:{outcome}", evidence_references=tuple(evidence),
            domain_trace_reference=None, provenance_class=ProvenanceClass.GOVERNED_ASSESSMENT,
            created_at=datetime.now(timezone.utc), redaction_profile=redaction,
            previous_entry_hash=None, supersedes_entry_id=None,
            replay_status=ReplayStatus.NOT_REPLAYABLE,
            limitations=("CHANGE_IMPACT_V1_EPHEMERAL_REPORT",
                         *(item.value for item in report.limitations)),
        )
        try:
            existing = await self._ledger.load_exact_internal_entry(
                ledger_entry_id=identity, university_id=str(report.university_id))
            appended = False
            if existing is None:
                try:
                    await self._ledger.append(entry)
                    appended = True
                except DecisionTracePersistenceError as error:
                    if error.code is not DecisionTraceErrorCode.PERSISTENCE_CONFLICT:
                        raise
                    existing = await self._ledger.load_exact_internal_entry(
                        ledger_entry_id=identity, university_id=str(report.university_id))
            if existing is not None and not _same_trusted_evaluation(existing, entry):
                raise DecisionTracePersistenceError(
                    DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                    "producer retry did not match persisted evaluation")
            if existing is None and not appended:
                raise DecisionTracePersistenceError(
                    DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                    "audit duplicate could not be reconciled")
        except DecisionTracePersistenceError as error:
            raise ImpactServiceError(ImpactServiceCode.AUDIT_PERSISTENCE_UNAVAILABLE) from error
        return report.model_copy(update={"audit_status": "LEDGER_PERSISTED"})


def _report_fingerprint(report: ChangeImpactReport) -> str:
    data = report.model_dump(mode="json", exclude={"generated_at", "audit_status"})
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def _require_target_exists(delta: ChangeDelta, eligibility, progress) -> None:
    if isinstance(delta, PrerequisiteGroupDelta):
        exists = eligibility is not None and any(
            row.course_code == delta.target_course_code for row in eligibility.plan_courses)
    elif isinstance(delta, RequirementGroupCreditDelta):
        exists = progress is not None and any(
            row.group_code == delta.requirement_group_code
            for row in progress.requirement_groups)
    elif isinstance(delta, CourseCreditHoursDelta):
        exists = progress is not None and any(
            row.course_code == delta.course_code for row in progress.plan_courses)
    else:
        return
    if not exists:
        raise ImpactServiceError(ImpactServiceCode.SCOPE_UNAVAILABLE)


def _same_trusted_evaluation(stored, proposed) -> bool:
    if verify_integrity_hash(stored) is not IntegrityStatus.VERIFIED:
        return False
    ignored = {"created_at", "integrity_hash"}
    return all(getattr(stored, field.name) == getattr(proposed, field.name)
               for field in fields(proposed) if field.name not in ignored)


def _membership_failure_code(error: MockRegistrationPersistenceError) -> ImpactServiceCode:
    return (ImpactServiceCode.ACCESS_DENIED
            if error.code is PersistenceFailureCode.RESOURCE_NOT_FOUND
            else ImpactServiceCode.IMPACT_SERVICE_UNAVAILABLE)


def _relevant_source_versions(delta: ChangeDelta, plan_version: str | None, facts) -> tuple[str, ...]:
    """Use only actual available plan/course snapshot versions, never invent group versions."""
    versions = {plan_version} if plan_version else set()
    code = (delta.target_course_code if isinstance(delta, PrerequisiteGroupDelta)
            else delta.course_code if isinstance(delta, CourseCreditHoursDelta) else None)
    if code is not None:
        versions.update(fact.source_version for fact in facts if fact.course_code == code)
    return tuple(sorted(versions))
