"""Trusted P8 application service: integrity gate, authorization, and safe projections."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from app.advisor_persistence.errors import AdvisorPersistenceError
from app.advisor_service import AdvisorAuthorizationError, AdvisorAuthorizationService
from app.core.auth import CurrentUser
from app.decision_trace import (
    CanonicalLedgerEntry,
    IntegrityStatus,
    RedactionProfile,
    validate_entry,
    verify_integrity_hash,
)

from .errors import DecisionTraceErrorCode, DecisionTracePersistenceError
from .models import (
    DecisionTraceSafeMetadata, DecisionTraceSafeView, StudentDecisionEvidence,
    StudentDecisionHistoryDetail, StudentDecisionHistoryItem,
)
from .repository import SupabaseDecisionTraceRepository


class StudentScopeRepository(Protocol):
    async def load_student_authoritative_university(
        self, student_user_id: UUID
    ) -> UUID | None: ...


class DecisionTraceService:
    """No-route service boundary over server-side persistence and P7 authorization."""

    def __init__(
        self,
        repository: SupabaseDecisionTraceRepository,
        student_scope_repository: StudentScopeRepository,
        advisor_authorization_service: AdvisorAuthorizationService,
    ) -> None:
        self._repository = repository
        self._student_scopes = student_scope_repository
        self._advisor_authorization = advisor_authorization_service

    async def append_student(
        self, principal: CurrentUser | None, entry: CanonicalLedgerEntry
    ) -> str:
        """Reject user-submitted ledger envelopes until a trusted event adapter exists.

        A verified user may request a deterministic academic operation, but neither a
        user-supplied outcome nor a matching canonical hash proves that an approved
        deterministic workflow produced it.  This method intentionally has no
        persistence path.  A future internal adapter must derive an entry from a
        concrete, verified workflow result and call the repository only after that
        result is bound to its authoritative context.
        """
        _verified_principal_uuid(principal)
        _ = entry
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.UNSUPPORTED_APPEND_AUTHORITY,
            "user-submitted decision trace envelopes are not a trusted event source",
        )

    async def append_advisor(
        self,
        principal: CurrentUser | None,
        target_student_user_id: UUID | str | None,
        entry: CanonicalLedgerEntry,
    ) -> str:
        _verified_principal_uuid(principal)
        _target_student_uuid(target_student_user_id)
        _ = entry
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.UNSUPPORTED_APPEND_AUTHORITY,
            "user-submitted advisor trace envelopes are not a trusted event source",
        )

    async def get_student_trace(
        self, principal: CurrentUser | None, ledger_entry_id: str
    ) -> DecisionTraceSafeView:
        student_id = _verified_principal_uuid(principal)
        university_id = await _student_university(self._student_scopes, student_id)
        entry = await self._load_authorized_student_entry(
            ledger_entry_id, student_id, university_id
        )
        _require_viewer_visibility(entry, RedactionProfile.STUDENT_SAFE)
        return _safe_view(entry)

    async def list_student_history(
        self, principal: CurrentUser | None, *, limit: int = 20,
        before_created_at: datetime | None = None, before_entry_id: str | None = None,
    ) -> tuple[StudentDecisionHistoryItem, ...]:
        student_id = _verified_principal_uuid(principal)
        university_id = await _student_university(self._student_scopes, student_id)
        entries = await self._repository.list_student_entries(
            student_user_id=str(student_id), university_id=str(university_id), limit=limit,
            before_created_at=before_created_at, before_entry_id=before_entry_id,
        )
        result: list[StudentDecisionHistoryItem] = []
        for entry in entries:
            _require_viewer_visibility(entry, RedactionProfile.STUDENT_SAFE)
            _require_verified_hash(entry)
            predecessor_id = await self._visible_predecessor_id(entry, student_id, university_id)
            successor = await self._visible_successor(entry, student_id, university_id)
            result.append(StudentDecisionHistoryItem(
                ledger_entry_id=entry.ledger_entry_id, decision_type=entry.decision_type,
                decision_status=entry.decision_status, created_at=entry.created_at,
                source_engine=entry.source_engine, source_engine_version=entry.source_engine_version,
                policy_version=entry.policy_version, replay_status=entry.replay_status,
                supersedes_entry_id=predecessor_id, is_superseded=successor is not None,
                limitations=entry.limitations,
            ))
        return tuple(result)

    async def get_student_history_detail(
        self, principal: CurrentUser | None, ledger_entry_id: str,
    ) -> StudentDecisionHistoryDetail:
        student_id = _verified_principal_uuid(principal)
        university_id = await _student_university(self._student_scopes, student_id)
        entry = await self._load_authorized_student_entry(
            ledger_entry_id, student_id, university_id,
            viewer_profile=RedactionProfile.STUDENT_SAFE,
        )
        predecessor_id = await self._visible_predecessor_id(entry, student_id, university_id)
        successor = await self._visible_successor(entry, student_id, university_id)
        return StudentDecisionHistoryDetail(
            ledger_entry_id=entry.ledger_entry_id, decision_type=entry.decision_type,
            decision_status=entry.decision_status, created_at=entry.created_at,
            source_engine=entry.source_engine, source_engine_version=entry.source_engine_version,
            policy_version=entry.policy_version, source_versions=entry.source_versions,
            replay_status=entry.replay_status, provenance_class=entry.provenance_class,
            limitations=entry.limitations, integrity_status="VERIFIED",
            supersedes_entry_id=predecessor_id, is_superseded=successor is not None,
            evidence=tuple(StudentDecisionEvidence(
                source=ref.source, identifier=ref.identifier, version=ref.version,
                locator=ref.locator, uri=_safe_evidence_uri(ref.uri),
            ) for ref in entry.evidence_references),
        )

    async def list_advisor_history(
        self, principal: CurrentUser | None, target_student_user_id: UUID | str | None,
        *, limit: int = 20, before_created_at: datetime | None = None,
        before_entry_id: str | None = None,
    ) -> tuple[StudentDecisionHistoryItem, ...]:
        student_id, university_id = await self._authorized_advisor_scope(principal, target_student_user_id)
        entries = await self._repository.list_student_entries(
            student_user_id=str(student_id), university_id=str(university_id), limit=limit,
            before_created_at=before_created_at, before_entry_id=before_entry_id,
            redaction_profiles=("STUDENT_SAFE", "ADVISOR_SAFE"),
        )
        result: list[StudentDecisionHistoryItem] = []
        for entry in entries:
            _require_viewer_visibility(entry, RedactionProfile.ADVISOR_SAFE)
            _require_verified_hash(entry)
            predecessor_id = await self._visible_predecessor_id(
                entry, student_id, university_id, RedactionProfile.ADVISOR_SAFE,
            )
            successor = await self._visible_successor(
                entry, student_id, university_id, RedactionProfile.ADVISOR_SAFE,
            )
            result.append(StudentDecisionHistoryItem(
                ledger_entry_id=entry.ledger_entry_id, decision_type=entry.decision_type,
                decision_status=entry.decision_status, created_at=entry.created_at,
                source_engine=entry.source_engine, source_engine_version=entry.source_engine_version,
                policy_version=entry.policy_version, replay_status=entry.replay_status,
                supersedes_entry_id=predecessor_id, is_superseded=successor is not None,
                limitations=entry.limitations,
            ))
        return tuple(result)

    async def get_advisor_history_detail(
        self, principal: CurrentUser | None, target_student_user_id: UUID | str | None,
        ledger_entry_id: str,
    ) -> StudentDecisionHistoryDetail:
        student_id, university_id = await self._authorized_advisor_scope(principal, target_student_user_id)
        entry = await self._load_authorized_student_entry(
            ledger_entry_id, student_id, university_id,
            viewer_profile=RedactionProfile.ADVISOR_SAFE,
        )
        predecessor_id = await self._visible_predecessor_id(
            entry, student_id, university_id, RedactionProfile.ADVISOR_SAFE,
        )
        successor = await self._visible_successor(
            entry, student_id, university_id, RedactionProfile.ADVISOR_SAFE,
        )
        return StudentDecisionHistoryDetail(
            ledger_entry_id=entry.ledger_entry_id, decision_type=entry.decision_type,
            decision_status=entry.decision_status, created_at=entry.created_at,
            source_engine=entry.source_engine, source_engine_version=entry.source_engine_version,
            policy_version=entry.policy_version, source_versions=entry.source_versions,
            replay_status=entry.replay_status, provenance_class=entry.provenance_class,
            limitations=entry.limitations, integrity_status="VERIFIED",
            supersedes_entry_id=predecessor_id, is_superseded=successor is not None,
            evidence=tuple(StudentDecisionEvidence(
                source=ref.source, identifier=ref.identifier, version=ref.version,
                locator=ref.locator, uri=_safe_evidence_uri(ref.uri),
            ) for ref in entry.evidence_references),
        )

    async def _authorized_advisor_scope(
        self, principal: CurrentUser | None, target_student_user_id: UUID | str | None,
    ) -> tuple[UUID, UUID]:
        advisor_id = _verified_principal_uuid(principal)
        student_id = _target_student_uuid(target_student_user_id)
        try:
            context = await self._advisor_authorization.authorize_advisor_for_student(
                advisor_id, student_id,
            )
        except AdvisorAuthorizationError as error:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.ACCESS_DENIED, "advisor trace authority was denied",
            ) from error
        if context.advisor_user_id != advisor_id or context.student_user_id != student_id:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE, "advisor scope mismatch",
            )
        return student_id, context.university_id

    async def _visible_predecessor_id(
        self, entry: CanonicalLedgerEntry, student_id: UUID, university_id: UUID,
        viewer_profile: RedactionProfile = RedactionProfile.STUDENT_SAFE,
    ) -> str | None:
        if entry.supersedes_entry_id is None:
            return None
        predecessor = await self._repository.load_student_entry(
            ledger_entry_id=entry.supersedes_entry_id,
            student_user_id=str(student_id), university_id=str(university_id),
            **({"redaction_profile": RedactionProfile.STUDENT_SAFE.value}
               if viewer_profile is RedactionProfile.STUDENT_SAFE else
               {"redaction_profiles": ("STUDENT_SAFE", "ADVISOR_SAFE")}),
        )
        if predecessor is None:
            return None
        _require_viewer_visibility(predecessor, viewer_profile)
        _require_verified_hash(predecessor)
        if entry.previous_entry_hash != predecessor.integrity_hash:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.INTEGRITY_FAILURE, "supersession hash does not match"
            )
        return predecessor.ledger_entry_id

    async def _visible_successor(
        self, entry: CanonicalLedgerEntry, student_id: UUID, university_id: UUID,
        viewer_profile: RedactionProfile = RedactionProfile.STUDENT_SAFE,
    ) -> CanonicalLedgerEntry | None:
        successor = await self._repository.load_student_successor(
            ledger_entry_id=entry.ledger_entry_id,
            student_user_id=str(student_id), university_id=str(university_id),
            **({} if viewer_profile is RedactionProfile.STUDENT_SAFE else
               {"redaction_profiles": ("STUDENT_SAFE", "ADVISOR_SAFE")}),
        )
        if successor is not None:
            _require_viewer_visibility(successor, viewer_profile)
            _require_verified_hash(successor)
            if successor.previous_entry_hash != entry.integrity_hash:
                raise DecisionTracePersistenceError(
                    DecisionTraceErrorCode.INTEGRITY_FAILURE, "successor hash does not match"
                )
        return successor

    async def get_advisor_trace(
        self,
        principal: CurrentUser | None,
        target_student_user_id: UUID | str | None,
        ledger_entry_id: str,
    ) -> DecisionTraceSafeView:
        advisor_id = _verified_principal_uuid(principal)
        student_id = _target_student_uuid(target_student_user_id)
        try:
            context = await self._advisor_authorization.authorize_advisor_for_student(
                advisor_id, student_id
            )
        except AdvisorAuthorizationError as error:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.ACCESS_DENIED, "advisor trace authority was denied"
            ) from error
        entry = await self._load_authorized_student_entry(
            ledger_entry_id, student_id, context.university_id
        )
        _require_viewer_visibility(entry, RedactionProfile.ADVISOR_SAFE)
        return _safe_view(entry)

    async def get_institutional_individual_trace(
        self, principal: CurrentUser | None, ledger_entry_id: str
    ) -> DecisionTraceSafeView:
        """Explicit denial: institutional analysts have no individual trace/evidence interface."""
        _verified_principal_uuid(principal)
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.ACCESS_DENIED,
            "institutional viewers cannot retrieve individual decision traces",
        )

    async def _load_authorized_student_entry(
        self, ledger_entry_id: str, student_id: UUID, university_id: UUID,
        viewer_profile: RedactionProfile | None = None,
    ) -> CanonicalLedgerEntry:
        if not isinstance(ledger_entry_id, str) or not ledger_entry_id.strip():
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.NOT_FOUND, "ledger identity is required"
            )
        entry = await self._repository.load_student_entry(
            ledger_entry_id=ledger_entry_id,
            student_user_id=str(student_id),
            university_id=str(university_id),
            **({"redaction_profile": viewer_profile.value}
               if viewer_profile is RedactionProfile.STUDENT_SAFE else
               {"redaction_profiles": ("STUDENT_SAFE", "ADVISOR_SAFE")}
               if viewer_profile is RedactionProfile.ADVISOR_SAFE else {}),
        )
        if entry is None:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.NOT_FOUND, "individual decision trace was not found"
            )
        if (entry.ledger_entry_id != ledger_entry_id or entry.student_user_id != str(student_id)
                or entry.university_id != str(university_id)
                or entry.subject_scope_type.value != "STUDENT_INDIVIDUAL"):
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "individual decision trace scope mismatch",
            )
        if viewer_profile is not None:
            _require_viewer_visibility(entry, viewer_profile)
        _require_verified_hash(entry)
        return entry


async def _student_university(
    repository: StudentScopeRepository, student_id: UUID
) -> UUID:
    try:
        university = await repository.load_student_authoritative_university(student_id)
    except AdvisorPersistenceError as error:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.PERSISTENCE_UNAVAILABLE,
            "student scope lookup is unavailable",
        ) from error
    if university is None:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.ACCESS_DENIED,
            "student authoritative university scope was unavailable",
        )
    return university


def _verified_principal_uuid(principal: CurrentUser | None) -> UUID:
    """Accept only the existing Auth dependency result, never a raw request UUID."""
    if not isinstance(principal, CurrentUser):
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.AUTH_REQUIRED,
            "a principal verified by get_current_user is required",
        )
    try:
        return UUID(principal.user_id)
    except (TypeError, ValueError) as error:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.AUTH_REQUIRED, "verified principal is invalid"
        ) from error


def _target_student_uuid(value: UUID | str | None) -> UUID:
    if value is None:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.ACCESS_DENIED, "target student is required"
        )
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError) as error:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.ACCESS_DENIED, "target student is invalid"
        ) from error


def _require_verified_hash(entry: CanonicalLedgerEntry) -> None:
    try:
        validate_entry(entry)
    except ValueError as error:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.INTEGRITY_FAILURE, "decision trace domain validation failed"
        ) from error
    if verify_integrity_hash(entry) is not IntegrityStatus.VERIFIED:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.INTEGRITY_FAILURE,
            "decision trace integrity hash does not match the Slice 1 canonical payload",
        )


def _require_viewer_visibility(
    entry: CanonicalLedgerEntry, viewer_profile: RedactionProfile
) -> None:
    """Fail closed unless the stored classification explicitly permits this viewer."""
    permitted = {
        RedactionProfile.STUDENT_SAFE: frozenset({RedactionProfile.STUDENT_SAFE}),
        RedactionProfile.ADVISOR_SAFE: frozenset(
            {RedactionProfile.STUDENT_SAFE, RedactionProfile.ADVISOR_SAFE}
        ),
    }
    if entry.redaction_profile not in permitted.get(viewer_profile, frozenset()):
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.ACCESS_DENIED,
            "stored trace classification does not permit this viewer",
        )


def _safe_view(entry: CanonicalLedgerEntry) -> DecisionTraceSafeView:
    _require_verified_hash(entry)
    return DecisionTraceSafeView(
        metadata=DecisionTraceSafeMetadata(
            ledger_entry_id=entry.ledger_entry_id,
            decision_type=entry.decision_type,
            decision_status=entry.decision_status,
            created_at=entry.created_at,
            replay_status=entry.replay_status,
        )
    )


def _safe_evidence_uri(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    return value
