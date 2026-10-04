"""Real Local Supabase checks for WC-038 pgvector infrastructure."""

from __future__ import annotations

import os
import subprocess
import hashlib
import asyncio
from uuid import uuid4

import httpx

import pytest

from app.institutional_policy.embedding_backfill import (
    PolicyEmbeddingBackfillService, SupabasePolicyEmbeddingBackfillStorage,
)
from app.institutional_policy.embeddings import EmbeddingModel


URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
SERVER_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
ANON_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_ANON_KEY")
pytestmark = pytest.mark.skipif(not all((URL, SERVER_KEY, ANON_KEY)), reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values")


def test_pgvector_embedding_schema_and_semantic_rpc_security() -> None:
    sql = """
    select exists(select 1 from pg_extension where extname = 'vector'),
      exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname='policy_passage_embeddings'),
      (select relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname='policy_passage_embeddings'),
      has_table_privilege('anon','public.policy_passage_embeddings','select'),
      has_table_privilege('authenticated','public.policy_passage_embeddings','insert'),
      p.prosecdef, coalesce(array_to_string(p.proconfig, ','), ''),
      has_function_privilege('public',p.oid,'execute'), has_function_privilege('anon',p.oid,'execute'),
      has_function_privilege('authenticated',p.oid,'execute'), has_function_privilege('service_role',p.oid,'execute')
    from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname='search_verified_policy_passages_semantic';
    """
    result = subprocess.run(["docker", "exec", "supabase_db_Morshidi", "psql", "-U", "postgres", "-d", "postgres", "-At", "-F", "|", "-c", sql], check=True, capture_output=True, text=True)
    row = result.stdout.strip().split("|")
    assert row == ["t", "t", "t", "f", "f", "t", 'search_path=""', "f", "f", "f", "t"]
    schema_sql = """
    select a.atttypmod,
      exists(select 1 from pg_constraint where conrelid='public.policy_passage_embeddings'::regclass
             and contype='f' and confrelid='public.policy_passages'::regclass),
      exists(select 1 from pg_constraint where conrelid='public.policy_passage_embeddings'::regclass
             and conname='uq_policy_passage_embeddings_passage_provider_model' and contype='u'),
      has_table_privilege('service_role','public.policy_passage_embeddings','insert'),
      has_table_privilege('authenticated','public.policy_passage_embeddings','select')
    from pg_attribute a where a.attrelid='public.policy_passage_embeddings'::regclass
      and a.attname='embedding';
    """
    schema = subprocess.run(["docker", "exec", "supabase_db_Morshidi", "psql", "-U", "postgres",
        "-d", "postgres", "-At", "-F", "|", "-c", schema_sql], check=True, capture_output=True, text=True)
    assert schema.stdout.strip().split("|") == ["1536", "t", "t", "t", "f"]


def _headers(key: str, bearer: str | None = None) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {bearer or key}",
            "Content-Type": "application/json", "Prefer": "return=representation"}


def _vector(first: float, second: float = 0.0) -> list[float]:
    return [first, second, *([0.0] * 1534)]


def test_real_semantic_rpc_filters_ranks_and_preserves_citations() -> None:
    """Exercise actual Postgres vector inserts and the actual service-role RPC."""
    service = _headers(SERVER_KEY or "")
    university_a = "10000000-0000-0000-0000-000000000001"
    token = uuid4().hex[:10]
    created_documents: list[str] = []
    created_university: str | None = None
    created_user: str | None = None
    with httpx.Client(timeout=30.0) as client:
        def post(table: str, data: dict) -> dict:
            response = client.post(f"{URL}/rest/v1/{table}", headers=service, json=data)
            assert response.status_code in (200, 201), response.text
            return response.json()[0]

        def create_policy(university: str, suffix: str, status: str, texts: list[str],
                          start: str = "2020-01-01T00:00:00Z", end: str | None = None) -> tuple[dict, list[dict]]:
            document = post("policy_documents", {"university_id": university,
                "document_code": f"SEM-{token}-{suffix}", "title": f"Fixture {suffix}",
                "authority_level": "university_council", "category": "academic_bylaws"})
            created_documents.append(document["id"])
            version_data = {"document_id": document["id"], "version_tag": "v1",
                "status": status, "effective_start_date": start, "effective_end_date": end,
                "content_sha256": "a" * 64, "source_url": "https://example.test/policy.pdf"}
            if status == "verified":
                version_data.update({"verified_at": "2020-01-01T00:00:00Z", "verified_by": "test-office"})
            version = post("policy_document_versions", version_data)
            passages = []
            for index, passage_text in enumerate(texts):
                passage = post("policy_passages", {"version_id": version["id"],
                    "passage_text": passage_text, "passage_sha256": hashlib.sha256(passage_text.encode()).hexdigest(),
                    "locator_text": f"Article {index + 1}", "article_number": str(index + 1),
                    "section_number": "2", "page_number": 40 + index,
                    "heading": "Withdrawal", "sequence_order": index})
                passages.append(passage)
            return version, passages

        def insert_embedding(passage: dict, vector: list[float], *, provider: str = "fixture",
                             model: str = "fixture-1536", dimensions: int = 1536) -> httpx.Response:
            return client.post(f"{URL}/rest/v1/policy_passage_embeddings", headers=service, json={
                "passage_id": passage["id"], "embedding": vector, "provider": provider,
                "model": model, "dimensions": dimensions,
                "source_content_sha256": passage["passage_sha256"]})

        def search(university: str, *, provider: str = "fixture", model: str = "fixture-1536",
                   limit: int = 20) -> httpx.Response:
            return client.post(f"{URL}/rest/v1/rpc/search_verified_policy_passages_semantic",
                headers=service, json={"p_university_id": university, "p_query_embedding": _vector(1),
                    "p_provider": provider, "p_model": model, "p_limit": limit})

        try:
            other = post("universities", {"name_ar": f"جامعة اختبار {token}",
                "name_en": f"Semantic test {token}", "country": "Jordan", "active": True})
            created_university = other["id"]
            verified, good = create_policy(university_a, "A", "verified", [
                "يجوز للطالب الانسحاب من المساق وفق المواعيد المحددة.",
                "العبء الدراسي للطالب تحدده تعليمات الجامعة.",
                "تعليمات أخرى عن التسجيل في الجامعة.",
            ])
            assert insert_embedding(good[0], _vector(1)).status_code in (200, 201)
            assert insert_embedding(good[1], _vector(0.9, 0.1)).status_code in (200, 201)
            assert insert_embedding(good[2], _vector(0.9, 0.1)).status_code in (200, 201)
            assert insert_embedding(good[0], _vector(1)).status_code == 409  # unique triple
            assert insert_embedding(good[0], [1.0, 0.0]).status_code >= 400
            assert insert_embedding(good[0], _vector(1), model="wrong-dim", dimensions=2).status_code >= 400
            for status in ("unverified", "pending_review", "withdrawn", "superseded"):
                _, excluded = create_policy(university_a, status, status, [f"excluded {status}"])
                assert insert_embedding(excluded[0], _vector(1)).status_code in (200, 201)
            _, cross = create_policy(created_university, "B", "verified", ["other university policy"])
            assert insert_embedding(cross[0], _vector(1)).status_code in (200, 201)
            _, future = create_policy(university_a, "future", "verified", ["future policy"], start="2099-01-01T00:00:00Z")
            assert insert_embedding(future[0], _vector(1)).status_code in (200, 201)
            _, expired = create_policy(university_a, "expired", "verified", ["old policy"], end="2021-01-01T00:00:00Z")
            assert insert_embedding(expired[0], _vector(1)).status_code in (200, 201)

            result = search(university_a)
            assert result.status_code == 200, result.text
            rows = [row for row in result.json() if row["document_code"].startswith(f"SEM-{token}-")]
            assert [row["passage_id"] for row in rows] == [passage["id"] for passage in good]
            assert rows[0]["semantic_similarity"] == pytest.approx(1.0)
            assert rows[0]["semantic_similarity"] > rows[1]["semantic_similarity"]
            assert rows[1]["semantic_similarity"] == pytest.approx(rows[2]["semantic_similarity"])
            assert rows[0]["passage_text"] == good[0]["passage_text"]
            assert (rows[0]["locator_text"], rows[0]["article_number"], rows[0]["section_number"],
                    rows[0]["page_number"], rows[0]["heading"]) == ("Article 1", "1", "2", 40, "Withdrawal")
            assert (rows[0]["version_id"], rows[0]["version_tag"], rows[0]["verified_by"],
                    rows[0]["source_url"], rows[0]["content_sha256"], rows[0]["passage_sha256"]) == (
                    verified["id"], "v1", "test-office", "https://example.test/policy.pdf",
                    "a" * 64, good[0]["passage_sha256"])
            limited = search(university_a, limit=1)
            assert limited.status_code == 200 and len(limited.json()) == 1
            assert search(university_a, model="unknown-model").json() == []
            assert search(university_a, provider="unknown-provider").json() == []
            assert search(created_university).json()[0]["passage_id"] == cross[0]["id"]

            def candidates(document_id: str) -> list[dict]:
                response = client.post(f"{URL}/rest/v1/rpc/list_verified_policy_embedding_candidates",
                    headers=service, json={"p_provider": "fixture", "p_model": "fixture-1536",
                        "p_document_id": document_id, "p_limit": 20})
                assert response.status_code == 200, response.text
                return response.json()

            eligible = candidates(created_documents[0])
            assert {row["passage_id"] for row in eligible} == {passage["id"] for passage in good}
            assert all(row["existing_source_content_sha256"] == row["passage_sha256"]
                       and row["existing_dimensions"] == 1536 for row in eligible)
            for excluded_document in created_documents[1:5] + created_documents[6:]:
                assert candidates(excluded_document) == []
            assert {row["passage_id"] for row in candidates(created_documents[5])} == {cross[0]["id"]}

            class FixedProvider:
                model = EmbeddingModel("fixture", "operator-test", 1536)

                async def embed_query(self, text):
                    return tuple(_vector(1))

                async def embed_batch(self, texts):
                    return tuple(tuple(_vector(1)) for _ in texts)

            async def run_operator_path():
                async with httpx.AsyncClient(timeout=30.0) as async_client:
                    storage = SupabasePolicyEmbeddingBackfillStorage(URL or "", SERVER_KEY or "", async_client)
                    backfill = PolicyEmbeddingBackfillService(storage, FixedProvider())
                    first = await backfill.run(batch_size=2, limit=3, document_id=created_documents[0])
                    second = await backfill.run(batch_size=2, limit=3, document_id=created_documents[0])
                    return first, second

            first_backfill, second_backfill = asyncio.run(run_operator_path())
            assert (first_backfill.inserted, first_backfill.skipped, first_backfill.failed) == (3, 0, 0)
            assert (second_backfill.inserted, second_backfill.skipped, second_backfill.failed) == (0, 3, 0)

            user = client.post(f"{URL}/auth/v1/admin/users", headers=service,
                json={"email": f"semantic-{token}@example.test", "password": f"Valid-{token}-Password!", "email_confirm": True})
            user.raise_for_status()
            created_user = user.json()["id"]
            signed_in = client.post(f"{URL}/auth/v1/token", params={"grant_type": "password"},
                headers={"apikey": ANON_KEY or "", "Content-Type": "application/json"},
                json={"email": f"semantic-{token}@example.test", "password": f"Valid-{token}-Password!"})
            signed_in.raise_for_status()
            for headers in (_headers(ANON_KEY or ""), _headers(ANON_KEY or "", signed_in.json()["access_token"])):
                assert client.get(f"{URL}/rest/v1/policy_passage_embeddings", headers=headers).status_code in (401, 403)
                direct_write = client.post(f"{URL}/rest/v1/policy_passage_embeddings", headers=headers,
                    json={"passage_id": good[0]["id"], "embedding": _vector(1),
                        "provider": "forbidden", "model": "forbidden", "dimensions": 1536,
                        "source_content_sha256": good[0]["passage_sha256"]})
                assert direct_write.status_code in (401, 403)
                denied = client.post(f"{URL}/rest/v1/rpc/search_verified_policy_passages_semantic",
                    headers=headers, json={"p_university_id": university_a, "p_query_embedding": _vector(1),
                        "p_provider": "fixture", "p_model": "fixture-1536", "p_limit": 10})
                assert denied.status_code in (401, 403, 404)
                candidate_denied = client.post(f"{URL}/rest/v1/rpc/list_verified_policy_embedding_candidates",
                    headers=headers, json={"p_provider": "fixture", "p_model": "fixture-1536", "p_limit": 1})
                assert candidate_denied.status_code in (401, 403, 404)
        finally:
            for document_id in created_documents:
                versions_response = client.get(f"{URL}/rest/v1/policy_document_versions",
                    headers=service, params={"document_id": f"eq.{document_id}"})
                for version in versions_response.json():
                    passages_response = client.get(f"{URL}/rest/v1/policy_passages", headers=service,
                        params={"version_id": f"eq.{version['id']}"})
                    for passage in passages_response.json():
                        client.delete(f"{URL}/rest/v1/policy_passage_embeddings", headers=service,
                            params={"passage_id": f"eq.{passage['id']}"})
                    client.delete(f"{URL}/rest/v1/policy_passages", headers=service,
                        params={"version_id": f"eq.{version['id']}"})
                client.delete(f"{URL}/rest/v1/policy_document_versions", headers=service,
                    params={"document_id": f"eq.{document_id}"})
                client.delete(f"{URL}/rest/v1/policy_documents", headers=service,
                    params={"id": f"eq.{document_id}"})
            if created_user:
                client.delete(f"{URL}/auth/v1/admin/users/{created_user}", headers=service)
            if created_university:
                client.delete(f"{URL}/rest/v1/universities", headers=service,
                    params={"id": f"eq.{created_university}"})
