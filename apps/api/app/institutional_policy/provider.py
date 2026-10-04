"""Institutional policy provider protocol and deterministic in-memory provider (WC-038).

AI EXPLAINS — DETERMINISTIC RULES DECIDE.
The provider enforces source admission, tenant isolation, exact citations,
conflict preservation, and academic engine handoff.
"""

from __future__ import annotations

import datetime
from typing import Protocol, runtime_checkable

from .classifier import classify_academic_query
from .enums import (
    GroundingStatus,
    LimitationCode,
    PolicyErrorCode,
    SourceAdmissionStatus,
)
from .errors import PolicyRetrievalError
from .models import (
    PolicyAnswerGrounding,
    PolicyConflict,
    PolicyDocument,
    PolicyDocumentVersion,
    PolicyPassage,
    PolicyRetrievalLimitation,
    PolicyRetrievalQuery,
    PolicyRetrievalResult,
    PolicySourceReference,
)


@runtime_checkable
class InstitutionalPolicyProvider(Protocol):
    """Governed protocol for retrieving and citing institutional regulations."""

    async def retrieve_passages(self, query: PolicyRetrievalQuery) -> PolicyRetrievalResult:
        """Retrieve verified policy passages for a query under strict governance."""
        ...

    async def resolve_source_version(
        self, university_id: str, document_id: str, version_tag: str
    ) -> PolicyDocumentVersion | None:
        """Resolve a specific document version within the university tenant scope."""
        ...

    async def get_citation(self, university_id: str, passage: PolicyPassage) -> PolicySourceReference:
        """Construct an exact, verifiable citation for an authoritative passage."""
        ...

    async def evaluate_grounding(self, query: PolicyRetrievalQuery) -> PolicyAnswerGrounding:
        """Evaluate whether a query can be answered with grounded regulatory evidence."""
        ...


class InMemoryInstitutionalPolicyProvider:
    """Deterministic in-memory policy provider for local verification and fixtures.

    Enforces:
    - Zero arbitrary SQL / table access.
    - Tenant isolation: documents belong strictly to one university.
    - Source admission: UNVERIFIED, SUPERSEDED, and UNAVAILABLE handling.
    - Deterministic engine handoff for computable academic rules.
    - Conflict preservation and abstention.
    - Deterministic canonical result ordering.
    """

    def __init__(self) -> None:
        # Key: (university_id, document_id) -> PolicyDocument
        self._documents: dict[tuple[str, str], PolicyDocument] = {}
        # Key: (university_id, document_id, version_tag) -> PolicyDocumentVersion
        self._versions: dict[tuple[str, str, str], PolicyDocumentVersion] = {}
        # Key: passage_id -> PolicyPassage
        self._passages: dict[str, PolicyPassage] = {}
        # Registered conflict pairs
        self._conflicts: list[PolicyConflict] = []

    def add_document(self, document: PolicyDocument) -> None:
        """Register an authoritative policy document entity."""
        self._documents[(document.university_id, document.document_id)] = document

    def add_version(self, version: PolicyDocumentVersion) -> None:
        """Register a versioned release of an authoritative policy document."""
        # Find document to get university_id
        uni_matches = [
            doc.university_id for (u_id, d_id), doc in self._documents.items() if d_id == version.document_id
        ]
        if not uni_matches:
            raise PolicyRetrievalError(
                PolicyErrorCode.DOCUMENT_NOT_FOUND,
                f"Cannot register version: parent document {version.document_id} not found",
            )
        uni_id = uni_matches[0]
        self._versions[(uni_id, version.document_id, version.version_tag)] = version

    def add_passage(self, passage: PolicyPassage) -> None:
        """Register a discrete regulatory passage with exact anchor."""
        key = (passage.university_id, passage.document_id, passage.version_tag)
        if key not in self._versions:
            raise PolicyRetrievalError(
                PolicyErrorCode.VERSION_NOT_FOUND,
                f"Cannot register passage: version {passage.version_tag} of document {passage.document_id} not registered",
            )
        self._passages[passage.passage_id] = passage

    def register_conflict(self, conflict: PolicyConflict) -> None:
        """Register a known regulatory conflict between two provisions."""
        self._conflicts.append(conflict)

    async def resolve_source_version(
        self, university_id: str, document_id: str, version_tag: str
    ) -> PolicyDocumentVersion | None:
        """Resolve a specific document version within the university tenant scope."""
        return self._versions.get((university_id, document_id, version_tag))

    async def get_citation(self, university_id: str, passage: PolicyPassage) -> PolicySourceReference:
        """Construct an exact, verifiable citation for an authoritative passage."""
        if passage.university_id != university_id:
            raise PolicyRetrievalError(
                PolicyErrorCode.UNAUTHORIZED_TENANT,
                f"Passage university_id '{passage.university_id}' does not match query tenant '{university_id}'",
            )

        doc = self._documents.get((university_id, passage.document_id))
        if not doc:
            raise PolicyRetrievalError(
                PolicyErrorCode.DOCUMENT_NOT_FOUND,
                f"Parent document '{passage.document_id}' not found for tenant '{university_id}'",
            )

        ver = self._versions.get((university_id, passage.document_id, passage.version_tag))
        if not ver:
            raise PolicyRetrievalError(
                PolicyErrorCode.VERSION_NOT_FOUND,
                f"Parent version '{passage.version_tag}' not found for document '{passage.document_id}'",
            )

        if passage.anchor.document_id != passage.document_id or passage.anchor.version_tag != passage.version_tag:
            raise PolicyRetrievalError(
                PolicyErrorCode.MISMATCHED_CITATION,
                "Passage anchor document_id/version_tag does not match passage metadata",
            )

        return PolicySourceReference(
            document_id=passage.document_id,
            version_tag=passage.version_tag,
            title=doc.title,
            locator=passage.anchor.locator_text,
            provenance_class="GOVERNED_ASSESSMENT",
            status=passage.status,
            content_sha256=passage.content_sha256,
        )

    async def retrieve_passages(self, query: PolicyRetrievalQuery) -> PolicyRetrievalResult:
        """Retrieve verified policy passages for a query under strict governance."""
        eval_time = datetime.datetime.now(datetime.timezone.utc)

        # 1. Deterministic Engine Handoff Classifier Gate
        handoff = classify_academic_query(query.query_text)
        if handoff is not None:
            return PolicyRetrievalResult(
                query=query,
                grounding_status=GroundingStatus.DETERMINISTIC_ENGINE_REQUIRED,
                evaluated_at=eval_time,
                engine_handoff=handoff,
                limitations=(
                    PolicyRetrievalLimitation(
                        code=LimitationCode.ENGINE_COMPUTATION_REQUIRED,
                        detail=handoff.reason,
                    ),
                ),
            )

        # 2. Filter Candidate Passages by University Scope (Tenant Isolation)
        tenant_passages = [
            p for p in self._passages.values() if p.university_id == query.university_id
        ]

        if query.specific_document_ids:
            tenant_passages = [
                p for p in tenant_passages if p.document_id in query.specific_document_ids
            ]

        # 3. Match by specific version or search across current/active versions
        if query.specific_version_tag:
            matching_passages = [
                p for p in tenant_passages if p.version_tag == query.specific_version_tag
            ]
        else:
            # Default behavior: omit SUPERSEDED and UNAVAILABLE passages from general search
            matching_passages = [
                p for p in tenant_passages
                if p.status not in (SourceAdmissionStatus.SUPERSEDED, SourceAdmissionStatus.UNAVAILABLE)
            ]

        # Match content or topic tags against query tokens
        query_words = set(re_tokenize(query.query_text.lower()))
        filtered_matches: list[PolicyPassage] = []
        for p in matching_passages:
            p_words = set(re_tokenize(p.content.lower()))
            topic_words = {tag.lower() for tag in p.topic_tags}
            if query_words.intersection(p_words) or query_words.intersection(topic_words):
                filtered_matches.append(p)

        # 4. Handle Case: No Evidence Found
        if not filtered_matches:
            return PolicyRetrievalResult(
                query=query,
                grounding_status=GroundingStatus.NO_EVIDENCE,
                evaluated_at=eval_time,
                limitations=(
                    PolicyRetrievalLimitation(
                        code=LimitationCode.NO_MATCHING_PASSAGE,
                        detail="No authoritative policy passages matching query were found in this university corpus.",
                    ),
                ),
            )

        # 5. Check Source Admission Status
        # If any matched passage is explicitly UNVERIFIED
        unverified = [p for p in filtered_matches if p.status == SourceAdmissionStatus.UNVERIFIED]
        if unverified:
            return PolicyRetrievalResult(
                query=query,
                grounding_status=GroundingStatus.UNVERIFIED_SOURCE,
                evaluated_at=eval_time,
                passages=tuple(unverified),
                limitations=(
                    PolicyRetrievalLimitation(
                        code=LimitationCode.UNVERIFIED_SOURCE_REJECTED,
                        detail="Matched evidence originates from an UNVERIFIED policy source. Abstaining from response.",
                    ),
                ),
            )

        # If any matched passage is explicitly UNAVAILABLE
        unavailable = [p for p in filtered_matches if p.status == SourceAdmissionStatus.UNAVAILABLE]
        if unavailable:
            return PolicyRetrievalResult(
                query=query,
                grounding_status=GroundingStatus.UNAVAILABLE_SOURCE,
                evaluated_at=eval_time,
                limitations=(
                    PolicyRetrievalLimitation(
                        code=LimitationCode.SOURCE_UNAVAILABLE,
                        detail="Referenced policy passage or version is currently UNAVAILABLE.",
                    ),
                ),
            )

        # 6. Check for Conflicting Evidence
        matched_passage_ids = {p.passage_id for p in filtered_matches}
        active_conflicts = [
            c for c in self._conflicts
            if c.passage_id_a in matched_passage_ids and c.passage_id_b in matched_passage_ids
        ]
        conflicting_status_passages = [
            p for p in filtered_matches if p.status == SourceAdmissionStatus.CONFLICTING
        ]

        if active_conflicts or len(conflicting_status_passages) >= 2:
            return PolicyRetrievalResult(
                query=query,
                grounding_status=GroundingStatus.CONFLICTING_EVIDENCE,
                evaluated_at=eval_time,
                passages=tuple(sorted(filtered_matches, key=_passage_sort_key)),
                conflicts=tuple(active_conflicts),
                limitations=(
                    PolicyRetrievalLimitation(
                        code=LimitationCode.CONFLICTING_SOURCES_DETECTED,
                        detail="Conflicting verified regulatory provisions detected on this topic. Abstaining from definitive ruling.",
                    ),
                ),
            )

        # 7. Grounded Result: Deduplicate, Deterministically Sort, and Bound Passages
        unique_passages = list({p.passage_id: p for p in filtered_matches}.values())
        unique_passages.sort(key=_passage_sort_key)
        bounded_passages = unique_passages[: query.max_passages]

        # Generate exact citations
        citations: list[PolicySourceReference] = []
        for p in bounded_passages:
            citation = await self.get_citation(query.university_id, p)
            citations.append(citation)

        # Deterministic citation deduplication & sort
        unique_citations = list({(c.document_id, c.version_tag, c.locator): c for c in citations}.values())
        unique_citations.sort(key=lambda c: (c.document_id, c.version_tag, c.locator))

        return PolicyRetrievalResult(
            query=query,
            grounding_status=GroundingStatus.GROUNDED,
            evaluated_at=eval_time,
            passages=tuple(bounded_passages),
            citations=tuple(unique_citations),
        )

    async def evaluate_grounding(self, query: PolicyRetrievalQuery) -> PolicyAnswerGrounding:
        """Evaluate whether a query can be answered with grounded regulatory evidence."""
        res = await self.retrieve_passages(query)
        is_grounded = res.grounding_status == GroundingStatus.GROUNDED
        rejection_reason = None
        if not is_grounded and res.limitations:
            rejection_reason = res.limitations[0].detail

        return PolicyAnswerGrounding(
            status=res.grounding_status,
            is_grounded=is_grounded,
            citations=res.citations,
            engine_handoff=res.engine_handoff,
            limitations=res.limitations,
            rejection_reason=rejection_reason,
        )


def _passage_sort_key(p: PolicyPassage) -> tuple[str, str, str, str]:
    """Deterministic ordering tuple for regulatory passages."""
    return (p.document_id, p.version_tag, p.anchor.locator_text, p.passage_id)


def re_tokenize(text: str) -> list[str]:
    """Simple alphanumeric tokenizer supporting Arabic and English words."""
    import re
    return re.findall(r"[\w\u0621-\u064A]+", text)
