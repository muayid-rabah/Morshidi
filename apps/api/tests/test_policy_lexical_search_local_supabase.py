"""Real Local Supabase checks for the WC-038 backend-only lexical-search RPC."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
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

KNOWN_UNIVERSITY = "10000000-0000-0000-0000-000000000001"


def _headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def test_lexical_search_rpc_catalog_security_contract() -> None:
    """Inspect the actual Local Supabase catalog, not a mocked definition."""
    sql = """
    select p.prosecdef, coalesce(array_to_string(p.proconfig, ','), ''),
           has_function_privilege('public', p.oid, 'EXECUTE'),
           has_function_privilege('anon', p.oid, 'EXECUTE'),
           has_function_privilege('authenticated', p.oid, 'EXECUTE'),
           has_function_privilege('service_role', p.oid, 'EXECUTE')
      from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = 'search_verified_policy_passages'
    """
    completed = subprocess.run(
        ["docker", "exec", "supabase_db_Morshidi", "psql", "-U", "postgres", "-d", "postgres", "-At", "-F", "|", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = [line for line in completed.stdout.splitlines() if line]
    assert len(rows) == 1
    security_definer, config, public_execute, anon_execute, authenticated_execute, service_execute = rows[0].split("|")
    assert security_definer == "t"
    assert config == 'search_path=""'
    assert (public_execute, anon_execute, authenticated_execute, service_execute) == ("f", "f", "f", "t")


def test_lexical_search_rpc_is_service_role_only_and_bounded() -> None:
    """The real RPC accepts service_role and rejects browser credentials."""
    payload = {"p_university_id": KNOWN_UNIVERSITY, "p_query": "العبء الدراسي", "p_limit": 20}
    with httpx.Client(timeout=15.0) as client:
        service = client.post(
            f"{URL}/rest/v1/rpc/search_verified_policy_passages",
            headers=_headers(SERVER_KEY or ""),
            json=payload,
        )
        assert service.status_code == 200, service.text
        assert isinstance(service.json(), list)
        assert len(service.json()) <= 20

        anon = client.post(
            f"{URL}/rest/v1/rpc/search_verified_policy_passages",
            headers=_headers(ANON_KEY or ""),
            json=payload,
        )
        assert anon.status_code in (401, 403, 404), anon.text


def test_lexical_search_returns_only_current_verified_tenant_evidence() -> None:
    """Use real tables and the real RPC; no search result is mocked."""
    now = datetime.now(timezone.utc).isoformat()
    code = f"LEX-{uuid4().hex[:10]}"
    text = "الحد الأعلى للعبء الدراسي هو ثماني عشرة ساعة معتمدة."
    with httpx.Client(timeout=15.0) as client:
        headers = {**_headers(SERVER_KEY or ""), "Prefer": "return=representation"}
        document = client.post(f"{URL}/rest/v1/policy_documents", headers=headers, json={
            "university_id": KNOWN_UNIVERSITY, "document_code": code,
            "title": "لائحة العبء الدراسي والانسحاب", "authority_level": "university_council",
            "category": "academic_bylaws",
        })
        document.raise_for_status()
        document_id = document.json()[0]["id"]
        try:
            for status, passage in (
                ("verified", text),
                ("unverified", "نص غير موثق للعبء الدراسي"),
                ("pending_review", "نص قيد المراجعة للعبء الدراسي"),
                ("withdrawn", "نص مسحوب للعبء الدراسي"),
                ("superseded", "نص مستبدل للعبء الدراسي"),
            ):
                version = client.post(f"{URL}/rest/v1/policy_document_versions", headers=headers, json={
                    "document_id": document_id, "version_tag": f"v-{status}",
                    "effective_start_date": now, "content_sha256": "a" * 64,
                    "status": status, **({"verified_at": now, "verified_by": "local-test"} if status == "verified" else {}),
                })
                version.raise_for_status()
                client.post(f"{URL}/rest/v1/policy_passages", headers=headers, json={
                    "version_id": version.json()[0]["id"], "passage_text": passage,
                    "locator_text": "المادة 18", "article_number": "18", "section_number": "2",
                    "page_number": 44, "heading": "العبء الدراسي", "sequence_order": 0,
                    "passage_sha256": "b" * 64,
                }).raise_for_status()

            response = client.post(f"{URL}/rest/v1/rpc/search_verified_policy_passages", headers=headers, json={
                "p_university_id": KNOWN_UNIVERSITY, "p_query": "العبء الدراسي", "p_limit": 20,
            })
            response.raise_for_status()
            rows = [row for row in response.json() if row["document_code"] == code]
            assert len(rows) == 1
            assert rows[0]["passage_text"] == text
            assert rows[0]["locator_text"] == "المادة 18"
            assert rows[0]["article_number"] == "18"
            assert rows[0]["section_number"] == "2"
            assert rows[0]["page_number"] == 44
            assert rows[0]["heading"] == "العبء الدراسي"
            assert rows[0]["status"] == "verified"

            no_match = client.post(f"{URL}/rest/v1/rpc/search_verified_policy_passages", headers=headers, json={
                "p_university_id": KNOWN_UNIVERSITY, "p_query": "عبارة لا تظهر في أي سياسة", "p_limit": 1,
            })
            no_match.raise_for_status()
            assert no_match.json() == []
        finally:
            versions = client.get(f"{URL}/rest/v1/policy_document_versions?document_id=eq.{document_id}", headers=headers).json()
            for version in versions:
                client.delete(f"{URL}/rest/v1/policy_passages?version_id=eq.{version['id']}", headers=headers)
            client.delete(f"{URL}/rest/v1/policy_document_versions?document_id=eq.{document_id}", headers=headers)
            client.delete(f"{URL}/rest/v1/policy_documents?id=eq.{document_id}", headers=headers)


def test_lexical_search_ranking_tie_break_tenant_and_limit_are_real() -> None:
    """Exercise ranking and tenant filtering against rows created in Local Supabase."""
    now = datetime.now(timezone.utc).isoformat()
    token = f"wc038{uuid4().hex[:12]}"
    created_document_ids: list[str] = []
    created_university_id: str | None = None
    headers = {**_headers(SERVER_KEY or ""), "Prefer": "return=representation"}

    def create_document(client: httpx.Client, university_id: str, code_suffix: str, passage_text: str) -> str:
        document = client.post(f"{URL}/rest/v1/policy_documents", headers=headers, json={
            "university_id": university_id, "document_code": f"LEX-{token}-{code_suffix}",
            "title": f"Local lexical ranking {code_suffix}", "authority_level": "university_council",
            "category": "academic_bylaws",
        })
        document.raise_for_status()
        document_id = document.json()[0]["id"]
        created_document_ids.append(document_id)
        version = client.post(f"{URL}/rest/v1/policy_document_versions", headers=headers, json={
            "document_id": document_id, "version_tag": "v1", "effective_start_date": now,
            "content_sha256": "c" * 64, "status": "verified", "verified_at": now, "verified_by": "local-test",
        })
        version.raise_for_status()
        passage = client.post(f"{URL}/rest/v1/policy_passages", headers=headers, json={
            "version_id": version.json()[0]["id"], "passage_text": passage_text,
            "locator_text": "Article 7", "article_number": "7", "page_number": 7,
            "heading": "Ranking", "sequence_order": 0, "passage_sha256": "d" * 64,
        })
        passage.raise_for_status()
        return document_id

    with httpx.Client(timeout=15.0) as client:
        try:
            university = client.post(f"{URL}/rest/v1/universities", headers=headers, json={
                "name_ar": f"جامعة اختبار بحث محلي {token}",
                "name_en": f"Local lexical isolation test {token}",
                "country": "Jordan", "active": True,
            })
            university.raise_for_status()
            created_university_id = university.json()[0]["id"]
            phrase_code = f"LEX-{token}-PHRASE"
            tie_a_code = f"LEX-{token}-TIE-A"
            tie_b_code = f"LEX-{token}-TIE-B"
            create_document(client, KNOWN_UNIVERSITY, "PHRASE", f"{token} exact phrase ranking evidence")
            create_document(client, KNOWN_UNIVERSITY, "TIE-A", f"{token} exact phrase ranking evidence")
            create_document(client, KNOWN_UNIVERSITY, "TIE-B", f"{token} exact phrase ranking evidence")
            create_document(client, created_university_id, "OTHER", f"{token} exact phrase ranking evidence")

            response = client.post(f"{URL}/rest/v1/rpc/search_verified_policy_passages", headers=headers, json={
                "p_university_id": KNOWN_UNIVERSITY, "p_query": f"{token} exact phrase ranking", "p_limit": 20,
            })
            response.raise_for_status()
            rows = [row for row in response.json() if row["document_code"].startswith(f"LEX-{token}-")]
            assert [row["document_code"] for row in rows] == [phrase_code, tie_a_code, tie_b_code]
            assert f"LEX-{token}-OTHER" not in [row["document_code"] for row in rows]
            assert rows[0]["passage_text"] == f"{token} exact phrase ranking evidence"

            limited = client.post(f"{URL}/rest/v1/rpc/search_verified_policy_passages", headers=headers, json={
                "p_university_id": KNOWN_UNIVERSITY, "p_query": token, "p_limit": 1,
            })
            limited.raise_for_status()
            assert len(limited.json()) == 1
        finally:
            for document_id in created_document_ids:
                versions = client.get(f"{URL}/rest/v1/policy_document_versions?document_id=eq.{document_id}", headers=headers).json()
                for version in versions:
                    client.delete(f"{URL}/rest/v1/policy_passages?version_id=eq.{version['id']}", headers=headers)
                client.delete(f"{URL}/rest/v1/policy_document_versions?document_id=eq.{document_id}", headers=headers)
                client.delete(f"{URL}/rest/v1/policy_documents?id=eq.{document_id}", headers=headers)
            if created_university_id is not None:
                cleanup = client.delete(f"{URL}/rest/v1/universities", headers=headers,
                    params={"id": f"eq.{created_university_id}"})
                cleanup.raise_for_status()
                remaining = client.get(f"{URL}/rest/v1/universities", headers=headers,
                    params={"select": "id", "id": f"eq.{created_university_id}"})
                remaining.raise_for_status()
                assert remaining.json() == []
