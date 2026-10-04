"""Unit coverage for the internal, non-persisting P6 outbox-to-P8 mapper."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.decision_trace import DecisionStatus, canonical_ledger_payload, verify_integrity_hash
from app.decision_trace_persistence import (
    DecisionTraceErrorCode,
    DecisionTracePersistenceError,
    P6DecisionTraceOutboxEvent,
    TrustedP6OutboxProjection,
    map_verified_mock_registration_submit,
)
from app.mock_registration.models import IntentLifecycle, IntentProvenance, ValidationStatus
from app.mock_registration.registries import ReasonCode
from app.mock_registration_persistence.models import PersistedIntentCourse, PersistedIntentRevision


def _revision(**changes: object) -> PersistedIntentRevision:
    values: dict[str, object] = {
        "revision_id": UUID("00000000-0000-0000-0000-000000000101"),
        "intent_id": UUID("00000000-0000-0000-0000-000000000102"),
        "owner_user_id": UUID("00000000-0000-0000-0000-000000000103"),
        "university_id": UUID("00000000-0000-0000-0000-000000000104"),
        "major_id": UUID("00000000-0000-0000-0000-000000000105"),
        "study_plan_id": UUID("00000000-0000-0000-0000-000000000106"),
        "study_plan_version": "plan12:v7",
        "target_period_id": UUID("00000000-0000-0000-0000-000000000107"),
        "revision": 3,
        "lifecycle_status": IntentLifecycle.SUBMITTED,
        "validation_status": ValidationStatus.VALID,
        "content_fingerprint": "a" * 64,
        "intent_provenance": IntentProvenance.DECLARED_STUDENT_INTENT,
        "intent_source_version": "intent:v2",
        "validation_reason_codes": (ReasonCode.MOCK_REG_ELIGIBILITY_REVIEW_REQUIRED,),
        "catalog_source_versions": ("catalog:z", "catalog:a"),
        "prerequisite_source_versions": ("prereq:v3",),
        "progress_state_version": "progress:v9",
        "progress_state_reference": "progress-state:opaque",
        "phase5_policy_version": "phase5:v1",
        "phase6_policy_version": "phase6:v1",
        "p6_contract_version": "1.0",
        "target_period_source_version": "period:v1",
        "transparency_notice_version": "notice:v1",
        "transparency_acknowledged_at": datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
        "actor_class": "STUDENT_AUTHENTICATED",
        "created_at": datetime(2026, 9, 25, 12, 1, 2, 123456, tzinfo=timezone.utc),
        "courses": (
            PersistedIntentCourse(UUID("00000000-0000-0000-0000-000000000108"), "AI101", 1),
            PersistedIntentCourse(UUID("00000000-0000-0000-0000-000000000109"), "AI201", 2),
        ),
    }
    values.update(changes)
    return PersistedIntentRevision(**values)  # type: ignore[arg-type]


def _snapshot(revision: PersistedIntentRevision) -> dict[str, object]:
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
        "created_at": revision.created_at.isoformat(),
        "courses": [
            {
                "course_id": str(course.course_id),
                "course_code": course.course_code,
                "selection_order": course.selection_order,
            }
            for course in revision.courses
        ],
    }


def _projection(
    revision: PersistedIntentRevision | None = None, **event_changes: object
) -> TrustedP6OutboxProjection:
    revision = revision or _revision()
    event_values: dict[str, object] = {
        "event_id": revision.revision_id,
        "revision_id": revision.revision_id,
        "owner_user_id": revision.owner_user_id,
        "university_id": revision.university_id,
        "major_id": revision.major_id,
        "study_plan_id": revision.study_plan_id,
        "study_plan_version": revision.study_plan_version,
        "target_period_id": revision.target_period_id,
        "revision": revision.revision,
        "event_type": "MOCK_REGISTRATION_SUBMIT",
        "snapshot_contract_version": "1.0",
        "source_snapshot": _snapshot(revision),
        "processing_state": "PENDING",
    }
    event_values.update(event_changes)
    return TrustedP6OutboxProjection(
        revision=revision,
        outbox_required=True,
        outbox_event=P6DecisionTraceOutboxEvent(**event_values),  # type: ignore[arg-type]
    )


def _integrity_error(callable_object, *args) -> None:
    with pytest.raises(DecisionTracePersistenceError) as failure:
        callable_object(*args)
    assert failure.value.code is DecisionTraceErrorCode.INTEGRITY_FAILURE


def test_maps_every_approved_field_and_canonical_hash_from_verified_projection() -> None:
    revision = _revision()
    entry = map_verified_mock_registration_submit(_projection(revision))

    assert entry.ledger_entry_id == str(revision.revision_id)
    assert entry.actor_id == entry.subject_scope_id == entry.student_user_id == str(revision.owner_user_id)
    assert entry.university_id == str(revision.university_id)
    assert entry.source_engine == "P6_MOCK_REGISTRATION_VALIDATION"
    assert entry.source_engine_version == revision.p6_contract_version
    assert entry.policy_version == revision.phase6_policy_version
    assert entry.decision_status is DecisionStatus.VALIDATED
    assert entry.outcome_reference == f"P6_NON_BINDING_INTENT:{revision.revision_id}:VALID:{revision.content_fingerprint}"
    assert entry.created_at == revision.created_at
    assert entry.replay_status.value == "NOT_REPLAYABLE"
    assert entry.limitations == tuple(sorted((
        "NON_BINDING_DECLARED_INTENT_NOT_OFFICIAL_REGISTRATION",
        "P6_HISTORICAL_REPLAY_NOT_AVAILABLE",
    )))
    assert tuple(reference.source for reference in entry.evidence_references) == (
        "P6_INTENT_COURSE_SET", "P6_INTENT_REVISION", "P6_TARGET_PERIOD"
    )
    assert all(reference.locator is None and reference.uri is None for reference in entry.evidence_references)
    assert verify_integrity_hash(entry)


def test_review_required_maps_only_to_flagged_review_and_source_versions_are_canonical() -> None:
    revision = _revision(validation_status=ValidationStatus.REVIEW_REQUIRED)
    entry = map_verified_mock_registration_submit(_projection(revision))
    assert entry.decision_status is DecisionStatus.FLAGGED_REVIEW
    assert entry.source_versions == tuple(sorted(set((
        "plan12:v7", "intent:v2", "catalog:z", "catalog:a", "prereq:v3", "progress:v9",
        "phase5:v1", "phase6:v1", "1.0", "period:v1", "notice:v1",
    ))))


@pytest.mark.parametrize(
    ("projection", "description"),
    [
        (_projection(), "control"),
        (_projection(_revision(lifecycle_status=IntentLifecycle.WITHDRAWN)), "lifecycle"),
        (_projection(_revision(validation_status=ValidationStatus.INVALID)), "validation"),
        (_projection(_revision(actor_class="SYSTEM_ENGINE")), "actor"),
        (_projection(snapshot_contract_version="2.0"), "contract"),
        (_projection(event_type="MOCK_REGISTRATION_WITHDRAW"), "event"),
        (_projection(event_id=UUID("00000000-0000-0000-0000-000000000199")), "identity"),
    ],
)
def test_rejects_ineligible_or_mismatched_projection(projection, description: str) -> None:
    if description == "control":
        legacy = replace(projection, outbox_required=False)
        _integrity_error(map_verified_mock_registration_submit, legacy)
    else:
        _integrity_error(map_verified_mock_registration_submit, projection)


def test_rejects_missing_or_non_reconstructible_event_snapshot() -> None:
    projection = _projection()
    _integrity_error(map_verified_mock_registration_submit, replace(projection, outbox_event=None))
    assert projection.outbox_event is not None
    altered = dict(projection.outbox_event.source_snapshot)
    altered["content_fingerprint"] = "b" * 64
    _integrity_error(
        map_verified_mock_registration_submit,
        replace(projection, outbox_event=replace(projection.outbox_event, source_snapshot=altered)),
    )


def test_same_immutable_source_has_identical_payload_hash_and_no_entry_argument_path() -> None:
    first = map_verified_mock_registration_submit(_projection())
    second = map_verified_mock_registration_submit(_projection())
    assert canonical_ledger_payload(first) == canonical_ledger_payload(second)
    assert first.integrity_hash == second.integrity_hash
    _integrity_error(map_verified_mock_registration_submit, first)
