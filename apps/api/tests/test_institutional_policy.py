"""Unit tests for Phase P8 University Regulation RAG & Policy Retrieval (WC-038).

Tests:
1. Verified source accepted
2. Unverified source rejected / held
3. Exact citation version preserved
4. Missing evidence -> abstention
5. Conflicting verified sources -> conflict + abstention
6. Deterministic eligibility question -> engine handoff
7. Deterministic progress question -> engine handoff
8. Unsupported question -> explicit limitation
9. Superseded source does not silently replace exact-version retrieval
10. Cross-university source scope rejected
11. Citation cannot reference mismatched document/version
12. Arbitrary raw query/SQL interface does not exist
13. No hidden chain-of-thought/raw reasoning persistence fields
14. Canonical result ordering is deterministic
15. Duplicate passage handling is deterministic
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import fields

import pytest

from app.institutional_policy import (
    CitationAnchor,
    EngineHandoffTarget,
    GroundingStatus,
    InMemoryInstitutionalPolicyProvider,
    InstitutionalPolicyProvider,
    LimitationCode,
    PolicyAuthorityLevel,
    PolicyCategory,
    PolicyConflict,
    PolicyDocument,
    PolicyDocumentVersion,
    PolicyErrorCode,
    PolicyPassage,
    PolicyRetrievalError,
    PolicyRetrievalQuery,
    PolicySourceReference,
    SourceAdmissionStatus,
    classify_academic_query,
)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fixture_provider() -> InMemoryInstitutionalPolicyProvider:
    provider = InMemoryInstitutionalPolicyProvider()
    dt = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)

    # Document 1: General Academic Bylaws (University A)
    doc1 = PolicyDocument(
        document_id="doc-bylaws-001",
        university_id="univ-alpha-001",
        title="لائحة الدراسة والاختبارات الجامعية",
        document_code="REG-2026-01",
        authority_level=PolicyAuthorityLevel.UNIVERSITY_COUNCIL,
        category=PolicyCategory.ACADEMIC_BYLAWS,
        created_at=dt,
        language="ar",
    )
    provider.add_document(doc1)

    ver1_content = "نظام الدراسة والامتحانات لعام 2026"
    ver1 = PolicyDocumentVersion(
        version_id="ver-bylaws-2026",
        document_id="doc-bylaws-001",
        version_tag="v2026.1",
        effective_start_date=dt,
        content_sha256=_hash(ver1_content),
        status=SourceAdmissionStatus.VERIFIED,
        verified_at=dt,
        verified_by="academic_council_secretary",
    )
    provider.add_version(ver1)

    # Passage 1: Add/Drop Period
    p1_content = "يجوز للطالب حذف أو إضافة أي مقرر خلال الأسبوع الأول من بدء الفصل الدراسي فقط."
    p1_anchor = CitationAnchor(
        anchor_id="anchor-p1",
        document_id="doc-bylaws-001",
        version_tag="v2026.1",
        locator_text="المادة 12، الفقرة 1، ص 15",
        article_number="12",
        section_number="1",
        page_number=15,
        heading="الحذف والإضافة",
    )
    p1 = PolicyPassage(
        passage_id="pas-001",
        document_id="doc-bylaws-001",
        version_tag="v2026.1",
        university_id="univ-alpha-001",
        anchor=p1_anchor,
        content=p1_content,
        content_sha256=_hash(p1_content),
        status=SourceAdmissionStatus.VERIFIED,
        topic_tags=("الحذف", "الإضافة", "التسجيل", "add", "drop"),
    )
    provider.add_passage(p1)

    # Passage 2: Maximum Semester Load
    p2_content = "الحد الأقصى للعبء الدراسي في الفصل الاعتيادي هو 18 ساعة معتمدة."
    p2_anchor = CitationAnchor(
        anchor_id="anchor-p2",
        document_id="doc-bylaws-001",
        version_tag="v2026.1",
        locator_text="المادة 15، الفقرة 2، ص 18",
        article_number="15",
        section_number="2",
        page_number=18,
        heading="العبء الدراسي",
    )
    p2 = PolicyPassage(
        passage_id="pas-002",
        document_id="doc-bylaws-001",
        version_tag="v2026.1",
        university_id="univ-alpha-001",
        anchor=p2_anchor,
        content=p2_content,
        content_sha256=_hash(p2_content),
        status=SourceAdmissionStatus.VERIFIED,
        topic_tags=("العبء", "ساعة", "معتمدة", "credit", "load"),
    )
    provider.add_passage(p2)

    return provider


# =========================================================================
# TEST 1: Verified source accepted
# =========================================================================

@pytest.mark.anyio
async def test_01_verified_source_accepted() -> None:
    provider = _fixture_provider()
    query = PolicyRetrievalQuery(
        query_text="ما هي ضوابط حذف وإضافة المقررات؟",
        university_id="univ-alpha-001",
    )

    result = await provider.retrieve_passages(query)
    assert result.grounding_status == GroundingStatus.GROUNDED
    assert len(result.passages) == 1
    assert result.passages[0].passage_id == "pas-001"
    assert len(result.citations) == 1
    assert result.citations[0].title == "لائحة الدراسة والاختبارات الجامعية"
    assert result.citations[0].version_tag == "v2026.1"
    assert result.citations[0].locator == "المادة 12، الفقرة 1، ص 15"
    assert result.citations[0].status == SourceAdmissionStatus.VERIFIED

    grounding = await provider.evaluate_grounding(query)
    assert grounding.is_grounded is True
    assert grounding.status == GroundingStatus.GROUNDED
    assert len(grounding.citations) == 1


# =========================================================================
# TEST 2: Unverified source rejected / held
# =========================================================================

@pytest.mark.anyio
async def test_02_unverified_source_rejected_or_held() -> None:
    provider = _fixture_provider()
    dt = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)

    # Register an UNVERIFIED student blog / forum post document
    unverified_doc = PolicyDocument(
        document_id="doc-blog-002",
        university_id="univ-alpha-001",
        title="دليل غير رسمي للطلاب",
        document_code="UNOFFICIAL-GUIDE",
        authority_level=PolicyAuthorityLevel.DEPARTMENT_COUNCIL,
        category=PolicyCategory.ACADEMIC_BYLAWS,
        created_at=dt,
    )
    provider.add_document(unverified_doc)

    unver_version = PolicyDocumentVersion(
        version_id="ver-unverified",
        document_id="doc-blog-002",
        version_tag="v1.0-draft",
        effective_start_date=dt,
        content_sha256=_hash("مسودة غير معتمدة"),
        status=SourceAdmissionStatus.UNVERIFIED,
    )
    provider.add_version(unver_version)

    unver_content = "يمكن تجاوز الغياب بعذر غير موثق بحسب الاتفاق مع المدرس."
    unver_passage = PolicyPassage(
        passage_id="pas-unverified-001",
        document_id="doc-blog-002",
        version_tag="v1.0-draft",
        university_id="univ-alpha-001",
        anchor=CitationAnchor(
            anchor_id="anchor-unver",
            document_id="doc-blog-002",
            version_tag="v1.0-draft",
            locator_text="الصفحة 5",
        ),
        content=unver_content,
        content_sha256=_hash(unver_content),
        status=SourceAdmissionStatus.UNVERIFIED,
        topic_tags=("غياب", "عذر", "absence"),
    )
    provider.add_passage(unver_passage)

    query = PolicyRetrievalQuery(
        query_text="هل يقبل غياب الطالب بدون عذر موثق؟",
        university_id="univ-alpha-001",
    )

    result = await provider.retrieve_passages(query)
    assert result.grounding_status == GroundingStatus.UNVERIFIED_SOURCE
    assert len(result.limitations) >= 1
    assert result.limitations[0].code == LimitationCode.UNVERIFIED_SOURCE_REJECTED
    assert len(result.citations) == 0  # No citations for unverified sources

    grounding = await provider.evaluate_grounding(query)
    assert grounding.is_grounded is False
    assert grounding.status == GroundingStatus.UNVERIFIED_SOURCE
    assert "UNVERIFIED" in str(grounding.rejection_reason)


# =========================================================================
# TEST 3: Exact citation version preserved
# =========================================================================

@pytest.mark.anyio
async def test_03_exact_citation_version_preserved() -> None:
    provider = _fixture_provider()
    dt = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)

    # Add an exact version 2025.2
    v2_content = "لائحة الساعات 2025"
    v2 = PolicyDocumentVersion(
        version_id="ver-2025-2",
        document_id="doc-bylaws-001",
        version_tag="v2025.2",
        effective_start_date=dt,
        content_sha256=_hash(v2_content),
        status=SourceAdmissionStatus.VERIFIED,
    )
    provider.add_version(v2)

    p_v2_content = "العبء الدراسي في لائحة 2025 كان 15 ساعة."
    p_v2 = PolicyPassage(
        passage_id="pas-v2025",
        document_id="doc-bylaws-001",
        version_tag="v2025.2",
        university_id="univ-alpha-001",
        anchor=CitationAnchor(
            anchor_id="anchor-v2025",
            document_id="doc-bylaws-001",
            version_tag="v2025.2",
            locator_text="المادة 8، ص 10",
        ),
        content=p_v2_content,
        content_sha256=_hash(p_v2_content),
        status=SourceAdmissionStatus.VERIFIED,
        topic_tags=("العبء", "ساعة"),
    )
    provider.add_passage(p_v2)

    # Query requesting specifically v2025.2
    query = PolicyRetrievalQuery(
        query_text="العبء الدراسي",
        university_id="univ-alpha-001",
        specific_version_tag="v2025.2",
    )
    res = await provider.retrieve_passages(query)
    assert res.grounding_status == GroundingStatus.GROUNDED
    assert len(res.citations) == 1
    assert res.citations[0].version_tag == "v2025.2"
    assert res.citations[0].locator == "المادة 8، ص 10"


# =========================================================================
# TEST 4: Missing evidence -> abstention
# =========================================================================

@pytest.mark.anyio
async def test_04_missing_evidence_triggers_abstention() -> None:
    provider = _fixture_provider()
    query = PolicyRetrievalQuery(
        query_text="ما هي رسوم السكن الجامعي للطلاب الوافدين؟",
        university_id="univ-alpha-001",
    )

    result = await provider.retrieve_passages(query)
    assert result.grounding_status == GroundingStatus.NO_EVIDENCE
    assert len(result.passages) == 0
    assert len(result.citations) == 0
    assert len(result.limitations) == 1
    assert result.limitations[0].code == LimitationCode.NO_MATCHING_PASSAGE

    grounding = await provider.evaluate_grounding(query)
    assert grounding.is_grounded is False
    assert grounding.status == GroundingStatus.NO_EVIDENCE


# =========================================================================
# TEST 5: Conflicting verified sources -> conflict + abstention
# =========================================================================

@pytest.mark.anyio
async def test_05_conflicting_verified_sources_triggers_conflict_and_abstention() -> None:
    provider = _fixture_provider()
    dt = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)

    # Register document B with opposing regulation on summer load
    doc_summer = PolicyDocument(
        document_id="doc-summer-001",
        university_id="univ-alpha-001",
        title="لائحة الفصل الصيفي",
        document_code="SUMMER-REG",
        authority_level=PolicyAuthorityLevel.DEAN_COUNCIL,
        category=PolicyCategory.REGISTRATION_REGULATIONS,
        created_at=dt,
    )
    provider.add_document(doc_summer)

    ver_summer = PolicyDocumentVersion(
        version_id="ver-summer-1",
        document_id="doc-summer-001",
        version_tag="v1.0",
        effective_start_date=dt,
        content_sha256=_hash("صيفي"),
        status=SourceAdmissionStatus.VERIFIED,
    )
    provider.add_version(ver_summer)

    content_a = "الحد الأقصى للتسجيل في الفصل الصيفي هو 9 ساعات لجميع الطلاب."
    pas_a = PolicyPassage(
        passage_id="pas-summer-a",
        document_id="doc-summer-001",
        version_tag="v1.0",
        university_id="univ-alpha-001",
        anchor=CitationAnchor(
            anchor_id="anc-sa",
            document_id="doc-summer-001",
            version_tag="v1.0",
            locator_text="المادة 4، ص 2",
        ),
        content=content_a,
        content_sha256=_hash(content_a),
        status=SourceAdmissionStatus.CONFLICTING,
        topic_tags=("صيفي", "ساعات", "summer"),
    )
    provider.add_passage(pas_a)

    content_b = "الحد الأقصى للتسجيل في الفصل الصيفي هو 6 ساعات ولا يجوز الزيادة مطلقا."
    pas_b = PolicyPassage(
        passage_id="pas-summer-b",
        document_id="doc-summer-001",
        version_tag="v1.0",
        university_id="univ-alpha-001",
        anchor=CitationAnchor(
            anchor_id="anc-sb",
            document_id="doc-summer-001",
            version_tag="v1.0",
            locator_text="المادة 9، ص 6",
        ),
        content=content_b,
        content_sha256=_hash(content_b),
        status=SourceAdmissionStatus.CONFLICTING,
        topic_tags=("صيفي", "ساعات", "summer"),
    )
    provider.add_passage(pas_b)

    # Register explicit conflict
    conflict = PolicyConflict(
        conflict_id="conf-001",
        document_id_a="doc-summer-001",
        version_a="v1.0",
        locator_a="المادة 4، ص 2",
        passage_id_a="pas-summer-a",
        document_id_b="doc-summer-001",
        version_b="v1.0",
        locator_b="المادة 9، ص 6",
        passage_id_b="pas-summer-b",
        description="تعارض بين المادة 4 (تحدد 9 ساعات) والمادة 9 (تحدد 6 ساعات كحد أقصى للصيفي).",
    )
    provider.register_conflict(conflict)

    query = PolicyRetrievalQuery(
        query_text="ما هو الحد الأقصى لساعات الفصل صيفي؟",
        university_id="univ-alpha-001",
    )

    result = await provider.retrieve_passages(query)
    assert result.grounding_status == GroundingStatus.CONFLICTING_EVIDENCE
    assert len(result.conflicts) == 1
    assert result.conflicts[0].conflict_id == "conf-001"
    assert len(result.limitations) == 1
    assert result.limitations[0].code == LimitationCode.CONFLICTING_SOURCES_DETECTED

    grounding = await provider.evaluate_grounding(query)
    assert grounding.is_grounded is False
    assert grounding.status == GroundingStatus.CONFLICTING_EVIDENCE


# =========================================================================
# TEST 6: Deterministic eligibility question -> engine handoff
# =========================================================================

@pytest.mark.anyio
async def test_06_deterministic_eligibility_question_routes_to_engine_handoff() -> None:
    provider = _fixture_provider()

    english_query = PolicyRetrievalQuery(
        query_text="Can I take course CS101 next semester?",
        university_id="univ-alpha-001",
    )
    res_en = await provider.retrieve_passages(english_query)
    assert res_en.grounding_status == GroundingStatus.DETERMINISTIC_ENGINE_REQUIRED
    assert res_en.engine_handoff is not None
    assert res_en.engine_handoff.target_engine == EngineHandoffTarget.ELIGIBILITY_ENGINE
    assert len(res_en.passages) == 0

    arabic_query = PolicyRetrievalQuery(
        query_text="هل يمكنني تسجيل مادة الخوارزميات؟",
        university_id="univ-alpha-001",
    )
    res_ar = await provider.retrieve_passages(arabic_query)
    assert res_ar.grounding_status == GroundingStatus.DETERMINISTIC_ENGINE_REQUIRED
    assert res_ar.engine_handoff is not None
    assert res_ar.engine_handoff.target_engine == EngineHandoffTarget.ELIGIBILITY_ENGINE


# =========================================================================
# TEST 7: Deterministic progress question -> engine handoff
# =========================================================================

@pytest.mark.anyio
async def test_07_deterministic_progress_question_routes_to_engine_handoff() -> None:
    provider = _fixture_provider()

    grad_query = PolicyRetrievalQuery(
        query_text="Can I graduate this semester?",
        university_id="univ-alpha-001",
    )
    res_grad = await provider.retrieve_passages(grad_query)
    assert res_grad.grounding_status == GroundingStatus.DETERMINISTIC_ENGINE_REQUIRED
    assert res_grad.engine_handoff is not None
    assert res_grad.engine_handoff.target_engine == EngineHandoffTarget.PROGRESS_ENGINE

    credits_query = PolicyRetrievalQuery(
        query_text="كم ساعة متبقية لي للتخرج في الخطة؟",
        university_id="univ-alpha-001",
    )
    res_credits = await provider.retrieve_passages(credits_query)
    assert res_credits.grounding_status == GroundingStatus.DETERMINISTIC_ENGINE_REQUIRED
    assert res_credits.engine_handoff is not None
    assert res_credits.engine_handoff.target_engine == EngineHandoffTarget.PROGRESS_ENGINE


# =========================================================================
# TEST 8: Unsupported question emits explicit limitation
# =========================================================================

@pytest.mark.anyio
async def test_08_unsupported_question_emits_explicit_limitation() -> None:
    provider = _fixture_provider()
    query = PolicyRetrievalQuery(
        query_text="ما هي قائمة وجبات مطعم الجامعة غدا؟",
        university_id="univ-alpha-001",
    )

    result = await provider.retrieve_passages(query)
    assert result.grounding_status == GroundingStatus.NO_EVIDENCE
    assert len(result.limitations) == 1
    assert result.limitations[0].code == LimitationCode.NO_MATCHING_PASSAGE


# =========================================================================
# TEST 9: Superseded source does not silently replace exact-version retrieval
# =========================================================================

@pytest.mark.anyio
async def test_09_superseded_source_does_not_silently_replace_exact_version() -> None:
    provider = _fixture_provider()
    dt_old = datetime.datetime(2020, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)

    # Ingest a SUPERSEDED historic version
    v_old = PolicyDocumentVersion(
        version_id="ver-old-2020",
        document_id="doc-bylaws-001",
        version_tag="v2020.1",
        effective_start_date=dt_old,
        content_sha256=_hash("قديم"),
        status=SourceAdmissionStatus.SUPERSEDED,
    )
    provider.add_version(v_old)

    p_old_content = "كان الحذف والإضافة متاحا لمدة أسبوعين في اللائحة القديمة."
    p_old = PolicyPassage(
        passage_id="pas-old-001",
        document_id="doc-bylaws-001",
        version_tag="v2020.1",
        university_id="univ-alpha-001",
        anchor=CitationAnchor(
            anchor_id="anc-old",
            document_id="doc-bylaws-001",
            version_tag="v2020.1",
            locator_text="المادة 5 قديمة",
        ),
        content=p_old_content,
        content_sha256=_hash(p_old_content),
        status=SourceAdmissionStatus.SUPERSEDED,
        topic_tags=("الحذف", "الإضافة"),
    )
    provider.add_passage(p_old)

    # General query: must NOT return the superseded passage
    gen_query = PolicyRetrievalQuery(
        query_text="الحذف والإضافة",
        university_id="univ-alpha-001",
    )
    gen_res = await provider.retrieve_passages(gen_query)
    passage_ids = [p.passage_id for p in gen_res.passages]
    assert "pas-old-001" not in passage_ids
    assert "pas-001" in passage_ids

    # Exact query requesting specific older version: returns that exact version
    exact_old_query = PolicyRetrievalQuery(
        query_text="الحذف والإضافة",
        university_id="univ-alpha-001",
        specific_version_tag="v2020.1",
    )
    exact_res = await provider.retrieve_passages(exact_old_query)
    assert len(exact_res.passages) == 1
    assert exact_res.passages[0].version_tag == "v2020.1"


# =========================================================================
# TEST 10: Cross-university source scope rejected
# =========================================================================

@pytest.mark.anyio
async def test_10_cross_university_source_scope_rejected() -> None:
    provider = _fixture_provider()
    dt = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)

    # Ingest document for University BETA
    doc_beta = PolicyDocument(
        document_id="doc-beta-001",
        university_id="univ-beta-002",
        title="لائحة جامعة بيتا",
        document_code="BETA-REG",
        authority_level=PolicyAuthorityLevel.UNIVERSITY_COUNCIL,
        category=PolicyCategory.ACADEMIC_BYLAWS,
        created_at=dt,
    )
    provider.add_document(doc_beta)

    v_beta = PolicyDocumentVersion(
        version_id="ver-beta-1",
        document_id="doc-beta-001",
        version_tag="v1.0",
        effective_start_date=dt,
        content_sha256=_hash("بيتا"),
        status=SourceAdmissionStatus.VERIFIED,
    )
    provider.add_version(v_beta)

    content_beta = "يجوز لطلاب جامعة بيتا التسجيل في 21 ساعة معتمدة."
    p_beta = PolicyPassage(
        passage_id="pas-beta-001",
        document_id="doc-beta-001",
        version_tag="v1.0",
        university_id="univ-beta-002",
        anchor=CitationAnchor(
            anchor_id="anc-beta",
            document_id="doc-beta-001",
            version_tag="v1.0",
            locator_text="المادة 1",
        ),
        content=content_beta,
        content_sha256=_hash(content_beta),
        status=SourceAdmissionStatus.VERIFIED,
        topic_tags=("ساعة", "معتمدة"),
    )
    provider.add_passage(p_beta)

    # University Alpha user queries: University Beta passage MUST NEVER be returned
    alpha_query = PolicyRetrievalQuery(
        query_text="كم ساعة معتمدة؟",
        university_id="univ-alpha-001",
    )
    res_alpha = await provider.retrieve_passages(alpha_query)
    for p in res_alpha.passages:
        assert p.university_id == "univ-alpha-001"
        assert p.document_id != "doc-beta-001"

    # Direct get_citation cross-tenant call fails
    with pytest.raises(PolicyRetrievalError) as exc_info:
        await provider.get_citation("univ-alpha-001", p_beta)
    assert exc_info.value.code == PolicyErrorCode.UNAUTHORIZED_TENANT


# =========================================================================
# TEST 11: Citation cannot reference mismatched document/version
# =========================================================================

def test_11_citation_cannot_reference_mismatched_document_or_version() -> None:
    # Anchor mismatch with passage
    mismatched_anchor = CitationAnchor(
        anchor_id="anc-mismatch",
        document_id="doc-OTHER",
        version_tag="v1.0",
        locator_text="Page 1",
    )
    content = "محتوى نظامي"
    with pytest.raises(ValueError, match="anchor.document_id must match"):
        PolicyPassage(
            passage_id="pas-mismatch",
            document_id="doc-bylaws-001",
            version_tag="v1.0",
            university_id="univ-alpha-001",
            anchor=mismatched_anchor,
            content=content,
            content_sha256=_hash(content),
        )


# =========================================================================
# TEST 12: Arbitrary raw query/SQL interface does not exist
# =========================================================================

def test_12_arbitrary_raw_query_or_sql_interface_does_not_exist() -> None:
    provider = InMemoryInstitutionalPolicyProvider()
    assert isinstance(provider, InstitutionalPolicyProvider)

    forbidden_methods = [
        "execute_sql",
        "raw_query",
        "cursor",
        "execute",
        "query_sql",
        "run_sql",
        "table",
        "get_all_records",
        "raw_select",
    ]
    for method_name in forbidden_methods:
        assert not hasattr(provider, method_name), f"Forbidden method '{method_name}' must not exist"


# =========================================================================
# TEST 13: No hidden chain-of-thought/raw reasoning persistence fields
# =========================================================================

def test_13_no_hidden_chain_of_thought_or_raw_reasoning_fields() -> None:
    from app.institutional_policy import models

    classes_to_inspect = [
        models.PolicyDocument,
        models.PolicyDocumentVersion,
        models.PolicyPassage,
        models.CitationAnchor,
        models.PolicySourceReference,
        models.PolicyRetrievalQuery,
        models.PolicyRetrievalResult,
        models.PolicyRetrievalLimitation,
        models.PolicyConflict,
        models.PolicyAnswerGrounding,
        models.DeterministicEngineHandoff,
    ]

    forbidden_field_substrings = [
        "thought",
        "chain_of_thought",
        "prompt",
        "llm_output",
        "reasoning_steps",
        "hidden_reasoning",
        "scratchpad",
    ]

    for cls in classes_to_inspect:
        for f in fields(cls):
            name_lower = f.name.lower()
            for forbidden in forbidden_field_substrings:
                assert forbidden not in name_lower, (
                    f"Class '{cls.__name__}' contains forbidden reasoning field '{f.name}'"
                )


# =========================================================================
# TEST 14: Canonical result ordering is deterministic
# =========================================================================

@pytest.mark.anyio
async def test_14_canonical_result_ordering_is_deterministic() -> None:
    provider = _fixture_provider()
    query = PolicyRetrievalQuery(
        query_text="حذف وإضافة العبء الدراسي ساعة",
        university_id="univ-alpha-001",
    )

    res1 = await provider.retrieve_passages(query)
    res2 = await provider.retrieve_passages(query)

    assert len(res1.passages) == 2
    # Verify deterministic identical ordering
    assert [p.passage_id for p in res1.passages] == [p.passage_id for p in res2.passages]
    assert [c.locator for c in res1.citations] == [c.locator for c in res2.citations]


# =========================================================================
# TEST 15: Duplicate passage handling is deterministic
# =========================================================================

@pytest.mark.anyio
async def test_15_duplicate_passage_handling_is_deterministic() -> None:
    provider = _fixture_provider()
    # Re-adding same passage ID overwrites cleanly without duplication
    p1 = provider._passages["pas-001"]
    provider.add_passage(p1)

    query = PolicyRetrievalQuery(
        query_text="حذف وإضافة",
        university_id="univ-alpha-001",
    )
    res = await provider.retrieve_passages(query)
    # Output passages and citations have no duplicates
    passage_ids = [p.passage_id for p in res.passages]
    assert len(passage_ids) == len(set(passage_ids))
