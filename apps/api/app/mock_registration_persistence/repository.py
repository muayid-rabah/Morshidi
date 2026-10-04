"""Server-key Supabase adapter for P6.4 persistence primitives only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx

from app.mock_registration.models import (
    IntentLifecycle,
    IntentProvenance,
    TargetPeriodClass,
    ValidationStatus,
)
from app.mock_registration.registries import ReasonCode

from .errors import (
    MockRegistrationPersistenceError,
    MockRegistrationPersistenceIntegrityError,
    PersistenceFailureCode,
)
from .models import (
    InstitutionalMembershipRecord,
    PersistRevisionCommand,
    PersistRevisionResult,
    PersistenceResultKind,
    PersistedIntentCourse,
    PersistedIntentRevision,
    PersistedTargetPeriod,
)

_REVISION_SELECT = (
    "id,intent_id,owner_user_id,university_id,major_id,study_plan_id,"
    "study_plan_version,target_period_id,revision,lifecycle_status,"
    "validation_status,content_fingerprint,intent_provenance,"
    "intent_source_version,validation_reason_codes,catalog_source_versions,"
    "prerequisite_source_versions,progress_state_version,"
    "progress_state_reference,phase5_policy_version,phase6_policy_version,"
    "p6_contract_version,target_period_source_version,"
    "transparency_notice_version,transparency_acknowledged_at,actor_class,"
    "created_at,mock_registration_intent_courses(course_id,course_code,selection_order)"
)


class SupabaseMockRegistrationRepository:
    """Exact-scope persistence adapter with no academic or authorization policy."""

    def __init__(
        self,
        supabase_url: str,
        server_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not supabase_url.strip() or not server_key.strip():
            raise ValueError("supabase_url and server_key must not be empty")
        self._rest_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._server_key = server_key
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def persist_revision(self, command: PersistRevisionCommand) -> PersistRevisionResult:
        body = {
            "p_intent_id": str(command.intent_id),
            "p_owner_user_id": str(command.owner_user_id),
            "p_university_id": str(command.university_id),
            "p_major_id": str(command.major_id),
            "p_study_plan_id": str(command.study_plan_id),
            "p_study_plan_version": command.study_plan_version,
            "p_target_period_id": str(command.target_period_id),
            "p_expected_current_revision": command.expected_current_revision,
            "p_lifecycle_status": command.lifecycle_status.value,
            "p_validation_status": command.validation_status.value,
            "p_content_fingerprint": command.content_fingerprint,
            "p_intent_provenance": command.intent_provenance.value,
            "p_intent_source_version": command.intent_source_version,
            "p_validation_reason_codes": [item.value for item in command.validation_reason_codes],
            "p_catalog_source_versions": list(command.catalog_source_versions),
            "p_prerequisite_source_versions": list(command.prerequisite_source_versions),
            "p_progress_state_version": command.progress_state_version,
            "p_progress_state_reference": command.progress_state_reference,
            "p_phase5_policy_version": command.phase5_policy_version,
            "p_phase6_policy_version": command.phase6_policy_version,
            "p_p6_contract_version": command.p6_contract_version,
            "p_target_period_source_version": command.target_period_source_version,
            "p_transparency_notice_version": command.transparency_notice_version,
            "p_actor_class": command.actor_class,
            "p_course_ids": [str(item) for item in command.course_ids],
            "p_course_codes": list(command.course_codes),
        }
        resource = "rpc/persist_mock_registration_revision"
        if command.replay_artifact is not None:
            artifact = command.replay_artifact
            body.update({
                "p_replay_canonical_payload": artifact.canonical_payload,
                "p_replay_canonical_sha256": artifact.canonical_sha256,
                "p_replay_source_versions": list(artifact.source_versions),
            })
            resource = "rpc/persist_mock_registration_revision_with_replay"
        response = await self._request("POST", resource, json=body)
        self._require_success(response, "persist revision")
        rows = _rows(response, "persist revision")
        if len(rows) != 1:
            raise MockRegistrationPersistenceIntegrityError("persist revision result")
        row = rows[0]
        try:
            kind = PersistenceResultKind(_text(row, "result_kind"))
        except ValueError as error:
            raise MockRegistrationPersistenceIntegrityError("persist revision result") from error
        return PersistRevisionResult(
            kind=kind,
            revision_id=_optional_uuid(row.get("persisted_revision_id")),
            revision=_optional_positive_int(row.get("persisted_revision")),
            content_fingerprint=_optional_text(row.get("persisted_fingerprint")),
        )

    async def load_target_period(
        self, target_period_id: UUID, university_id: UUID
    ) -> PersistedTargetPeriod:
        rows = await self._get_rows(
            "mock_registration_target_periods",
            {
                "select": "*",
                "id": f"eq.{target_period_id}",
                "university_id": f"eq.{university_id}",
            },
        )
        if not rows:
            raise MockRegistrationPersistenceError(
                PersistenceFailureCode.RESOURCE_NOT_FOUND, "load target period"
            )
        if len(rows) != 1:
            raise MockRegistrationPersistenceIntegrityError("load target period")
        return _target_period(rows[0])

    async def load_revision_history(
        self,
        *,
        owner_user_id: UUID,
        university_id: UUID,
        major_id: UUID,
        study_plan_id: UUID,
        study_plan_version: str,
        target_period_id: UUID,
    ) -> tuple[PersistedIntentRevision, ...]:
        rows = await self._get_rows(
            "mock_registration_intent_revisions",
            {
                "select": _REVISION_SELECT,
                "owner_user_id": f"eq.{owner_user_id}",
                "university_id": f"eq.{university_id}",
                "major_id": f"eq.{major_id}",
                "study_plan_id": f"eq.{study_plan_id}",
                "study_plan_version": f"eq.{study_plan_version}",
                "target_period_id": f"eq.{target_period_id}",
                "order": "revision.asc",
            },
        )
        return tuple(_revision(row) for row in rows)

    async def load_revision_by_id(self, revision_id: UUID) -> PersistedIntentRevision | None:
        """Internal audit lookup; never exposed as a browser endpoint."""
        rows = await self._get_rows("mock_registration_intent_revisions", {
            "select": _REVISION_SELECT, "id": f"eq.{revision_id}", "limit": "2",
        })
        if len(rows) > 1:
            raise MockRegistrationPersistenceIntegrityError("load revision by id")
        return _revision(rows[0]) if rows else None

    async def load_institution_period_candidates(
        self,
        *,
        university_id: UUID,
        target_period_id: UUID,
        study_plan_id: UUID | None = None,
    ) -> tuple[PersistedIntentRevision, ...]:
        params = {
            "select": _REVISION_SELECT,
            "university_id": f"eq.{university_id}",
            "target_period_id": f"eq.{target_period_id}",
            "order": "owner_user_id.asc,revision.asc",
        }
        if study_plan_id is not None:
            params["study_plan_id"] = f"eq.{study_plan_id}"
        rows = await self._get_rows("mock_registration_intent_revisions", params)
        return tuple(_revision(row) for row in rows)

    async def load_active_membership(
        self,
        *,
        subject_user_id: UUID,
        university_id: UUID,
        role: str = "INSTITUTIONAL_ANALYST",
    ) -> InstitutionalMembershipRecord:
        rows = await self._get_rows(
            "institutional_memberships",
            {
                "select": "*",
                "subject_user_id": f"eq.{subject_user_id}",
                "university_id": f"eq.{university_id}",
                "role": f"eq.{role}",
                "active": "eq.true",
            },
        )
        if not rows:
            raise MockRegistrationPersistenceError(
                PersistenceFailureCode.RESOURCE_NOT_FOUND, "load institutional membership"
            )
        if len(rows) != 1:
            raise MockRegistrationPersistenceIntegrityError("load institutional membership")
        return _membership(rows[0])

    async def load_active_memberships_for_user(
        self,
        *,
        subject_user_id: UUID,
        role: str = "INSTITUTIONAL_ANALYST",
    ) -> tuple[InstitutionalMembershipRecord, ...]:
        rows = await self._get_rows(
            "institutional_memberships",
            {
                "select": "*",
                "subject_user_id": f"eq.{subject_user_id}",
                "role": f"eq.{role}",
                "active": "eq.true",
            },
        )
        return tuple(_membership(row) for row in rows)

    async def _get_rows(
        self, resource: str, params: Mapping[str, str]
    ) -> list[Mapping[str, Any]]:
        response = await self._request("GET", resource, params=params)
        self._require_success(response, f"load {resource}")
        return _rows(response, resource)

    async def _request(
        self,
        method: str,
        resource: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            return await self._client.request(
                method,
                f"{self._rest_url}/{resource}",
                params=params,
                json=json,
                headers={
                    "apikey": self._server_key,
                    "Authorization": f"Bearer {self._server_key}",
                    "Accept": "application/json",
                    "Prefer": "return=representation",
                },
            )
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise MockRegistrationPersistenceError(
                PersistenceFailureCode.PERSISTENCE_UNAVAILABLE, resource
            ) from error

    @staticmethod
    def _require_success(response: httpx.Response, operation: str) -> None:
        if 200 <= response.status_code < 300:
            return
        code = _postgrest_code(response)
        failure = (
            PersistenceFailureCode.PERSISTENCE_CONFLICT
            if code in {"23503", "23505", "23514"}
            else PersistenceFailureCode.PERSISTENCE_UNAVAILABLE
        )
        raise MockRegistrationPersistenceError(failure, operation)


def _rows(response: httpx.Response, operation: str) -> list[Mapping[str, Any]]:
    try:
        value = response.json()
    except ValueError as error:
        raise MockRegistrationPersistenceIntegrityError(operation) from error
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise MockRegistrationPersistenceIntegrityError(operation)
    return list(value)


def _postgrest_code(response: httpx.Response) -> str | None:
    try:
        value = response.json()
    except ValueError:
        return None
    return value.get("code") if isinstance(value, Mapping) else None


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise MockRegistrationPersistenceIntegrityError(f"map {key}")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise MockRegistrationPersistenceIntegrityError("map optional text")
    return value


def _uuid(row: Mapping[str, Any], key: str) -> UUID:
    try:
        return UUID(_text(row, key))
    except ValueError as error:
        raise MockRegistrationPersistenceIntegrityError(f"map {key}") from error


def _optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError as error:
        raise MockRegistrationPersistenceIntegrityError("map optional UUID") from error


def _positive_int(row: Mapping[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MockRegistrationPersistenceIntegrityError(f"map {key}")
    return value


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MockRegistrationPersistenceIntegrityError("map optional revision")
    return value


def _datetime(row: Mapping[str, Any], key: str) -> datetime:
    value = _text(row, key)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MockRegistrationPersistenceIntegrityError(f"map {key}") from error


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MockRegistrationPersistenceIntegrityError("map optional datetime")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MockRegistrationPersistenceIntegrityError("map optional datetime") from error


def _text_tuple(row: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = row.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise MockRegistrationPersistenceIntegrityError(f"map {key}")
    if not all(isinstance(item, str) and item for item in value):
        raise MockRegistrationPersistenceIntegrityError(f"map {key}")
    return tuple(value)


def _target_period(row: Mapping[str, Any]) -> PersistedTargetPeriod:
    try:
        period_class = TargetPeriodClass(_text(row, "period_class"))
    except ValueError as error:
        raise MockRegistrationPersistenceIntegrityError("map target period") from error
    if not isinstance(row.get("verified_provider_source"), bool) or not isinstance(row.get("is_expired"), bool):
        raise MockRegistrationPersistenceIntegrityError("map target period booleans")
    return PersistedTargetPeriod(
        target_period_id=_uuid(row, "id"),
        university_id=_uuid(row, "university_id"),
        provider_namespace=_text(row, "provider_namespace"),
        period_key=_text(row, "period_key"),
        period_class=period_class,
        verified_provider_source=row["verified_provider_source"],
        source_version=_text(row, "source_version"),
        is_expired=row["is_expired"],
        expiration_source_version=_optional_text(row.get("expiration_source_version")),
        expired_at=_optional_datetime(row.get("expired_at")),
        created_at=_datetime(row, "created_at"),
        updated_at=_datetime(row, "updated_at"),
    )


def _revision(row: Mapping[str, Any]) -> PersistedIntentRevision:
    try:
        lifecycle = IntentLifecycle(_text(row, "lifecycle_status"))
        validation = ValidationStatus(_text(row, "validation_status"))
        provenance = IntentProvenance(_text(row, "intent_provenance"))
        reasons = tuple(ReasonCode(item) for item in _text_tuple(row, "validation_reason_codes"))
    except ValueError as error:
        raise MockRegistrationPersistenceIntegrityError("map revision enums") from error
    raw_courses = row.get("mock_registration_intent_courses")
    if not isinstance(raw_courses, Sequence) or isinstance(raw_courses, (str, bytes)):
        raise MockRegistrationPersistenceIntegrityError("map revision courses")
    courses = tuple(sorted((_course(item) for item in raw_courses if isinstance(item, Mapping)), key=lambda item: item.selection_order))
    if len(courses) != len(raw_courses):
        raise MockRegistrationPersistenceIntegrityError("map revision courses")
    return PersistedIntentRevision(
        revision_id=_uuid(row, "id"), intent_id=_uuid(row, "intent_id"),
        owner_user_id=_uuid(row, "owner_user_id"), university_id=_uuid(row, "university_id"),
        major_id=_uuid(row, "major_id"), study_plan_id=_uuid(row, "study_plan_id"),
        study_plan_version=_text(row, "study_plan_version"),
        target_period_id=_uuid(row, "target_period_id"), revision=_positive_int(row, "revision"),
        lifecycle_status=lifecycle, validation_status=validation,
        content_fingerprint=_text(row, "content_fingerprint"), intent_provenance=provenance,
        intent_source_version=_text(row, "intent_source_version"), validation_reason_codes=reasons,
        catalog_source_versions=_text_tuple(row, "catalog_source_versions"),
        prerequisite_source_versions=_text_tuple(row, "prerequisite_source_versions"),
        progress_state_version=_text(row, "progress_state_version"),
        progress_state_reference=_optional_text(row.get("progress_state_reference")),
        phase5_policy_version=_text(row, "phase5_policy_version"),
        phase6_policy_version=_text(row, "phase6_policy_version"),
        p6_contract_version=_text(row, "p6_contract_version"),
        target_period_source_version=_text(row, "target_period_source_version"),
        transparency_notice_version=_text(row, "transparency_notice_version"),
        transparency_acknowledged_at=_datetime(row, "transparency_acknowledged_at"),
        actor_class=_text(row, "actor_class"), created_at=_datetime(row, "created_at"),
        courses=courses,
    )


def _course(row: Mapping[str, Any]) -> PersistedIntentCourse:
    return PersistedIntentCourse(
        course_id=_uuid(row, "course_id"),
        course_code=_text(row, "course_code"),
        selection_order=_positive_int(row, "selection_order"),
    )


def _membership(row: Mapping[str, Any]) -> InstitutionalMembershipRecord:
    if row.get("active") is not True or _text(row, "role") != "INSTITUTIONAL_ANALYST":
        raise MockRegistrationPersistenceIntegrityError("map institutional membership")
    return InstitutionalMembershipRecord(
        membership_id=_uuid(row, "id"), subject_user_id=_uuid(row, "subject_user_id"),
        university_id=_uuid(row, "university_id"),
        provider_namespace=_text(row, "provider_namespace"), role=_text(row, "role"),
        active=True, authority_source=_text(row, "authority_source"),
        authority_source_version=_text(row, "authority_source_version"),
        created_at=_datetime(row, "created_at"), updated_at=_datetime(row, "updated_at"),
    )
