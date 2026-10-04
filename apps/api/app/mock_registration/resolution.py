"""Deterministic LATEST_VALID_INTENT_WINS resolution."""

from __future__ import annotations

from collections import defaultdict

from .models import (
    IntentLifecycle,
    IntentResolutionResult,
    ResolvedIntent,
    ResolutionDisposition,
    ValidatedIntent,
    ValidationStatus,
)
from .registries import ReasonCode


def current_intent_key(record: ValidatedIntent) -> tuple[object, ...]:
    intent = record.intent
    return (
        intent.owner_scope_id,
        intent.university_id,
        intent.major_id,
        intent.study_plan_id,
        intent.study_plan_version,
        intent.target_period,
    )


def resolve_current_intents(records: tuple[ValidatedIntent, ...]) -> IntentResolutionResult:
    grouped: dict[tuple[object, ...], list[ValidatedIntent]] = defaultdict(list)
    for record in records:
        grouped[current_intent_key(record)].append(record)
    resolved: list[ResolvedIntent] = []
    for key in sorted(grouped, key=lambda value: tuple(str(item) for item in value)):
        group = grouped[key]
        eligible = [
            item for item in group
            if item.status is not ValidationStatus.INVALID
            and item.intent.lifecycle_status is not IntentLifecycle.EXPIRED
        ]
        if not eligible:
            for item in group:
                disposition = (
                    ResolutionDisposition.EXPIRED
                    if item.intent.lifecycle_status is IntentLifecycle.EXPIRED
                    else ResolutionDisposition.INVALID
                )
                reason = (
                    ReasonCode.MOCK_REG_EXPIRED_INTENT,
                ) if disposition is ResolutionDisposition.EXPIRED else item.reason_codes
                resolved.append(ResolvedIntent(item, disposition, reason))
            continue
        max_revision = max(item.intent.revision for item in eligible)
        candidates = [item for item in eligible if item.intent.revision == max_revision]
        fingerprints = {item.content_fingerprint for item in candidates}
        conflict = len(fingerprints) > 1
        canonical_candidate = min(candidates, key=lambda item: (item.content_fingerprint, item.intent.intent_id))
        seen_current = False
        for item in sorted(group, key=_record_order):
            if item not in eligible:
                disposition = ResolutionDisposition.EXPIRED if item.intent.lifecycle_status is IntentLifecycle.EXPIRED else ResolutionDisposition.INVALID
                reasons = (ReasonCode.MOCK_REG_EXPIRED_INTENT,) if disposition is ResolutionDisposition.EXPIRED else item.reason_codes
            elif item.intent.revision < max_revision:
                disposition = ResolutionDisposition.SUPERSEDED
                reasons = (ReasonCode.MOCK_REG_REVISION_SUPERSEDED,)
            elif conflict:
                disposition = ResolutionDisposition.REVISION_CONFLICT
                reasons = (ReasonCode.MOCK_REG_REVISION_CONFLICT,)
            elif item.content_fingerprint == canonical_candidate.content_fingerprint and not seen_current:
                seen_current = True
                if item.intent.lifecycle_status is IntentLifecycle.WITHDRAWN:
                    disposition = ResolutionDisposition.WITHDRAWN
                    reasons = (ReasonCode.MOCK_REG_WITHDRAWN_INTENT,)
                else:
                    disposition = ResolutionDisposition.CURRENT
                    reasons = ()
            else:
                disposition = ResolutionDisposition.SUPERSEDED
                reasons = (ReasonCode.MOCK_REG_REVISION_SUPERSEDED,)
            resolved.append(ResolvedIntent(item, disposition, reasons))
    return IntentResolutionResult(tuple(sorted(resolved, key=_resolved_order)))


def _record_order(item):
    return (item.intent.revision, item.content_fingerprint, item.intent.intent_id)


def _resolved_order(item):
    return (*tuple(str(value) for value in current_intent_key(item.record)), *_record_order(item.record))
