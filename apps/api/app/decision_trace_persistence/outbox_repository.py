"""Typed, server-side PostgREST adapter for the bounded P6 outbox processor RPCs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from app.mock_registration.models import (
    IntentLifecycle,
    IntentProvenance,
    ValidationStatus,
)
from app.mock_registration.registries import ReasonCode
from app.mock_registration_persistence.models import (
    PersistedIntentCourse,
    PersistedIntentRevision,
)
from app.mock_registration.replay_artifact import P6ReplayArtifactV1

from .errors import DecisionTraceErrorCode, DecisionTracePersistenceError
from .models import ClaimedOutboxEvent
from .p6_outbox_mapper import P6DecisionTraceOutboxEvent, TrustedP6OutboxProjection


class SupabaseDecisionTraceOutboxRepository:
    """Service-only adapter restricted to bounded outbox RPCs with no raw table writes."""

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

    async def claim_events(
        self,
        *,
        worker_id: str,
        batch_size: int = 10,
        lease_seconds: int = 60,
        university_id: UUID | None = None,
    ) -> tuple[ClaimedOutboxEvent, ...]:
        """Atomically claim a bounded batch of pending or expired-lease outbox events."""
        if not worker_id or not worker_id.strip():
            raise ValueError("worker_id must be nonblank")
        if batch_size < 1 or batch_size > 100:
            raise ValueError("batch_size must be between 1 and 100")
        if lease_seconds < 10 or lease_seconds > 600:
            raise ValueError("lease_seconds must be between 10 and 600")

        body: dict[str, Any] = {
            "p_worker_id": worker_id.strip(),
            "p_batch_size": batch_size,
            "p_lease_seconds": lease_seconds,
            "p_university_id": str(university_id) if university_id else None,
        }
        response = await self._request("POST", "rpc/claim_decision_trace_outbox_events", json=body)
        self._require_success(response, "claim outbox events")
        rows = self._rows(response, "claim outbox events")
        claimed = []
        for row in rows:
            event = self._parse_claimed_event(row)
            artifact = await self.load_replay_artifact(
                revision_id=event.revision_id,
                university_id=event.projection.revision.university_id,
            )
            claimed.append(replace(event, projection=replace(
                event.projection, replay_artifact=artifact,
            )))
        return tuple(claimed)

    async def load_replay_artifact(
        self, *, revision_id: UUID, university_id: UUID,
    ) -> P6ReplayArtifactV1 | None:
        response = await self._request("GET", "p6_submit_replay_artifacts", params={
            "select": "revision_id,university_id,replay_contract_version,engine_id,engine_version,canonical_payload,canonical_sha256,source_versions",
            "revision_id": f"eq.{revision_id}", "university_id": f"eq.{university_id}",
            "limit": "2",
        })
        self._require_success(response, "load replay artifact")
        rows = self._rows(response, "load replay artifact")
        if not rows:
            return None
        if len(rows) != 1:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "replay artifact identity is not unique",
            )
        row = rows[0]
        try:
            if UUID(str(row["revision_id"])) != revision_id or UUID(str(row["university_id"])) != university_id:
                raise ValueError("scope")
            return P6ReplayArtifactV1(
                replay_contract_version=str(row["replay_contract_version"]),
                engine_id=str(row["engine_id"]),
                engine_version=str(row["engine_version"]),
                canonical_payload=str(row["canonical_payload"]),
                canonical_sha256=str(row["canonical_sha256"]),
                source_versions=tuple(row["source_versions"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "replay artifact row is malformed",
            ) from exc

    async def complete_event(
        self,
        *,
        event_id: UUID,
        claim_token: str,
        completed_ledger_integrity_hash: str,
    ) -> None:
        """Mark outbox event completed with verified ledger integrity hash."""
        if not claim_token or not claim_token.strip():
            raise ValueError("claim_token must be nonblank")
        body = {
            "p_event_id": str(event_id),
            "p_claim_token": claim_token.strip(),
            "p_completed_ledger_integrity_hash": completed_ledger_integrity_hash.strip(),
        }
        response = await self._request("POST", "rpc/complete_decision_trace_outbox_event", json=body)
        self._require_success(response, "complete outbox event")

    async def release_event(
        self,
        *,
        event_id: UUID,
        claim_token: str,
        error_class: str = "TRANSIENT_P8_UNAVAILABLE",
        backoff_seconds: int = 30,
        max_attempts: int = 5,
    ) -> None:
        """Release leased outbox event back to PENDING with backoff, or PERMANENT on max attempts."""
        if not claim_token or not claim_token.strip():
            raise ValueError("claim_token must be nonblank")
        body = {
            "p_event_id": str(event_id),
            "p_claim_token": claim_token.strip(),
            "p_error_class": error_class,
            "p_backoff_seconds": backoff_seconds,
            "p_max_attempts": max_attempts,
        }
        response = await self._request("POST", "rpc/release_decision_trace_outbox_event", json=body)
        self._require_success(response, "release outbox event")

    async def fail_event(
        self,
        *,
        event_id: UUID,
        claim_token: str,
        error_class: str,
    ) -> None:
        """Mark outbox event permanently failed closed for unrecoverable errors."""
        if not claim_token or not claim_token.strip():
            raise ValueError("claim_token must be nonblank")
        body = {
            "p_event_id": str(event_id),
            "p_claim_token": claim_token.strip(),
            "p_error_class": error_class,
        }
        response = await self._request("POST", "rpc/fail_decision_trace_outbox_event", json=body)
        self._require_success(response, "fail outbox event")

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
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                },
            )
        except (httpx.RequestError, httpx.TimeoutException) as error:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_UNAVAILABLE,
                f"transport failure during {method} {resource}",
            ) from error

    @staticmethod
    def _require_success(response: httpx.Response, operation: str) -> None:
        if 200 <= response.status_code < 300:
            return
        code = _postgrest_code(response)
        if code == "55000":
            # Stale claim token or invalid state
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.STALE_CLAIM,
                f"{operation} rejected: stale claim token or invalid state",
            )
        failure = (
            DecisionTraceErrorCode.PERSISTENCE_CONFLICT
            if code in {"23503", "23505", "23514"}
            else DecisionTraceErrorCode.PERSISTENCE_UNAVAILABLE
        )
        raise DecisionTracePersistenceError(failure, f"{operation} failed")

    @staticmethod
    def _rows(response: httpx.Response, operation: str) -> list[Mapping[str, Any]]:
        try:
            value = response.json()
        except ValueError as error:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                f"{operation} response is not JSON",
            ) from error
        if isinstance(value, list) and all(isinstance(row, Mapping) for row in value):
            return list(value)
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
            f"{operation} response is not a row array",
        )

    @classmethod
    def _parse_claimed_event(cls, row: Mapping[str, Any]) -> ClaimedOutboxEvent:
        try:
            event_id = UUID(str(row["event_id"]))
            revision_id = UUID(str(row["revision_id"]))
            claim_token = str(row["lease_owner"])
            attempt_count = int(row["attempt_count"])
            lease_expires_at = _utc_datetime(str(row["lease_expires_at"]))
            outbox_required = bool(row["outbox_required"])

            parent_data = row.get("parent_revision_data")
            if not isinstance(parent_data, Mapping):
                raise ValueError("missing parent_revision_data")

            courses = tuple(
                PersistedIntentCourse(
                    course_id=UUID(str(c["course_id"])),
                    course_code=str(c["course_code"]),
                    selection_order=int(c["selection_order"]),
                )
                for c in parent_data.get("courses", [])
            )
            revision = PersistedIntentRevision(
                revision_id=UUID(str(parent_data["id"])),
                intent_id=UUID(str(parent_data["intent_id"])),
                owner_user_id=UUID(str(parent_data["owner_user_id"])),
                university_id=UUID(str(parent_data["university_id"])),
                major_id=UUID(str(parent_data["major_id"])),
                study_plan_id=UUID(str(parent_data["study_plan_id"])),
                study_plan_version=str(parent_data["study_plan_version"]),
                target_period_id=UUID(str(parent_data["target_period_id"])),
                revision=int(parent_data["revision"]),
                lifecycle_status=IntentLifecycle(str(parent_data["lifecycle_status"])),
                validation_status=ValidationStatus(str(parent_data["validation_status"])),
                content_fingerprint=str(parent_data["content_fingerprint"]),
                intent_provenance=IntentProvenance(str(parent_data["intent_provenance"])),
                intent_source_version=str(parent_data["intent_source_version"]),
                validation_reason_codes=tuple(
                    ReasonCode(str(code))
                    for code in parent_data.get("validation_reason_codes", [])
                ),
                catalog_source_versions=tuple(
                    str(v) for v in parent_data.get("catalog_source_versions", [])
                ),
                prerequisite_source_versions=tuple(
                    str(v) for v in parent_data.get("prerequisite_source_versions", [])
                ),
                progress_state_version=str(parent_data["progress_state_version"]),
                progress_state_reference=parent_data.get("progress_state_reference"),
                phase5_policy_version=str(parent_data["phase5_policy_version"]),
                phase6_policy_version=str(parent_data["phase6_policy_version"]),
                p6_contract_version=str(parent_data["p6_contract_version"]),
                target_period_source_version=str(parent_data["target_period_source_version"]),
                transparency_notice_version=str(parent_data["transparency_notice_version"]),
                transparency_acknowledged_at=_utc_datetime(
                    str(parent_data["transparency_acknowledged_at"])
                ),
                actor_class=str(parent_data["actor_class"]),
                created_at=_utc_datetime(str(parent_data["created_at"])),
                courses=courses,
            )

            outbox_event = P6DecisionTraceOutboxEvent(
                event_id=event_id,
                revision_id=revision_id,
                owner_user_id=UUID(str(row["owner_user_id"])),
                university_id=UUID(str(row["university_id"])),
                major_id=UUID(str(row["major_id"])),
                study_plan_id=UUID(str(row["study_plan_id"])),
                study_plan_version=str(row["study_plan_version"]),
                target_period_id=UUID(str(row["target_period_id"])),
                revision=int(row["revision"]),
                event_type=str(row["event_type"]),
                snapshot_contract_version=str(row["snapshot_contract_version"]),
                source_snapshot=dict(row["source_snapshot"]),
                processing_state="PROCESSING",
            )
            projection = TrustedP6OutboxProjection(
                revision=revision,
                outbox_required=outbox_required,
                outbox_event=outbox_event,
            )
            return ClaimedOutboxEvent(
                event_id=event_id,
                revision_id=revision_id,
                claim_token=claim_token,
                attempt_count=attempt_count,
                lease_expires_at=lease_expires_at,
                projection=projection,
            )
        except (KeyError, ValueError, TypeError) as error:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "claimed outbox event cannot be parsed into a trusted projection",
            ) from error


def _utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid datetime: {value}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"datetime missing tzinfo: {value}")
    return parsed.astimezone(timezone.utc)


def _postgrest_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("code") if isinstance(body, Mapping) else None
