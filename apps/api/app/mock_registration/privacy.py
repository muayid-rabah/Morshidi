"""Whole-result disclosure policy helpers."""

from __future__ import annotations

from .models import PrivacyConfiguration


def validate_privacy_configuration(configuration: PrivacyConfiguration) -> None:
    value = configuration.minimum_disclosure_group_size
    if not isinstance(value, int) or isinstance(value, bool) or value < 2:
        raise ValueError("minimum_disclosure_group_size must be an integer of at least 2")
    if not configuration.policy_version.strip():
        raise ValueError("privacy policy version is required")


def should_suppress(contributing_owner_count: int, configuration: PrivacyConfiguration) -> bool:
    validate_privacy_configuration(configuration)
    return 0 < contributing_owner_count < configuration.minimum_disclosure_group_size
