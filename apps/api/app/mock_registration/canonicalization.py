"""Canonical forms used by P6 validation, fingerprinting, and ordering."""

from __future__ import annotations

from collections import Counter


def normalize_course_code(value: str) -> str:
    """Apply only the catalog contract's whitespace normalization."""

    return value.strip()


def canonicalize_course_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(normalize_course_code(value) for value in values))


def duplicate_course_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    counts = Counter(normalize_course_code(value) for value in values)
    return tuple(sorted(code for code, count in counts.items() if count > 1))
