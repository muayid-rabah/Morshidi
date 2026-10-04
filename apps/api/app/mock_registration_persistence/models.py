"""Typed P6.4 persistence records, separate from transport and domain policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.mock_registration.replay_artifact import P6ReplayArtifactV1

from app.mock_registration.models import (
    IntentLifecycle,
    IntentProvenance,
    TargetPeriodClass,
    ValidationStatus,
)
from app.mock_registration.registries import ReasonCode


class PersistenceResultKind(str, Enum):
    INSERTED = "INSERTED"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"


@dataclass(frozen=True)
class PersistedTargetPeriod:
    target_period_id: UUID
    university_id: UUID
    provider_namespace: str
    period_key: str
    period_class: TargetPeriodClass
    verified_provider_source: bool
    source_version: str
    is_expired: bool
    expiration_source_version: str | None
    expired_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PersistRevisionCommand:
    intent_id: UUID
    owner_user_id: UUID
    university_id: UUID
    major_id: UUID
    study_plan_id: UUID
    study_plan_version: str
    target_period_id: UUID
    expected_current_revision: int | None
    lifecycle_status: IntentLifecycle
    validation_status: ValidationStatus
    content_fingerprint: str
    intent_provenance: IntentProvenance
    intent_source_version: str
    validation_reason_codes: tuple[ReasonCode, ...]
    catalog_source_versions: tuple[str, ...]
    prerequisite_source_versions: tuple[str, ...]
    progress_state_version: str
    progress_state_reference: str | None
    phase5_policy_version: str
    phase6_policy_version: str
    p6_contract_version: str
    target_period_source_version: str
    transparency_notice_version: str
    actor_class: str
    course_ids: tuple[UUID, ...]
    course_codes: tuple[str, ...]
    replay_artifact: P6ReplayArtifactV1 | None = None


@dataclass(frozen=True)
class PersistRevisionResult:
    kind: PersistenceResultKind
    revision_id: UUID | None
    revision: int | None
    content_fingerprint: str | None


@dataclass(frozen=True)
class PersistedIntentCourse:
    course_id: UUID
    course_code: str
    selection_order: int


@dataclass(frozen=True)
class PersistedIntentRevision:
    revision_id: UUID
    intent_id: UUID
    owner_user_id: UUID
    university_id: UUID
    major_id: UUID
    study_plan_id: UUID
    study_plan_version: str
    target_period_id: UUID
    revision: int
    lifecycle_status: IntentLifecycle
    validation_status: ValidationStatus
    content_fingerprint: str
    intent_provenance: IntentProvenance
    intent_source_version: str
    validation_reason_codes: tuple[ReasonCode, ...]
    catalog_source_versions: tuple[str, ...]
    prerequisite_source_versions: tuple[str, ...]
    progress_state_version: str
    progress_state_reference: str | None
    phase5_policy_version: str
    phase6_policy_version: str
    p6_contract_version: str
    target_period_source_version: str
    transparency_notice_version: str
    transparency_acknowledged_at: datetime
    actor_class: str
    created_at: datetime
    courses: tuple[PersistedIntentCourse, ...]


@dataclass(frozen=True)
class InstitutionalMembershipRecord:
    membership_id: UUID
    subject_user_id: UUID
    university_id: UUID
    provider_namespace: str
    role: str
    active: bool
    authority_source: str
    authority_source_version: str
    created_at: datetime
    updated_at: datetime
