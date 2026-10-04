"""One-call provider-neutral interpretation contract and untrusted-output checks."""

from __future__ import annotations

from typing import Protocol

from .catalog import METRICS_BY_ID, InstitutionalMetricDefinition
from .models import AbstentionReason, ProviderInterpretation


class InterpreterUnavailable(RuntimeError):
    pass


class InvalidInterpreterOutput(RuntimeError):
    pass


class InstitutionalQueryInterpreter(Protocol):
    async def interpret(
        self, question: str, definitions: tuple[InstitutionalMetricDefinition, ...],
        scope_summary: dict[str, str], language: str,
    ) -> ProviderInterpretation: ...


class UnconfiguredInstitutionalQueryInterpreter:
    async def interpret(
        self, question: str, definitions: tuple[InstitutionalMetricDefinition, ...],
        scope_summary: dict[str, str], language: str,
    ) -> ProviderInterpretation:
        raise InterpreterUnavailable("institutional query provider unavailable")


def validated_metric(interpretation: ProviderInterpretation) -> tuple[InstitutionalMetricDefinition | None, AbstentionReason | None]:
    if interpretation.status == "ABSTAINED":
        if interpretation.metric_id is not None or not interpretation.abstention_reason:
            return None, AbstentionReason.INVALID_PROVIDER_OUTPUT
        try:
            return None, AbstentionReason(interpretation.abstention_reason)
        except ValueError:
            return None, AbstentionReason.INVALID_PROVIDER_OUTPUT
    if interpretation.status != "INTERPRETED" or interpretation.abstention_reason is not None:
        return None, AbstentionReason.INVALID_PROVIDER_OUTPUT
    if not isinstance(interpretation.metric_id, str):
        return None, AbstentionReason.INVALID_PROVIDER_OUTPUT
    metric = METRICS_BY_ID.get(interpretation.metric_id)
    if metric is None:
        return None, AbstentionReason.NO_APPROVED_METRIC
    return metric, None
