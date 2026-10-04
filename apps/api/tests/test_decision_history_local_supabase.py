"""Real Local Supabase owner-only history and browser-denial checks."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.core.auth import CurrentUser
from app.decision_trace import RedactionProfile
from app.decision_trace_persistence import DecisionTraceErrorCode, DecisionTracePersistenceError
from tests.test_decision_trace_persistence_service_local_supabase import (
    URL, ANON_KEY, SERVER_KEY, _assert_denied, _create_profile, _create_user,
    _plan_scope, _server_headers, _service, _student_entry, _user_headers,
)


pytestmark = pytest.mark.skipif(
    not all((URL, ANON_KEY, SERVER_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values",
)


@pytest.mark.anyio
async def test_local_student_history_scope_pagination_and_browser_denials() -> None:
    with httpx.Client(timeout=30) as raw:
        plan_id, university_id = _plan_scope(raw)
        owner_id, owner_token = _create_user(raw, "history-owner")
        other_id, other_token = _create_user(raw, "history-other")
        _create_profile(raw, owner_id, plan_id)
        _create_profile(raw, other_id, plan_id)
        foreign = raw.post(
            f"{URL}/rest/v1/universities", headers=_server_headers(),
            json={"name_ar": f"Synthetic History {uuid4()}",
                  "name_en": f"Synthetic History {uuid4()}", "country": "JO"},
        )
        foreign.raise_for_status()
        foreign_id = foreign.json()[0]["id"]

        async with httpx.AsyncClient(timeout=30) as client:
            service, repository = _service(client)
            owned = _student_entry(owner_id, university_id)
            second = _student_entry(owner_id, university_id)
            restricted = _student_entry(owner_id, university_id,
                                        redaction_profile=RedactionProfile.ADVISOR_SAFE)
            other = _student_entry(other_id, university_id)
            foreign_entry = _student_entry(owner_id, foreign_id)
            for item in (owned, second, restricted, other, foreign_entry):
                assert await repository.append(item) == item.ledger_entry_id

            page = await service.list_student_history(CurrentUser(owner_id), limit=1)
            assert len(page) == 1 and page[0].integrity_status == "VERIFIED"
            next_page = await service.list_student_history(
                CurrentUser(owner_id), limit=1,
                before_created_at=page[-1].created_at, before_entry_id=page[-1].ledger_entry_id,
            )
            assert len(next_page) == 1
            assert {page[0].ledger_entry_id, next_page[0].ledger_entry_id} == {
                owned.ledger_entry_id, second.ledger_entry_id,
            }
            assert await service.list_student_history(
                CurrentUser(owner_id), limit=1,
                before_created_at=next_page[-1].created_at,
                before_entry_id=next_page[-1].ledger_entry_id,
            ) == ()
            own_detail = await service.get_student_history_detail(CurrentUser(owner_id), owned.ledger_entry_id)
            assert own_detail.evidence and own_detail.integrity_status == "VERIFIED"
            for principal, target in (
                (other_id, owned.ledger_entry_id), (owner_id, other.ledger_entry_id),
                (owner_id, foreign_entry.ledger_entry_id), (owner_id, restricted.ledger_entry_id),
            ):
                with pytest.raises(DecisionTracePersistenceError) as caught:
                    await service.get_student_history_detail(CurrentUser(principal), target)
                assert caught.value.code in {DecisionTraceErrorCode.NOT_FOUND, DecisionTraceErrorCode.ACCESS_DENIED}

        # The server credential may read only after the application has established
        # owner/tenant scope. Browser roles receive no direct ledger/evidence grant.
        for table in ("decision_trace_ledger", "decision_trace_evidence"):
            server_read = raw.get(f"{URL}/rest/v1/{table}", headers=_server_headers(),
                                  params={"select": "ledger_entry_id", "ledger_entry_id": f"eq.{owned.ledger_entry_id}"})
            server_read.raise_for_status()
            assert server_read.json()
            for headers in ({"apikey": ANON_KEY or ""}, _user_headers(owner_token),
                            _user_headers(other_token)):
                _assert_denied(raw.get(f"{URL}/rest/v1/{table}", headers=headers,
                                       params={"select": "ledger_entry_id"}))
                _assert_denied(raw.patch(f"{URL}/rest/v1/{table}", headers=headers,
                                         params={"ledger_entry_id": f"eq.{owned.ledger_entry_id}"},
                                         json={"source" if table.endswith("evidence") else "source_engine": "forged"}))
                _assert_denied(raw.delete(f"{URL}/rest/v1/{table}", headers=headers,
                                          params={"ledger_entry_id": f"eq.{owned.ledger_entry_id}"}))
        _assert_denied(raw.get(
            f"{URL}/rest/v1/decision_trace_evidence", headers=_user_headers(other_token),
            params={"select": "*", "ledger_entry_id": f"eq.{owned.ledger_entry_id}"},
        ))
        _assert_denied(raw.post(
            f"{URL}/rest/v1/rpc/append_decision_trace_ledger",
            headers=_user_headers(owner_token), json={"p_entry": {}, "p_evidence": []},
        ))
