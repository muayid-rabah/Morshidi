"""Server-side embedding boundary for WC-038 semantic policy retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import httpx


OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


class PolicyEmbeddingError(RuntimeError):
    """Safe failure raised when a configured embeddings provider cannot serve a request."""


@dataclass(frozen=True, slots=True)
class EmbeddingModel:
    provider: str
    model: str
    dimensions: int


class PolicyEmbeddingProvider(Protocol):
    model: EmbeddingModel

    async def embed_query(self, text: str) -> tuple[float, ...]: ...

    async def embed_batch(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


class OpenAIPolicyEmbeddingProvider:
    """Narrow OpenAI embeddings adapter; keys stay exclusively in the API process."""

    def __init__(self, api_key: str, model: str, dimensions: int, client: httpx.AsyncClient) -> None:
        if not api_key.strip() or not model.strip() or dimensions <= 0:
            raise ValueError("policy embedding provider requires key, model, and positive dimensions")
        self._api_key = api_key
        self.model = EmbeddingModel("openai", model, dimensions)
        self._client = client

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return (await self.embed_batch((text,)))[0]

    async def embed_batch(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise PolicyEmbeddingError("policy.embedding.invalid_input")
        try:
            response = await self._client.post(
                OPENAI_EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self.model.model, "input": list(texts), "dimensions": self.model.dimensions},
                timeout=20.0,
            )
        except httpx.TimeoutException as exc:
            raise PolicyEmbeddingError("policy.embedding.timeout") from exc
        except httpx.HTTPError as exc:
            raise PolicyEmbeddingError("policy.embedding.unavailable") from exc
        if response.status_code >= 400:
            raise PolicyEmbeddingError("policy.embedding.provider_rejected")
        try:
            data = response.json()["data"]
            vectors = tuple(tuple(float(value) for value in item["embedding"]) for item in data)
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyEmbeddingError("policy.embedding.malformed_response") from exc
        if len(vectors) != len(texts) or any(len(vector) != self.model.dimensions for vector in vectors):
            raise PolicyEmbeddingError("policy.embedding.dimension_mismatch")
        return vectors
