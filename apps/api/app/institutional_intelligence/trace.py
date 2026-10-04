"""Deterministic decision trace generator for Institutional Intelligence."""

from __future__ import annotations

from typing import Any

from .models import InstitutionalDecisionTrace
from .registries import InstitutionalSignalId, SignalStatus


def build_decision_trace(
    base_trace_id: str | None,
    signal_id: InstitutionalSignalId,
    rule_id: str,
    inputs: dict[str, Any],
    status: SignalStatus,
    value: Any,
    limitations: tuple[str, ...] = (),
) -> InstitutionalDecisionTrace:
    """Builds an auditable, deterministic decision trace for a single signal."""
    # Stably derived trace ID without random uuid4() calls
    derived_trace_id = (
        f"{base_trace_id}:{signal_id.value}" if base_trace_id is not None else None
    )
    return InstitutionalDecisionTrace(
        trace_id=derived_trace_id,
        signal_id=signal_id,
        inputs=inputs,
        rule_id=rule_id,
        result_status=status,
        result_value=str(value) if value is not None else None,
        limitations=limitations,
    )
