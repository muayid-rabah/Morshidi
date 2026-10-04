from __future__ import annotations
import re,uuid
from dataclasses import replace
from datetime import timezone
from typing import Iterable
from .canonical import HASH_CONTRACT_VERSION,calculate_integrity_hash
from .models import CanonicalLedgerEntry,EvidenceReference,RedactedTraceMetadata
from .registries import ProvenanceClass,RedactionProfile,SubjectScopeType,materiality_for

DECISION_SCHEMA_VERSION='1.0'
_HEX_64=re.compile(r'^[0-9a-f]{64}$')

def _nonblank(value:str|None,name:str)->str:
    if value is None or not str(value).strip(): raise ValueError(f'{name} must be nonblank')
    return str(value).strip()

def validate_sha256_hash(value:str,field_name:str='hash')->str:
    if _HEX_64.fullmatch(value or '') is None: raise ValueError(f'{field_name} must be lowercase 64-char SHA-256 hex')
    return value

def _normalize_strings(values:Iterable[str],name:str)->tuple[str,...]:
    return tuple(sorted({_nonblank(v,name) for v in values}))

def _normalize_evidence(values:Iterable[EvidenceReference])->tuple[EvidenceReference,...]:
    out=[]; seen=set()
    for ref in values:
        clean=EvidenceReference(_nonblank(ref.source,'evidence.source'),_nonblank(ref.identifier,'evidence.identifier'),_nonblank(ref.version,'evidence.version'),ref.locator.strip() if isinstance(ref.locator,str) and ref.locator.strip() else None,ref.uri.strip() if isinstance(ref.uri,str) and ref.uri.strip() else None)
        key=(clean.source,clean.identifier,clean.version,clean.locator,clean.uri)
        if key not in seen: seen.add(key); out.append(clean)
    return tuple(sorted(out,key=lambda x:(x.source,x.identifier,x.version,x.locator or '',x.uri or '')))

def validate_entry(entry:CanonicalLedgerEntry)->CanonicalLedgerEntry:
    for value,name in [(entry.ledger_entry_id,'ledger_entry_id'),(entry.subject_scope_id,'subject_scope_id'),(entry.university_id,'university_id'),(entry.source_engine,'source_engine'),(entry.source_engine_version,'source_engine_version'),(entry.policy_version,'policy_version'),(entry.outcome_reference,'outcome_reference')]: _nonblank(value,name)
    if entry.hash_contract_version!=HASH_CONTRACT_VERSION: raise ValueError('Unsupported hash_contract_version')
    if entry.decision_schema_version!=DECISION_SCHEMA_VERSION: raise ValueError('Unsupported decision_schema_version')
    if entry.materiality_class is not materiality_for(entry.decision_type): raise ValueError('materiality_class does not match registry')
    if entry.created_at.tzinfo is None or entry.created_at.utcoffset() is None: raise ValueError('created_at must be timezone-aware UTC')
    if entry.created_at.utcoffset()!=timezone.utc.utcoffset(entry.created_at): raise ValueError('created_at must be normalized to UTC')
    if entry.subject_scope_type is SubjectScopeType.STUDENT_INDIVIDUAL: _nonblank(entry.student_user_id,'student_user_id')
    if entry.subject_scope_type is SubjectScopeType.INSTITUTIONAL_PERIOD and entry.student_user_id is not None: raise ValueError('student_user_id forbidden for institutional period')
    if entry.provenance_class is ProvenanceClass.AUTHORITATIVE_TRANSACTION and entry.scenario_id is not None: raise ValueError('scenario_id forbidden for authoritative transaction')
    if entry.supersedes_entry_id is not None and entry.supersedes_entry_id==entry.ledger_entry_id: raise ValueError('entry cannot supersede itself')
    if entry.integrity_hash: validate_sha256_hash(entry.integrity_hash,'integrity_hash')
    if entry.previous_entry_hash is not None: validate_sha256_hash(entry.previous_entry_hash,'previous_entry_hash')
    if not entry.source_versions: raise ValueError('source_versions must not be empty')
    return entry

def create_canonical_ledger_entry(**kwargs)->CanonicalLedgerEntry:
    kwargs=dict(kwargs)
    kwargs.setdefault('ledger_entry_id',str(uuid.uuid4())); kwargs.setdefault('integrity_hash',''); kwargs.setdefault('hash_contract_version',HASH_CONTRACT_VERSION); kwargs.setdefault('decision_schema_version',DECISION_SCHEMA_VERSION)
    kwargs['source_versions']=_normalize_strings(kwargs.get('source_versions',()),'source_versions')
    kwargs['limitations']=_normalize_strings(kwargs.get('limitations',()),'limitations')
    kwargs['evidence_references']=_normalize_evidence(kwargs.get('evidence_references',()))
    entry=CanonicalLedgerEntry(**kwargs); validate_entry(entry)
    final=replace(entry,integrity_hash=calculate_integrity_hash(entry)); validate_entry(final); return final

def create_superseding_entry(previous:CanonicalLedgerEntry,*,ledger_entry_id:str|None=None,decision_status=None,outcome_reference:str|None=None,limitations:Iterable[str]|None=None,**changes)->CanonicalLedgerEntry:
    new_id=ledger_entry_id or str(uuid.uuid4())
    if new_id==previous.ledger_entry_id: raise ValueError('superseding entry must have new identity')
    kwargs={name:getattr(previous,name) for name in previous.__dataclass_fields__ if name!='integrity_hash'}
    kwargs.update(changes); kwargs.update({'ledger_entry_id':new_id,'supersedes_entry_id':previous.ledger_entry_id,'previous_entry_hash':previous.integrity_hash,'integrity_hash':''})
    if decision_status is not None: kwargs['decision_status']=decision_status
    if outcome_reference is not None: kwargs['outcome_reference']=outcome_reference
    if limitations is not None: kwargs['limitations']=tuple(limitations)
    return create_canonical_ledger_entry(**kwargs)

def project_trace_metadata(entry:CanonicalLedgerEntry,redaction_profile:RedactionProfile)->RedactedTraceMetadata:
    student_id=entry.student_user_id; scope_id=entry.subject_scope_id; limitations=entry.limitations
    if redaction_profile in {RedactionProfile.AGGREGATE_ANALYST,RedactionProfile.PUBLIC_REDACTED}:
        student_id=None
        if entry.subject_scope_type is SubjectScopeType.STUDENT_INDIVIDUAL: scope_id='REDACTED'
    if redaction_profile is RedactionProfile.PUBLIC_REDACTED: limitations=tuple(sorted(set((*limitations,'PUBLIC_REDACTED'))))
    return RedactedTraceMetadata(entry.ledger_entry_id,entry.decision_type,entry.subject_scope_type,scope_id,entry.university_id,student_id,entry.source_engine,entry.source_engine_version,entry.policy_version,entry.decision_status,entry.created_at,entry.replay_status,limitations)
