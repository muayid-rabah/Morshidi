"""P8 WC-038 Local Supabase integration tests for policy persistence & provider.

Validates:
1. insert verified document/version/passages through trusted setup
2. verified source retrieval
3. unverified excluded
4. pending_review excluded
5. withdrawn excluded
6. superseded not silently substituted
7. exact version retrieval
8. exact citation locator preserved
9. deterministic passage ordering
10. cross-university isolation
11. client roles cannot mutate
12. service_role trusted access works
13. invalid effective date range rejected
14. duplicate document/version identity rejected
15. citation references the same exact version actually retrieved
"""

from __future__ import annotations

import datetime
import hashlib
import os
from uuid import uuid4

import httpx
import pytest

from app.institutional_policy import (
    CitationAnchor,
    GroundingStatus,
    LimitationCode,
    PolicyAuthorityLevel,
    PolicyCategory,
    PolicyErrorCode,
    PolicyPassage,
    PolicyRetrievalError,
    PolicyRetrievalQuery,
    SourceAdmissionStatus,
    SupabaseInstitutionalPolicyProvider,
)

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


def _anon_headers() -> dict[str, str]:
    return {
        "apikey": ANON_KEY or "",
        "Authorization": f"Bearer {ANON_KEY or ''}",
        "Content-Type": "application/json",
    }


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "apikey": ANON_KEY or "",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _create_user(client: httpx.Client, label: str) -> tuple[str, str]:
    password = f"P8-local-{uuid4()}-Aa1!"
    email = f"p8-policy-{label}-{uuid4()}@local.test"
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


def _get_university_id(client: httpx.Client) -> str:
    res = client.post(
        f"{URL}/rest/v1/universities",
        headers=_server_headers(),
        json={
            "name_ar": f"جامعة تجريبية {uuid4().hex[:6]}",
            "name_en": f"Test University {uuid4().hex[:6]}",
            "country": "Jordan",
            "active": True,
        },
    )
    res.raise_for_status()
    return res.json()[0]["id"]


def _create_foreign_university(client: httpx.Client) -> str:
    res = client.post(
        f"{URL}/rest/v1/universities",
        headers=_server_headers(),
        json={
            "name_ar": f"جامعة تجريبية {uuid4().hex[:6]}",
            "name_en": f"Foreign University {uuid4().hex[:6]}",
            "country": "Jordan",
            "active": True,
        },
    )
    res.raise_for_status()
    return res.json()[0]["id"]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# 1. Insert verified document/version/passages through trusted setup
def test_01_insert_verified_document_version_passages_through_trusted_setup():
    with httpx.Client() as client:
        uni_id = _get_university_id(client)
        code = f"REG-TEST-{uuid4().hex[:8]}"

        doc_res = client.post(
            f"{URL}/rest/v1/policy_documents",
            headers=_server_headers(),
            json={
                "university_id": uni_id,
                "document_code": code,
                "title": "تعليمات التسجيل واختيار المقررات",
                "authority_level": "university_council",
                "category": "registration_regulations",
                "language": "ar",
            },
        )
        assert doc_res.status_code == 201, doc_res.text
        doc_id = doc_res.json()[0]["id"]

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ver_res = client.post(
            f"{URL}/rest/v1/policy_document_versions",
            headers=_server_headers(),
            json={
                "document_id": doc_id,
                "version_tag": "v2026.1",
                "effective_start_date": now_iso,
                "content_sha256": _sha256("نص وثيقة تعليمات التسجيل الكاملة"),
                "status": "verified",
                "verified_at": now_iso,
                "verified_by": "dean_of_admissions",
            },
        )
        assert ver_res.status_code == 201, ver_res.text
        ver_id = ver_res.json()[0]["id"]

        passage_text = "يجوز للطالب تسجيل 18 ساعة كحد أقصى في الفصل الدراسي الاعتيادي."
        pas_res = client.post(
            f"{URL}/rest/v1/policy_passages",
            headers=_server_headers(),
            json={
                "version_id": ver_id,
                "passage_text": passage_text,
                "locator_text": "المادة 5، الفقرة أ",
                "article_number": "5",
                "section_number": "أ",
                "page_number": 12,
                "heading": "الحد الأقصى للعبء الدراسي",
                "sequence_order": 1,
                "passage_sha256": _sha256(passage_text),
            },
        )
        assert pas_res.status_code == 201, pas_res.text
        assert pas_res.json()[0]["version_id"] == ver_id


# 2. Verified source retrieval via SupabaseInstitutionalPolicyProvider
@pytest.mark.anyio
async def test_02_verified_source_retrieval():
    async with httpx.AsyncClient() as http_client:
        uni_id = _get_university_id(httpx.Client())
        code = f"REG-LOAD-{uuid4().hex[:8]}"

        # Setup data
        with httpx.Client() as sync_client:
            doc = sync_client.post(
                f"{URL}/rest/v1/policy_documents",
                headers=_server_headers(),
                json={
                    "university_id": uni_id,
                    "document_code": code,
                    "title": "لائحة الإنذار الأكاديمي",
                    "authority_level": "dean_council",
                    "category": "academic_bylaws",
                    "language": "ar",
                },
            ).json()[0]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ver = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc["id"],
                    "version_tag": "v1.0",
                    "effective_start_date": now_iso,
                    "content_sha256": _sha256("نص لائحة الإنذار"),
                    "status": "verified",
                    "verified_at": now_iso,
                    "verified_by": "academic_affairs",
                },
            ).json()[0]
            sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver["id"],
                    "passage_text": "يوضع الطالب تحت الإنذار الأكاديمي إذا قل معدله التراكمي عن نقطتين.",
                    "locator_text": "المادة 20، ص 30",
                    "article_number": "20",
                    "page_number": 30,
                    "sequence_order": 1,
                },
            )

        provider = SupabaseInstitutionalPolicyProvider(
            supabase_url=URL, server_key=SERVER_KEY, client=http_client
        )
        query = PolicyRetrievalQuery(
            query_text="ما هي شروط الإنذار الأكاديمي للطالب؟",
            university_id=uni_id,
            max_passages=5,
        )
        result = await provider.retrieve_passages(query)
        assert result.grounding_status == GroundingStatus.GROUNDED
        assert len(result.passages) > 0
        assert "الإنذار الأكاديمي" in result.passages[0].content
        assert len(result.citations) > 0
        assert result.citations[0].title == "لائحة الإنذار الأكاديمي"


# 3. Unverified excluded
@pytest.mark.anyio
async def test_03_unverified_source_excluded():
    async with httpx.AsyncClient() as http_client:
        uni_id = _get_university_id(httpx.Client())
        code = f"REG-UNVER-{uuid4().hex[:8]}"

        with httpx.Client() as sync_client:
            doc = sync_client.post(
                f"{URL}/rest/v1/policy_documents",
                headers=_server_headers(),
                json={
                    "university_id": uni_id,
                    "document_code": code,
                    "title": "مسودة لائحة غير معتمدة",
                    "authority_level": "department_council",
                    "category": "academic_bylaws",
                },
            ).json()[0]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ver = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc["id"],
                    "version_tag": "draft-0.1",
                    "effective_start_date": now_iso,
                    "content_sha256": _sha256("مسودة نص غير معتمد"),
                    "status": "unverified",
                },
            ).json()[0]
            sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver["id"],
                    "passage_text": "يجوز تجاوز المتطلب السابق بموافقة شفهية في المسودة فقط.",
                    "locator_text": "المادة مسودة 1",
                    "sequence_order": 1,
                },
            )

        provider = SupabaseInstitutionalPolicyProvider(
            supabase_url=URL, server_key=SERVER_KEY, client=http_client
        )
        q = PolicyRetrievalQuery(
            query_text="تجاوز المتطلب السابق موافقة شفهية",
            university_id=uni_id,
            specific_version_tag="draft-0.1",
        )
        r = await provider.retrieve_passages(q)
        assert r.grounding_status == GroundingStatus.UNVERIFIED_SOURCE
        assert any(lim.code == LimitationCode.UNVERIFIED_SOURCE_REJECTED for lim in r.limitations)


# 4. Pending review excluded
@pytest.mark.anyio
async def test_04_pending_review_excluded():
    async with httpx.AsyncClient() as http_client:
        uni_id = _get_university_id(httpx.Client())
        code = f"REG-PEND-{uuid4().hex[:8]}"

        with httpx.Client() as sync_client:
            doc = sync_client.post(
                f"{URL}/rest/v1/policy_documents",
                headers=_server_headers(),
                json={
                    "university_id": uni_id,
                    "document_code": code,
                    "title": "تعليمات قيد المراجعة الإدارية",
                    "authority_level": "dean_council",
                    "category": "examination_regulations",
                },
            ).json()[0]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ver = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc["id"],
                    "version_tag": "review-2026",
                    "effective_start_date": now_iso,
                    "content_sha256": _sha256("تعليمات معلقة"),
                    "status": "pending_review",
                },
            ).json()[0]
            sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver["id"],
                    "passage_text": "إعادة تصحيح ورقة الامتحان تخضع لرسوم قيد المراجعة.",
                    "locator_text": "المادة مراجعة 5",
                    "sequence_order": 1,
                },
            )

        provider = SupabaseInstitutionalPolicyProvider(
            supabase_url=URL, server_key=SERVER_KEY, client=http_client
        )
        q = PolicyRetrievalQuery(
            query_text="إعادة تصحيح ورقة الامتحان",
            university_id=uni_id,
            specific_version_tag="review-2026",
        )
        r = await provider.retrieve_passages(q)
        assert r.grounding_status == GroundingStatus.UNVERIFIED_SOURCE
        assert any(lim.code == LimitationCode.PENDING_REVIEW_HELD for lim in r.limitations)


# 5. Withdrawn excluded
@pytest.mark.anyio
async def test_05_withdrawn_excluded():
    async with httpx.AsyncClient() as http_client:
        uni_id = _get_university_id(httpx.Client())
        code = f"REG-WITH-{uuid4().hex[:8]}"

        with httpx.Client() as sync_client:
            doc = sync_client.post(
                f"{URL}/rest/v1/policy_documents",
                headers=_server_headers(),
                json={
                    "university_id": uni_id,
                    "document_code": code,
                    "title": "تعليمات ملغاة رسمياً",
                    "authority_level": "university_council",
                    "category": "disciplinary_bylaws",
                },
            ).json()[0]
            ver = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc["id"],
                    "version_tag": "v1999-revoked",
                    "effective_start_date": "1999-01-01T00:00:00Z",
                    "effective_end_date": "2020-01-01T00:00:00Z",
                    "content_sha256": _sha256("نص ملغي"),
                    "status": "withdrawn",
                },
            ).json()[0]
            sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver["id"],
                    "passage_text": "عقوبة الفصل النهائي لعدم تسديد الرسوم تم إلغاؤها.",
                    "locator_text": "المادة 99",
                    "sequence_order": 1,
                },
            )

        provider = SupabaseInstitutionalPolicyProvider(
            supabase_url=URL, server_key=SERVER_KEY, client=http_client
        )
        q = PolicyRetrievalQuery(
            query_text="عقوبة الفصل النهائي الرسوم",
            university_id=uni_id,
            specific_version_tag="v1999-revoked",
        )
        r = await provider.retrieve_passages(q)
        assert r.grounding_status == GroundingStatus.UNAVAILABLE_SOURCE
        assert any(lim.code == LimitationCode.WITHDRAWN_SOURCE_EXCLUDED for lim in r.limitations)


# 6. Superseded not silently substituted
@pytest.mark.anyio
async def test_06_superseded_not_silently_substituted():
    async with httpx.AsyncClient() as http_client:
        uni_id = _get_university_id(httpx.Client())
        code = f"REG-HIST-{uuid4().hex[:8]}"

        with httpx.Client() as sync_client:
            doc = sync_client.post(
                f"{URL}/rest/v1/policy_documents",
                headers=_server_headers(),
                json={
                    "university_id": uni_id,
                    "document_code": code,
                    "title": "تعليمات الانتقال القديمة",
                    "authority_level": "dean_council",
                    "category": "credit_transfer_rules",
                },
            ).json()[0]
            ver_old = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc["id"],
                    "version_tag": "v2020.1",
                    "effective_start_date": "2020-01-01T00:00:00Z",
                    "effective_end_date": "2025-01-01T00:00:00Z",
                    "content_sha256": _sha256("نص قديم تم استبداله"),
                    "status": "superseded",
                },
            ).json()[0]
            sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver_old["id"],
                    "passage_text": "يجوز معادلة 50 بالمئة من ساعات الانتقال من جامعة أخرى في النظام القديم.",
                    "locator_text": "المادة 15 القديمة",
                    "sequence_order": 1,
                },
            )

        provider = SupabaseInstitutionalPolicyProvider(
            supabase_url=URL, server_key=SERVER_KEY, client=http_client
        )
        q = PolicyRetrievalQuery(
            query_text="معادلة ساعات الانتقال من جامعة أخرى",
            university_id=uni_id,
        )
        r = await provider.retrieve_passages(q)
        assert r.grounding_status != GroundingStatus.GROUNDED or all(
            p.status != SourceAdmissionStatus.SUPERSEDED for p in r.passages
        )


# 7. Exact version retrieval
@pytest.mark.anyio
async def test_07_exact_version_retrieval():
    async with httpx.AsyncClient() as http_client:
        uni_id = _get_university_id(httpx.Client())
        code = f"REG-VERS-{uuid4().hex[:8]}"

        with httpx.Client() as sync_client:
            doc = sync_client.post(
                f"{URL}/rest/v1/policy_documents",
                headers=_server_headers(),
                json={
                    "university_id": uni_id,
                    "document_code": code,
                    "title": "تعليمات الامتحانات المتعددة الإصدارات",
                    "authority_level": "dean_council",
                    "category": "examination_regulations",
                },
            ).json()[0]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ver1 = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc["id"],
                    "version_tag": "v1.0",
                    "effective_start_date": now_iso,
                    "content_sha256": _sha256("إصدار 1"),
                    "status": "verified",
                    "verified_at": now_iso,
                    "verified_by": "exam_board",
                },
            ).json()[0]
            ver2 = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc["id"],
                    "version_tag": "v2.0",
                    "effective_start_date": now_iso,
                    "content_sha256": _sha256("إصدار 2"),
                    "status": "verified",
                    "verified_at": now_iso,
                    "verified_by": "exam_board",
                },
            ).json()[0]
            sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver1["id"],
                    "passage_text": "علامة النجاح في المقرر هي 50 بالمئة في الإصدار الأول.",
                    "locator_text": "المادة 1 ف1",
                    "sequence_order": 1,
                },
            )
            sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver2["id"],
                    "passage_text": "علامة النجاح في المقرر هي 60 بالمئة في الإصدار الثاني.",
                    "locator_text": "المادة 1 ف2",
                    "sequence_order": 1,
                },
            )

        provider = SupabaseInstitutionalPolicyProvider(
            supabase_url=URL, server_key=SERVER_KEY, client=http_client
        )
        q = PolicyRetrievalQuery(
            query_text="علامة النجاح في المقرر",
            university_id=uni_id,
            specific_version_tag="v2.0",
        )
        r = await provider.retrieve_passages(q)
        assert r.grounding_status == GroundingStatus.GROUNDED
        assert len(r.passages) == 1
        assert r.passages[0].version_tag == "v2.0"
        assert "60 بالمئة" in r.passages[0].content


# 8. Exact citation locator preserved
@pytest.mark.anyio
async def test_08_exact_citation_locator_preserved():
    async with httpx.AsyncClient() as http_client:
        uni_id = _get_university_id(httpx.Client())
        code = f"REG-CITE-{uuid4().hex[:8]}"

        with httpx.Client() as sync_client:
            doc = sync_client.post(
                f"{URL}/rest/v1/policy_documents",
                headers=_server_headers(),
                json={
                    "university_id": uni_id,
                    "document_code": code,
                    "title": "لائحة التخرج ومنح الدرجات العلمية",
                    "authority_level": "university_council",
                    "category": "graduation_requirements",
                },
            ).json()[0]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ver = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc["id"],
                    "version_tag": "v2026-final",
                    "effective_start_date": now_iso,
                    "content_sha256": _sha256("شروط التخرج"),
                    "status": "verified",
                    "verified_at": now_iso,
                    "verified_by": "council_secretary",
                },
            ).json()[0]
            pas = sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver["id"],
                    "passage_text": "يمنح الطالب درجة البكالوريوس عند إتمام جميع متطلبات الخطة بنجاح.",
                    "locator_text": "الباب الثالث، المادة 45، فقرة ج، ص 88",
                    "article_number": "45",
                    "section_number": "ج",
                    "page_number": 88,
                    "heading": "شروط منح الدرجة",
                    "sequence_order": 1,
                },
            ).json()[0]

        provider = SupabaseInstitutionalPolicyProvider(
            supabase_url=URL, server_key=SERVER_KEY, client=http_client
        )
        q = PolicyRetrievalQuery(
            query_text="شروط منح درجة البكالوريوس",
            university_id=uni_id,
        )
        r = await provider.retrieve_passages(q)
        assert r.grounding_status == GroundingStatus.GROUNDED
        assert len(r.citations) >= 1
        citation = r.citations[0]
        assert citation.locator == "الباب الثالث، المادة 45، فقرة ج، ص 88"
        assert citation.version_tag == "v2026-final"
        assert citation.title == "لائحة التخرج ومنح الدرجات العلمية"


# 9. Deterministic passage ordering
@pytest.mark.anyio
async def test_09_deterministic_passage_ordering():
    async with httpx.AsyncClient() as http_client:
        uni_id = _get_university_id(httpx.Client())
        code = f"REG-ORDER-{uuid4().hex[:8]}"

        with httpx.Client() as sync_client:
            doc = sync_client.post(
                f"{URL}/rest/v1/policy_documents",
                headers=_server_headers(),
                json={
                    "university_id": uni_id,
                    "document_code": code,
                    "title": "تعليمات مرتبة تسلسلياً",
                    "authority_level": "dean_council",
                    "category": "academic_bylaws",
                },
            ).json()[0]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ver = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc["id"],
                    "version_tag": "v1.0",
                    "effective_start_date": now_iso,
                    "content_sha256": _sha256("نص مرتب"),
                    "status": "verified",
                    "verified_at": now_iso,
                    "verified_by": "secretary",
                },
            ).json()[0]
            # Insert out of sequence order
            sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver["id"],
                    "passage_text": "الفقرة الثالثة في تسلسل الأحكام التعليمية.",
                    "locator_text": "المادة 3",
                    "sequence_order": 3,
                },
            )
            sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver["id"],
                    "passage_text": "الفقرة الأولى في تسلسل الأحكام التعليمية.",
                    "locator_text": "المادة 1",
                    "sequence_order": 1,
                },
            )
            sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver["id"],
                    "passage_text": "الفقرة الثانية في تسلسل الأحكام التعليمية.",
                    "locator_text": "المادة 2",
                    "sequence_order": 2,
                },
            )

        provider = SupabaseInstitutionalPolicyProvider(
            supabase_url=URL, server_key=SERVER_KEY, client=http_client
        )
        q = PolicyRetrievalQuery(
            query_text="تسلسل الأحكام التعليمية",
            university_id=uni_id,
        )
        r1 = await provider.retrieve_passages(q)
        r2 = await provider.retrieve_passages(q)
        assert len(r1.passages) == 3
        assert len(r2.passages) == 3
        # Check identical ordering
        assert [p.passage_id for p in r1.passages] == [p.passage_id for p in r2.passages]


# 10. Cross-university isolation
@pytest.mark.anyio
async def test_10_cross_university_isolation():
    async with httpx.AsyncClient() as http_client:
        with httpx.Client() as sync_client:
            uni_a = _get_university_id(sync_client)
            uni_b = _create_foreign_university(sync_client)

            doc_b = sync_client.post(
                f"{URL}/rest/v1/policy_documents",
                headers=_server_headers(),
                json={
                    "university_id": uni_b,
                    "document_code": f"REG-UNI-B-{uuid4().hex[:6]}",
                    "title": "تعليمات خاصة بالجامعة الثانية فقط",
                    "authority_level": "university_council",
                    "category": "academic_bylaws",
                },
            ).json()[0]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ver_b = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc_b["id"],
                    "version_tag": "v1.0",
                    "effective_start_date": now_iso,
                    "content_sha256": _sha256("سري للجامعة ب"),
                    "status": "verified",
                    "verified_at": now_iso,
                    "verified_by": "uni_b_dean",
                },
            ).json()[0]
            pas_b = sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver_b["id"],
                    "passage_text": "مكافأة التفوق حصرية لطلاب الجامعة الثانية حصراً.",
                    "locator_text": "المادة ب 1",
                    "sequence_order": 1,
                },
            ).json()[0]

        provider = SupabaseInstitutionalPolicyProvider(
            supabase_url=URL, server_key=SERVER_KEY, client=http_client
        )
        # Querying with University A tenant must NOT return University B passages
        q = PolicyRetrievalQuery(
            query_text="مكافأة التفوق حصرية",
            university_id=uni_a,
        )
        r = await provider.retrieve_passages(q)
        assert r.grounding_status == GroundingStatus.NO_EVIDENCE

        # Cross-tenant get_citation attempt fails closed
        anchor = CitationAnchor(
            anchor_id=f"anchor-{pas_b['id']}",
            document_id=doc_b["id"],
            version_tag="v1.0",
            locator_text=pas_b["locator_text"],
        )
        p_obj = PolicyPassage(
            passage_id=pas_b["id"],
            document_id=doc_b["id"],
            version_tag="v1.0",
            university_id=uni_b,
            anchor=anchor,
            content=pas_b["passage_text"],
            content_sha256=_sha256(pas_b["passage_text"]),
        )
        with pytest.raises(PolicyRetrievalError) as exc_info:
            await provider.get_citation(uni_a, p_obj)
        assert exc_info.value.code == PolicyErrorCode.UNAUTHORIZED_TENANT


# 11. Client roles cannot mutate
def test_11_client_roles_cannot_mutate():
    with httpx.Client() as client:
        uni_id = _get_university_id(client)
        _student_id, student_token = _create_user(client, "student")

        # 1. Anon attempts INSERT on policy_documents
        res_anon = client.post(
            f"{URL}/rest/v1/policy_documents",
            headers=_anon_headers(),
            json={
                "university_id": uni_id,
                "document_code": f"MALICIOUS-{uuid4().hex[:6]}",
                "title": "تسلل غير مصرح به",
                "authority_level": "dean_council",
                "category": "academic_bylaws",
            },
        )
        # Must be rejected (401 or 403 or RLS empty response)
        assert res_anon.status_code in (401, 403), f"Anon mutation not denied: {res_anon.text}"

        # 2. Authenticated user attempts INSERT on policy_documents
        res_auth = client.post(
            f"{URL}/rest/v1/policy_documents",
            headers=_auth_headers(student_token),
            json={
                "university_id": uni_id,
                "document_code": f"STUDENT-MALICIOUS-{uuid4().hex[:6]}",
                "title": "تسلل طالب",
                "authority_level": "dean_council",
                "category": "academic_bylaws",
            },
        )
        assert res_auth.status_code in (401, 403), f"Auth mutation not denied: {res_auth.text}"

        # 3. Authenticated user attempts DELETE on policy_passages
        res_del = client.delete(
            f"{URL}/rest/v1/policy_passages",
            headers=_auth_headers(student_token),
            params={"id": "gt.00000000-0000-0000-0000-000000000000"},
        )
        assert res_del.status_code in (401, 403), f"Auth delete not denied: {res_del.text}"


# 12. Service role trusted access works
def test_12_service_role_trusted_access_works():
    with httpx.Client() as client:
        uni_id = _get_university_id(client)
        code = f"REG-SRV-{uuid4().hex[:8]}"

        doc = client.post(
            f"{URL}/rest/v1/policy_documents",
            headers=_server_headers(),
            json={
                "university_id": uni_id,
                "document_code": code,
                "title": "وثيقة الخدمة الموثوقة",
                "authority_level": "department_council",
                "category": "academic_bylaws",
            },
        ).json()[0]

        read_res = client.get(
            f"{URL}/rest/v1/policy_documents",
            headers=_server_headers(),
            params={"id": f"eq.{doc['id']}"},
        )
        assert read_res.status_code == 200
        assert len(read_res.json()) == 1

        del_res = client.delete(
            f"{URL}/rest/v1/policy_documents",
            headers=_server_headers(),
            params={"id": f"eq.{doc['id']}"},
        )
        assert del_res.status_code in (200, 204)


# 13. Invalid effective date range rejected
def test_13_invalid_effective_date_range_rejected():
    with httpx.Client() as client:
        uni_id = _get_university_id(client)
        doc = client.post(
            f"{URL}/rest/v1/policy_documents",
            headers=_server_headers(),
            json={
                "university_id": uni_id,
                "document_code": f"DATE-TEST-{uuid4().hex[:6]}",
                "title": "فحص التاريخ",
                "authority_level": "dean_council",
                "category": "academic_bylaws",
            },
        ).json()[0]

        bad_res = client.post(
            f"{URL}/rest/v1/policy_document_versions",
            headers=_server_headers(),
            json={
                "document_id": doc["id"],
                "version_tag": "v-bad-dates",
                "effective_start_date": "2026-06-01T00:00:00Z",
                "effective_end_date": "2026-01-01T00:00:00Z",
                "content_sha256": _sha256("تاريخ خاطئ"),
                "status": "unverified",
            },
        )
        assert bad_res.status_code in (400, 422), f"Invalid date range should be rejected: {bad_res.text}"


# 14. Duplicate document/version identity rejected
def test_14_duplicate_document_version_identity_rejected():
    with httpx.Client() as client:
        uni_id = _get_university_id(client)
        doc = client.post(
            f"{URL}/rest/v1/policy_documents",
            headers=_server_headers(),
            json={
                "university_id": uni_id,
                "document_code": f"DUP-TEST-{uuid4().hex[:6]}",
                "title": "فحص التكرار",
                "authority_level": "dean_council",
                "category": "academic_bylaws",
            },
        ).json()[0]
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        first_res = client.post(
            f"{URL}/rest/v1/policy_document_versions",
            headers=_server_headers(),
            json={
                "document_id": doc["id"],
                "version_tag": "v1.0",
                "effective_start_date": now_iso,
                "content_sha256": _sha256("الأصل"),
                "status": "verified",
                "verified_at": now_iso,
                "verified_by": "verifier",
            },
        )
        assert first_res.status_code == 201

        dup_res = client.post(
            f"{URL}/rest/v1/policy_document_versions",
            headers=_server_headers(),
            json={
                "document_id": doc["id"],
                "version_tag": "v1.0",
                "effective_start_date": now_iso,
                "content_sha256": _sha256("مكرر"),
                "status": "unverified",
            },
        )
        assert dup_res.status_code in (400, 409), f"Duplicate version should be rejected: {dup_res.text}"


# 15. Citation references the same exact version actually retrieved
@pytest.mark.anyio
async def test_15_citation_references_the_same_exact_version_actually_retrieved():
    async with httpx.AsyncClient() as http_client:
        uni_id = _get_university_id(httpx.Client())
        code = f"REG-MATCH-{uuid4().hex[:8]}"

        with httpx.Client() as sync_client:
            doc = sync_client.post(
                f"{URL}/rest/v1/policy_documents",
                headers=_server_headers(),
                json={
                    "university_id": uni_id,
                    "document_code": code,
                    "title": "تعليمات مطابقة الاقتباس الدقيق",
                    "authority_level": "university_council",
                    "category": "academic_bylaws",
                },
            ).json()[0]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ver = sync_client.post(
                f"{URL}/rest/v1/policy_document_versions",
                headers=_server_headers(),
                json={
                    "document_id": doc["id"],
                    "version_tag": "v2026.exact",
                    "effective_start_date": now_iso,
                    "content_sha256": _sha256("نص مطابقة تام"),
                    "status": "verified",
                    "verified_at": now_iso,
                    "verified_by": "board",
                },
            ).json()[0]
            pas = sync_client.post(
                f"{URL}/rest/v1/policy_passages",
                headers=_server_headers(),
                json={
                    "version_id": ver["id"],
                    "passage_text": "قاعدة مطابقة مرجع الاقتباس مع النسخة المسترجعة دون تباين.",
                    "locator_text": "المادة 111",
                    "sequence_order": 1,
                },
            ).json()[0]

        provider = SupabaseInstitutionalPolicyProvider(
            supabase_url=URL, server_key=SERVER_KEY, client=http_client
        )
        q = PolicyRetrievalQuery(
            query_text="قاعدة مطابقة مرجع الاقتباس",
            university_id=uni_id,
        )
        res = await provider.retrieve_passages(q)
        assert res.grounding_status == GroundingStatus.GROUNDED
        assert len(res.passages) == 1
        assert len(res.citations) == 1
        p = res.passages[0]
        c = res.citations[0]
        assert p.version_tag == "v2026.exact"
        assert c.version_tag == "v2026.exact"
        assert c.document_id == p.document_id
        assert c.locator == p.anchor.locator_text

        # Calling get_citation on a passage with mismatched anchor raises MISMATCHED_CITATION
        mismatched_anchor = CitationAnchor(
            anchor_id="anchor-fake",
            document_id=p.document_id,
            version_tag="v_DIFFERENT",  # Mismatched version
            locator_text=p.anchor.locator_text,
        )
        corrupt_passage = PolicyPassage(
            passage_id=p.passage_id,
            document_id=p.document_id,
            version_tag=p.version_tag,
            university_id=p.university_id,
            anchor=p.anchor,
            content=p.content,
            content_sha256=p.content_sha256,
        )
        object.__setattr__(corrupt_passage, "anchor", mismatched_anchor)
        with pytest.raises(PolicyRetrievalError) as exc_info:
            await provider.get_citation(uni_id, corrupt_passage)
        assert exc_info.value.code == PolicyErrorCode.MISMATCHED_CITATION
