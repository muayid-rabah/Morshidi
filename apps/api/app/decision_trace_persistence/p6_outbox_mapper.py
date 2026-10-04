"""Internal-only, fail-closed mapper for approved P6 submit outbox facts.

This module deliberately has no database client and no append call.  A future
separately approved service-only projection boundary must construct
``TrustedP6OutboxProjection`` from the immutable P6 revision, ordered courses,
and outbox event.  It must never be populated from a request payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.decision_trace import (
    ActorClass,
    CanonicalLedgerEntry,
    DecisionStatus,
    DecisionType,
    EvidenceReference,
    IntegrityStatus,
    ProvenanceClass,
    RedactionProfile,
    ReplayStatus,
    SubjectScopeType,
    create_canonical_ledger_entry,
    materiality_for,
    verify_integrity_hash,
)
from app.mock_registration.models import IntentLifecycle, ValidationStatus
from app.mock_registration.replay_artifact import (
    P6ReplayArtifactV1, P6ReplayArtifactError, verify_p6_replay_artifact,
)
from app.mock_registration_persistence.models import PersistedIntentRevision

from .errors import DecisionTraceErrorCode, DecisionTracePersistenceError


_EVENT_TYPE = "MOCK_REGISTRATION_SUBMIT"
_SNAPSHOT_CONTRACT_VERSION = "1.0"
_P6_ACTOR_CLASS = "STUDENT_AUTHENTICATED"
_SOURCE_ENGINE = "P6_MOCK_REGISTRATION_VALIDATION"
_LIMITATIONS = (
    "NON_BINDING_DECLARED_INTENT_NOT_OFFICIAL_REGISTRATION",
    "P6_HISTORICAL_REPLAY_NOT_AVAILABLE",
)
_SNAPSHOT_KEYS = frozenset(
    {
        "revision_id",
        "intent_id",
        "owner_user_id",
        "university_id",
        "major_id",
        "study_plan_id",
        "study_plan_version",
        "target_period_id",
        "revision",
        "lifecycle_status",
        "validation_status",
        "content_fingerprint",
        "intent_provenance",
        "intent_source_version",
        "validation_reason_codes",
        "catalog_source_versions",
        "prerequisite_source_versions",
        "progress_state_version",
        "progress_state_reference",
        "phase5_policy_version",
        "phase6_policy_version",
        "p6_contract_version",
        "target_period_source_version",
        "transparency_notice_version",
        "actor_class",
        "created_at",
        "courses",
    }
)


@dataclass(frozen=True, slots=True)
class P6DecisionTraceOutboxEvent:
    """The immutable source portion of one P6 outbox event; no processing authority."""

    event_id: UUID
    revision_id: UUID
    owner_user_id: UUID
    university_id: UUID
    major_id: UUID
    study_plan_id: UUID
    study_plan_version: str
    target_period_id: UUID
    revision: int
    event_type: str
    snapshot_contract_version: str
    source_snapshot: Mapping[str, Any]
    processing_state: str


@dataclass(frozen=True, slots=True)
class TrustedP6OutboxProjection:
    """Typed result of a future trusted, bounded server-side P6 projection.

    ``outbox_required`` comes from the immutable parent row, not client input.
    The mapper verifies all cross-record invariants again before constructing a
    P8 entry.  This type is intentionally not a transport model.
    """

    revision: PersistedIntentRevision
    outbox_required: bool
    outbox_event: P6DecisionTraceOutboxEvent | None
    replay_artifact: P6ReplayArtifactV1 | None = None


def map_verified_mock_registration_submit(
    projection: TrustedP6OutboxProjection,
) -> CanonicalLedgerEntry:
    """Map one eligibility-verified P6 submit event without persistence.

    The caller cannot supply a ledger entry, hash, actor, provenance, outcome,
    or evidence.  Every P8 value is derived here only after the immutable P6
    parent/event/snapshot consistency gate passes.
    """

    if not isinstance(projection, TrustedP6OutboxProjection):
        _reject("trusted P6 outbox projection is required")

    revision = projection.revision
    event = projection.outbox_event
    if not projection.outbox_required:
        _reject("legacy or unverified P6 revision is not eligible")
    if revision.lifecycle_status is not IntentLifecycle.SUBMITTED:
        _reject("only submitted P6 revisions are eligible")
    if revision.validation_status not in {
        ValidationStatus.VALID,
        ValidationStatus.REVIEW_REQUIRED,
    }:
        _reject("unsupported P6 validation status")
    if revision.actor_class != _P6_ACTOR_CLASS:
        _reject("unsupported P6 actor class")
    if event is None:
        _reject("required P6 outbox event is missing")
    _validate_event_and_snapshot(revision, event)

    artifact = projection.replay_artifact
    if artifact is not None:
        try:
            payload = verify_p6_replay_artifact(artifact)
            if (
                payload["intent"]["owner_scope_id"] != str(revision.owner_user_id)
                or payload["intent"]["university_id"] != str(revision.university_id)
                or payload["intent"]["major_id"] != str(revision.major_id)
                or payload["intent"]["study_plan_id"] != str(revision.study_plan_id)
                or payload["intent"]["study_plan_version"] != revision.study_plan_version
                or tuple(payload["context"]["source_versions"]) != revision.catalog_source_versions
                or tuple(payload["context"]["source_versions"]) != revision.prerequisite_source_versions
                or tuple(payload["context"]["engine_policy_versions"][:2]) != (
                    revision.phase5_policy_version, revision.phase6_policy_version)
                or payload["historical_output"]["status"] != revision.validation_status.value
                or tuple(payload["historical_output"]["reason_codes"]) != tuple(
                    code.value for code in revision.validation_reason_codes)
                or payload["historical_output"]["content_fingerprint"] != revision.content_fingerprint
                or tuple(payload["historical_output"]["canonical_course_codes"]) != tuple(
                    course.course_code for course in revision.courses)
            ):
                _reject("replay artifact does not match immutable P6 revision")
        except (P6ReplayArtifactError, KeyError, TypeError) as exc:
            _reject("replay artifact integrity failure")

    decision_status = {
        ValidationStatus.VALID: DecisionStatus.VALIDATED,
        ValidationStatus.REVIEW_REQUIRED: DecisionStatus.FLAGGED_REVIEW,
    }[revision.validation_status]
    evidence = (
        EvidenceReference(
            source="P6_INTENT_COURSE_SET",
            identifier=str(revision.revision_id),
            version=revision.p6_contract_version,
            locator=None,
            uri=None,
        ),
        EvidenceReference(
            source="P6_INTENT_REVISION",
            identifier=str(revision.revision_id),
            version=revision.p6_contract_version,
            locator=None,
            uri=None,
        ),
        EvidenceReference(
            source="P6_TARGET_PERIOD",
            identifier=str(revision.target_period_id),
            version=revision.target_period_source_version,
            locator=None,
            uri=None,
        ),
    )
    if artifact is not None:
        evidence += (EvidenceReference(
            source="P6_REPLAY_ARTIFACT", identifier=str(revision.revision_id),
            version=artifact.replay_contract_version, locator=None, uri=None,
        ),)
    entry = create_canonical_ledger_entry(
        ledger_entry_id=str(revision.revision_id),
        decision_type=DecisionType.MOCK_REGISTRATION_SUBMIT,
        materiality_class=materiality_for(DecisionType.MOCK_REGISTRATION_SUBMIT),
        actor_class=ActorClass.STUDENT,
        actor_id=str(revision.owner_user_id),
        subject_scope_type=SubjectScopeType.STUDENT_INDIVIDUAL,
        subject_scope_id=str(revision.owner_user_id),
        university_id=str(revision.university_id),
        student_user_id=str(revision.owner_user_id),
        source_engine=_SOURCE_ENGINE,
        source_engine_version=revision.p6_contract_version,
        policy_version=revision.phase6_policy_version,
        source_versions=_source_versions(revision),
        input_state_reference=revision.progress_state_reference,
        scenario_id=None,
        decision_status=decision_status,
        outcome_reference=(
            f"P6_NON_BINDING_INTENT:{revision.revision_id}:"
            f"{revision.validation_status.value}:{revision.content_fingerprint}"
        ),
        evidence_references=evidence,
        domain_trace_reference=None,
        provenance_class=ProvenanceClass.AUTHORITATIVE_TRANSACTION,
        created_at=_require_utc(revision.created_at, "revision created_at"),
        redaction_profile=RedactionProfile.STUDENT_SAFE,
        previous_entry_hash=None,
        supersedes_entry_id=None,
        replay_status=(ReplayStatus.REPLAYABLE_EXACT if artifact is not None
                       else ReplayStatus.NOT_REPLAYABLE),
        limitations=(("NON_BINDING_DECLARED_INTENT_NOT_OFFICIAL_REGISTRATION",)
                     if artifact is not None else _LIMITATIONS),
    )
    if verify_integrity_hash(entry) is not IntegrityStatus.VERIFIED:
        _reject("Slice 1 canonical hash construction failed")
    expected_sources = ("P6_INTENT_COURSE_SET", "P6_INTENT_REVISION", "P6_TARGET_PERIOD")
    if artifact is not None:
        expected_sources = tuple(sorted((*expected_sources, "P6_REPLAY_ARTIFACT")))
    if tuple(item.source for item in entry.evidence_references) != expected_sources:
        _reject("unexpected canonical evidence order")
    return entry


def _validate_event_and_snapshot(
    revision: PersistedIntentRevision, event: P6DecisionTraceOutboxEvent
) -> None:
    if event.event_id != revision.revision_id or event.revision_id != revision.revision_id:
        _reject("outbox identity does not match P6 revision")
    if event.event_type != _EVENT_TYPE:
        _reject("unsupported P6 outbox event type")
    if event.snapshot_contract_version != _SNAPSHOT_CONTRACT_VERSION:
        _reject("unsupported P6 outbox snapshot contract")
    if (
        event.owner_user_id != revision.owner_user_id
        or event.university_id != revision.university_id
        or event.major_id != revision.major_id
        or event.study_plan_id != revision.study_plan_id
        or event.study_plan_version != revision.study_plan_version
        or event.target_period_id != revision.target_period_id
        or event.revision != revision.revision
    ):
        _reject("outbox scope does not match P6 revision")
    snapshot = event.source_snapshot
    if not isinstance(snapshot, Mapping) or set(snapshot) != _SNAPSHOT_KEYS:
        _reject("P6 outbox snapshot shape is not exact")
    expected = _expected_snapshot(revision)
    if not _snapshot_matches(expected, snapshot):
        _reject("P6 outbox snapshot does not reconstruct immutable source facts")


def _expected_snapshot(revision: PersistedIntentRevision) -> dict[str, Any]:
    ordered_courses = tuple(sorted(revision.courses, key=lambda item: item.selection_order))
    if ordered_courses != revision.courses or tuple(
        item.selection_order for item in ordered_courses
    ) != tuple(range(1, len(ordered_courses) + 1)):
        _reject("P6 courses are not canonical ordered immutable source facts")
    return {
        "revision_id": str(revision.revision_id),
        "intent_id": str(revision.intent_id),
        "owner_user_id": str(revision.owner_user_id),
        "university_id": str(revision.university_id),
        "major_id": str(revision.major_id),
        "study_plan_id": str(revision.study_plan_id),
        "study_plan_version": revision.study_plan_version,
        "target_period_id": str(revision.target_period_id),
        "revision": revision.revision,
        "lifecycle_status": revision.lifecycle_status.value,
        "validation_status": revision.validation_status.value,
        "content_fingerprint": revision.content_fingerprint,
        "intent_provenance": revision.intent_provenance.value,
        "intent_source_version": revision.intent_source_version,
        "validation_reason_codes": [item.value for item in revision.validation_reason_codes],
        "catalog_source_versions": list(revision.catalog_source_versions),
        "prerequisite_source_versions": list(revision.prerequisite_source_versions),
        "progress_state_version": revision.progress_state_version,
        "progress_state_reference": revision.progress_state_reference,
        "phase5_policy_version": revision.phase5_policy_version,
        "phase6_policy_version": revision.phase6_policy_version,
        "p6_contract_version": revision.p6_contract_version,
        "target_period_source_version": revision.target_period_source_version,
        "transparency_notice_version": revision.transparency_notice_version,
        "actor_class": revision.actor_class,
        "created_at": _require_utc(revision.created_at, "revision created_at"),
        "courses": [
            {
                "course_id": str(item.course_id),
                "course_code": item.course_code,
                "selection_order": item.selection_order,
            }
            for item in ordered_courses
        ],
    }


def _snapshot_matches(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if key == "created_at":
            try:
                if _parse_snapshot_timestamp(actual_value) != expected_value:
                    return False
            except (TypeError, ValueError):
                return False
        elif actual_value != expected_value:
            return False
    return True


def _source_versions(revision: PersistedIntentRevision) -> tuple[str, ...]:
    values = (
        revision.study_plan_version,
        revision.intent_source_version,
        *revision.catalog_source_versions,
        *revision.prerequisite_source_versions,
        revision.progress_state_version,
        revision.phase5_policy_version,
        revision.phase6_policy_version,
        revision.p6_contract_version,
        revision.target_period_source_version,
        revision.transparency_notice_version,
    )
    if any(not isinstance(value, str) or not value.strip() for value in values):
        _reject("required immutable P6 source version is missing")
    return tuple(values)


def _require_utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        _reject(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_snapshot_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise TypeError("snapshot timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("snapshot timestamp")
    return parsed.astimezone(timezone.utc)


def _reject(message: str) -> None:
    raise DecisionTracePersistenceError(DecisionTraceErrorCode.INTEGRITY_FAILURE, message)
