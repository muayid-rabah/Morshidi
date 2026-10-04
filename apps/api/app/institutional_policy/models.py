"""Immutable typed domain contracts for institutional policy retrieval (WC-038).

AI EXPLAINS — DETERMINISTIC RULES DECIDE.
These contracts preserve provenance, source admission, exact citations,
conflict detection, and deterministic academic engine handoff.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from .enums import (
    EngineHandoffTarget,
    GroundingStatus,
    LimitationCode,
    PolicyAuthorityLevel,
    PolicyCategory,
    SourceAdmissionStatus,
)


@dataclass(frozen=True, slots=True)
class CitationAnchor:
    """Exact structural anchor within a policy document."""

    anchor_id: str
    document_id: str
    version_tag: str
    locator_text: str
    article_number: str | None = None
    section_number: str | None = None
    page_number: int | None = None
    heading: str | None = None

    def __post_init__(self) -> None:
        if not self.anchor_id.strip():
            raise ValueError("anchor_id cannot be empty")
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        if not self.version_tag.strip():
            raise ValueError("version_tag cannot be empty")
        if not self.locator_text.strip():
            raise ValueError("locator_text cannot be empty")


@dataclass(frozen=True, slots=True)
class PolicyDocument:
    """Authoritative university policy document entity."""

    document_id: str
    university_id: str
    title: str
    document_code: str
    authority_level: PolicyAuthorityLevel
    category: PolicyCategory
    created_at: datetime
    language: str = "ar"

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        if not self.university_id.strip():
            raise ValueError("university_id cannot be empty")
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if not self.document_code.strip():
            raise ValueError("document_code cannot be empty")


@dataclass(frozen=True, slots=True)
class PolicyDocumentVersion:
    """Versioned release of an authoritative policy document."""

    version_id: str
    document_id: str
    version_tag: str
    effective_start_date: datetime
    content_sha256: str
    effective_end_date: datetime | None = None
    status: SourceAdmissionStatus = SourceAdmissionStatus.VERIFIED
    verified_at: datetime | None = None
    verified_by: str | None = None

    def __post_init__(self) -> None:
        if not self.version_id.strip():
            raise ValueError("version_id cannot be empty")
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        if not self.version_tag.strip():
            raise ValueError("version_tag cannot be empty")
        if len(self.content_sha256) != 64:
            raise ValueError("content_sha256 must be a 64-character lowercase hex string")


@dataclass(frozen=True, slots=True)
class PolicyPassage:
    """Discrete, verbatim regulatory passage extracted from a policy version."""

    passage_id: str
    document_id: str
    version_tag: str
    university_id: str
    anchor: CitationAnchor
    content: str
    content_sha256: str
    status: SourceAdmissionStatus = SourceAdmissionStatus.VERIFIED
    topic_tags: tuple[str, ...] = ()
    conflict_cluster_id: str | None = None

    def __post_init__(self) -> None:
        if not self.passage_id.strip():
            raise ValueError("passage_id cannot be empty")
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        if not self.version_tag.strip():
            raise ValueError("version_tag cannot be empty")
        if not self.university_id.strip():
            raise ValueError("university_id cannot be empty")
        if not self.content.strip():
            raise ValueError("passage content cannot be empty")
        if self.anchor.document_id != self.document_id:
            raise ValueError("anchor.document_id must match passage.document_id")
        if self.anchor.version_tag != self.version_tag:
            raise ValueError("anchor.version_tag must match passage.version_tag")
        expected_sha = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.content_sha256 != expected_sha:
            raise ValueError(f"content_sha256 mismatch: expected {expected_sha}, got {self.content_sha256}")


@dataclass(frozen=True, slots=True)
class PolicySourceReference:
    """Verifiable citation referencing an authoritative policy passage."""

    document_id: str
    version_tag: str
    title: str
    locator: str
    provenance_class: str = "GOVERNED_ASSESSMENT"
    status: SourceAdmissionStatus = SourceAdmissionStatus.VERIFIED
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        if not self.version_tag.strip():
            raise ValueError("version_tag cannot be empty")
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if not self.locator.strip():
            raise ValueError("locator cannot be empty")


@dataclass(frozen=True, slots=True)
class DeterministicEngineHandoff:
    """Typed routing descriptor for queries owned by deterministic academic engines."""

    target_engine: EngineHandoffTarget
    query_topic: str
    reason: str

    def __post_init__(self) -> None:
        if not self.query_topic.strip():
            raise ValueError("query_topic cannot be empty")
        if not self.reason.strip():
            raise ValueError("reason cannot be empty")


@dataclass(frozen=True, slots=True)
class PolicyRetrievalLimitation:
    """Typed limitation accompanying a retrieval result or abstention."""

    code: LimitationCode
    detail: str

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise ValueError("detail cannot be empty")


@dataclass(frozen=True, slots=True)
class PolicyConflict:
    """Detected conflict between two verified regulatory provisions."""

    conflict_id: str
    document_id_a: str
    version_a: str
    locator_a: str
    passage_id_a: str
    document_id_b: str
    version_b: str
    locator_b: str
    passage_id_b: str
    description: str

    def __post_init__(self) -> None:
        if not self.conflict_id.strip():
            raise ValueError("conflict_id cannot be empty")
        if not self.description.strip():
            raise ValueError("description cannot be empty")


@dataclass(frozen=True, slots=True)
class PolicyRetrievalQuery:
    """Governed query requesting institutional policy evidence."""

    query_text: str
    university_id: str
    effective_date: datetime | None = None
    specific_document_ids: tuple[str, ...] = ()
    specific_version_tag: str | None = None
    max_passages: int = 5

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise ValueError("query_text cannot be empty")
        if not self.university_id.strip():
            raise ValueError("university_id cannot be empty")
        if self.max_passages <= 0:
            raise ValueError("max_passages must be positive")


@dataclass(frozen=True, slots=True)
class PolicyAnswerGrounding:
    """Grounded evidence assessment envelope for answering a user request."""

    status: GroundingStatus
    is_grounded: bool
    citations: tuple[PolicySourceReference, ...] = ()
    engine_handoff: DeterministicEngineHandoff | None = None
    limitations: tuple[PolicyRetrievalLimitation, ...] = ()
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyRetrievalResult:
    """Governed response from an InstitutionalPolicyProvider."""

    query: PolicyRetrievalQuery
    grounding_status: GroundingStatus
    evaluated_at: datetime
    passages: tuple[PolicyPassage, ...] = ()
    citations: tuple[PolicySourceReference, ...] = ()
    conflicts: tuple[PolicyConflict, ...] = ()
    limitations: tuple[PolicyRetrievalLimitation, ...] = ()
    engine_handoff: DeterministicEngineHandoff | None = None
