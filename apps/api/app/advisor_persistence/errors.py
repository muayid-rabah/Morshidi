"""Persistence error classes for Advisor Authorization and Assignment subsystem."""

from __future__ import annotations


class AdvisorPersistenceError(Exception):
    """Base error for advisor assignment persistence failures."""

    def __init__(self, message: str, operation: str = "", status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.operation = operation
        self.status_code = status_code


class AdvisorPersistenceIntegrityError(AdvisorPersistenceError):
    """Raised when persisted assignment records violate data integrity invariants."""
