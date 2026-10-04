"""Typed, server-side PostgREST adapter for the immutable P8 ledger tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

import httpx

from app.decision_trace import (
    CanonicalLedgerEntry,
    EvidenceReference,
    IntegrityStatus,
    canonical_ledger_payload,
    validate_entry,
    verify_integrity_hash,
)

from .errors import DecisionTraceErrorCode, DecisionTracePersistenceError


_LEDGER_SELECT = (
    "ledger_entry_id,decision_type,materiality_class,actor_class,actor_id,"
    "subject_scope_type,subject_scope_id,university_id,student_user_id,"
    "source_engine,source_engine_version,policy_version,source_versions,"
    "input_state_reference,scenario_id,decision_status,outcome_reference,"
    "domain_trace_reference,provenance_class,created_at,redaction_profile,"
    "integrity_hash,previous_entry_hash,supersedes_entry_id,replay_status,"
    "limitations,hash_contract_version,decision_schema_version"
)
_EVIDENCE_SELECT = "ledger_entry_id,evidence_position,source,identifier,version,locator,uri"
_MAX_EVIDENCE_REFERENCES = 1000
_MAX_HISTORY_PAGE = 50


class SupabaseDecisionTraceRepository:
    """Repository restricted to canonical append and exact, already-authorized student scope reads."""

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

    async def append(self, entry: CanonicalLedgerEntry) -> str:
        """Persist one already-authorized canonical entry and its ordered evidence atomically."""
        _require_verified_entry(entry)
        body = _append_body(entry)
        response = await self._request(
            "POST",
            "rpc/append_decision_trace_ledger",
            json=body,
        )
        self._require_success(response, "append decision trace")
        appended_id = _rpc_text(response, "append decision trace")
        if appended_id != entry.ledger_entry_id:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "append RPC returned an unexpected ledger identity",
            )
        return appended_id

    async def load_exact_internal_entry(
        self, *, ledger_entry_id: str, university_id: str,
    ) -> CanonicalLedgerEntry | None:
        """Internal-only, tenant-bound lookup for trusted producer retry reconciliation.

        This is not an HTTP/viewer method and grants no browser read authority.
        """
        rows = await self._get_rows("decision_trace_ledger", {
            "select": _LEDGER_SELECT,
            "ledger_entry_id": f"eq.{ledger_entry_id}",
            "university_id": f"eq.{university_id}",
            "limit": "2",
        })
        if not rows:
            return None
        if len(rows) != 1:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "producer retry identity matched multiple entries",
            )
        return await self._entry_with_evidence(rows[0])

    async def load_student_entry(
        self,
        *,
        ledger_entry_id: str,
        student_user_id: str,
        university_id: str,
        redaction_profile: str | None = None,
        redaction_profiles: tuple[str, ...] | None = None,
    ) -> CanonicalLedgerEntry | None:
        """Load at most one individual trace after service authorization has fixed owner and tenant."""
        if redaction_profiles is not None and (redaction_profile is not None or not redaction_profiles
                or set(redaction_profiles) - {"STUDENT_SAFE", "ADVISOR_SAFE"}):
            raise ValueError("invalid viewer redaction profiles")
        params = {
                "select": _LEDGER_SELECT,
                "ledger_entry_id": f"eq.{ledger_entry_id}",
                "student_user_id": f"eq.{student_user_id}",
                "university_id": f"eq.{university_id}",
                "subject_scope_type": "eq.STUDENT_INDIVIDUAL",
                "limit": "2",
            }
        if redaction_profile is not None:
            params["redaction_profile"] = f"eq.{redaction_profile}"
        if redaction_profiles is not None:
            params["redaction_profile"] = f"in.({','.join(redaction_profiles)})"
        rows = await self._get_rows("decision_trace_ledger", params)
        if not rows:
            return None
        if len(rows) != 1:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "exact trace lookup returned multiple rows",
            )
        evidence_rows = await self._get_rows(
            "decision_trace_evidence",
            {
                "select": _EVIDENCE_SELECT,
                "ledger_entry_id": f"eq.{ledger_entry_id}",
                "order": "evidence_position.asc",
                # Fetch one extra row so a server-side limit can never silently
                # transform a historical entry into a trusted partial record.
                "limit": str(_MAX_EVIDENCE_REFERENCES + 1),
            },
        )
        if len(evidence_rows) > _MAX_EVIDENCE_REFERENCES:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "stored decision trace exceeds the supported evidence bound",
            )
        return _ledger_entry(rows[0], evidence_rows)

    async def list_student_entries(
        self, *, student_user_id: str, university_id: str, limit: int,
        before_created_at: datetime | None = None, before_entry_id: str | None = None,
        redaction_profiles: tuple[str, ...] = ("STUDENT_SAFE",),
    ) -> tuple[CanonicalLedgerEntry, ...]:
        """Return a bounded, stable page of viewer-permitted individual entries."""
        if not 1 <= limit <= _MAX_HISTORY_PAGE or (before_created_at is None) != (before_entry_id is None):
            raise ValueError("invalid history pagination")
        if not redaction_profiles or set(redaction_profiles) - {"STUDENT_SAFE", "ADVISOR_SAFE"}:
            raise ValueError("invalid viewer redaction profiles")
        params = {
            "select": _LEDGER_SELECT,
            "student_user_id": f"eq.{student_user_id}",
            "university_id": f"eq.{university_id}",
            "subject_scope_type": "eq.STUDENT_INDIVIDUAL",
            "redaction_profile": ("eq.STUDENT_SAFE" if redaction_profiles == ("STUDENT_SAFE",)
                                   else f"in.({','.join(redaction_profiles)})"),
            "order": "created_at.desc,ledger_entry_id.desc",
            "limit": str(limit),
        }
        if before_created_at is not None and before_entry_id is not None:
            if before_created_at.tzinfo is None or before_created_at.utcoffset() is None:
                raise ValueError("history cursor must be timezone-aware")
            stamp = before_created_at.astimezone(timezone.utc).isoformat(timespec="microseconds")
            params["or"] = f"(created_at.lt.{stamp},and(created_at.eq.{stamp},ledger_entry_id.lt.{before_entry_id}))"
        rows = await self._get_rows("decision_trace_ledger", params)
        if len(rows) > limit:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE, "history page exceeded bound"
            )
        entries: list[CanonicalLedgerEntry] = []
        for row in rows:
            entry = await self._entry_with_evidence(row)
            if (entry.student_user_id != student_user_id or entry.university_id != university_id
                    or entry.subject_scope_type.value != "STUDENT_INDIVIDUAL"
                    or entry.redaction_profile.value not in redaction_profiles):
                raise DecisionTracePersistenceError(
                    DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE, "history scope mismatch"
                )
            if before_created_at is not None and before_entry_id is not None:
                if (entry.created_at, entry.ledger_entry_id) >= (before_created_at, before_entry_id):
                    raise DecisionTracePersistenceError(
                        DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE, "history cursor mismatch"
                    )
            entries.append(entry)
        expected = sorted(entries, key=lambda item: (item.created_at, item.ledger_entry_id), reverse=True)
        if entries != expected or len({entry.ledger_entry_id for entry in entries}) != len(entries):
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE, "history order is invalid"
            )
        return tuple(entries)

    async def load_student_successor(
        self, *, ledger_entry_id: str, student_user_id: str, university_id: str,
        redaction_profiles: tuple[str, ...] = ("STUDENT_SAFE",),
    ) -> CanonicalLedgerEntry | None:
        """Look up only a visible successor; never disclose a restricted successor."""
        if not redaction_profiles or set(redaction_profiles) - {"STUDENT_SAFE", "ADVISOR_SAFE"}:
            raise ValueError("invalid viewer redaction profiles")
        rows = await self._get_rows("decision_trace_ledger", {
            "select": _LEDGER_SELECT,
            "supersedes_entry_id": f"eq.{ledger_entry_id}",
            "student_user_id": f"eq.{student_user_id}",
            "university_id": f"eq.{university_id}",
            "subject_scope_type": "eq.STUDENT_INDIVIDUAL",
            "redaction_profile": ("eq.STUDENT_SAFE" if redaction_profiles == ("STUDENT_SAFE",)
                                   else f"in.({','.join(redaction_profiles)})"),
            "limit": "2",
        })
        if not rows:
            return None
        if len(rows) != 1:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE, "multiple successors found"
            )
        entry = await self._entry_with_evidence(rows[0])
        if (entry.supersedes_entry_id != ledger_entry_id or entry.student_user_id != student_user_id
                or entry.university_id != university_id or entry.redaction_profile.value not in redaction_profiles
                or entry.subject_scope_type.value != "STUDENT_INDIVIDUAL"):
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE, "successor scope mismatch"
            )
        return entry

    async def _entry_with_evidence(self, row: Mapping[str, Any]) -> CanonicalLedgerEntry:
        try:
            ledger_entry_id = _required_text(row, "ledger_entry_id")
        except ValueError as error:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE, "history identity is invalid"
            ) from error
        evidence_rows = await self._get_rows("decision_trace_evidence", {
            "select": _EVIDENCE_SELECT,
            "ledger_entry_id": f"eq.{ledger_entry_id}",
            "order": "evidence_position.asc",
            "limit": str(_MAX_EVIDENCE_REFERENCES + 1),
        })
        if len(evidence_rows) > _MAX_EVIDENCE_REFERENCES:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "stored decision trace exceeds the supported evidence bound",
            )
        return _ledger_entry(row, evidence_rows)

    async def _get_rows(
        self, resource: str, params: Mapping[str, str]
    ) -> list[Mapping[str, Any]]:
        response = await self._request("GET", resource, params=params)
        self._require_success(response, f"load {resource}")
        try:
            value = response.json()
        except ValueError as error:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                f"{resource} response is not JSON",
            ) from error
        if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                f"{resource} response is not a row array",
            )
        return list(value)

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
        failure = (
            DecisionTraceErrorCode.PERSISTENCE_CONFLICT
            if code in {"23503", "23505", "23514", "55000"}
            else DecisionTraceErrorCode.PERSISTENCE_UNAVAILABLE
        )
        raise DecisionTracePersistenceError(failure, f"{operation} failed")


def _append_body(entry: CanonicalLedgerEntry) -> dict[str, Any]:
    _require_storage_round_trip_safe(entry)
    if len(entry.evidence_references) > _MAX_EVIDENCE_REFERENCES:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.INTEGRITY_FAILURE,
            "decision trace exceeds the supported evidence bound",
        )
    payload = canonical_ledger_payload(entry)
    evidence = payload.pop("evidence_references")
    payload["integrity_hash"] = entry.integrity_hash
    return {"p_entry": payload, "p_evidence": evidence}


def _require_verified_entry(entry: CanonicalLedgerEntry) -> None:
    try:
        validate_entry(entry)
    except ValueError as error:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.INTEGRITY_FAILURE, "ledger entry failed domain validation"
        ) from error
    if verify_integrity_hash(entry) is not IntegrityStatus.VERIFIED:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.INTEGRITY_FAILURE,
            "ledger entry integrity hash does not match the Slice 1 canonical payload",
        )


def _require_storage_round_trip_safe(entry: CanonicalLedgerEntry) -> None:
    """Reject input that Slice 2A SQL would trim or UUID-normalize before hashing."""
    for value in (
        entry.actor_id,
        entry.input_state_reference,
        entry.scenario_id,
        entry.domain_trace_reference,
        entry.previous_entry_hash,
        entry.supersedes_entry_id,
    ):
        if value is not None and (not isinstance(value, str) or value != value.strip()):
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.INTEGRITY_FAILURE,
                "ledger field cannot be losslessly stored by the Slice 2A representation",
            )
    for value in (entry.university_id, entry.student_user_id):
        if value is not None:
            try:
                if str(UUID(value)) != value:
                    raise ValueError
            except (TypeError, ValueError) as error:
                raise DecisionTracePersistenceError(
                    DecisionTraceErrorCode.INTEGRITY_FAILURE,
                    "tenant or student identity is not a canonical UUID string",
                ) from error
    for reference in entry.evidence_references:
        for value in (
            reference.source,
            reference.identifier,
            reference.version,
            reference.locator,
            reference.uri,
        ):
            if value is not None and (not isinstance(value, str) or value != value.strip()):
                raise DecisionTracePersistenceError(
                    DecisionTraceErrorCode.INTEGRITY_FAILURE,
                    "evidence cannot be losslessly stored by the Slice 2A representation",
                )


def _ledger_entry(
    row: Mapping[str, Any], evidence_rows: Sequence[Mapping[str, Any]]
) -> CanonicalLedgerEntry:
    try:
        from app.decision_trace.registries import (
            ActorClass,
            DecisionStatus,
            DecisionType,
            MaterialityClass,
            ProvenanceClass,
            RedactionProfile,
            ReplayStatus,
            SubjectScopeType,
        )

        entry = CanonicalLedgerEntry(
            ledger_entry_id=_required_text(row, "ledger_entry_id"),
            decision_type=DecisionType(_required_text(row, "decision_type")),
            materiality_class=MaterialityClass(_required_text(row, "materiality_class")),
            actor_class=ActorClass(_required_text(row, "actor_class")),
            actor_id=_optional_text(row.get("actor_id")),
            subject_scope_type=SubjectScopeType(_required_text(row, "subject_scope_type")),
            subject_scope_id=_required_text(row, "subject_scope_id"),
            university_id=_canonical_uuid_text(row, "university_id"),
            student_user_id=_optional_canonical_uuid_text(row.get("student_user_id")),
            source_engine=_required_text(row, "source_engine"),
            source_engine_version=_required_text(row, "source_engine_version"),
            policy_version=_required_text(row, "policy_version"),
            source_versions=_text_tuple(row, "source_versions"),
            input_state_reference=_optional_text(row.get("input_state_reference")),
            scenario_id=_optional_text(row.get("scenario_id")),
            decision_status=DecisionStatus(_required_text(row, "decision_status")),
            outcome_reference=_required_text(row, "outcome_reference"),
            evidence_references=_evidence(evidence_rows, _required_text(row, "ledger_entry_id")),
            domain_trace_reference=_optional_text(row.get("domain_trace_reference")),
            provenance_class=ProvenanceClass(_required_text(row, "provenance_class")),
            created_at=_utc_datetime(row, "created_at"),
            redaction_profile=RedactionProfile(_required_text(row, "redaction_profile")),
            integrity_hash=_required_text(row, "integrity_hash"),
            previous_entry_hash=_optional_text(row.get("previous_entry_hash")),
            supersedes_entry_id=_optional_text(row.get("supersedes_entry_id")),
            replay_status=ReplayStatus(_required_text(row, "replay_status")),
            limitations=_text_tuple(row, "limitations"),
            hash_contract_version=_required_text(row, "hash_contract_version"),
            decision_schema_version=_required_text(row, "decision_schema_version"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
            "stored decision trace cannot be reconstructed as a canonical domain entry",
        ) from error
    _require_verified_entry(entry)
    return entry


def _evidence(
    rows: Sequence[Mapping[str, Any]], ledger_entry_id: str
) -> tuple[EvidenceReference, ...]:
    references: list[EvidenceReference] = []
    for expected_position, row in enumerate(rows, start=1):
        if _required_text(row, "ledger_entry_id") != ledger_entry_id:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "evidence response belongs to another ledger entry",
            )
        position = row.get("evidence_position")
        if isinstance(position, bool) or not isinstance(position, int) or position != expected_position:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
                "evidence positions are not contiguous canonical order",
            )
        references.append(
            EvidenceReference(
                source=_required_text(row, "source"),
                identifier=_required_text(row, "identifier"),
                version=_required_text(row, "version"),
                locator=_optional_text(row.get("locator")),
                uri=_optional_text(row.get("uri")),
            )
        )
    return tuple(references)


def _required_text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing {key}")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("invalid optional text")
    return value


def _text_tuple(row: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = row.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"invalid {key}")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"invalid {key}")
    return tuple(value)


def _canonical_uuid_text(row: Mapping[str, Any], key: str) -> str:
    return _optional_canonical_uuid_text(row.get(key)) or _raise_missing_uuid(key)


def _raise_missing_uuid(key: str) -> str:
    raise ValueError(f"missing {key}")


def _optional_canonical_uuid_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid UUID")
    parsed = str(UUID(value))
    if parsed != value:
        raise ValueError("noncanonical UUID")
    return parsed


def _utc_datetime(row: Mapping[str, Any], key: str) -> datetime:
    value = _required_text(row, key)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid {key}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"invalid {key}")
    return parsed.astimezone(timezone.utc)


def _postgrest_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("code") if isinstance(body, Mapping) else None


def _rpc_text(response: httpx.Response, operation: str) -> str:
    try:
        value = response.json()
    except ValueError as error:
        raise DecisionTracePersistenceError(
            DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
            f"{operation} response is not JSON",
        ) from error
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str) and value[0]:
        return value[0]
    raise DecisionTracePersistenceError(
        DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE,
        f"{operation} response is not a ledger identity",
    )
