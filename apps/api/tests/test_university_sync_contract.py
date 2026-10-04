from __future__ import annotations

import hashlib
import hmac
import json
import asyncio

import httpx
from pydantic import SecretStr
from app.core.config import settings
from app.university_sync.client import HttpUniversityOfferingProvider, UniversityContractClient
from app.university_sync.event_routes import student_scope_from_email, verify_signature
from app.university_sync.events import UniversityEventStore


def test_signature_accepts_only_exact_body_and_secret() -> None:
    body = b'{"id":"event"}'
    signature = "sha256=" + hmac.new(b"dev-secret", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, signature, "dev-secret")
    assert not verify_signature(body + b" ", signature, "dev-secret")
    assert not verify_signature(body, signature, "different-secret")
    assert not verify_signature(body, None, "dev-secret")


def test_student_scope_is_derived_from_verified_account_email() -> None:
    assert student_scope_from_email("202510004@std.morshidi.edu.jo") == "202510004"
    for email in ("202510004@other.example", None):
        try:
            student_scope_from_email(email)
        except Exception:
            continue
        raise AssertionError("invalid student scope was accepted")


def test_notification_query_is_scoped_to_one_student_and_global_announcements() -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        store = UniversityEventStore("https://db.example", "private-test-key", client)
        asyncio.run(store.list_notifications("202510004"))
    finally:
        asyncio.run(client.aclose())

    assert captured["or"] == "(student_id.eq.202510004,student_id.is.null)"
    assert captured["order"] == "created_at.desc,id.desc"


def test_event_ingestion_forwards_envelope_to_transactional_rpc() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"duplicate": False, "applied": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        store = UniversityEventStore("https://db.example", "private-test-key", client)
        event = {"id": "9d5e9478-801a-4b4d-a9b1-0d49555f3273", "type": "grade.posted",
                 "version": 2, "occurredAt": "2026-10-04T10:00:00Z", "studentId": "202510004",
                 "payload": {"courseCode": "CS101"}, "idempotencyKey": "grade-202510004-1"}
        result = asyncio.run(store.ingest(event))
    finally:
        asyncio.run(client.aclose())

    assert str(captured["url"]).endswith("/rpc/ingest_university_event")
    assert captured["payload"] == {"p_event": event}
    assert result == {"duplicate": False, "applied": True}


def test_live_provider_uses_calendar_uuid_mapping_and_preserves_synthetic_provenance(monkeypatch) -> None:
    monkeypatch.setattr(settings, "uni_base_url", "https://uni.example")
    monkeypatch.setattr(settings, "uni_service_key", SecretStr("server-only-test-key"))
    monkeypatch.setattr(settings, "uni_university_id", "4c5e6d99-6a19-4cee-9c30-c12c61308e85")
    monkeypatch.setattr(settings, "supabase_url", "https://db.example")
    monkeypatch.setattr(settings, "supabase_secret_key", SecretStr("db-server-only-test-key"))

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/calendar"):
            return httpx.Response(200, json={"currentTerm": {"code": "2026-1", "label": "الفصل الأول"}})
        if request.url.path.endswith("/v1/manifest"):
            return httpx.Response(200, json={"schema_version": "1.0.0", "synthetic": True})
        if request.url.path.endswith("/v1/offerings"):
            return httpx.Response(200, json=[{"id": "section-1", "course_code": "CS101", "status": "متاحة",
                "days_array": ["الأحد"], "start_time": "08:00", "end_time": "09:30", "capacity": 20, "enrolled": 7}])
        if request.url.path.endswith("/mock_registration_target_periods"):
            assert request.url.params["id"] == "eq.7e475e14-94c8-4a1c-8592-44cf564cb925"
            assert request.url.params["period_key"] == "eq.2026-1"
            return httpx.Response(200, json=[{"id": "7e475e14-94c8-4a1c-8592-44cf564cb925",
                "period_key": "2026-1", "source_version": "uni-v1"}])
        raise AssertionError(f"unexpected contract request: {request.url.path}")

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            contract = UniversityContractClient(client)
            provider = HttpUniversityOfferingProvider(contract, settings.uni_university_id)
            return await provider.load_snapshot(settings.uni_university_id,
                "7e475e14-94c8-4a1c-8592-44cf564cb925")
        finally:
            await client.aclose()

    snapshot = asyncio.run(run())
    assert snapshot is not None
    assert snapshot.source_type.value == "SYNTHETIC"
    assert "SYNTHETIC" in snapshot.provenance
    assert snapshot.sections[0].available == 13
