"""Validated institution configuration and exact-scope provider composition.

This is an internal boundary, not a tenant picker or production config loader.
Academic decisions remain with existing deterministic engines and scoped data.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class CapabilityState(str, Enum):
    ENABLED = "ENABLED"
    MODELED_ONLY = "MODELED_ONLY"
    UNAVAILABLE = "UNAVAILABLE"
    EXTERNAL_DEPENDENCY = "EXTERNAL_DEPENDENCY"


class ProviderUnavailable(LookupError):
    """No authorized, configured provider exists for this exact institution."""


PROVIDER_KINDS = frozenset({"catalog", "policy", "offerings", "historical",
                            "skills", "career", "internship", "transition",
                            "sis", "identity"})
CAPABILITY_PROVIDER = {
    "academic_roadmap": "catalog",
    "policy_rag": "policy",
    "offerings": "offerings",
    "career_intelligence": "career",
    "plan_transition": "transition",
}
SUPPORTED_LOCALES = frozenset({"ar", "en"})
THEME_KEYS = frozenset({"default", "sand", "indigo"})
TIMEZONE_KEYS = frozenset({"Asia/Amman", "Europe/London", "UTC"})


@dataclass(frozen=True)
class InstitutionContext:
    institution_id: str
    institution_key: str
    display_name: str
    status: str
    country_code: str
    default_locale: str
    supported_locales: tuple[str, ...]
    timezone: str
    academic_config_key: str
    branding_config_key: str
    config_version: str

    def __post_init__(self) -> None:
        if not self.institution_id.strip() or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.institution_key):
            raise ValueError("Invalid institution identity")
        if not self.display_name.strip() or self.status not in {"ACTIVE", "INACTIVE"}:
            raise ValueError("Invalid institution display/status")
        if not re.fullmatch(r"[A-Z]{2}", self.country_code):
            raise ValueError("Invalid country code")
        if not self.supported_locales or len(set(self.supported_locales)) != len(self.supported_locales) or \
           set(self.supported_locales) - SUPPORTED_LOCALES or self.default_locale not in self.supported_locales:
            raise ValueError("Unsupported locale configuration")
        # Explicitly supported IANA keys avoid host-dependent Windows tzdata.
        # Expand only alongside a verified timezone-data dependency.
        if self.timezone not in TIMEZONE_KEYS:
            raise ValueError("Invalid institution timezone")
        if not all((self.academic_config_key.strip(), self.branding_config_key.strip(), self.config_version.strip())):
            raise ValueError("Missing institution configuration reference")


@dataclass(frozen=True)
class ProviderBinding:
    provider_key: str
    institution_id: str

    def __post_init__(self) -> None:
        if not self.provider_key.strip() or not self.institution_id.strip():
            raise ValueError("Incomplete provider binding")


@dataclass(frozen=True)
class InstitutionConfig:
    context: InstitutionContext
    capabilities: Mapping[str, CapabilityState]
    provider_bindings: Mapping[str, ProviderBinding]
    theme_key: str
    provenance: str
    source_version: str
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        capabilities = dict(self.capabilities)
        bindings = dict(self.provider_bindings)
        if self.theme_key not in THEME_KEYS or not self.provenance.strip() or not self.source_version.strip():
            raise ValueError("Invalid branding or config provenance")
        if set(capabilities) - CAPABILITY_PROVIDER.keys() or \
           any(not isinstance(state, CapabilityState) for state in capabilities.values()):
            raise ValueError("Unknown capability/state")
        if set(bindings) - PROVIDER_KINDS or any(
            binding.institution_id != self.context.institution_id or not binding.provider_key.strip()
            for binding in bindings.values()
        ):
            raise ValueError("Unknown or cross-tenant provider binding")
        for capability, state in capabilities.items():
            if state in {CapabilityState.ENABLED, CapabilityState.MODELED_ONLY} and \
               CAPABILITY_PROVIDER[capability] not in bindings:
                raise ValueError("Capability requires an explicit provider")
        object.__setattr__(self, "capabilities", MappingProxyType(capabilities))
        object.__setattr__(self, "provider_bindings", MappingProxyType(bindings))
        payload = {
            "context": vars(self.context),
            "capabilities": {key: value.value for key, value in sorted(capabilities.items())},
            "bindings": {key: vars(value) for key, value in sorted(bindings.items())},
            "theme_key": self.theme_key,
            "provenance": self.provenance,
            "source_version": self.source_version,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        object.__setattr__(self, "fingerprint", hashlib.sha256(canonical.encode()).hexdigest())

    def public_view(self) -> dict:
        """Only presentation data. No provider keys, secrets, or authorization claims."""
        return {"institution_id": self.context.institution_id,
                "display_name": self.context.display_name,
                "default_locale": self.context.default_locale,
                "supported_locales": self.context.supported_locales,
                "theme_key": self.theme_key,
                "capabilities": {key: state.value for key, state in self.capabilities.items()},
                "config_version": self.context.config_version,
                "config_fingerprint": self.fingerprint}


@dataclass(frozen=True)
class InstitutionProviderBundle:
    config: InstitutionConfig
    providers: Mapping[str, object]

    def require(self, kind: str) -> object:
        capabilities = [capability for capability, provider in CAPABILITY_PROVIDER.items() if provider == kind]
        if capabilities and all(self.config.capabilities.get(capability) in
                                {None, CapabilityState.UNAVAILABLE, CapabilityState.EXTERNAL_DEPENDENCY}
                                for capability in capabilities):
            raise ProviderUnavailable("PROVIDER_UNAVAILABLE")
        if kind not in self.config.provider_bindings or kind not in self.providers:
            raise ProviderUnavailable("PROVIDER_UNAVAILABLE")
        return self.providers[kind]

    def cache_key(self, *parts: str) -> tuple[str, ...]:
        return (self.config.context.institution_id, self.config.fingerprint, *parts)


class InstitutionProviderRegistry:
    """Exact-ID registry; bindings resolve only against same-tenant server-side adapters."""

    def __init__(self, configs: tuple[InstitutionConfig, ...],
                 adapters: Mapping[tuple[str, str], object]):
        ids = [config.context.institution_id for config in configs]
        slugs = [config.context.institution_key for config in configs]
        if len(ids) != len(set(ids)) or len(slugs) != len(set(slugs)):
            raise ValueError("Duplicate institution identity or slug")
        registered = dict(adapters)
        if any(key[0] not in ids for key in registered):
            raise ValueError("Adapter registered for unknown institution")
        bundles = {}
        for config in configs:
            providers = {}
            for kind, binding in config.provider_bindings.items():
                adapter = registered.get((config.context.institution_id, binding.provider_key))
                if adapter is None:
                    raise ValueError("Unknown provider binding")
                if getattr(adapter, "institution_id", None) != config.context.institution_id:
                    raise ValueError("Provider adapter scope mismatch")
                providers[kind] = adapter
            bundles[config.context.institution_id] = InstitutionProviderBundle(config, MappingProxyType(providers))
        self._bundles = MappingProxyType(bundles)

    def resolve(self, institution_id: str) -> InstitutionProviderBundle:
        try:
            bundle = self._bundles[institution_id]
        except KeyError:
            raise ProviderUnavailable("PROVIDER_UNAVAILABLE") from None
        if bundle.config.context.status != "ACTIVE":
            raise ProviderUnavailable("PROVIDER_UNAVAILABLE")
        return bundle
