"""Enums governing institutional policy retrieval, source admission, and grounding."""

from __future__ import annotations

from enum import Enum


class SourceAdmissionStatus(str, Enum):
    """Formal admission status of an institutional policy document or passage."""

    VERIFIED = "VERIFIED"
    """Officially verified and approved institutional policy source."""

    UNVERIFIED = "UNVERIFIED"
    """Draft, unapproved, external, or unverified source; strictly held / rejected."""

    SUPERSEDED = "SUPERSEDED"
    """Historically valid policy version that has been superseded by a newer version."""

    CONFLICTING = "CONFLICTING"
    """Source currently flagged for conflicting regulatory interpretations."""

    UNAVAILABLE = "UNAVAILABLE"
    """Archived, revoked, or temporarily inaccessible source."""

    PENDING_REVIEW = "PENDING_REVIEW"
    """Source under formal administrative review; held from authoritative retrieval."""

    WITHDRAWN = "WITHDRAWN"
    """Source formally withdrawn by university authority; excluded from retrieval."""


class GroundingStatus(str, Enum):
    """Deterministic grounding evaluation status for a policy query."""

    GROUNDED = "GROUNDED"
    """All retrieved evidence is verified, consistent, and cited."""

    NO_EVIDENCE = "NO_EVIDENCE"
    """No matching evidence was found in the authoritative corpus; abstains."""

    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    """Verified sources contain mutually conflicting provisions; abstains from definitive answer."""

    UNVERIFIED_SOURCE = "UNVERIFIED_SOURCE"
    """Only unverified or untrusted sources matched; rejected and abstained."""

    UNAVAILABLE_SOURCE = "UNAVAILABLE_SOURCE"
    """Referenced source is archived or unavailable; abstains."""

    DETERMINISTIC_ENGINE_REQUIRED = "DETERMINISTIC_ENGINE_REQUIRED"
    """Question involves computable academic rules; routed to deterministic engine."""


class EngineHandoffTarget(str, Enum):
    """Approved deterministic engines for academic computation."""

    ELIGIBILITY_ENGINE = "ELIGIBILITY_ENGINE"
    """Phase 5 prerequisite and course eligibility evaluation."""

    PROGRESS_ENGINE = "PROGRESS_ENGINE"
    """Phase 6 monotonic degree progress and audit evaluation."""

    SEMESTER_PLANNER_ENGINE = "SEMESTER_PLANNER_ENGINE"
    """Phase 8 semester planning and workload optimization."""

    DEGREE_PATH_ENGINE = "DEGREE_PATH_ENGINE"
    """Phase 9 multi-semester degree path simulation."""

    MOCK_REGISTRATION_ENGINE = "MOCK_REGISTRATION_ENGINE"
    """Phase 6 mock registration intent and demand revalidation."""

    ADVISOR_AUTHORIZATION_ENGINE = "ADVISOR_AUTHORIZATION_ENGINE"
    """Phase 7 advisor assignment and tenancy authorization."""


class PolicyAuthorityLevel(str, Enum):
    """Institutional authority tier issuing the regulation."""

    MINISTRY_OF_HIGHER_EDUCATION = "MINISTRY_OF_HIGHER_EDUCATION"
    UNIVERSITY_COUNCIL = "UNIVERSITY_COUNCIL"
    DEAN_COUNCIL = "DEAN_COUNCIL"
    FACULTY_BOARD = "FACULTY_BOARD"
    DEPARTMENT_COUNCIL = "DEPARTMENT_COUNCIL"


class PolicyCategory(str, Enum):
    """Topical category of academic regulation."""

    ACADEMIC_BYLAWS = "ACADEMIC_BYLAWS"
    REGISTRATION_REGULATIONS = "REGISTRATION_REGULATIONS"
    EXAMINATION_REGULATIONS = "EXAMINATION_REGULATIONS"
    DISCIPLINARY_BYLAWS = "DISCIPLINARY_BYLAWS"
    GRADUATION_REQUIREMENTS = "GRADUATION_REQUIREMENTS"
    CREDIT_TRANSFER_RULES = "CREDIT_TRANSFER_RULES"


class LimitationCode(str, Enum):
    """Finite limitation reason codes explaining retrieval boundaries."""

    NO_MATCHING_PASSAGE = "NO_MATCHING_PASSAGE"
    ENGINE_COMPUTATION_REQUIRED = "ENGINE_COMPUTATION_REQUIRED"
    CONFLICTING_SOURCES_DETECTED = "CONFLICTING_SOURCES_DETECTED"
    UNVERIFIED_SOURCE_REJECTED = "UNVERIFIED_SOURCE_REJECTED"
    SUPERSEDED_SOURCE_EXCLUDED = "SUPERSEDED_SOURCE_EXCLUDED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    CROSS_UNIVERSITY_DENIED = "CROSS_UNIVERSITY_DENIED"
    UNSUPPORTED_OUT_OF_CORPUS = "UNSUPPORTED_OUT_OF_CORPUS"
    STUDENT_RECORD_DISCLOSURE_DENIED = "STUDENT_RECORD_DISCLOSURE_DENIED"
    PENDING_REVIEW_HELD = "PENDING_REVIEW_HELD"
    WITHDRAWN_SOURCE_EXCLUDED = "WITHDRAWN_SOURCE_EXCLUDED"


class PolicyErrorCode(str, Enum):
    """Typed domain error codes for institutional policy operations."""

    INVALID_SOURCE = "INVALID_SOURCE"
    MISMATCHED_CITATION = "MISMATCHED_CITATION"
    UNAUTHORIZED_TENANT = "UNAUTHORIZED_TENANT"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"
    CORRUPTED_CONTENT = "CORRUPTED_CONTENT"
    ENGINE_HANDOFF_VIOLATION = "ENGINE_HANDOFF_VIOLATION"
