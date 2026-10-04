from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.institutional_policy.embeddings import OpenAIPolicyEmbeddingProvider, PolicyEmbeddingError
from app.institutional_policy.service import StudentPolicyService, _fuse_policy_results
from app.institutional_policy.embedding_backfill import PolicyEmbeddingBackfillService
from app.institutional_policy.embeddings import EmbeddingModel


def test_policy_embedding_default_contract_is_large_at_1536_dimensions() -> None:
    assert Settings.model_fields["policy_embedding_model"].default == "text-embedding-3-large"
    assert Settings.model_fields["policy_embedding_dimensions"].default == 1536


def test_openai_embedding_provider_batches_and_validates_dimensions() -> None:
    async def run() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]})))
        provider = OpenAIPolicyEmbeddingProvider("secret", "test-model", 2, client)
        assert await provider.embed_batch(("one", "two")) == ((0.1, 0.2), (0.3, 0.4))
        await client.aclose()
    asyncio.run(run())


def test_openai_embedding_provider_maps_provider_failure_safely() -> None:
    async def run() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
        provider = OpenAIPolicyEmbeddingProvider("secret", "test-model", 2, client)
        with pytest.raises(PolicyEmbeddingError, match="provider_rejected"):
            await provider.embed_query("Arabic policy query")
        await client.aclose()
    asyncio.run(run())


def test_hybrid_rrf_is_deterministic_and_preserves_single_evidence_row() -> None:
    lexical = [{"passage_id": "a", "document_code": "B", "sequence_order": 1, "score": 10}, {"passage_id": "b", "document_code": "A", "sequence_order": 2, "score": 9}]
    semantic = [{"passage_id": "b", "document_code": "A", "sequence_order": 2, "semantic_similarity": 0.9}, {"passage_id": "c", "document_code": "C", "sequence_order": 1, "semantic_similarity": 0.8}]
    result = _fuse_policy_results(lexical, semantic, 10)
    assert [row["passage_id"] for row in result] == ["b", "a", "c"]
    assert result[0]["lexical_rank"] == 2
    assert result[0]["semantic_rank"] == 1
    assert result[0]["semantic_similarity"] == 0.9


def test_semantic_mode_never_silently_falls_back_to_lexical() -> None:
    class Storage:
        async def list_verified_documents(self, university_id): return []
        async def get_document_detail(self, university_id, document_id): return None
        async def search_verified_passages(self, *args): return []
        async def search_semantic_passages(self, *args): return []
    async def run() -> None:
        with pytest.raises(PolicyEmbeddingError, match="not_configured"):
            await StudentPolicyService(Storage()).search_policies_for_student("u", "انسحاب المادة", 5, mode="semantic")
    asyncio.run(run())


class FakeEmbeddingProvider:
    def __init__(self, model: str = "m1", dimensions: int = 2, fail: bool = False) -> None:
        self.model = EmbeddingModel("test", model, dimensions)
        self.fail = fail
        self.calls: list[tuple[str, ...]] = []

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return (0.0,) * self.model.dimensions

    async def embed_batch(self, texts):
        self.calls.append(tuple(texts))
        if self.fail:
            raise PolicyEmbeddingError("policy.embedding.unavailable")
        return tuple((0.1,) * self.model.dimensions for _ in texts)


class FakeEmbeddingStorage:
    def __init__(self, passages: list[dict]) -> None:
        self.passages = passages
        self.embeddings: dict[tuple[str, str, str], dict] = {}
        self.writes: list[dict] = []
        self.read_limits: list[int] = []
        self.fail_id: str | None = None

    async def list_embed_candidates(self, provider, model, after_passage_id, limit, document_id):
        self.read_limits.append(limit)
        eligible = [row for row in self.passages if row["status"] == "verified" and row["current"]
                    and (document_id is None or row["document_id"] == document_id)
                    and (after_passage_id is None or row["passage_id"] > after_passage_id)]
        rows = []
        for passage in sorted(eligible, key=lambda row: row["passage_id"])[:limit]:
            existing = self.embeddings.get((passage["passage_id"], provider, model), {})
            rows.append({"passage_id": passage["passage_id"], "passage_text": passage["passage_text"],
                         "passage_sha256": passage["passage_sha256"],
                         "existing_source_content_sha256": existing.get("source_content_sha256"),
                         "existing_dimensions": existing.get("dimensions")})
        return rows

    async def upsert_embedding(self, row):
        if row["passage_id"] == self.fail_id:
            response = httpx.Response(503, request=httpx.Request("POST", "https://local.test/embeddings"))
            raise httpx.HTTPStatusError("local write failure", request=response.request, response=response)
        self.writes.append(row)
        self.embeddings[(row["passage_id"], row["provider"], row["model"])] = row


DOC_A = "00000000-0000-0000-0000-000000000001"
DOC_B = "00000000-0000-0000-0000-000000000002"


def _passage(index: int, *, status: str = "verified", current: bool = True, document_id: str = DOC_A) -> dict:
    return {"passage_id": f"p{index}", "passage_text": f"exact passage {index}",
            "passage_sha256": f"{index:064x}", "status": status,
            "current": current, "document_id": document_id}


def test_backfill_first_run_is_idempotent_and_reacts_to_hash_model_dimension_changes() -> None:
    async def run() -> None:
        source = _passage(1)
        storage = FakeEmbeddingStorage([source])
        provider = FakeEmbeddingProvider()
        service = PolicyEmbeddingBackfillService(storage, provider)
        first = await service.run()
        assert (first.inserted, first.skipped, first.failed) == (1, 0, 0)
        second = await service.run()
        assert (second.inserted, second.skipped, second.failed) == (0, 1, 0)
        source["passage_sha256"] = "f" * 64
        changed = await service.run()
        assert changed.inserted == 1
        assert storage.writes[-1]["source_content_sha256"] == "f" * 64
        new_model = await PolicyEmbeddingBackfillService(storage, FakeEmbeddingProvider("m2")).run()
        assert new_model.inserted == 1
        new_dimensions = await PolicyEmbeddingBackfillService(storage, FakeEmbeddingProvider("m2", 3)).run()
        assert new_dimensions.inserted == 1
        assert len(storage.embeddings) == 2  # unique passage/provider/model; dimensions replace same model row
    asyncio.run(run())


def test_backfill_filters_nonadmitted_versions_and_honors_bounds_scope_and_dry_run() -> None:
    async def run() -> None:
        passages = [_passage(i) for i in range(1, 5)]
        passages += [_passage(5, status="unverified"), _passage(6, status="pending_review"),
                     _passage(7, status="withdrawn"), _passage(8, status="superseded"),
                     _passage(9, current=False), _passage(10, document_id=DOC_B)]
        storage = FakeEmbeddingStorage(passages)
        provider = FakeEmbeddingProvider()
        service = PolicyEmbeddingBackfillService(storage, provider)
        dry = await service.run(batch_size=2, limit=3, dry_run=True)
        assert (dry.scanned, dry.inserted, dry.would_embed, dry.failed) == (3, 0, 3, 0)
        assert provider.calls == [] and storage.writes == []
        scoped = await service.run(batch_size=2, limit=3, document_id=DOC_B, dry_run=True)
        assert (scoped.scanned, scoped.would_embed, scoped.inserted) == (1, 1, 0)
        result = await service.run(batch_size=2, limit=5)
        assert (result.scanned, result.inserted, result.skipped, result.failed) == (5, 5, 0, 0)
        assert [len(batch) for batch in provider.calls] == [2, 2, 1]
        assert max(storage.read_limits) <= 2
        assert all(row["passage_id"] not in {"p5", "p6", "p7", "p8", "p9"} for row in storage.writes)
        with pytest.raises(ValueError):
            await service.run(batch_size=101)
        with pytest.raises(ValueError):
            await service.run(limit=1001)
    asyncio.run(run())


def test_backfill_provider_batch_failure_and_partial_write_failure_are_counted() -> None:
    async def run() -> None:
        source = [_passage(1), _passage(2), _passage(3)]
        storage = FakeEmbeddingStorage(source)
        provider = FakeEmbeddingProvider(fail=True)
        failed_batch = await PolicyEmbeddingBackfillService(storage, provider).run(batch_size=2, limit=3)
        assert (failed_batch.scanned, failed_batch.inserted, failed_batch.failed) == (2, 0, 2)
        assert storage.writes == []
        storage.fail_id = "p2"
        partial = await PolicyEmbeddingBackfillService(storage, FakeEmbeddingProvider()).run(batch_size=3, limit=3)
        assert (partial.scanned, partial.inserted, partial.failed) == (3, 2, 1)
        assert ("p2", "test", "m1") not in storage.embeddings
        assert len(storage.writes) == 2
    asyncio.run(run())
