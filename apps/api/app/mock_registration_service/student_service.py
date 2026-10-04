"""Authenticated owner-derived Mock Registration application service."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.catalog.errors import CatalogRepositoryError
from app.mock_registration.models import (
    IntentLifecycle, IntentProvenance, RegistrationIntent, ValidationStatus,
)
from app.mock_registration.resolution import resolve_current_intents
from app.mock_registration.validation import validate_registration_intent
from app.mock_registration.replay_artifact import create_p6_replay_artifact
from app.mock_registration_persistence.errors import (
    MockRegistrationPersistenceError, PersistenceFailureCode,
)
from app.mock_registration_persistence.models import (
    PersistRevisionCommand, PersistedIntentRevision, PersistenceResultKind,
)
from app.mock_registration_persistence.repository import SupabaseMockRegistrationRepository
from app.student.errors import StudentRepositoryError

from .context import AcademicContextLoader, domain_context
from .errors import MockRegistrationServiceError, ServiceErrorCode
from .models import CurrentValidity, RevalidationStatus, StudentIntentResult
from .revalidation import domain_period, revalidate, stored_domain_record

LIMITATIONS = (
    "Mock Registration is declared, non-binding intent; it is not registration or enrollment.",
    "No seat, offering, approval, or official university action is guaranteed.",
)


class MockRegistrationStudentService:
    def __init__(self, persistence: SupabaseMockRegistrationRepository,
                 contexts: AcademicContextLoader) -> None:
        self._persistence = persistence
        self._contexts = contexts

    async def current(self, owner: str, target_period_id: UUID) -> StudentIntentResult:
        snapshot = await self._context(owner)
        period = await self._period(target_period_id, snapshot.university_id)
        history = await self._history(snapshot, target_period_id)
        row = _latest(history, period)
        if row is None:
            raise MockRegistrationServiceError(ServiceErrorCode.RESOURCE_NOT_FOUND)
        validation = revalidate(row, period, snapshot)
        return _student_result(row, period, validation.current_validity, validation.status,
                               validation.reason_codes, False)

    async def submit(self, owner: str, *, target_period_id: UUID,
                     course_codes: tuple[str, ...], expected_current_revision: int | None,
                     transparency_notice_version: str) -> StudentIntentResult:
        snapshot = await self._context(owner)
        period = await self._period(target_period_id, snapshot.university_id)
        if period.is_expired:
            raise MockRegistrationServiceError(ServiceErrorCode.PERIOD_INVALID)
        next_revision = (expected_current_revision or 0) + 1
        intent = RegistrationIntent(
            str(uuid4()), str(snapshot.owner_user_id), str(snapshot.university_id),
            str(snapshot.major_id), str(snapshot.study_plan_id), snapshot.study_plan_version,
            domain_period(period), next_revision, IntentLifecycle.SUBMITTED, course_codes,
            _provenance(period.period_class.value), snapshot.snapshot_token,
        )
        historical_context = domain_context(snapshot, domain_period(period))
        validated = validate_registration_intent(intent, historical_context)
        if validated.status is ValidationStatus.INVALID:
            raise MockRegistrationServiceError(ServiceErrorCode.INVALID_INTENT,
                                               reasons=validated.reason_codes)
        fresh = await self._context(owner)
        if fresh.snapshot_token != snapshot.snapshot_token:
            raise MockRegistrationServiceError(ServiceErrorCode.ACADEMIC_STATE_CHANGED)
        course_ids = tuple(snapshot.course_id(code) for code in validated.canonical_course_codes)
        if any(value is None for value in course_ids):
            raise MockRegistrationServiceError(ServiceErrorCode.PLAN_SCOPE_INVALID)
        result = await self._persist(PersistRevisionCommand(
            intent_id=UUID(intent.intent_id), owner_user_id=snapshot.owner_user_id,
            university_id=snapshot.university_id, major_id=snapshot.major_id,
            study_plan_id=snapshot.study_plan_id, study_plan_version=snapshot.study_plan_version,
            target_period_id=target_period_id, expected_current_revision=expected_current_revision,
            lifecycle_status=IntentLifecycle.SUBMITTED, validation_status=validated.status,
            content_fingerprint=validated.content_fingerprint, intent_provenance=intent.source_class,
            intent_source_version=snapshot.snapshot_token,
            validation_reason_codes=validated.reason_codes,
            catalog_source_versions=snapshot.source_versions,
            prerequisite_source_versions=snapshot.source_versions,
            progress_state_version=snapshot.progress_state_version,
            progress_state_reference=snapshot.progress_state_reference,
            phase5_policy_version="phase5:v1", phase6_policy_version="phase6:v1",
            p6_contract_version="1.0", target_period_source_version=period.source_version,
            transparency_notice_version=transparency_notice_version,
            actor_class="STUDENT_AUTHENTICATED",
            course_ids=tuple(value for value in course_ids if value is not None),
            course_codes=validated.canonical_course_codes,
            replay_artifact=create_p6_replay_artifact(intent, historical_context, validated),
        ))
        row = await self._persisted_row(snapshot, target_period_id, result.revision)
        current = (CurrentValidity.CURRENT_VALID if validated.status is ValidationStatus.VALID
                   else CurrentValidity.REVIEW_REQUIRED)
        return _student_result(row, period, current, RevalidationStatus.COMPLETE,
                               validated.reason_codes,
                               result.kind is PersistenceResultKind.IDEMPOTENT_REPLAY)

    async def withdraw(self, owner: str, *, target_period_id: UUID,
                       expected_current_revision: int,
                       transparency_notice_version: str) -> StudentIntentResult:
        snapshot = await self._context(owner)
        period = await self._period(target_period_id, snapshot.university_id)
        history = await self._history(snapshot, target_period_id)
        current = _latest(history, period)
        if current is None or current.lifecycle_status is IntentLifecycle.WITHDRAWN:
            raise MockRegistrationServiceError(ServiceErrorCode.RESOURCE_NOT_FOUND)
        revision = expected_current_revision + 1
        intent = RegistrationIntent(
            str(uuid4()), str(snapshot.owner_user_id), str(snapshot.university_id),
            str(snapshot.major_id), str(snapshot.study_plan_id), snapshot.study_plan_version,
            domain_period(period), revision, IntentLifecycle.WITHDRAWN, (),
            _provenance(period.period_class.value), snapshot.snapshot_token,
        )
        validated = validate_registration_intent(intent, domain_context(snapshot, domain_period(period)))
        fresh = await self._context(owner)
        if fresh.snapshot_token != snapshot.snapshot_token:
            raise MockRegistrationServiceError(ServiceErrorCode.ACADEMIC_STATE_CHANGED)
        result = await self._persist(PersistRevisionCommand(
            UUID(intent.intent_id), snapshot.owner_user_id, snapshot.university_id,
            snapshot.major_id, snapshot.study_plan_id, snapshot.study_plan_version,
            target_period_id, expected_current_revision, IntentLifecycle.WITHDRAWN,
            ValidationStatus.VALID, validated.content_fingerprint, intent.source_class,
            snapshot.snapshot_token, (), snapshot.source_versions, snapshot.source_versions,
            snapshot.progress_state_version, snapshot.progress_state_reference,
            "phase5:v1", "phase6:v1", "1.0", period.source_version,
            transparency_notice_version, "STUDENT_AUTHENTICATED", (), (),
        ))
        row = await self._persisted_row(snapshot, target_period_id, result.revision)
        return _student_result(row, period, None, RevalidationStatus.COMPLETE, (),
                               result.kind is PersistenceResultKind.IDEMPOTENT_REPLAY)

    async def _context(self, owner: str):
        try:
            owner_id = UUID(owner)
            snapshot = await self._contexts.load_owner_context(owner_id)
        except (ValueError, StudentRepositoryError, CatalogRepositoryError) as error:
            raise MockRegistrationServiceError(ServiceErrorCode.ACADEMIC_CONTEXT_UNAVAILABLE) from error
        if snapshot.owner_user_id != owner_id:
            raise MockRegistrationServiceError(ServiceErrorCode.OWNER_SCOPE_MISMATCH)
        return snapshot

    async def _period(self, period_id: UUID, university_id: UUID):
        try:
            return await self._persistence.load_target_period(period_id, university_id)
        except MockRegistrationPersistenceError as error:
            code = (ServiceErrorCode.PERIOD_INVALID if error.code is PersistenceFailureCode.RESOURCE_NOT_FOUND
                    else ServiceErrorCode.PERSISTENCE_UNAVAILABLE)
            raise MockRegistrationServiceError(code) from error

    async def _history(self, snapshot, period_id):
        try:
            return await self._persistence.load_revision_history(
                owner_user_id=snapshot.owner_user_id, university_id=snapshot.university_id,
                major_id=snapshot.major_id, study_plan_id=snapshot.study_plan_id,
                study_plan_version=snapshot.study_plan_version, target_period_id=period_id)
        except MockRegistrationPersistenceError as error:
            raise MockRegistrationServiceError(ServiceErrorCode.PERSISTENCE_UNAVAILABLE) from error

    async def _persist(self, command):
        try:
            result = await self._persistence.persist_revision(command)
        except MockRegistrationPersistenceError as error:
            code = (ServiceErrorCode.PERSISTENCE_CONFLICT
                    if error.code is PersistenceFailureCode.PERSISTENCE_CONFLICT
                    else ServiceErrorCode.PERSISTENCE_UNAVAILABLE)
            raise MockRegistrationServiceError(code) from error
        if result.kind is PersistenceResultKind.REVISION_CONFLICT:
            raise MockRegistrationServiceError(ServiceErrorCode.REVISION_CONFLICT,
                                               current_revision=result.revision)
        if result.kind is PersistenceResultKind.PERSISTENCE_CONFLICT:
            raise MockRegistrationServiceError(ServiceErrorCode.PERSISTENCE_CONFLICT,
                                               current_revision=result.revision)
        return result

    async def _persisted_row(self, snapshot, period_id, revision):
        history = await self._history(snapshot, period_id)
        row = next((item for item in history if item.revision == revision), None)
        if row is None:
            raise MockRegistrationServiceError(ServiceErrorCode.PERSISTENCE_UNAVAILABLE)
        return row


def _latest(history: tuple[PersistedIntentRevision, ...], period):
    if not history:
        return None
    resolution = resolve_current_intents(tuple(stored_domain_record(row, period) for row in history))
    if not resolution.records:
        return None
    winner = max(resolution.records, key=lambda item: item.record.intent.revision)
    return next(row for row in history if row.revision == winner.record.intent.revision)


def _student_result(row, period, validity, freshness, reasons, replay):
    return StudentIntentResult(
        row.intent_id, row.target_period_id, period.period_class, row.revision,
        row.lifecycle_status, tuple(item.course_code for item in row.courses),
        row.validation_status, row.validation_reason_codes, validity, freshness,
        reasons, replay, row.created_at, LIMITATIONS,
    )


def _provenance(period_class: str) -> IntentProvenance:
    return (IntentProvenance.SYNTHETIC_SANDBOX_INTENT
            if period_class == "SYNTHETIC_SANDBOX_PERIOD"
            else IntentProvenance.DECLARED_STUDENT_INTENT)

