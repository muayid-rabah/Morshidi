"""Opt-in real local Supabase integration tests for atomic policy ingestion RPC (WC-038).

These tests run only when local Supabase credentials are configured via:
    MORSHIDI_LOCAL_SUPABASE_URL
    MORSHIDI_LOCAL_SUPABASE_SERVER_KEY
    MORSHIDI_LOCAL_SUPABASE_ANON_KEY
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
import httpx
import pytest

from app.institutional_policy.enums import (
    PolicyAuthorityLevel,
    PolicyCategory,
    SourceAdmissionStatus,
)
from app.institutional_policy.ingestion import (
    PolicyConflictError,
    PolicyDocumentIngestionInput,
    PolicyIngestionError,
    PolicyPassageIngestionInput,
    SupabasePolicyIngestionStorage,
    TenantViolationError,
)

URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
SERVER_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
ANON_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_ANON_KEY")

pytestmark = pytest.mark.skipif(
    not all((URL, SERVER_KEY, ANON_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values to run integration tests",
)

# Known university ID from migrations
KNOWN_UNIV_ID = "10000000-0000-0000-0000-000000000001"


def _cleanup_policy(client: httpx.Client, doc_code: str) -> None:
    headers = {"apikey": SERVER_KEY or "", "Authorization": f"Bearer {SERVER_KEY}"}
    try:
        resp = client.get(
            f"{URL}/rest/v1/policy_documents?document_code=eq.{doc_code}",
            headers=headers,
        )
        if resp.status_code == 200:
            for doc in resp.json():
                d_id = doc["id"]
                v_resp = client.get(
                    f"{URL}/rest/v1/policy_document_versions?document_id=eq.{d_id}",
                    headers=headers,
                )
                if v_resp.status_code == 200:
                    for v in v_resp.json():
                        client.delete(
                            f"{URL}/rest/v1/policy_passages?version_id=eq.{v['id']}",
                            headers=headers,
                        )
                client.delete(
                    f"{URL}/rest/v1/policy_document_versions?document_id=eq.{d_id}",
                    headers=headers,
                )
                client.delete(
                    f"{URL}/rest/v1/policy_documents?id=eq.{d_id}",
                    headers=headers,
                )
    except Exception:
        pass


def test_atomic_persistence_creates_document_version_and_passages() -> None:
    async def run() -> None:
        doc_code = f"POL-TEST-{uuid.uuid4().hex[:8].upper()}"
        with httpx.Client(timeout=15.0) as http:
            _cleanup_policy(http, doc_code)

        async with httpx.AsyncClient(timeout=15.0) as client:
            storage = SupabasePolicyIngestionStorage(URL or "", SERVER_KEY or "", client=client)

            passages = [
                PolicyPassageIngestionInput(
                    passage_text="المادة 1: تسري هذه التعليمات على جميع الطلبة في الجامعة.",
                    locator_text="المادة 1",
                    article_number="1",
                    sequence_order=0,
                ),
                PolicyPassageIngestionInput(
                    passage_text="المادة 2: الحد الأدنى للساعات المعتمدة في الفصل هو 12 ساعة.",
                    locator_text="المادة 2",
                    article_number="2",
                    sequence_order=1,
                ),
            ]

            payload = PolicyDocumentIngestionInput(
                university_id=KNOWN_UNIV_ID,
                document_code=doc_code,
                title="تعليمات الساعات المعتمدة التجريبية",
                authority_level=PolicyAuthorityLevel.UNIVERSITY_COUNCIL,
                category=PolicyCategory.ACADEMIC_BYLAWS,
                version_tag="1.0",
                status=SourceAdmissionStatus.VERIFIED,
                passages=passages,
            )

            res = await storage.persist_document_version(payload)
            assert res.created is True
            assert res.passage_count == 2
            assert res.status == "verified"
            assert res.document_id is not None
            assert res.version_id is not None

            # Verify in database directly
            headers = {"apikey": SERVER_KEY or "", "Authorization": f"Bearer {SERVER_KEY}"}
            p_resp = await client.get(
                f"{URL}/rest/v1/policy_passages?version_id=eq.{res.version_id}&order=sequence_order.asc",
                headers=headers,
            )
            assert p_resp.status_code == 200
            db_passages = p_resp.json()
            assert len(db_passages) == 2
            assert db_passages[0]["article_number"] == "1"
            assert db_passages[1]["article_number"] == "2"

        with httpx.Client(timeout=15.0) as http:
            _cleanup_policy(http, doc_code)

    asyncio.run(run())


def test_atomic_rollback_on_invalid_passage_leaves_no_records() -> None:
    async def run() -> None:
        doc_code = f"POL-ROLLBACK-{uuid.uuid4().hex[:8].upper()}"
        with httpx.Client(timeout=15.0) as http:
            _cleanup_policy(http, doc_code)

        async with httpx.AsyncClient(timeout=15.0) as client:
            storage = SupabasePolicyIngestionStorage(URL or "", SERVER_KEY or "", client=client)

            # Passage 1 is valid, but passage 2 violates DB check constraint (negative page_number)
            # Directly call RPC with raw body containing an invalid passage
            url = f"{URL}/rest/v1/rpc/persist_policy_document_version"
            headers = {"apikey": SERVER_KEY or "", "Authorization": f"Bearer {SERVER_KEY}"}
            rpc_body = {
                "p_university_id": KNOWN_UNIV_ID,
                "p_document_code": doc_code,
                "p_title": "وثيقة تفشل ذرياً",
                "p_authority_level": "university_council",
                "p_category": "academic_bylaws",
                "p_language": "ar",
                "p_version_tag": "1.0",
                "p_content_sha256": "f" * 64,
                "p_status": "verified",
                "p_verified_at": "2026-09-27T00:00:00Z",
                "p_verified_by": "Auditor",
                "p_passages": [
                    {
                        "passage_text": "نص المادة الأولى السليم",
                        "locator_text": "المادة 1",
                        "sequence_order": 0,
                    },
                    {
                        "passage_text": "نص المادة الثانية الذي سينتهك القيد",
                        "locator_text": "المادة 2",
                        "sequence_order": 1,
                        "page_number": -5,  # CHECK (page_number > 0) violation!
                    },
                ],
            }

            resp = await client.post(url, headers=headers, json=rpc_body)
            # Must fail with check constraint violation (PostgREST returns 400 or 409)
            assert resp.status_code in (400, 409)

            # CRITICAL VERIFICATION: Single-transaction atomicity!
            # Neither the document nor the version must exist in the database!
            doc_check = await client.get(
                f"{URL}/rest/v1/policy_documents?document_code=eq.{doc_code}",
                headers=headers,
            )
            assert doc_check.status_code == 200
            assert len(doc_check.json()) == 0, "Document must not exist after rollback!"

        with httpx.Client(timeout=15.0) as http:
            _cleanup_policy(http, doc_code)

    asyncio.run(run())


def test_idempotent_reingestion_returns_existing_version() -> None:
    async def run() -> None:
        doc_code = f"POL-IDEM-{uuid.uuid4().hex[:8].upper()}"
        with httpx.Client(timeout=15.0) as http:
            _cleanup_policy(http, doc_code)

        async with httpx.AsyncClient(timeout=15.0) as client:
            storage = SupabasePolicyIngestionStorage(URL or "", SERVER_KEY or "", client=client)

            passages = [
                PolicyPassageIngestionInput(
                    passage_text="المادة 1: نص متطابق للتكرار.",
                    locator_text="المادة 1",
                    sequence_order=0,
                )
            ]
            payload = PolicyDocumentIngestionInput(
                university_id=KNOWN_UNIV_ID,
                document_code=doc_code,
                title="وثيقة التكرار المتطابق",
                authority_level=PolicyAuthorityLevel.DEAN_COUNCIL,
                category=PolicyCategory.REGISTRATION_REGULATIONS,
                version_tag="1.0",
                status=SourceAdmissionStatus.VERIFIED,
                passages=passages,
            )

            # First ingestion
            res1 = await storage.persist_document_version(payload)
            assert res1.created is True

            # Second identical ingestion
            res2 = await storage.persist_document_version(payload)
            assert res2.created is False
            assert res2.version_id == res1.version_id
            assert res2.document_id == res1.document_id
            assert res2.passage_count == 1

        with httpx.Client(timeout=15.0) as http:
            _cleanup_policy(http, doc_code)

    asyncio.run(run())


def test_conflict_abort_without_modifying_version() -> None:
    async def run() -> None:
        doc_code = f"POL-CONF-{uuid.uuid4().hex[:8].upper()}"
        with httpx.Client(timeout=15.0) as http:
            _cleanup_policy(http, doc_code)

        async with httpx.AsyncClient(timeout=15.0) as client:
            storage = SupabasePolicyIngestionStorage(URL or "", SERVER_KEY or "", client=client)

            passages = [
                PolicyPassageIngestionInput(
                    passage_text="المادة 1: النص الأصلي.",
                    locator_text="المادة 1",
                    sequence_order=0,
                )
            ]
            payload1 = PolicyDocumentIngestionInput(
                university_id=KNOWN_UNIV_ID,
                document_code=doc_code,
                title="وثيقة التعارض",
                authority_level=PolicyAuthorityLevel.FACULTY_BOARD,
                category=PolicyCategory.EXAMINATION_REGULATIONS,
                version_tag="1.0",
                status=SourceAdmissionStatus.VERIFIED,
                passages=passages,
            )
            res1 = await storage.persist_document_version(payload1)
            assert res1.created is True

            # Differing content for the same version_tag
            payload2 = PolicyDocumentIngestionInput(
                university_id=KNOWN_UNIV_ID,
                document_code=doc_code,
                title="وثيقة التعارض",
                authority_level=PolicyAuthorityLevel.FACULTY_BOARD,
                category=PolicyCategory.EXAMINATION_REGULATIONS,
                version_tag="1.0",
                status=SourceAdmissionStatus.VERIFIED,
                content_sha256="0" * 64,  # Mismatched hash
                passages=passages,
            )

            with pytest.raises(PolicyConflictError):
                await storage.persist_document_version(payload2)

        with httpx.Client(timeout=15.0) as http:
            _cleanup_policy(http, doc_code)

    asyncio.run(run())


def test_invalid_university_rejected() -> None:
    async def run() -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            storage = SupabasePolicyIngestionStorage(URL or "", SERVER_KEY or "", client=client)

            payload = PolicyDocumentIngestionInput(
                university_id=str(uuid.uuid4()),  # Non-existent university
                document_code="POL-UNIV-FAIL",
                title="جامعة غير موجودة",
                authority_level="university_council",
                category="academic_bylaws",
                version_tag="1.0",
            )

            with pytest.raises(TenantViolationError):
                await storage.persist_document_version(payload)

    asyncio.run(run())


def test_unauthorized_roles_rejected() -> None:
    async def run() -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            url = f"{URL}/rest/v1/rpc/persist_policy_document_version"
            # 1. Anon role
            headers_anon = {"apikey": ANON_KEY or "", "Authorization": f"Bearer {ANON_KEY}"}
            r_anon = await client.post(
                url,
                headers=headers_anon,
                json={"p_university_id": KNOWN_UNIV_ID},
            )
            # PostgREST hides functions revoked from the role -> 404 Not Found or 401/403
            assert r_anon.status_code in (401, 403, 404)

            # 2. No token
            r_noauth = await client.post(url, json={"p_university_id": KNOWN_UNIV_ID})
            assert r_noauth.status_code in (401, 403, 404)

    asyncio.run(run())
