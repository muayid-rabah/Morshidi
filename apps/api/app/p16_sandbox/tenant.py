"""Tenant registration for Morshidi Sandbox University.

Reuses the P13 InstitutionContext and InstitutionConfig architecture to establish
a strictly isolated, bounded synthetic tenant.
"""

from __future__ import annotations

from app.institution_context.registry import (
    CapabilityState,
    InstitutionConfig,
    InstitutionContext,
    ProviderBinding,
)

SANDBOX_INSTITUTION_ID = "morshidi-sandbox"
SANDBOX_INSTITUTION_KEY = "morshidi-sandbox"
SANDBOX_DISPLAY_NAME = "جامعة مرشدي — البيئة التجريبية"
SANDBOX_DISPLAY_NAME_EN = "Morshidi University (Sandbox)"
SANDBOX_COUNTRY_CODE = "JO"
SANDBOX_DEFAULT_LOCALE = "ar"
SANDBOX_SUPPORTED_LOCALES = ("ar", "en")
SANDBOX_TIMEZONE = "Asia/Amman"
SANDBOX_THEME_KEY = "sand"
SANDBOX_PROVENANCE = "MORSHIDI_SANDBOX_UNIVERSITY"
SANDBOX_SOURCE_VERSION = "2026.10.02.v1"
SANDBOX_PLAN_ID = "12"


def is_sandbox_institution(institution_id: str | None) -> bool:
    """Return True only if the provided institution matches the isolated sandbox tenant."""
    return institution_id == SANDBOX_INSTITUTION_ID


def assert_sandbox_institution(institution_id: str | None) -> None:
    """Strictly prevent sandbox fallback or persona application to real institutions."""
    if not is_sandbox_institution(institution_id):
        raise PermissionError(
            f"Operation is restricted to the sandbox tenant ({SANDBOX_INSTITUTION_ID}). "
            f"Attempted access for: {institution_id!r}"
        )


def get_sandbox_institution_config() -> InstitutionConfig:
    """Construct the canonical InstitutionConfig for the Morshidi Sandbox tenant."""
    context = InstitutionContext(
        institution_id=SANDBOX_INSTITUTION_ID,
        institution_key=SANDBOX_INSTITUTION_KEY,
        display_name=SANDBOX_DISPLAY_NAME,
        status="ACTIVE",
        country_code=SANDBOX_COUNTRY_CODE,
        default_locale=SANDBOX_DEFAULT_LOCALE,
        supported_locales=SANDBOX_SUPPORTED_LOCALES,
        timezone=SANDBOX_TIMEZONE,
        academic_config_key="academic-v1",
        branding_config_key="branding-v1",
        config_version="v1",
    )

    capabilities = {
        "offerings": CapabilityState.ENABLED,
        "academic_roadmap": CapabilityState.MODELED_ONLY,
        "policy_rag": CapabilityState.MODELED_ONLY,
        "career_intelligence": CapabilityState.MODELED_ONLY,
        "plan_transition": CapabilityState.MODELED_ONLY,
    }

    bindings = {
        "offerings": ProviderBinding("sandbox-offerings", SANDBOX_INSTITUTION_ID),
        "catalog": ProviderBinding("sandbox-catalog", SANDBOX_INSTITUTION_ID),
        "policy": ProviderBinding("sandbox-policy", SANDBOX_INSTITUTION_ID),
        "career": ProviderBinding("sandbox-career", SANDBOX_INSTITUTION_ID),
        "transition": ProviderBinding("sandbox-transition", SANDBOX_INSTITUTION_ID),
        "sis": ProviderBinding("sandbox-sis", SANDBOX_INSTITUTION_ID),
    }

    return InstitutionConfig(
        context=context,
        capabilities=capabilities,
        provider_bindings=bindings,
        theme_key=SANDBOX_THEME_KEY,
        provenance=SANDBOX_PROVENANCE,
        source_version=SANDBOX_SOURCE_VERSION,
    )
