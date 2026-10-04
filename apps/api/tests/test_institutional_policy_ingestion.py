"""Pure unit tests for institutional policy ingestion layer (WC-038).

AI EXPLAINS — DETERMINISTIC RULES DECIDE.
Verifies:
- Input validation on documents and passages.
- In-memory single-transaction atomic ingestion.
- Idempotency on matching hash and status.
- Conflict rejection on mismatched hash or status.
- University boundary / tenant isolation.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
import pytest

from app.institutional_policy.enums import (
    PolicyAuthorityLevel,
    PolicyCategory,
    SourceAdmissionStatus,
)
from app.institutional_policy.ingestion import (
    InMemoryPolicyIngestionStorage,
    PolicyConflictError,
    PolicyDocumentIngestionInput,
    PolicyPassageIngestionInput,
    TenantViolationError,
)


def test_passage_input_validation() -> None:
    # Valid passage
    p = PolicyPassageIngestionInput(
        passage_text="يجب على الطالب الالتزام بالخطة الدراسية.",
        locator_text="المادة 12، فقرة أ",
        article_number="12",
        section_number="أ",
        page_number=5,
        sequence_order=1,
    )
    assert p.passage_text == "يجب على الطالب الالتزام بالخطة الدراسية."
    assert p.locator_text == "المادة 12، فقرة أ"

    # Empty text
    with pytest.raises(ValueError, match="passage_text cannot be empty"):
        PolicyPassageIngestionInput(passage_text="", locator_text="المادة 1")

    # Empty locator
    with pytest.raises(ValueError, match="locator_text cannot be empty"):
        PolicyPassageIngestionInput(passage_text="نص سليم", locator_text="   ")

    # Invalid page number
    with pytest.raises(ValueError, match="page_number must be positive"):
        PolicyPassageIngestionInput(passage_text="نص سليم", locator_text="المادة 1", page_number=0)

    # Invalid sequence order
    with pytest.raises(ValueError, match="sequence_order must be non-negative"):
        PolicyPassageIngestionInput(passage_text="نص سليم", locator_text="المادة 1", sequence_order=-1)


def test_document_input_validation() -> None:
    univ_id = str(uuid.uuid4())
    # Valid document
    doc = PolicyDocumentIngestionInput(
        university_id=univ_id,
        document_code="REG-2026-01",
        title="تعليمات منح درجة البكالوريوس",
        authority_level=PolicyAuthorityLevel.UNIVERSITY_COUNCIL,
        category=PolicyCategory.ACADEMIC_BYLAWS,
        version_tag="1.0",
    )
    assert doc.document_code == "REG-2026-01"

    # Empty university_id
    with pytest.raises(ValueError, match="university_id cannot be empty"):
        PolicyDocumentIngestionInput(
            university_id="   ",
            document_code="REG-01",
            title="تعليمات",
            authority_level="university_council",
            category="academic_bylaws",
        )

    # Empty document_code
    with pytest.raises(ValueError, match="document_code cannot be empty"):
        PolicyDocumentIngestionInput(
            university_id=univ_id,
            document_code="",
            title="تعليمات",
            authority_level="university_council",
            category="academic_bylaws",
        )

    # Empty title
    with pytest.raises(ValueError, match="title cannot be empty"):
        PolicyDocumentIngestionInput(
            university_id=univ_id,
            document_code="REG-01",
            title="",
            authority_level="university_council",
            category="academic_bylaws",
        )


def test_in_memory_atomic_ingestion_success() -> None:
    async def run() -> None:
        univ_id = str(uuid.uuid4())
        storage = InMemoryPolicyIngestionStorage(known_universities={univ_id})

        passages = [
            PolicyPassageIngestionInput(
                passage_text="المادة 1: تسمى هذه التعليمات تعليمات البكالوريوس.",
                locator_text="المادة 1",
                article_number="1",
                sequence_order=0,
            ),
            PolicyPassageIngestionInput(
                passage_text="المادة 2: تسري هذه التعليمات على جميع الطلبة المسجلين.",
                locator_text="المادة 2",
                article_number="2",
                sequence_order=1,
            ),
        ]

        payload = PolicyDocumentIngestionInput(
            university_id=univ_id,
            document_code="UOR-BYLAW-01",
            title="تعليمات البكالوريوس",
            authority_level=PolicyAuthorityLevel.UNIVERSITY_COUNCIL,
            category=PolicyCategory.ACADEMIC_BYLAWS,
            version_tag="1.0",
            passages=passages,
        )

        res = await storage.persist_document_version(payload)
        assert res.created is True
        assert res.passage_count == 2
        assert res.status == "VERIFIED"
        assert res.document_id in [d["id"] for d in storage.documents.values()]
        assert res.version_id in [v["id"] for v in storage.versions.values()]

    asyncio.run(run())


def test_in_memory_idempotent_reingestion() -> None:
    async def run() -> None:
        univ_id = str(uuid.uuid4())
        storage = InMemoryPolicyIngestionStorage(known_universities={univ_id})

        passages = [
            PolicyPassageIngestionInput(
                passage_text="نص المادة الأولى",
                locator_text="المادة 1",
                sequence_order=0,
            )
        ]
        payload = PolicyDocumentIngestionInput(
            university_id=univ_id,
            document_code="POL-IDEM-01",
            title="لائحة تجريبية",
            authority_level="university_council",
            category="academic_bylaws",
            version_tag="1.0",
            passages=passages,
        )

        res1 = await storage.persist_document_version(payload)
        assert res1.created is True

        # Re-ingest exact same payload
        res2 = await storage.persist_document_version(payload)
        assert res2.created is False
        assert res2.version_id == res1.version_id
        assert res2.document_id == res1.document_id
        assert res2.passage_count == 1

    asyncio.run(run())


def test_in_memory_conflict_rejection() -> None:
    async def run() -> None:
        univ_id = str(uuid.uuid4())
        storage = InMemoryPolicyIngestionStorage(known_universities={univ_id})

        passages1 = [
            PolicyPassageIngestionInput(
                passage_text="نص النسخة الأصلية",
                locator_text="المادة 1",
            )
        ]
        payload1 = PolicyDocumentIngestionInput(
            university_id=univ_id,
            document_code="POL-CONF-01",
            title="لائحة التعارض",
            authority_level="university_council",
            category="academic_bylaws",
            version_tag="1.0",
            passages=passages1,
        )
        await storage.persist_document_version(payload1)

        # Ingest same version_tag but differing passage text (changes content_sha256)
        passages2 = [
            PolicyPassageIngestionInput(
                passage_text="نص معدل مختلف تماماً",
                locator_text="المادة 1",
            )
        ]
        payload2 = PolicyDocumentIngestionInput(
            university_id=univ_id,
            document_code="POL-CONF-01",
            title="لائحة التعارض",
            authority_level="university_council",
            category="academic_bylaws",
            version_tag="1.0",
            passages=passages2,
        )

        with pytest.raises(PolicyConflictError, match="already exists with different content"):
            await storage.persist_document_version(payload2)

    asyncio.run(run())


def test_in_memory_tenant_violation() -> None:
    async def run() -> None:
        valid_univ = str(uuid.uuid4())
        invalid_univ = str(uuid.uuid4())
        storage = InMemoryPolicyIngestionStorage(known_universities={valid_univ})

        payload = PolicyDocumentIngestionInput(
            university_id=invalid_univ,
            document_code="POL-TENANT-01",
            title="لائحة جامعة وهمية",
            authority_level="university_council",
            category="academic_bylaws",
            version_tag="1.0",
        )

        with pytest.raises(TenantViolationError, match="does not exist"):
            await storage.persist_document_version(payload)

    asyncio.run(run())
