"""Supabase PostgREST adapter for institutional policy retrieval (WC-038).

AI EXPLAINS — DETERMINISTIC RULES DECIDE.
Enforces:
- Reading only verified active policy versions by default.
- Preserving exact version tags and exact citation locators.
- University-level tenant isolation.
- Detection and preservation of conflicting verified sources.
- Safe abstention on missing evidence or unverified sources.
- No silent substitution of superseded or withdrawn versions.
- Zero arbitrary SQL or raw query execution capability.
"""

from __future__ import annotations

import datetime
import hashlib
from collections.abc import Mapping, Sequence
from typing import Any
import httpx

from .classifier import classify_academic_query
from .enums import (
    GroundingStatus,
    LimitationCode,
    PolicyAuthorityLevel,
    PolicyCategory,
    PolicyErrorCode,
    SourceAdmissionStatus,
)
from .errors import PolicyRetrievalError
from .models import (
    CitationAnchor,
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
from .provider import _passage_sort_key, re_tokenize


class SupabaseInstitutionalPolicyProvider:
    """Server-side Supabase PostgREST adapter for governed institutional policy retrieval."""

    def __init__(
        self,
        supabase_url: str,
        server_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._supabase_url = supabase_url.rstrip("/")
        self._server_key = server_key
        self._rest_url = f"{self._supabase_url}/rest/v1"
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._conflicts: list[PolicyConflict] = []

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    def register_conflict(self, conflict: PolicyConflict) -> None:
        self._conflicts.append(conflict)

    async def _get_rows(
        self, resource: str, params: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        try:
            response = await self._client.get(
                f"{self._rest_url}/{resource}",
                params=params,
                headers={
                    "apikey": self._server_key,
                    "Authorization": f"Bearer {self._server_key}",
                    "Accept": "application/json",
                },
            )
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise PolicyRetrievalError(
                PolicyErrorCode.INVALID_SOURCE,
                f"Transport failure while querying {resource}: {error}",
            ) from error

        if not (200 <= response.status_code < 300):
            raise PolicyRetrievalError(
                PolicyErrorCode.INVALID_SOURCE,
                f"PostgREST returned status {response.status_code} for {resource}",
            )

        try:
            body = response.json()
        except ValueError as error:
            raise PolicyRetrievalError(
                PolicyErrorCode.CORRUPTED_CONTENT,
                f"Invalid JSON response from {resource}",
            ) from error

        if not isinstance(body, list) or not all(isinstance(x, dict) for x in body):
            raise PolicyRetrievalError(
                PolicyErrorCode.CORRUPTED_CONTENT,
                f"Expected list response from {resource}",
            )

        return body

    async def resolve_source_version(
        self, university_id: str, document_id: str, version_tag: str
    ) -> PolicyDocumentVersion | None:
        if not university_id.strip():
            raise PolicyRetrievalError(
                PolicyErrorCode.UNAUTHORIZED_TENANT,
                "university_id cannot be empty",
            )
        if not document_id.strip():
            raise PolicyRetrievalError(
                PolicyErrorCode.DOCUMENT_NOT_FOUND,
                "document_id cannot be empty",
            )
        if not version_tag.strip():
            raise PolicyRetrievalError(
                PolicyErrorCode.VERSION_NOT_FOUND,
                "version_tag cannot be empty",
            )

        params = {
            "select": (
                "id,document_id,version_tag,status,effective_start_date,"
                "effective_end_date,content_sha256,verified_at,verified_by,"
                "source_url,source_snapshot_ref,policy_documents!inner(id,university_id)"
            ),
            "document_id": f"eq.{document_id}",
            "version_tag": f"eq.{version_tag}",
            "policy_documents.university_id": f"eq.{university_id}",
        }
        rows = await self._get_rows("policy_document_versions", params)
        if not rows:
            return None
        return _map_version(rows[0])

    async def get_citation(
        self, university_id: str, passage: PolicyPassage
    ) -> PolicySourceReference:
        if passage.university_id != university_id:
            raise PolicyRetrievalError(
                PolicyErrorCode.UNAUTHORIZED_TENANT,
                f"Passage university_id '{passage.university_id}' does not match query tenant '{university_id}'",
            )

        if (
            passage.anchor.document_id != passage.document_id
            or passage.anchor.version_tag != passage.version_tag
        ):
            raise PolicyRetrievalError(
                PolicyErrorCode.MISMATCHED_CITATION,
                "Passage anchor document_id/version_tag does not match passage metadata",
            )

        doc_rows = await self._get_rows(
            "policy_documents",
            {
                "select": "id,university_id,title",
                "id": f"eq.{passage.document_id}",
                "university_id": f"eq.{university_id}",
            },
        )
        if not doc_rows:
            raise PolicyRetrievalError(
                PolicyErrorCode.DOCUMENT_NOT_FOUND,
                f"Parent document '{passage.document_id}' not found for tenant '{university_id}'",
            )

        doc_title = str(doc_rows[0].get("title") or passage.document_id)
        ver = await self.resolve_source_version(
            university_id, passage.document_id, passage.version_tag
        )
        if not ver:
            raise PolicyRetrievalError(
                PolicyErrorCode.VERSION_NOT_FOUND,
                f"Parent version '{passage.version_tag}' not found for document '{passage.document_id}'",
            )

        return PolicySourceReference(
            document_id=passage.document_id,
            version_tag=passage.version_tag,
            title=doc_title,
            locator=passage.anchor.locator_text,
            provenance_class="GOVERNED_ASSESSMENT",
            status=passage.status,
            content_sha256=passage.content_sha256,
        )

    async def retrieve_passages(
        self, query: PolicyRetrievalQuery
    ) -> PolicyRetrievalResult:
        eval_time = datetime.datetime.now(datetime.timezone.utc)

        # 1. Deterministic Engine Handoff Gate
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

        # 2. Build PostgREST Query
        params: dict[str, str] = {
            "select": (
                "id,passage_text,locator_text,article_number,section_number,"
                "page_number,heading,sequence_order,passage_sha256,"
                "policy_document_versions!inner("
                "id,document_id,version_tag,status,effective_start_date,"
                "effective_end_date,content_sha256,verified_at,verified_by,"
                "policy_documents!inner("
                "id,university_id,document_code,title,authority_level,category,language"
                ")"
                ")"
            ),
            "policy_document_versions.policy_documents.university_id": f"eq.{query.university_id}",
            "order": "sequence_order.asc,locator_text.asc",
        }

        if query.specific_document_ids:
            doc_ids = ",".join(query.specific_document_ids)
            params["policy_document_versions.document_id"] = f"in.({doc_ids})"

        if query.specific_version_tag:
            params["policy_document_versions.version_tag"] = f"eq.{query.specific_version_tag}"
        else:
            params["policy_document_versions.status"] = "eq.verified"

        rows = await self._get_rows("policy_passages", params)

        all_passages: list[PolicyPassage] = []
        titles_by_doc_id: dict[str, str] = {}
        for row in rows:
            passage, doc_title = _map_passage(row, query.university_id)
            all_passages.append(passage)
            titles_by_doc_id[passage.document_id] = doc_title

        # Filter matches by query tokens
        query_words = set(re_tokenize(query.query_text.lower()))
        filtered_matches: list[PolicyPassage] = []
        for p in all_passages:
            p_words = set(re_tokenize(p.content.lower()))
            locator_words = set(re_tokenize(p.anchor.locator_text.lower()))
            heading_words = set(re_tokenize((p.anchor.heading or "").lower()))
            topic_words = {tag.lower() for tag in p.topic_tags}
            if (
                query_words.intersection(p_words)
                or query_words.intersection(locator_words)
                or query_words.intersection(heading_words)
                or query_words.intersection(topic_words)
            ):
                filtered_matches.append(p)

        # 3. Handle Case: No Evidence Found
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

        # 4. Check Source Admission Status
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

        pending = [p for p in filtered_matches if p.status == SourceAdmissionStatus.PENDING_REVIEW]
        if pending:
            return PolicyRetrievalResult(
                query=query,
                grounding_status=GroundingStatus.UNVERIFIED_SOURCE,
                evaluated_at=eval_time,
                passages=tuple(pending),
                limitations=(
                    PolicyRetrievalLimitation(
                        code=LimitationCode.PENDING_REVIEW_HELD,
                        detail="Matched policy version is PENDING_REVIEW and currently held from authoritative retrieval.",
                    ),
                ),
            )

        withdrawn = [p for p in filtered_matches if p.status == SourceAdmissionStatus.WITHDRAWN]
        if withdrawn:
            return PolicyRetrievalResult(
                query=query,
                grounding_status=GroundingStatus.UNAVAILABLE_SOURCE,
                evaluated_at=eval_time,
                passages=tuple(withdrawn),
                limitations=(
                    PolicyRetrievalLimitation(
                        code=LimitationCode.WITHDRAWN_SOURCE_EXCLUDED,
                        detail="Matched policy version is WITHDRAWN and no longer authoritative.",
                    ),
                ),
            )

        if not query.specific_version_tag:
            superseded = [p for p in filtered_matches if p.status == SourceAdmissionStatus.SUPERSEDED]
            if superseded:
                return PolicyRetrievalResult(
                    query=query,
                    grounding_status=GroundingStatus.UNAVAILABLE_SOURCE,
                    evaluated_at=eval_time,
                    passages=tuple(superseded),
                    limitations=(
                        PolicyRetrievalLimitation(
                            code=LimitationCode.SUPERSEDED_SOURCE_EXCLUDED,
                            detail="Matched evidence originates from a SUPERSEDED policy version and was not explicitly requested.",
                        ),
                    ),
                )

        # 5. Check Contradictions / Conflicts
        doc_ids = {p.document_id for p in filtered_matches}
        active_conflict: PolicyConflict | None = None
        for conf in self._conflicts:
            if conf.document_id_a in doc_ids and conf.document_id_b in doc_ids:
                active_conflict = conf
                break

        if active_conflict is not None:
            return PolicyRetrievalResult(
                query=query,
                grounding_status=GroundingStatus.CONFLICTING_EVIDENCE,
                evaluated_at=eval_time,
                passages=tuple(filtered_matches),
                conflicts=(active_conflict,),
                limitations=(
                    PolicyRetrievalLimitation(
                        code=LimitationCode.CONFLICTING_SOURCES_DETECTED,
                        detail=f"Conflicting regulations detected between {active_conflict.document_id_a} and {active_conflict.document_id_b}: {active_conflict.description}",
                    ),
                ),
            )

        # 6. Build Bound Results and Citations
        unique_passages = list({p.passage_id: p for p in filtered_matches}.values())
        unique_passages.sort(key=_passage_sort_key)
        bounded_passages = unique_passages[: query.max_passages]

        seen_citations: set[tuple[str, str, str]] = set()
        unique_citations: list[PolicySourceReference] = []
        for p in bounded_passages:
            c_key = (p.document_id, p.version_tag, p.anchor.locator_text)
            if c_key not in seen_citations:
                seen_citations.add(c_key)
                title = titles_by_doc_id.get(p.document_id, p.document_id)
                unique_citations.append(
                    PolicySourceReference(
                        document_id=p.document_id,
                        version_tag=p.version_tag,
                        title=title,
                        locator=p.anchor.locator_text,
                        provenance_class="GOVERNED_ASSESSMENT",
                        status=p.status,
                        content_sha256=p.content_sha256,
                    )
                )

        return PolicyRetrievalResult(
            query=query,
            grounding_status=GroundingStatus.GROUNDED,
            evaluated_at=eval_time,
            passages=tuple(bounded_passages),
            citations=tuple(unique_citations),
        )

    async def evaluate_grounding(
        self, query: PolicyRetrievalQuery
    ) -> PolicyAnswerGrounding:
        res = await self.retrieve_passages(query)
        is_grounded = res.grounding_status == GroundingStatus.GROUNDED
        rejection_reason = None
        if not is_grounded and res.limitations:
            rejection_reason = res.limitations[0].detail

        return PolicyAnswerGrounding(
            grounding_status=res.grounding_status,
            is_grounded=is_grounded,
            authoritative_citations=res.citations,
            rejection_reason=rejection_reason,
            unresolved_conflicts=res.conflicts,
        )


def _map_version(row: Mapping[str, Any]) -> PolicyDocumentVersion:
    status_str = str(row.get("status", "")).upper()
    status = (
        SourceAdmissionStatus(status_str)
        if status_str in SourceAdmissionStatus.__members__
        else SourceAdmissionStatus.UNVERIFIED
    )

    eff_start = row.get("effective_start_date")
    start_dt = (
        datetime.datetime.fromisoformat(eff_start)
        if isinstance(eff_start, str)
        else datetime.datetime.now(datetime.timezone.utc)
    )

    eff_end = row.get("effective_end_date")
    end_dt = datetime.datetime.fromisoformat(eff_end) if isinstance(eff_end, str) else None

    v_at = row.get("verified_at")
    ver_dt = datetime.datetime.fromisoformat(v_at) if isinstance(v_at, str) else None

    return PolicyDocumentVersion(
        version_id=str(row["id"]),
        document_id=str(row["document_id"]),
        version_tag=str(row["version_tag"]),
        effective_start_date=start_dt,
        effective_end_date=end_dt,
        content_sha256=str(row["content_sha256"]),
        status=status,
        verified_at=ver_dt,
        verified_by=row.get("verified_by"),
    )


def _map_passage(
    row: Mapping[str, Any], query_university_id: str
) -> tuple[PolicyPassage, str]:
    version_row = row["policy_document_versions"]
    doc_row = version_row["policy_documents"]

    doc_id = str(version_row["document_id"])
    version_tag = str(version_row["version_tag"])
    doc_title = str(doc_row["title"])
    u_id = str(doc_row["university_id"])

    # Double check tenant isolation
    if u_id != query_university_id:
        raise PolicyRetrievalError(
            PolicyErrorCode.UNAUTHORIZED_TENANT,
            f"Cross-tenant leak detected: passage university_id '{u_id}' does not match query tenant '{query_university_id}'",
        )

    status_str = str(version_row.get("status", "")).upper()
    status = (
        SourceAdmissionStatus(status_str)
        if status_str in SourceAdmissionStatus.__members__
        else SourceAdmissionStatus.UNVERIFIED
    )

    locator = str(row["locator_text"])
    passage_id = str(row["id"])
    content = str(row["passage_text"])
    sha = str(row.get("passage_sha256") or hashlib.sha256(content.encode("utf-8")).hexdigest())

    anchor = CitationAnchor(
        anchor_id=f"anchor-{passage_id}",
        document_id=doc_id,
        version_tag=version_tag,
        locator_text=locator,
        article_number=row.get("article_number"),
        section_number=row.get("section_number"),
        page_number=row.get("page_number"),
        heading=row.get("heading"),
    )

    passage = PolicyPassage(
        passage_id=passage_id,
        document_id=doc_id,
        version_tag=version_tag,
        university_id=u_id,
        anchor=anchor,
        content=content,
        content_sha256=sha,
        status=status,
    )

    return passage, doc_title
