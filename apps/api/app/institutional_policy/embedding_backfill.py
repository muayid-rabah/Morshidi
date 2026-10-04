"""Explicit service-role WC-038 embedding backfill; run as a backend operator module."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import math
from typing import Any, Protocol, Sequence
from uuid import UUID

import httpx

from .embeddings import EmbeddingModel, OpenAIPolicyEmbeddingProvider, PolicyEmbeddingError, PolicyEmbeddingProvider


@dataclass(frozen=True, slots=True)
class BackfillSummary:
    scanned: int = 0
    inserted: int = 0
    skipped: int = 0
    failed: int = 0
    would_embed: int = 0


class PolicyEmbeddingBackfillStorage(Protocol):
    async def list_embed_candidates(
        self, provider: str, model: str, after_passage_id: str | None,
        limit: int, document_id: str | None,
    ) -> Sequence[dict[str, Any]]: ...

    async def upsert_embedding(self, row: dict[str, Any]) -> None: ...


class SupabasePolicyEmbeddingBackfillStorage:
    """Trusted PostgREST adapter; the candidate RPC enforces source admission in SQL."""

    def __init__(self, url: str, service_key: str, client: httpx.AsyncClient) -> None:
        self._rest_url = f"{url.rstrip('/')}/rest/v1"
        self._client = client
        self._headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

    async def list_embed_candidates(
        self, provider: str, model: str, after_passage_id: str | None,
        limit: int, document_id: str | None,
    ) -> Sequence[dict[str, Any]]:
        response = await self._client.post(
            f"{self._rest_url}/rpc/list_verified_policy_embedding_candidates",
            headers=self._headers,
            json={"p_provider": provider, "p_model": model, "p_after_passage_id": after_passage_id,
                  "p_limit": limit, "p_document_id": document_id},
        )
        response.raise_for_status()
        return response.json()

    async def upsert_embedding(self, row: dict[str, Any]) -> None:
        response = await self._client.post(
            f"{self._rest_url}/policy_passage_embeddings",
            params={"on_conflict": "passage_id,provider,model"},
            headers={**self._headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=row,
        )
        response.raise_for_status()


class _DryRunProvider:
    """Model identity for source inspection without loading or calling a provider."""

    def __init__(self, model: str, dimensions: int) -> None:
        self.model = EmbeddingModel("openai", model, dimensions)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        raise PolicyEmbeddingError("policy.embedding.dry_run_only")

    async def embed_batch(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        raise PolicyEmbeddingError("policy.embedding.dry_run_only")


class PolicyEmbeddingBackfillService:
    def __init__(self, storage: PolicyEmbeddingBackfillStorage, provider: PolicyEmbeddingProvider) -> None:
        self._storage = storage
        self._provider = provider

    async def run(
        self, *, batch_size: int = 50, limit: int = 500,
        document_id: str | None = None, dry_run: bool = False,
    ) -> BackfillSummary:
        if not 1 <= batch_size <= 100 or not 1 <= limit <= 1000:
            raise ValueError("batch_size must be 1..100 and limit must be 1..1000")
        if document_id is not None:
            UUID(document_id)
        scanned = inserted = skipped = failed = would_embed = 0
        cursor: str | None = None
        while scanned < limit:
            rows = await self._storage.list_embed_candidates(
                self._provider.model.provider, self._provider.model.model,
                cursor, min(batch_size, limit - scanned), document_id,
            )
            if not rows:
                break
            scanned += len(rows)
            cursor = str(rows[-1]["passage_id"])
            stale = [row for row in rows if row["existing_source_content_sha256"] != row["passage_sha256"]
                     or row["existing_dimensions"] != self._provider.model.dimensions]
            skipped += len(rows) - len(stale)
            if dry_run:
                would_embed += len(stale)
                continue
            if not stale:
                continue
            try:
                vectors = await self._provider.embed_batch(tuple(str(row["passage_text"]) for row in stale))
                if len(vectors) != len(stale) or any(
                    len(vector) != self._provider.model.dimensions or not all(math.isfinite(x) for x in vector)
                    for vector in vectors
                ):
                    raise PolicyEmbeddingError("policy.embedding.dimension_mismatch")
            except (PolicyEmbeddingError, httpx.HTTPError):
                failed += len(stale)
                break  # Stop after a provider batch failure; no writes for that batch.
            for row, vector in zip(stale, vectors, strict=True):
                try:
                    await self._storage.upsert_embedding({
                        "passage_id": row["passage_id"], "embedding": list(vector),
                        "provider": self._provider.model.provider, "model": self._provider.model.model,
                        "dimensions": self._provider.model.dimensions,
                        "source_content_sha256": row["passage_sha256"],
                    })
                    inserted += 1
                except httpx.HTTPError:
                    failed += 1
        return BackfillSummary(scanned, inserted, skipped, failed, would_embed)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill current verified policy passage embeddings")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--document-id", type=str)
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def _run_operator(args: argparse.Namespace) -> int:
    from app.core.config import settings

    if not settings.supabase_url or settings.supabase_secret_key is None:
        print("Backfill unavailable: trusted Supabase configuration is missing")
        return 2
    if not args.dry_run and (settings.policy_embedding_api_key is None or not settings.policy_embedding_api_key.get_secret_value().strip()):
        print("Backfill unavailable: embedding provider configuration is missing")
        return 2
    if settings.policy_embedding_dimensions != 1536:
        print("Backfill unavailable: embedding dimensions do not match vector schema")
        return 2
    async with httpx.AsyncClient(timeout=30.0) as client:
        provider: PolicyEmbeddingProvider = (
            _DryRunProvider(settings.policy_embedding_model, settings.policy_embedding_dimensions)
            if args.dry_run else OpenAIPolicyEmbeddingProvider(
                settings.policy_embedding_api_key.get_secret_value(),  # type: ignore[union-attr]
                settings.policy_embedding_model, settings.policy_embedding_dimensions, client,
            )
        )
        storage = SupabasePolicyEmbeddingBackfillStorage(
            settings.supabase_url, settings.supabase_secret_key.get_secret_value(), client,
        )
        try:
            result = await PolicyEmbeddingBackfillService(storage, provider).run(
                batch_size=args.batch_size, limit=args.limit,
                document_id=args.document_id, dry_run=args.dry_run,
            )
        except (ValueError, httpx.HTTPError, KeyError, TypeError):
            print("Backfill failed: invalid arguments or trusted database unavailable")
            return 2
    print(f"Backfill summary: scanned={result.scanned} inserted={result.inserted} "
          f"skipped={result.skipped} failed={result.failed} would_embed={result.would_embed}")
    return 1 if result.failed else 0


def main() -> int:
    return asyncio.run(_run_operator(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
