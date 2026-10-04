"""P16 Sandbox Integration Package.

Provides contract-driven synthetic university integration for local/CI evaluation
and interactive connected demos without modifying production infrastructure or data.
"""

from .drift import DriftStatus, validate_sandbox_contract
from .evidence_manifest import get_wc050_manifest
from .observability import SandboxObservability, sandbox_obs
from .offering_provider import SandboxOfferingProvider
from .persona import (
    ALLOWED_PERSONA_IDS,
    SandboxPersonaSecurityError,
    resolve_sandbox_persona,
    sanitize_persona_view,
)
from .sis_adapter import SandboxSISAdapter
from .tenant import SANDBOX_INSTITUTION_ID, get_sandbox_institution_config
from .transport import (
    HTTPReadOnlyTransport,
    SandboxUniversityTransport,
    StaticFixtureTransport,
)

__all__ = [
    "DriftStatus",
    "validate_sandbox_contract",
    "get_wc050_manifest",
    "SandboxObservability",
    "sandbox_obs",
    "SandboxOfferingProvider",
    "ALLOWED_PERSONA_IDS",
    "SandboxPersonaSecurityError",
    "resolve_sandbox_persona",
    "sanitize_persona_view",
    "SandboxSISAdapter",
    "SANDBOX_INSTITUTION_ID",
    "get_sandbox_institution_config",
    "SandboxUniversityTransport",
    "StaticFixtureTransport",
    "HTTPReadOnlyTransport",
]
