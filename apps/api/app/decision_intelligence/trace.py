"""Trace helpers kept separate from decision computation."""

from __future__ import annotations

from app.decision_intelligence.models import RelativeOrderChange


def relative_order_changes(
    baseline_order: tuple[str, ...],
    final_order: tuple[str, ...],
) -> tuple[RelativeOrderChange, ...]:
    baseline_rank = {code: index + 1 for index, code in enumerate(baseline_order)}
    final_rank = {code: index + 1 for index, code in enumerate(final_order)}
    return tuple(
        RelativeOrderChange(code, baseline_rank[code], final_rank[code])
        for code in baseline_order
        if baseline_rank[code] != final_rank[code]
    )
