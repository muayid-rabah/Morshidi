"""Typed domain errors for institutional policy retrieval."""

from __future__ import annotations

from .enums import PolicyErrorCode


class PolicyRetrievalError(Exception):
    """Base domain exception for institutional policy operations."""

    def __init__(self, code: PolicyErrorCode, detail: str) -> None:
        super().__init__(f"[{code.value}] {detail}")
        self.code = code
        self.detail = detail
