"""Phase P8: Institutional Policy Ingestion Layer (WC-038).

AI EXPLAINS — DETERMINISTIC RULES DECIDE.
Atomic ingestion of verified university regulations and institutional policies.
Enforces:
- Single-transaction atomic writes (via PostgreSQL RPC persist_policy_document_version).
- Exact version tagging, content SHA-256 integrity, and immutable passage locators.
- University-level tenant boundary validation.
- Strict rejection of conflicting version content.
- Zero client-controlled bypass.
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence
from uuid import UUID

import httpx

from .enums import PolicyAuthorityLevel, PolicyCategory, PolicyErrorCode, SourceAdmissionStatus
from .errors import PolicyRetrievalError


class PolicyIngestionError(PolicyRetrievalError):
    """Raised when policy ingestion fails."""

    def __init__(self, code: PolicyErrorCode, detail: str) -> None:
        super().__init__(code, detail)


class PolicyConflictError(PolicyIngestionError):
    """Raised when a policy version tag conflicts with existing persisted data."""

    def __init__(self, detail: str) -> None:
        super().__init__(PolicyErrorCode.CORRUPTED_CONTENT, detail)


class TenantViolationError(PolicyIngestionError):
    """Raised when tenant boundary or university ID is invalid."""

    def __init__(self, detail: str) -> None:
        super().__init__(PolicyErrorCode.UNAUTHORIZED_TENANT, detail)


@dataclass(frozen=True)
class PolicyPassageIngestionInput:
    """Input payload for a single policy passage."""

    passage_text: str
    locator_text: str
    article_number: str | None = None
    section_number: str | None = None
    page_number: int | None = None
    heading: str | None = None
    sequence_order: int | None = None
    passage_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.passage_text or not self.passage_text.strip():
            raise ValueError("passage_text cannot be empty")
        if not self.locator_text or not self.locator_text.strip():
            raise ValueError("locator_text cannot be empty")
        if self.page_number is not None and self.page_number <= 0:
            raise ValueError("page_number must be positive")
        if self.sequence_order is not None and self.sequence_order < 0:
            raise ValueError("sequence_order must be non-negative")


@dataclass(frozen=True)
class PolicyDocumentIngestionInput:
    """Input payload for a policy document version and its passages."""

    university_id: str | UUID
    document_code: str
    title: str
    authority_level: PolicyAuthorityLevel | str
    category: PolicyCategory | str
    language: str = "ar"
    version_tag: str = "1.0"
    effective_start_date: datetime.datetime | str | None = None
    effective_end_date: datetime.datetime | str | None = None
    content_sha256: str | None = None
    status: SourceAdmissionStatus | str = SourceAdmissionStatus.VERIFIED
    verified_at: datetime.datetime | str | None = None
    verified_by: str | None = None
    source_url: str | None = None
    source_snapshot_ref: str | None = None
    passages: Sequence[PolicyPassageIngestionInput] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not str(self.university_id).strip():
            raise ValueError("university_id cannot be empty")
        if not self.document_code or not self.document_code.strip():
            raise ValueError("document_code cannot be empty")
        if not self.title or not self.title.strip():
            raise ValueError("title cannot be empty")
        if not self.version_tag or not self.version_tag.strip():
            raise ValueError("version_tag cannot be empty")


@dataclass(frozen=True)
class PolicyIngestionResult:
    """Result of an atomic policy ingestion operation."""

    document_id: str
    version_id: str
    passage_count: int
    status: str
    created: bool


class PolicyIngestionStorage(Protocol):
    """Storage boundary protocol for policy ingestion."""

    async def persist_document_version(
        self, payload: PolicyDocumentIngestionInput
    ) -> PolicyIngestionResult:
        ...


class InMemoryPolicyIngestionStorage:
    """In-memory atomic implementation of PolicyIngestionStorage for pure testing."""

    def __init__(self, known_universities: set[str] | None = None) -> None:
        self.known_universities = known_universities or set()
        self.documents: dict[str, dict[str, Any]] = {}
        self.versions: dict[str, dict[str, Any]] = {}
        self.passages: list[dict[str, Any]] = []

    async def persist_document_version(
        self, payload: PolicyDocumentIngestionInput
    ) -> PolicyIngestionResult:
        univ_id = str(payload.university_id)
        if self.known_universities and univ_id not in self.known_universities:
            raise TenantViolationError(f"University {univ_id} does not exist")

        doc_key = f"{univ_id}:{payload.document_code}"
        if doc_key not in self.documents:
            import uuid
            doc_id = str(uuid.uuid4())
            self.documents[doc_key] = {
                "id": doc_id,
                "university_id": univ_id,
                "document_code": payload.document_code,
                "title": payload.title,
                "authority_level": str(payload.authority_level.value if isinstance(payload.authority_level, PolicyAuthorityLevel) else payload.authority_level),
                "category": str(payload.category.value if isinstance(payload.category, PolicyCategory) else payload.category),
                "language": payload.language,
            }
        else:
            doc_id = self.documents[doc_key]["id"]

        # Compute content sha256 if not provided
        content_hash = payload.content_sha256
        if not content_hash:
            h = hashlib.sha256()
            for p in payload.passages:
                h.update(p.passage_text.encode("utf-8"))
            content_hash = h.hexdigest()

        status_str = payload.status.value if isinstance(payload.status, SourceAdmissionStatus) else str(payload.status)

        version_key = f"{doc_id}:{payload.version_tag}"
        if version_key in self.versions:
            existing = self.versions[version_key]
            if existing["content_sha256"] != content_hash or existing["status"].lower() != status_str.lower():
                raise PolicyConflictError(
                    f"Version {payload.version_tag} already exists with different content or status"
                )
            existing_count = sum(1 for p in self.passages if p["version_id"] == existing["id"])
            return PolicyIngestionResult(
                document_id=doc_id,
                version_id=existing["id"],
                passage_count=existing_count,
                status=existing["status"],
                created=False,
            )

        import uuid
        version_id = str(uuid.uuid4())
        self.versions[version_key] = {
            "id": version_id,
            "document_id": doc_id,
            "version_tag": payload.version_tag,
            "content_sha256": content_hash,
            "status": status_str,
        }

        seq = 0
        for p in payload.passages:
            self.passages.append({
                "id": str(uuid.uuid4()),
                "version_id": version_id,
                "passage_text": p.passage_text,
                "locator_text": p.locator_text,
                "article_number": p.article_number,
                "section_number": p.section_number,
                "page_number": p.page_number,
                "heading": p.heading,
                "sequence_order": p.sequence_order if p.sequence_order is not None else seq,
                "passage_sha256": p.passage_sha256,
            })
            seq += 1

        return PolicyIngestionResult(
            document_id=doc_id,
            version_id=version_id,
            passage_count=len(payload.passages),
            status=status_str,
            created=True,
        )


class SupabasePolicyIngestionStorage:
    """Production Supabase implementation calling the single-transaction RPC boundary."""

    def __init__(
        self,
        supabase_url: str,
        server_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._supabase_url = supabase_url.rstrip("/")
        self._server_key = server_key
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def persist_document_version(
        self, payload: PolicyDocumentIngestionInput
    ) -> PolicyIngestionResult:
        # Calculate SHA256 if not provided
        content_hash = payload.content_sha256
        if not content_hash:
            h = hashlib.sha256()
            for p in payload.passages:
                h.update(p.passage_text.encode("utf-8"))
            content_hash = h.hexdigest()

        status_str = (
            payload.status.value
            if isinstance(payload.status, SourceAdmissionStatus)
            else str(payload.status)
        ).lower()

        auth_level = (
            payload.authority_level.value
            if isinstance(payload.authority_level, PolicyAuthorityLevel)
            else str(payload.authority_level)
        ).lower()

        cat = (
            payload.category.value
            if isinstance(payload.category, PolicyCategory)
            else str(payload.category)
        ).lower()

        passages_payload = []
        for idx, p in enumerate(payload.passages):
            p_hash = p.passage_sha256
            if not p_hash:
                p_hash = hashlib.sha256(p.passage_text.encode("utf-8")).hexdigest()
            passages_payload.append({
                "passage_text": p.passage_text,
                "locator_text": p.locator_text,
                "article_number": p.article_number,
                "section_number": p.section_number,
                "page_number": p.page_number,
                "heading": p.heading,
                "sequence_order": p.sequence_order if p.sequence_order is not None else idx,
                "passage_sha256": p_hash,
            })

        start_date = (
            payload.effective_start_date.isoformat()
            if isinstance(payload.effective_start_date, datetime.datetime)
            else payload.effective_start_date
        ) or datetime.datetime.now(datetime.timezone.utc).isoformat()

        end_date = (
            payload.effective_end_date.isoformat()
            if isinstance(payload.effective_end_date, datetime.datetime)
            else payload.effective_end_date
        )

        verified_at = (
            payload.verified_at.isoformat()
            if isinstance(payload.verified_at, datetime.datetime)
            else payload.verified_at
        )
        if status_str == "verified" and not verified_at:
            verified_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        verified_by = payload.verified_by
        if status_str == "verified" and not verified_by:
            verified_by = "Morshidi Academic Authority"

        rpc_body = {
            "p_university_id": str(payload.university_id),
            "p_document_code": payload.document_code,
            "p_title": payload.title,
            "p_authority_level": auth_level,
            "p_category": cat,
            "p_language": payload.language or "ar",
            "p_version_tag": payload.version_tag,
            "p_effective_start_date": start_date,
            "p_effective_end_date": end_date,
            "p_content_sha256": content_hash,
            "p_status": status_str,
            "p_verified_at": verified_at,
            "p_verified_by": verified_by,
            "p_source_url": payload.source_url,
            "p_source_snapshot_ref": payload.source_snapshot_ref,
            "p_passages": passages_payload,
        }

        url = f"{self._supabase_url}/rest/v1/rpc/persist_policy_document_version"
        headers = {
            "apikey": self._server_key,
            "Authorization": f"Bearer {self._server_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self._client.post(url, headers=headers, json=rpc_body)
        except httpx.RequestError as exc:
            raise PolicyIngestionError(
                PolicyErrorCode.INVALID_SOURCE, f"PostgREST request failed: {exc}"
            ) from exc

        if resp.status_code == 200:
            data = resp.json()
            return PolicyIngestionResult(
                document_id=data["document_id"],
                version_id=data["version_id"],
                passage_count=data["passage_count"],
                status=data["status"],
                created=data["created"],
            )

        err_body: dict[str, Any] = {}
        try:
            err_body = resp.json()
        except Exception:
            pass

        code = err_body.get("code")
        msg = err_body.get("message", resp.text)

        if code == "23503" or "does not exist" in msg:
            raise TenantViolationError(f"Tenant or foreign key violation: {msg}")

        if code == "23505" or resp.status_code == 409 or "already exists" in msg:
            raise PolicyConflictError(f"Policy version conflict: {msg}")

        raise PolicyIngestionError(
            PolicyErrorCode.CORRUPTED_CONTENT,
            f"RPC persistence failed (HTTP {resp.status_code}): {msg}",
        )
