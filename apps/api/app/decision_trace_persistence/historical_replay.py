"""Internal-only exact execution of a new P6 submit's historical validator."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.decision_trace import DecisionType, IntegrityStatus, ReplayStatus, verify_integrity_hash
from app.mock_registration.replay_artifact import (
    P6ReplayArtifactError, P6ReplayVerification, execute_p6_replay,
    verify_p6_replay_artifact,
)
from app.mock_registration_persistence.repository import SupabaseMockRegistrationRepository

from .outbox_repository import SupabaseDecisionTraceOutboxRepository
from .repository import SupabaseDecisionTraceRepository


@dataclass(frozen=True, slots=True)
class ExactP6ReplayResult:
    ledger_entry_id: str
    mode: str
    status: str
    matched: bool
    reason_code: str | None
    engine_version: str | None
    replay_contract_version: str | None
    historical_validation_status: str | None
    replayed_validation_status: str | None
    historical_reason_codes: tuple[str, ...]
    replayed_reason_codes: tuple[str, ...]
    historical_content_fingerprint: str | None
    replayed_content_fingerprint: str | None


def _unavailable(ledger_id: str, reason: str) -> ExactP6ReplayResult:
    return ExactP6ReplayResult(
        ledger_id, "EXACT_REPLAY", "UNAVAILABLE", False, reason, None, None,
        None, None, (), (), None, None,
    )


class P6HistoricalReplayService:
    """Trusted service, not a public generic replay dispatcher or academic writer."""

    def __init__(
        self, revisions: SupabaseMockRegistrationRepository,
        ledger: SupabaseDecisionTraceRepository,
        artifacts: SupabaseDecisionTraceOutboxRepository,
    ) -> None:
        self._revisions = revisions
        self._ledger = ledger
        self._artifacts = artifacts

    async def verify(self, ledger_entry_id: str) -> ExactP6ReplayResult:
        try:
            revision_id = UUID(ledger_entry_id)
        except ValueError:
            return _unavailable(ledger_entry_id, "INVALID_LEDGER_ID")
        revision = await self._revisions.load_revision_by_id(revision_id)
        if revision is None:
            return _unavailable(ledger_entry_id, "REVISION_UNAVAILABLE")
        entry = await self._ledger.load_exact_internal_entry(
            ledger_entry_id=ledger_entry_id, university_id=str(revision.university_id),
        )
        if entry is None or entry.decision_type is not DecisionType.MOCK_REGISTRATION_SUBMIT:
            return _unavailable(ledger_entry_id, "LEDGER_ENTRY_UNAVAILABLE")
        if verify_integrity_hash(entry) is not IntegrityStatus.VERIFIED:
            return _unavailable(ledger_entry_id, "LEDGER_INTEGRITY_FAILURE")
        if entry.replay_status is not ReplayStatus.REPLAYABLE_EXACT:
            return _unavailable(ledger_entry_id, "TRACE_NOT_REPLAYABLE")
        if (
            entry.ledger_entry_id != str(revision.revision_id)
            or entry.student_user_id != str(revision.owner_user_id)
            or entry.university_id != str(revision.university_id)
            or entry.source_engine_version != revision.p6_contract_version
            or entry.policy_version != revision.phase6_policy_version
            or entry.outcome_reference != (
                f"P6_NON_BINDING_INTENT:{revision.revision_id}:"
                f"{revision.validation_status.value}:{revision.content_fingerprint}"
            )
        ):
            return _unavailable(ledger_entry_id, "LEDGER_REVISION_MISMATCH")
        artifact = await self._artifacts.load_replay_artifact(
            revision_id=revision.revision_id, university_id=revision.university_id,
        )
        if artifact is None:
            return _unavailable(ledger_entry_id, "REPLAY_ARTIFACT_MISSING")
        try:
            payload = verify_p6_replay_artifact(artifact)
            if (
                artifact.engine_version != entry.source_engine_version
                or payload["intent"]["owner_scope_id"] != str(revision.owner_user_id)
                or payload["intent"]["university_id"] != str(revision.university_id)
                or payload["intent"]["major_id"] != str(revision.major_id)
                or payload["intent"]["study_plan_id"] != str(revision.study_plan_id)
                or payload["intent"]["study_plan_version"] != revision.study_plan_version
                or payload["intent"]["revision"] != revision.revision
                or payload["intent"]["source_version"] != revision.intent_source_version
                or payload["intent"]["target_period"]["source_version"] != revision.target_period_source_version
                or tuple(payload["context"]["source_versions"]) != revision.catalog_source_versions
                or tuple(payload["context"]["source_versions"]) != revision.prerequisite_source_versions
                or tuple(payload["context"]["engine_policy_versions"][:2]) != (
                    revision.phase5_policy_version, revision.phase6_policy_version)
                or not any(ref.source == "P6_REPLAY_ARTIFACT"
                           and ref.identifier == str(revision.revision_id)
                           and ref.version == artifact.replay_contract_version
                           for ref in entry.evidence_references)
            ):
                return _unavailable(ledger_entry_id, "REPLAY_IDENTITY_MISMATCH")
            result: P6ReplayVerification = execute_p6_replay(
                artifact, persisted_intent_id=str(revision.intent_id),
                persisted_status=revision.validation_status,
                persisted_reasons=tuple(code.value for code in revision.validation_reason_codes),
                persisted_fingerprint=revision.content_fingerprint,
                persisted_course_codes=tuple(course.course_code for course in revision.courses),
            )
        except P6ReplayArtifactError as exc:
            return _unavailable(ledger_entry_id, exc.reason_code)
        return ExactP6ReplayResult(
            ledger_entry_id, "EXACT_REPLAY", result.status, result.matched,
            result.reason_code, artifact.engine_version, artifact.replay_contract_version,
            result.historical_validation_status, result.replayed_validation_status,
            result.historical_reason_codes, result.replayed_reason_codes,
            result.historical_content_fingerprint, result.replayed_content_fingerprint,
        )
