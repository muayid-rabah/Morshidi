"""Empty-tenant and disposable synthetic-corpus gates against Local Supabase."""

from __future__ import annotations

import asyncio
import hashlib
import os
from uuid import uuid4

import httpx
import pytest

from app.institutional_policy.answering import PolicyAnswerDraft, PolicyAnswerService
from app.institutional_policy.embeddings import EmbeddingModel
from app.institutional_policy.service import StudentPolicyService, SupabasePolicyReadStorage


LOCAL_URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
LOCAL_SERVER_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")

pytestmark = pytest.mark.skipif(
    not all((LOCAL_URL, LOCAL_SERVER_KEY)),
    reason="set local-only Supabase URL and server key to run integration tests",
)


def test_local_empty_tenant_abstains_without_embedding_or_generation() -> None:
    async def operation():
        storage = SupabasePolicyReadStorage(LOCAL_URL or "", LOCAL_SERVER_KEY or "")
        try:
            service = PolicyAnswerService(StudentPolicyService(storage))
            return await service.answer(
                "ffffffff-ffff-ffff-ffff-ffffffffffff", "ما سياسة الانسحاب من المساق؟"
            )
        finally:
            await storage.close()

    result = asyncio.run(operation())
    assert result.status == "ABSTAINED"
    assert result.abstention_reason == "NO_VERIFIED_POLICY_EVIDENCE"
    assert result.answer is None and result.citations == ()


def test_local_synthetic_verified_passage_produces_exact_server_citation() -> None:
    """Use one disposable, explicitly synthetic corpus; provider calls are mocked."""
    token = uuid4().hex[:12]
    headers = {
        "apikey": LOCAL_SERVER_KEY or "",
        "Authorization": f"Bearer {LOCAL_SERVER_KEY or ''}",
        "Prefer": "return=representation",
    }
    created: dict[str, str] = {}
    passage_text = "نص اختباري فقط: يطلب الطالب الانسحاب من المساق عبر النموذج المحدد."
    passage_sha = hashlib.sha256(passage_text.encode("utf-8")).hexdigest()

    with httpx.Client(timeout=30.0) as client:
        def insert(table: str, body: dict) -> dict:
            response = client.post(f"{LOCAL_URL}/rest/v1/{table}", headers=headers, json=body)
            response.raise_for_status()
            return response.json()[0]

        try:
            university = insert("universities", {
                "name_ar": f"جامعة اختبار غير رسمية {token}",
                "name_en": f"Synthetic Policy Test {token}",
                "country": "Jordan", "active": True,
            })
            created["universities"] = university["id"]
            document = insert("policy_documents", {
                "university_id": university["id"], "document_code": f"ANSWER-SYNTHETIC-{token}",
                "title": "لائحة انسحاب اختبارية غير رسمية", "authority_level": "university_council",
                "category": "academic_bylaws",
            })
            created["policy_documents"] = document["id"]
            version = insert("policy_document_versions", {
                "document_id": document["id"], "version_tag": "test-1", "status": "verified",
                "effective_start_date": "2020-01-01T00:00:00Z", "content_sha256": "a" * 64,
                "verified_at": "2020-01-01T00:00:00Z", "verified_by": "synthetic-test",
                "source_url": "https://example.test/synthetic-withdrawal",
            })
            created["policy_document_versions"] = version["id"]
            passage = insert("policy_passages", {
                "version_id": version["id"], "passage_text": passage_text,
                "passage_sha256": passage_sha, "locator_text": "المادة 4",
                "article_number": "4", "page_number": 7, "sequence_order": 1,
            })
            created["policy_passages"] = passage["id"]
            insert("policy_passage_embeddings", {
                "passage_id": passage["id"], "embedding": [1.0, *([0.0] * 1535)],
                "provider": "synthetic-test", "model": "synthetic-answer-test",
                "dimensions": 1536, "source_content_sha256": passage_sha,
            })
            created["policy_passage_embeddings"] = passage["id"]

            class FixedEmbedding:
                model = EmbeddingModel("synthetic-test", "synthetic-answer-test", 1536)

                async def embed_query(self, text: str):
                    return tuple([1.0, *([0.0] * 1535)])

            class CitingProvider:
                calls = 0

                async def answer(self, question, language, evidence):
                    self.calls += 1
                    assert evidence[0].passage_text == passage_text
                    return PolicyAnswerDraft(
                        "ANSWERED", "يصف النص الاختباري إجراء طلب الانسحاب.", "ar",
                        (passage["id"],),
                    )

            provider = CitingProvider()

            async def operation():
                storage = SupabasePolicyReadStorage(LOCAL_URL or "", LOCAL_SERVER_KEY or "")
                try:
                    policies = StudentPolicyService(storage, FixedEmbedding())
                    return await PolicyAnswerService(policies, provider).answer(
                        university["id"], "ما سياسة الانسحاب من المساق؟"
                    )
                finally:
                    await storage.close()

            result = asyncio.run(operation())
            assert result.status == "ANSWERED" and provider.calls == 1
            assert len(result.citations) == 1
            citation = result.citations[0]
            assert (citation.document_id, citation.version_id, citation.passage_id) == (
                document["id"], version["id"], passage["id"]
            )
            assert (citation.passage_text, citation.locator_text, citation.page_number,
                    citation.passage_sha256, citation.source_url) == (
                passage_text, "المادة 4", 7, passage_sha,
                "https://example.test/synthetic-withdrawal",
            )
        finally:
            for table in (
                "policy_passage_embeddings", "policy_passages",
                "policy_document_versions", "policy_documents", "universities",
            ):
                if table in created:
                    column = "passage_id" if table == "policy_passage_embeddings" else "id"
                    response = client.delete(
                        f"{LOCAL_URL}/rest/v1/{table}", headers=headers,
                        params={column: f"eq.{created[table]}"},
                    )
                    response.raise_for_status()
                    assert len(response.json()) == 1, f"synthetic {table} cleanup failed"
