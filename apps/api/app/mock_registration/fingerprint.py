"""Privacy-minimized SHA-256 fingerprints for registration intent content."""

from __future__ import annotations

import hashlib

from .canonicalization import canonicalize_course_codes
from .models import RegistrationIntent


def _field(value: object) -> bytes:
    encoded = str(value).encode("utf-8")
    return str(len(encoded)).encode("ascii") + b":" + encoded


def calculate_intent_fingerprint(intent: RegistrationIntent) -> str:
    """Fingerprint decision-relevant content, never identity/contact/history data."""

    period = intent.target_period
    values: tuple[object, ...] = (
        intent.contract_version,
        intent.university_id,
        intent.major_id,
        intent.study_plan_id,
        intent.study_plan_version,
        period.university_id,
        _enum_value(period.period_class),
        period.period_key,
        period.source_version,
        period.verified_provider_source,
        _enum_value(intent.lifecycle_status),
        intent.revision,
        _enum_value(intent.source_class),
        intent.source_version,
        *canonicalize_course_codes(intent.course_codes),
    )
    payload = b"".join(_field(value) for value in values)
    return hashlib.sha256(payload).hexdigest()


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)
