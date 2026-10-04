"""WC-053 Observability, Structured Telemetry, SLOs, and Runbook Index.

Provides structured logging, correlation IDs, latency measurement, and health reporting.
CRITICAL INVARIANT: Zero sensitive student data or credentials may be logged.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Mapping

SLO_TARGETS = {
    "read_latency_p95_ms": 200.0,
    "availability_percentage": 99.9,
    "max_acceptable_drift": 0,
}

RUNBOOK_INDEX: dict[str, dict[str, str]] = {
    "DRIFT_DETECTED": {
        "title": "Sandbox Contract Drift Detected",
        "action": "Run `npm run export:data` in morshidi-uni and re-sync fixtures to Morshidi.",
        "severity": "HIGH",
    },
    "PERSONA_SECURITY_VIOLATION": {
        "title": "Attempted Cross-Tenant Persona Hint",
        "action": "Audit request IP and auth context. Persona hint must never apply outside morshidi-sandbox.",
        "severity": "CRITICAL",
    },
    "TRANSPORT_UNAVAILABLE": {
        "title": "Sandbox Transport Outage",
        "action": "Verify static fixture file presence or upstream contributor portal HTTP connectivity.",
        "severity": "MEDIUM",
    },
}


def mask_student_id(student_id: str | None) -> str:
    """Mask student ID to preserve privacy in audit logs."""
    if not student_id:
        return "UNKNOWN"
    s = str(student_id).strip()
    if len(s) <= 4:
        return "****"
    return f"{s[:2]}***{s[-2:]}"


@dataclass(frozen=True)
class SandboxTelemetryEvent:
    event_type: str
    correlation_id: str
    institution_id: str
    latency_ms: float
    status: str
    masked_student_id: str | None = None
    entity: str | None = None
    error_code: str | None = None


class SandboxObservability:
    """Aggregates safe audit events and operational health metrics."""

    def __init__(self) -> None:
        self._events: list[SandboxTelemetryEvent] = []

    def record_event(
        self,
        event_type: str,
        *,
        latency_ms: float,
        status: str = "SUCCESS",
        correlation_id: str | None = None,
        student_id: str | None = None,
        entity: str | None = None,
        error_code: str | None = None,
        institution_id: str = "morshidi-sandbox",
    ) -> SandboxTelemetryEvent:
        event = SandboxTelemetryEvent(
            event_type=event_type,
            correlation_id=correlation_id or str(uuid.uuid4()),
            institution_id=institution_id,
            latency_ms=round(latency_ms, 3),
            status=status,
            masked_student_id=mask_student_id(student_id) if student_id else None,
            entity=entity,
            error_code=error_code,
        )
        self._events.append(event)
        # Keep bounded history
        if len(self._events) > 1000:
            self._events = self._events[-500:]
        return event

    def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return [asdict(e) for e in self._events[-limit:]]

    def get_runbook(self, code: str) -> dict[str, str]:
        return RUNBOOK_INDEX.get(
            code,
            {
                "title": "General Sandbox Alert",
                "action": "Inspect logs and verify tenant configuration.",
                "severity": "LOW",
            },
        )


sandbox_obs = SandboxObservability()
