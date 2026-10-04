"""Finite failure types for the P8 trusted ledger persistence boundary."""

from __future__ import annotations

from enum import Enum


class DecisionTraceErrorCode(str, Enum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    UNSUPPORTED_APPEND_AUTHORITY = "UNSUPPORTED_APPEND_AUTHORITY"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    NOT_FOUND = "NOT_FOUND"
    PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"
    PERSISTENCE_UNAVAILABLE = "PERSISTENCE_UNAVAILABLE"
    PERSISTENCE_INTEGRITY_FAILURE = "PERSISTENCE_INTEGRITY_FAILURE"
    STALE_CLAIM = "STALE_CLAIM"
    OUTBOX_FAILURE = "OUTBOX_FAILURE"


class DecisionTracePersistenceError(RuntimeError):
    def __init__(self, code: DecisionTraceErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
