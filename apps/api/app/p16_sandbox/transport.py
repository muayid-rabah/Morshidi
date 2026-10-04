"""Transport abstraction for Sandbox University synthetic data.

Provides identical domain mapping across local static fixtures (LOCAL / CI)
and read-only HTTP endpoints (CONNECTED DEMO) without coupling build paths or modifying production.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import httpx

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class SandboxTransportError(RuntimeError):
    """Safe transport error indicator. Never includes upstream tokens or secrets."""


class SandboxUniversityTransport(Protocol):
    """Protocol for reading synthetic sandbox university contracts."""

    async def load_manifest(self) -> Mapping[str, Any]:
        ...

    async def load_students(self) -> Sequence[Mapping[str, Any]]:
        ...

    async def load_courses(self) -> Sequence[Mapping[str, Any]]:
        ...

    async def load_offerings(self) -> Sequence[Mapping[str, Any]]:
        ...

    async def load_academic_records(self) -> Mapping[str, Any]:
        ...


class StaticFixtureTransport:
    """Reads static canonical contract snapshots from the local filesystem."""

    def __init__(self, fixtures_dir: Path | str | None = None) -> None:
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else DEFAULT_FIXTURES_DIR
        if not self.fixtures_dir.is_dir():
            raise SandboxTransportError(f"Fixtures directory does not exist: {self.fixtures_dir}")

    def _read_json(self, filename: str) -> Any:
        file_path = self.fixtures_dir / filename
        if not file_path.is_file():
            raise SandboxTransportError(f"Fixture file missing: {filename}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            raise SandboxTransportError(f"Failed to parse fixture {filename}") from exc

    async def load_manifest(self) -> Mapping[str, Any]:
        return self._read_json("manifest.json")

    async def load_students(self) -> Sequence[Mapping[str, Any]]:
        return self._read_json("students.json")

    async def load_courses(self) -> Sequence[Mapping[str, Any]]:
        return self._read_json("courses.json")

    async def load_offerings(self) -> Sequence[Mapping[str, Any]]:
        return self._read_json("offerings.json")

    async def load_academic_records(self) -> Mapping[str, Any]:
        return self._read_json("academic-records.json")


class HTTPReadOnlyTransport:
    """Reads canonical contracts from a running contributor portal via read-only HTTP."""

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 3.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client
        self.timeout_seconds = timeout_seconds

    async def _get_json(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        try:
            if self._client is not None:
                resp = await self._client.get(url, timeout=self.timeout_seconds)
                resp.raise_for_status()
                return resp.json()
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=self.timeout_seconds)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            raise SandboxTransportError(f"HTTP GET failed for path {path}") from exc

    async def load_manifest(self) -> Mapping[str, Any]:
        return await self._get_json("/api/v1/manifest.json")

    async def load_students(self) -> Sequence[Mapping[str, Any]]:
        return await self._get_json("/api/v1/students.json")

    async def load_courses(self) -> Sequence[Mapping[str, Any]]:
        return await self._get_json("/api/v1/courses.json")

    async def load_offerings(self) -> Sequence[Mapping[str, Any]]:
        return await self._get_json("/api/v1/offerings.json")

    async def load_academic_records(self) -> Mapping[str, Any]:
        return await self._get_json("/api/v1/academic-records.json")
