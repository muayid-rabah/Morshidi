from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from .registries import ActorClass,DecisionStatus,DecisionType,MaterialityClass,ProvenanceClass,RedactionProfile,ReplayMode,ReplayStatus,SubjectScopeType

@dataclass(frozen=True,slots=True)
class EvidenceReference:
    source:str; identifier:str; version:str; locator:str|None=None; uri:str|None=None

@dataclass(frozen=True,slots=True)
class CanonicalLedgerEntry:
    ledger_entry_id:str; decision_type:DecisionType; materiality_class:MaterialityClass; actor_class:ActorClass; actor_id:str|None
    subject_scope_type:SubjectScopeType; subject_scope_id:str; university_id:str; student_user_id:str|None
    source_engine:str; source_engine_version:str; policy_version:str; source_versions:tuple[str,...]
    input_state_reference:str|None; scenario_id:str|None; decision_status:DecisionStatus; outcome_reference:str
    evidence_references:tuple[EvidenceReference,...]; domain_trace_reference:str|None; provenance_class:ProvenanceClass
    created_at:datetime; redaction_profile:RedactionProfile; integrity_hash:str; previous_entry_hash:str|None
    supersedes_entry_id:str|None; replay_status:ReplayStatus; limitations:tuple[str,...]
    hash_contract_version:str='1.0'; decision_schema_version:str='1.0'

@dataclass(frozen=True,slots=True)
class RedactedTraceMetadata:
    ledger_entry_id:str; decision_type:DecisionType; subject_scope_type:SubjectScopeType; subject_scope_id:str; university_id:str
    student_user_id:str|None; source_engine:str; source_engine_version:str; policy_version:str; decision_status:DecisionStatus
    created_at:datetime; replay_status:ReplayStatus; limitations:tuple[str,...]

@dataclass(frozen=True,slots=True)
class ReplayRequest:
    mode:ReplayMode; available_source_versions:tuple[str,...]=(); available_engine_versions:tuple[str,...]=(); available_policy_versions:tuple[str,...]=(); current_outcome_reference:str|None=None; current_decision_status:DecisionStatus|None=None

@dataclass(frozen=True,slots=True)
class ReplayAvailability:
    available:bool; mode:ReplayMode; reason_code:str|None=None; missing_source_versions:tuple[str,...]=(); engine_version_available:bool=True; policy_version_available:bool=True

@dataclass(frozen=True,slots=True)
class ReplayResult:
    mode:ReplayMode; historical_ledger_entry_id:str; historical_outcome_reference:str; recomputed_outcome_reference:str|None
    historical_decision_status:DecisionStatus; recomputed_decision_status:DecisionStatus|None; changed:bool; availability:ReplayAvailability
