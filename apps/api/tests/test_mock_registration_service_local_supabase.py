"""Opt-in real Auth -> FastAPI -> service -> P6.2 -> P6.4 integration."""

from __future__ import annotations

import os
import asyncio
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.decision_trace_persistence.outbox_repository import SupabaseDecisionTraceOutboxRepository
from app.decision_trace_persistence.repository import SupabaseDecisionTraceRepository
from app.decision_trace_persistence.processor import DecisionTraceOutboxProcessor
from app.decision_trace_persistence.historical_replay import P6HistoricalReplayService
from app.mock_registration_persistence.repository import SupabaseMockRegistrationRepository

URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
SERVER_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
ANON_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_ANON_KEY")
pytestmark = pytest.mark.skipif(not all((URL, SERVER_KEY, ANON_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values")


def _server_headers():
    return {"apikey": SERVER_KEY, "Authorization": f"Bearer {SERVER_KEY}",
            "Content-Type": "application/json", "Prefer": "return=representation"}


def _create_user(client, email, password):
    response = client.post(f"{URL}/auth/v1/admin/users", headers=_server_headers(),
        json={"email": email, "password": password, "email_confirm": True})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _token(client, email, password):
    response = client.post(f"{URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_p6_5_real_authenticated_service_api_and_aggregate_pipeline():
    marker = uuid4().hex
    student_email = f"p65-student-{marker}@synthetic.invalid"
    analyst_email = f"p65-analyst-{marker}@synthetic.invalid"
    password = "Synthetic-only-P6.5-password!"
    with httpx.Client(timeout=30) as raw:
        rows = raw.get(f"{URL}/rest/v1/study_plan_courses", headers=_server_headers(), params={
            "select": "study_plan_id,course_id,prerequisite_logic_status,courses(course_code)",
            "prerequisite_logic_status": "eq.not_applicable", "limit": "1"}).json()
        assert rows
        plan_id, course_code = rows[0]["study_plan_id"], rows[0]["courses"]["course_code"]
        plan = raw.get(f"{URL}/rest/v1/study_plans", headers=_server_headers(), params={
            "select": "id,majors(faculties(university_id))", "id": f"eq.{plan_id}"}).json()[0]
        university_id = plan["majors"]["faculties"]["university_id"]
        student_id = _create_user(raw, student_email, password)
        analyst_id = _create_user(raw, analyst_email, password)
        profile_response = raw.post(f"{URL}/rest/v1/student_academic_profiles", headers=_server_headers(),
            json={"owner_user_id": student_id, "study_plan_id": plan_id})
        assert profile_response.status_code == 201
        profile_id = profile_response.json()[0]["id"]
        period_rows = raw.post(f"{URL}/rest/v1/mock_registration_target_periods",
            headers=_server_headers(), json={"university_id": university_id,
                "provider_namespace": "synthetic-p65", "period_key": marker,
                "period_class": "SYNTHETIC_SANDBOX_PERIOD",
                "verified_provider_source": False, "source_version": "synthetic-p65:v1"}).json()
        period_id = period_rows[0]["id"]
        assert raw.post(f"{URL}/rest/v1/institutional_memberships", headers=_server_headers(),
            json={"subject_user_id": analyst_id, "university_id": university_id,
                "provider_namespace": "synthetic-p65", "role": "INSTITUTIONAL_ANALYST",
                "active": True, "authority_source": "synthetic-test",
                "authority_source_version": "v1"}).status_code == 201
        student_token = _token(raw, student_email, password)
        analyst_token = _token(raw, analyst_email, password)

    with TestClient(app) as client:
        student_auth = {"Authorization": f"Bearer {student_token}"}
        body = {"target_period_id": period_id, "course_codes": [course_code],
                "expected_current_revision": None,
                "transparency_notice_version": "synthetic-notice:v1"}
        created = client.post("/api/v1/me/mock-registration/revisions",
                              headers=student_auth, json=body)
        assert created.status_code == 201, created.text
        assert created.json()["revision"] == 1
        replay = client.post("/api/v1/me/mock-registration/revisions",
                             headers=student_auth, json=body)
        assert replay.status_code == 201 and replay.json()["idempotent_replay"] is True
        with httpx.Client(timeout=30) as raw:
            revisions = raw.get(f"{URL}/rest/v1/mock_registration_intent_revisions",
                headers=_server_headers(), params={"select": "id", "owner_user_id": f"eq.{student_id}",
                    "target_period_id": f"eq.{period_id}", "revision": "eq.1"}).json()
            assert len(revisions) == 1
            revision_id = revisions[0]["id"]
            artifact_rows = raw.get(f"{URL}/rest/v1/p6_submit_replay_artifacts",
                headers=_server_headers(), params={"select": "revision_id,replay_contract_version,engine_version,canonical_sha256",
                    "revision_id": f"eq.{revision_id}"}).json()
            assert len(artifact_rows) == 1
            assert artifact_rows[0]["replay_contract_version"] == "P6_REPLAY_ARTIFACT_V1"
            for key in (ANON_KEY, student_token):
                blocked = raw.get(f"{URL}/rest/v1/p6_submit_replay_artifacts",
                    headers={"apikey": ANON_KEY, "Authorization": f"Bearer {key}"},
                    params={"select": "*", "revision_id": f"eq.{revision_id}"})
                assert blocked.status_code in (401, 403)
                browser_headers = {"apikey": ANON_KEY, "Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"}
                assert raw.post(f"{URL}/rest/v1/p6_submit_replay_artifacts",
                    headers=browser_headers, json={"revision_id": revision_id}).status_code in (401, 403)
                assert raw.patch(f"{URL}/rest/v1/p6_submit_replay_artifacts",
                    headers=browser_headers, params={"revision_id": f"eq.{revision_id}"},
                    json={"engine_version": "2.0"}).status_code in (401, 403)
                assert raw.delete(f"{URL}/rest/v1/p6_submit_replay_artifacts",
                    headers=browser_headers,
                    params={"revision_id": f"eq.{revision_id}"}).status_code in (401, 403)
            assert raw.patch(f"{URL}/rest/v1/p6_submit_replay_artifacts",
                headers=_server_headers(), params={"revision_id": f"eq.{revision_id}"},
                json={"engine_version": "2.0"}).status_code in (400, 403)
            assert raw.delete(f"{URL}/rest/v1/p6_submit_replay_artifacts",
                headers=_server_headers(),
                params={"revision_id": f"eq.{revision_id}"}).status_code in (400, 403)

        async def verify_historical():
            outbox = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
            ledger = SupabaseDecisionTraceRepository(URL, SERVER_KEY)
            revisions_repo = SupabaseMockRegistrationRepository(URL, SERVER_KEY)
            try:
                claimed = await outbox.claim_events(worker_id=f"p6-replay-{marker}", batch_size=100)
                item = next(row for row in claimed if str(row.event_id) == revision_id)
                assert item.projection.replay_artifact is not None
                processed = await DecisionTraceOutboxProcessor(outbox, ledger).process_event(item)
                assert processed.ledger_entry_id == revision_id
                entry = await ledger.load_exact_internal_entry(
                    ledger_entry_id=revision_id, university_id=university_id)
                assert entry is not None and entry.replay_status.value == "REPLAYABLE_EXACT"
                assert any(ref.source == "P6_REPLAY_ARTIFACT" for ref in entry.evidence_references)
                service = P6HistoricalReplayService(revisions_repo, ledger, outbox)
                exact = await service.verify(revision_id)
                artifact = item.projection.replay_artifact

                class ArtifactProbe:
                    def __init__(self, value):
                        self.value = value

                    async def load_replay_artifact(self, **_):
                        return self.value

                async def probe(value):
                    return await P6HistoricalReplayService(
                        revisions_repo, ledger, ArtifactProbe(value)).verify(revision_id)

                missing = await probe(None)
                assert missing.status == "UNAVAILABLE"
                assert missing.reason_code == "REPLAY_ARTIFACT_MISSING"
                unavailable_engine = await probe(replace(artifact, engine_version="2.0"))
                assert unavailable_engine.status == "UNAVAILABLE"
                assert unavailable_engine.reason_code == "ENGINE_VERSION_UNAVAILABLE"
                tampered = await probe(replace(artifact, canonical_payload=artifact.canonical_payload + " "))
                assert tampered.status == "UNAVAILABLE"
                assert tampered.reason_code == "REPLAY_ARTIFACT_INTEGRITY_FAILURE"
                return exact
            finally:
                await outbox.close()
                await ledger.close()
                await revisions_repo.close()

        exact = asyncio.run(verify_historical())
        assert exact.status == "MATCHED" and exact.matched
        assert exact.historical_validation_status == exact.replayed_validation_status
        assert exact.historical_reason_codes == exact.replayed_reason_codes
        assert exact.historical_content_fingerprint == exact.replayed_content_fingerprint
        detail = client.get(f"/api/v1/me/decision-history/{revision_id}", headers=student_auth)
        assert detail.status_code == 200, detail.text
        assert "canonical_payload" not in detail.text
        assert "student_attempts" not in detail.text
        assert "eligibility_catalog" not in detail.text
        assert "progress_catalog" not in detail.text
        with httpx.Client(timeout=30) as raw:
            changed = raw.post(f"{URL}/rest/v1/student_course_attempts",
                headers=_server_headers(), json={"profile_id": profile_id,
                    "course_id": rows[0]["course_id"], "outcome": "PASSED"})
            assert changed.status_code == 201, changed.text
            attempt_id = changed.json()[0]["id"]
        try:
            drifted = asyncio.run(verify_historical_after_drift(revision_id, university_id))
            assert drifted.status == "MATCHED" and drifted.matched
        finally:
            with httpx.Client(timeout=30) as raw:
                deleted = raw.delete(f"{URL}/rest/v1/student_course_attempts",
                    headers=_server_headers(), params={"id": f"eq.{attempt_id}"})
                assert deleted.status_code in (200, 204)
        current = client.get("/api/v1/me/mock-registration/current", headers=student_auth,
                             params={"target_period_id": period_id})
        assert current.status_code == 200 and current.json()["current_validity"] == "CURRENT_VALID"
        stale = dict(body, expected_current_revision=99)
        conflict = client.post("/api/v1/me/mock-registration/revisions",
                               headers=student_auth, json=stale)
        assert conflict.status_code == 409 and conflict.json()["error_code"] == "REVISION_CONFLICT"
        demand_params = {"university_id": university_id, "target_period_id": period_id}
        denied = client.get("/api/v1/institutional/demand", headers=student_auth,
                            params=demand_params)
        assert denied.status_code == 403
        aggregate = client.get("/api/v1/institutional/demand",
            headers={"Authorization": f"Bearer {analyst_token}"}, params=demand_params)
        assert aggregate.status_code == 200, aggregate.text
        payload = aggregate.json()
        assert payload["status"] == "SUPPRESSED" and payload["metrics"] == []
        assert "owner_user_id" not in str(payload)
        withdrawn = client.post("/api/v1/me/mock-registration/withdrawals",
            headers=student_auth, json={"target_period_id": period_id,
                "expected_current_revision": 1,
                "transparency_notice_version": "synthetic-notice:v1"})
        assert withdrawn.status_code == 201 and withdrawn.json()["lifecycle_status"] == "WITHDRAWN"
        with httpx.Client(timeout=30) as raw:
            later = raw.get(f"{URL}/rest/v1/mock_registration_intent_revisions",
                headers=_server_headers(), params={"select": "id", "owner_user_id": f"eq.{student_id}",
                    "target_period_id": f"eq.{period_id}", "revision": "eq.2"}).json()
            assert len(later) == 1
            no_artifact = raw.get(f"{URL}/rest/v1/p6_submit_replay_artifacts",
                headers=_server_headers(), params={"select": "revision_id",
                    "revision_id": f"eq.{later[0]['id']}"}).json()
            assert no_artifact == []


async def verify_historical_after_drift(revision_id, university_id):
    outbox = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    ledger = SupabaseDecisionTraceRepository(URL, SERVER_KEY)
    revisions = SupabaseMockRegistrationRepository(URL, SERVER_KEY)
    try:
        return await P6HistoricalReplayService(revisions, ledger, outbox).verify(revision_id)
    finally:
        await outbox.close()
        await ledger.close()
        await revisions.close()
