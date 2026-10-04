"""Grounded, read-only policy answers over the existing verified hybrid search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx

from .classifier import classify_academic_query
from .embeddings import PolicyEmbeddingError
from .models import DeterministicEngineHandoff
from .service import StudentPolicyService


_PERSONAL_DECISION = re.compile(
    r"\b(?:you are eligible|you can register|you may register|your remaining credits|"
    r"you can graduate)\b|(?:أنت مؤهل|يمكنك تسجيل|يحق لك تسجيل|باقي لك|يمكنك التخرج)",
    re.IGNORECASE,
)
_PROMPT_INJECTION = re.compile(
    r"(?:ignore (?:all |previous |system )?instructions|reveal (?:the )?(?:system prompt|api key)|"
    r"use your (?:own )?knowledge|تجاهل التعليمات|أجب من معلوماتك|اكشف تعليمات النظام|"
    r"اعرض مفتاح(?: واجهة)? البرمجة)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PolicyAnswerCitation:
    document_id: str
    document_code: str
    document_title: str
    version_id: str
    version_tag: str
    passage_id: str
    locator_text: str
    passage_text: str
    article_number: str | None
    section_number: str | None
    page_number: int | None
    heading: str | None
    source_url: str | None
    passage_sha256: str | None


@dataclass(frozen=True, slots=True)
class PolicyAnswerEvidence:
    passage_id: str
    passage_text: str
    document_title: str
    version_tag: str
    locator_text: str


@dataclass(frozen=True, slots=True)
class PolicyAnswerDraft:
    status: str
    answer: str | None
    language: str | None
    cited_passage_ids: tuple[str, ...]
    abstention_reason: str | None = None


class PolicyAnswerProviderError(RuntimeError):
    """Safe provider failure with no upstream response content."""


class PolicyAnswerProvider(Protocol):
    async def answer(
        self, question: str, language: str, evidence: tuple[PolicyAnswerEvidence, ...]
    ) -> PolicyAnswerDraft: ...


@dataclass(frozen=True, slots=True)
class PolicyAnswerResult:
    status: str
    answer: str | None = None
    language: str | None = None
    citations: tuple[PolicyAnswerCitation, ...] = ()
    retrieval_mode: str = "hybrid"
    abstention_reason: str | None = None
    handoff: DeterministicEngineHandoff | None = None


def _required(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid policy evidence")
    return value


def _optional_text(row: Mapping[str, Any], field: str) -> str | None:
    value = row.get(field)
    if value is not None and not isinstance(value, str):
        raise ValueError("invalid policy evidence")
    return value


def _citation(row: Mapping[str, Any]) -> PolicyAnswerCitation:
    if row.get("status") != "verified":
        raise ValueError("unverified policy evidence")
    page = row.get("page_number")
    if page is not None and (isinstance(page, bool) or not isinstance(page, int) or page < 1):
        raise ValueError("invalid policy evidence")
    return PolicyAnswerCitation(
        document_id=_required(row, "document_id"),
        document_code=_required(row, "document_code"),
        document_title=_required(row, "document_title"),
        version_id=_required(row, "version_id"),
        version_tag=_required(row, "version_tag"),
        passage_id=_required(row, "passage_id"),
        locator_text=_required(row, "locator_text"),
        passage_text=_required(row, "passage_text"),
        article_number=_optional_text(row, "article_number"),
        section_number=_optional_text(row, "section_number"),
        page_number=page,
        heading=_optional_text(row, "heading"),
        source_url=_optional_text(row, "source_url"),
        passage_sha256=_optional_text(row, "passage_sha256"),
    )


def _abstain(reason: str, language: str | None = None) -> PolicyAnswerResult:
    return PolicyAnswerResult(status="ABSTAINED", language=language, abstention_reason=reason)


class PolicyAnswerService:
    """Enforce handoff, evidence, and citation guards around an untrusted provider."""

    def __init__(
        self, policies: StudentPolicyService, provider: PolicyAnswerProvider | None = None
    ) -> None:
        self._policies = policies
        self._provider = provider

    async def answer(self, university_id: str, question: str, limit: int = 6) -> PolicyAnswerResult:
        cleaned = " ".join(question.split())
        if not 1 <= limit <= 8 or not cleaned:
            raise ValueError("invalid policy answer request")
        language = "ar" if re.search(r"[\u0600-\u06ff]", cleaned) else "en"
        handoff = classify_academic_query(cleaned)
        if handoff is not None:
            return PolicyAnswerResult(status="HANDOFF_REQUIRED", language=language, handoff=handoff)
        if _PROMPT_INJECTION.search(cleaned):
            return _abstain("UNSAFE_POLICY_QUERY", language)

        try:
            # This read makes the currently empty institutional corpus abstain even
            # when an embedding or answer provider has not been configured.
            if not await self._policies.list_policies_for_student(university_id):
                return _abstain("NO_VERIFIED_POLICY_EVIDENCE", language)
            rows = await self._policies.search_policies_for_student(
                university_id, cleaned, limit, mode="hybrid"
            )
        except (PolicyEmbeddingError, httpx.HTTPError):
            return _abstain("RETRIEVAL_UNAVAILABLE", language)
        if not rows:
            return _abstain("NO_VERIFIED_POLICY_EVIDENCE", language)
        try:
            citations = tuple(_citation(row) for row in rows)
        except (TypeError, ValueError):
            return _abstain("INVALID_POLICY_EVIDENCE", language)
        ids = tuple(item.passage_id for item in citations)
        if len(ids) != len(set(ids)):
            return _abstain("INVALID_POLICY_EVIDENCE", language)
        if any(_PROMPT_INJECTION.search(item.passage_text) for item in citations):
            return _abstain("UNTRUSTED_POLICY_CONTENT", language)
        versions: dict[str, str] = {}
        for item in citations:
            previous = versions.setdefault(item.document_id, item.version_id)
            if previous != item.version_id:
                return _abstain("CONFLICTING_POLICY_VERSIONS", language)
        if self._provider is None:
            return _abstain("PROVIDER_UNAVAILABLE", language)

        evidence = tuple(
            PolicyAnswerEvidence(
                item.passage_id, item.passage_text, item.document_title,
                item.version_tag, item.locator_text,
            )
            for item in citations
        )
        try:
            draft = await self._provider.answer(cleaned, language, evidence)
        except Exception:
            return _abstain("PROVIDER_UNAVAILABLE", language)
        if not isinstance(draft, PolicyAnswerDraft):
            return _abstain("INVALID_PROVIDER_OUTPUT", language)
        if draft.status == "ABSTAINED":
            return _abstain("INSUFFICIENT_POLICY_EVIDENCE", language)
        if draft.status != "ANSWERED":
            return _abstain("INVALID_PROVIDER_OUTPUT", language)
        if (
            not isinstance(draft.answer, str)
            or not draft.answer.strip()
            or len(draft.answer) > 2000
            or draft.language != language
            or not isinstance(draft.cited_passage_ids, tuple)
            or not draft.cited_passage_ids
            or any(not isinstance(item, str) for item in draft.cited_passage_ids)
            or len(draft.cited_passage_ids) != len(set(draft.cited_passage_ids))
            or not set(draft.cited_passage_ids).issubset(ids)
        ):
            return _abstain("INVALID_PROVIDER_OUTPUT", language)
        if (
            classify_academic_query(draft.answer) is not None
            or _PERSONAL_DECISION.search(draft.answer)
            or _PROMPT_INJECTION.search(draft.answer)
        ):
            return _abstain("DETERMINISTIC_DECISION_GUARD", language)
        cited_ids = set(draft.cited_passage_ids)
        return PolicyAnswerResult(
            status="ANSWERED",
            answer=draft.answer.strip(),
            language=language,
            citations=tuple(item for item in citations if item.passage_id in cited_ids),
        )
