"""Phase P8 University Regulation RAG & Policy Retrieval (WC-038).

AI EXPLAINS — DETERMINISTIC RULES DECIDE.
Pure domain foundation for governed institutional policy retrieval, source admission,
exact citation generation, conflict preservation, and deterministic academic engine handoff.
"""

from __future__ import annotations

from .classifier import classify_academic_query
from .enums import (
    EngineHandoffTarget,
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
    DeterministicEngineHandoff,
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
from .provider import (
    InMemoryInstitutionalPolicyProvider,
    InstitutionalPolicyProvider,
)
from .supabase_provider import SupabaseInstitutionalPolicyProvider
from .ingestion import (
    InMemoryPolicyIngestionStorage,
    PolicyConflictError,
    PolicyDocumentIngestionInput,
    PolicyIngestionError,
    PolicyIngestionResult,
    PolicyIngestionStorage,
    PolicyPassageIngestionInput,
    SupabasePolicyIngestionStorage,
    TenantViolationError,
)
from .service import (
    InMemoryPolicyReadStorage,
    PolicyReadStorage,
    StudentPolicyService,
    SupabasePolicyReadStorage,
)

__all__ = [
    "SourceAdmissionStatus",
    "GroundingStatus",
    "EngineHandoffTarget",
    "PolicyAuthorityLevel",
    "PolicyCategory",
    "LimitationCode",
    "PolicyErrorCode",
    "PolicyRetrievalError",
    "CitationAnchor",
    "PolicyDocument",
    "PolicyDocumentVersion",
    "PolicyPassage",
    "PolicySourceReference",
    "DeterministicEngineHandoff",
    "PolicyRetrievalLimitation",
    "PolicyConflict",
    "PolicyRetrievalQuery",
    "PolicyAnswerGrounding",
    "PolicyRetrievalResult",
    "classify_academic_query",
    "InstitutionalPolicyProvider",
    "InMemoryInstitutionalPolicyProvider",
    "SupabaseInstitutionalPolicyProvider",
    "PolicyPassageIngestionInput",
    "PolicyDocumentIngestionInput",
    "PolicyIngestionResult",
    "PolicyIngestionStorage",
    "InMemoryPolicyIngestionStorage",
    "SupabasePolicyIngestionStorage",
    "PolicyIngestionError",
    "PolicyConflictError",
    "TenantViolationError",
    "PolicyReadStorage",
    "InMemoryPolicyReadStorage",
    "SupabasePolicyReadStorage",
    "StudentPolicyService",
]
