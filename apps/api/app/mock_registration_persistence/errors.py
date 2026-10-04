"""Safe persistence-layer failures; raw database details never escape."""

from __future__ import annotations

from enum import Enum


class PersistenceFailureCode(str, Enum):
    PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"
    PERSISTENCE_UNAVAILABLE = "PERSISTENCE_UNAVAILABLE"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"


class MockRegistrationPersistenceError(RuntimeError):
    def __init__(self, code: PersistenceFailureCode, operation: str):
        super().__init__(f"Mock Registration persistence operation failed: {operation}")
        self.code = code
        self.operation = operation


class MockRegistrationPersistenceIntegrityError(MockRegistrationPersistenceError):
    def __init__(self, operation: str):
        super().__init__(PersistenceFailureCode.PERSISTENCE_CONFLICT, operation)
