from __future__ import annotations
from .models import CanonicalLedgerEntry,ReplayAvailability,ReplayRequest,ReplayResult
from .registries import ReplayMode,ReplayStatus

def check_exact_replay_availability(entry:CanonicalLedgerEntry,request:ReplayRequest)->ReplayAvailability:
    if request.mode is ReplayMode.NOT_REPLAYABLE or entry.replay_status is ReplayStatus.NOT_REPLAYABLE:
        return ReplayAvailability(False,ReplayMode.NOT_REPLAYABLE,'TRACE_NOT_REPLAYABLE')
    if request.mode is not ReplayMode.EXACT_REPLAY: return ReplayAvailability(True,request.mode)
    available=set(request.available_source_versions); missing=tuple(sorted(v for v in entry.source_versions if v not in available))
    engine_ok=entry.source_engine_version in set(request.available_engine_versions); policy_ok=entry.policy_version in set(request.available_policy_versions)
    if missing: return ReplayAvailability(False,ReplayMode.EXACT_REPLAY,'SOURCE_VERSION_UNAVAILABLE',missing,engine_ok,policy_ok)
    if not engine_ok: return ReplayAvailability(False,ReplayMode.EXACT_REPLAY,'ENGINE_VERSION_UNAVAILABLE',(),False,policy_ok)
    if not policy_ok: return ReplayAvailability(False,ReplayMode.EXACT_REPLAY,'POLICY_VERSION_UNAVAILABLE',(),engine_ok,False)
    return ReplayAvailability(True,ReplayMode.EXACT_REPLAY)

def evaluate_replay_comparison(entry:CanonicalLedgerEntry,request:ReplayRequest)->ReplayResult:
    availability=check_exact_replay_availability(entry,request)
    if request.mode is ReplayMode.EXACT_REPLAY:
        recomputed_outcome=entry.outcome_reference if availability.available else None; recomputed_status=entry.decision_status if availability.available else None
    elif request.mode is ReplayMode.CURRENT_RECOMPUTATION:
        recomputed_outcome=request.current_outcome_reference; recomputed_status=request.current_decision_status
    else: recomputed_outcome=None; recomputed_status=None
    changed=recomputed_outcome is not None and (recomputed_outcome!=entry.outcome_reference or recomputed_status!=entry.decision_status)
    return ReplayResult(request.mode,entry.ledger_entry_id,entry.outcome_reference,recomputed_outcome,entry.decision_status,recomputed_status,changed,availability)
