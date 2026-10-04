"""P8 Slice 2A local-only PostgreSQL/Supabase security verification.

These tests intentionally exercise the isolated local stack.  They do not test
the future Slice 2B Python authorization or Slice 1 hash recomputation service.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import os
import subprocess
from uuid import uuid4

import httpx
import pytest


URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
SERVER_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
ANON_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_ANON_KEY")

pytestmark = pytest.mark.skipif(
    not all((URL, SERVER_KEY, ANON_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values",
)


def _server_headers() -> dict[str, str]:
    return {
        "apikey": SERVER_KEY or "",
        "Authorization": f"Bearer {SERVER_KEY or ''}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _create_user(client: httpx.Client, label: str) -> tuple[str, str]:
    password = f"P8-local-{uuid4()}-Aa1!"
    email = f"p8-2a-{label}-{uuid4()}@local.test"
    created = client.post(
        f"{URL}/auth/v1/admin/users",
        headers=_server_headers(),
        json={"email": email, "password": password, "email_confirm": True},
    )
    created.raise_for_status()
    signed_in = client.post(
        f"{URL}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": ANON_KEY or "", "Content-Type": "application/json"},
        json={"email": email, "password": password},
    )
    signed_in.raise_for_status()
    return created.json()["id"], signed_in.json()["access_token"]


def _university_id(client: httpx.Client) -> str:
    rows = client.get(
        f"{URL}/rest/v1/study_plans",
        headers=_server_headers(),
        params={"select": "id,majors(faculties(university_id))", "limit": "1"},
    )
    rows.raise_for_status()
    return rows.json()[0]["majors"]["faculties"]["university_id"]


def _foreign_university_id(client: httpx.Client) -> str:
    marker = uuid4().hex
    response = client.post(
        f"{URL}/rest/v1/universities",
        headers=_server_headers(),
        json={
            "name_en": f"P8 Local Foreign University {marker}",
            "name_ar": f"P8 Local Foreign University {marker}",
            "country": "JO",
        },
    )
    response.raise_for_status()
    return response.json()[0]["id"]


def _entry(university_id: str, student_user_id: str, **overrides: object) -> dict[str, object]:
    ledger_entry_id = str(overrides.pop("ledger_entry_id", uuid4()))
    entry: dict[str, object] = {
        "ledger_entry_id": ledger_entry_id,
        "decision_type": "MOCK_REGISTRATION_SUBMIT",
        "materiality_class": "LEDGER_REQUIRED",
        "actor_class": "STUDENT",
        "actor_id": student_user_id,
        "subject_scope_type": "STUDENT_INDIVIDUAL",
        "subject_scope_id": f"student-scope:{student_user_id}",
        "university_id": university_id,
        "student_user_id": student_user_id,
        "source_engine": "mock_registration",
        "source_engine_version": "6.5",
        "policy_version": "P8.1",
        "source_versions": ["catalog:plan12:v1", "policy:p8.1"],
        "input_state_reference": "local:p8-2a-input",
        "scenario_id": None,
        "decision_status": "EXECUTED",
        "outcome_reference": "local:p8-2a-outcome",
        "domain_trace_reference": "local:p8-2a-domain-trace",
        "provenance_class": "AUTHORITATIVE_TRANSACTION",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "redaction_profile": "STUDENT_SAFE",
        "integrity_hash": hashlib.sha256(f"p8-2a:{ledger_entry_id}".encode()).hexdigest(),
        "previous_entry_hash": None,
        "supersedes_entry_id": None,
        "replay_status": "REPLAYABLE_EXACT",
        "limitations": [],
        "hash_contract_version": "1.0",
        "decision_schema_version": "1.0",
    }
    entry.update(overrides)
    return entry


def _evidence() -> list[dict[str, object]]:
    return [
        {
            "source": "catalog",
            "identifier": "plan-12",
            "version": "v1",
            "locator": "courses/1501112",
            "uri": "https://local.invalid/catalog/plan-12",
        },
        {
            "source": "policy",
            "identifier": "p8.1",
            "version": "v1",
            "locator": "section-5",
            "uri": None,
        },
    ]


def _append(client: httpx.Client, entry: dict[str, object], evidence: object = None) -> httpx.Response:
    return client.post(
        f"{URL}/rest/v1/rpc/append_decision_trace_ledger",
        headers=_server_headers(),
        json={"p_entry": entry, "p_evidence": _evidence() if evidence is None else evidence},
    )


def _service_rows(client: httpx.Client, table: str, **params: str) -> list[dict[str, object]]:
    response = client.get(f"{URL}/rest/v1/{table}", headers=_server_headers(), params=params)
    response.raise_for_status()
    return response.json()


def _assert_direct_access_denied(response: httpx.Response) -> None:
    assert response.status_code in {401, 403, 404} or (
        response.status_code == 200 and response.json() == []
    ), response.text


def test_p8_2a_authorized_service_append_is_atomic_and_preserves_evidence_order() -> None:
    with httpx.Client(timeout=30) as client:
        student_id, _ = _create_user(client, "atomic")
        university_id = _university_id(client)
        entry = _entry(university_id, student_id)
        appended = _append(client, entry)
        assert appended.status_code == 200, appended.text
        assert _service_rows(
            client, "decision_trace_ledger", select="ledger_entry_id,integrity_hash", ledger_entry_id=f"eq.{entry['ledger_entry_id']}"
        ) == [{"ledger_entry_id": entry["ledger_entry_id"], "integrity_hash": entry["integrity_hash"]}]
        evidence_rows = _service_rows(
            client,
            "decision_trace_evidence",
            select="evidence_position,source,identifier,version",
            ledger_entry_id=f"eq.{entry['ledger_entry_id']}",
            order="evidence_position.asc",
        )
        assert [(row["evidence_position"], row["source"], row["identifier"]) for row in evidence_rows] == [
            (1, "catalog", "plan-12"),
            (2, "policy", "p8.1"),
        ]

        invalid_entry = _entry(university_id, student_id)
        invalid_evidence = [{"source": "catalog", "identifier": "", "version": "v1"}]
        rejected = _append(client, invalid_entry, invalid_evidence)
        assert rejected.status_code >= 400
        assert _service_rows(
            client, "decision_trace_ledger", select="ledger_entry_id", ledger_entry_id=f"eq.{invalid_entry['ledger_entry_id']}"
        ) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda entry: entry.update(decision_type="GET_PROGRESS"),
        lambda entry: entry.update(materiality_class="LEDGER_OPTIONAL"),
        lambda entry: entry.pop("outcome_reference"),
    ],
    ids=["invalid-decision-type", "invalid-materiality", "missing-required-field"],
)
def test_p8_2a_rejects_noncanonical_material_or_missing_parent_fields(mutate) -> None:
    with httpx.Client(timeout=30) as client:
        student_id, _ = _create_user(client, "invalid-parent")
        entry = _entry(_university_id(client), student_id)
        mutate(entry)
        assert _append(client, entry).status_code >= 400


def test_p8_2a_rejects_duplicate_identity_and_invalid_evidence_shape() -> None:
    with httpx.Client(timeout=30) as client:
        student_id, _ = _create_user(client, "duplicate")
        entry = _entry(_university_id(client), student_id)
        assert _append(client, entry).status_code == 200
        assert _append(client, entry).status_code >= 400

        malformed_evidence_entry = _entry(_university_id(client), student_id)
        malformed = _append(client, malformed_evidence_entry, [{"source": "only-source"}])
        assert malformed.status_code >= 400
        assert _service_rows(
            client,
            "decision_trace_ledger",
            select="ledger_entry_id",
            ledger_entry_id=f"eq.{malformed_evidence_entry['ledger_entry_id']}",
        ) == []


def test_p8_2a_denies_direct_client_rows_writes_evidence_and_rpc_execution() -> None:
    with httpx.Client(timeout=30) as client:
        owner_id, owner_token = _create_user(client, "owner")
        other_id, other_token = _create_user(client, "other")
        analyst_id, analyst_token = _create_user(client, "analyst")
        university_id = _university_id(client)
        entry = _entry(university_id, owner_id)
        assert _append(client, entry).status_code == 200

        membership = client.post(
            f"{URL}/rest/v1/institutional_memberships",
            headers=_server_headers(),
            json={
                "subject_user_id": analyst_id,
                "university_id": university_id,
                "provider_namespace": f"p8-local-{uuid4()}",
                "role": "INSTITUTIONAL_ANALYST",
                "active": True,
                "authority_source": "local-p8-test",
                "authority_source_version": "v1",
            },
        )
        assert membership.status_code == 201, membership.text

        for token in (owner_token, other_token, analyst_token):
            headers = {"apikey": ANON_KEY or "", "Authorization": f"Bearer {token}"}
            _assert_direct_access_denied(
                client.get(
                    f"{URL}/rest/v1/decision_trace_ledger",
                    headers=headers,
                    params={"select": "ledger_entry_id", "ledger_entry_id": f"eq.{entry['ledger_entry_id']}"},
                )
            )
            _assert_direct_access_denied(
                client.get(
                    f"{URL}/rest/v1/decision_trace_evidence",
                    headers=headers,
                    params={"select": "ledger_entry_id", "ledger_entry_id": f"eq.{entry['ledger_entry_id']}"},
                )
            )

        owner_headers = {"apikey": ANON_KEY or "", "Authorization": f"Bearer {owner_token}"}
        _assert_direct_access_denied(
            client.post(f"{URL}/rest/v1/decision_trace_ledger", headers=owner_headers, json=entry)
        )
        _assert_direct_access_denied(
            client.patch(
                f"{URL}/rest/v1/decision_trace_ledger",
                headers=owner_headers,
                params={"ledger_entry_id": f"eq.{entry['ledger_entry_id']}"},
                json={"outcome_reference": "tampered"},
            )
        )
        _assert_direct_access_denied(
            client.delete(
                f"{URL}/rest/v1/decision_trace_ledger",
                headers=owner_headers,
                params={"ledger_entry_id": f"eq.{entry['ledger_entry_id']}"},
            )
        )
        _assert_direct_access_denied(
            client.post(
                f"{URL}/rest/v1/rpc/append_decision_trace_ledger",
                headers=owner_headers,
                json={"p_entry": _entry(university_id, owner_id), "p_evidence": []},
            )
        )


def test_p8_2a_rejects_invalid_supersession_hash_scope_and_predecessor() -> None:
    with httpx.Client(timeout=30) as client:
        student_id, _ = _create_user(client, "supersession")
        university_id = _university_id(client)
        predecessor = _entry(university_id, student_id)
        assert _append(client, predecessor).status_code == 200

        missing = _entry(
            university_id,
            student_id,
            supersedes_entry_id=str(uuid4()),
            previous_entry_hash=hashlib.sha256(b"missing").hexdigest(),
        )
        assert _append(client, missing).status_code >= 400

        wrong_hash = _entry(
            university_id,
            student_id,
            supersedes_entry_id=predecessor["ledger_entry_id"],
            previous_entry_hash=hashlib.sha256(b"wrong").hexdigest(),
        )
        assert _append(client, wrong_hash).status_code >= 400

        foreign_scope = _entry(
            _foreign_university_id(client),
            student_id,
            supersedes_entry_id=predecessor["ledger_entry_id"],
            previous_entry_hash=predecessor["integrity_hash"],
        )
        assert _append(client, foreign_scope).status_code >= 400


def test_p8_2a_allows_only_one_concurrent_successor_and_preserves_predecessor() -> None:
    with httpx.Client(timeout=30) as client:
        student_id, _ = _create_user(client, "concurrency")
        university_id = _university_id(client)
        predecessor = _entry(university_id, student_id)
        assert _append(client, predecessor).status_code == 200

        first = _entry(
            university_id,
            student_id,
            supersedes_entry_id=predecessor["ledger_entry_id"],
            previous_entry_hash=predecessor["integrity_hash"],
            outcome_reference="local:p8-2a-successor-one",
        )
        second = _entry(
            university_id,
            student_id,
            supersedes_entry_id=predecessor["ledger_entry_id"],
            previous_entry_hash=predecessor["integrity_hash"],
            outcome_reference="local:p8-2a-successor-two",
        )

        def append_concurrently(candidate: dict[str, object]) -> int:
            with httpx.Client(timeout=30) as concurrent_client:
                return _append(concurrent_client, candidate).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(append_concurrently, (first, second)))
        assert statuses.count(200) == 1
        assert sum(status >= 400 for status in statuses) == 1

        stored_predecessor = _service_rows(
            client,
            "decision_trace_ledger",
            select="integrity_hash,outcome_reference",
            ledger_entry_id=f"eq.{predecessor['ledger_entry_id']}",
        )
        assert stored_predecessor == [
            {"integrity_hash": predecessor["integrity_hash"], "outcome_reference": predecessor["outcome_reference"]}
        ]


def test_p8_2a_database_triggers_block_owner_update_delete_for_parent_and_evidence() -> None:
    with httpx.Client(timeout=30) as client:
        student_id, _ = _create_user(client, "immutability")
        entry = _entry(_university_id(client), student_id)
        assert _append(client, entry).status_code == 200

    commands = [
        f"update public.decision_trace_ledger set outcome_reference = 'tampered' where ledger_entry_id = '{entry['ledger_entry_id']}';",
        f"delete from public.decision_trace_evidence where ledger_entry_id = '{entry['ledger_entry_id']}' and evidence_position = 1;",
    ]
    for command in commands:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "supabase_db_Morshidi",
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "-c",
                command,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "append-only" in f"{result.stdout}\n{result.stderr}"
