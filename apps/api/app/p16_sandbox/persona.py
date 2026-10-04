"""Persona security and resolution boundaries for Morshidi Sandbox University.

CRITICAL SECURITY INVARIANT:
A sandbox_student / persona hint is purely a demo navigation hint, NEVER authentication.
It must never authenticate a real user, override session credentials, bypass ownership,
or switch to a non-sandbox tenant.
"""

from __future__ import annotations

from typing import Any, Mapping

from .tenant import SANDBOX_INSTITUTION_ID, is_sandbox_institution

ALLOWED_PERSONA_IDS: frozenset[str] = frozenset({
    "202310001",
    "202410002",
    "202410003",
    "202510004",
    "202610005",
})

SYNTHETIC_WATERMARK = "SYNTHETIC_SANDBOX_PERSONA — NOT PRODUCTION IDENTITY"


class SandboxPersonaSecurityError(PermissionError):
    """Raised when persona hint is attempted on a non-sandbox institution."""


class SandboxPersonaNotFoundError(LookupError):
    """Raised when an unknown or unauthorized persona hint is requested."""


def resolve_sandbox_persona(
    persona_hint: str | None,
    institution_id: str | None,
) -> str:
    """Validate and resolve persona hint within strict sandbox tenant isolation."""
    if not persona_hint or not str(persona_hint).strip():
        raise ValueError("Persona hint cannot be empty")

    persona_clean = str(persona_hint).strip()

    # Invariant: Persona hint selection is only authorized on the sandbox tenant
    if not is_sandbox_institution(institution_id):
        raise SandboxPersonaSecurityError(
            f"Persona hint selection is strictly forbidden outside the sandbox tenant. "
            f"Attempted for tenant: {institution_id!r}"
        )

    # Invariant: Only explicitly allowlisted synthetic personas can be selected
    if persona_clean not in ALLOWED_PERSONA_IDS:
        raise SandboxPersonaNotFoundError(
            f"Persona {persona_clean!r} is not an authorized sandbox persona"
        )

    return persona_clean


def sanitize_persona_view(raw_profile: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize student profile and inject synthetic watermarks. Zero credential exposure."""
    safe_profile = {
        k: v
        for k, v in raw_profile.items()
        if k not in {
            "password",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "credential",
            "session_id",
        }
    }

    safe_profile["synthetic"] = True
    safe_profile["watermark"] = SYNTHETIC_WATERMARK
    safe_profile["institution_id"] = SANDBOX_INSTITUTION_ID

    return safe_profile
