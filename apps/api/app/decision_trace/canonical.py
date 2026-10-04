from __future__ import annotations
import hashlib,hmac,json,re
from dataclasses import fields
from datetime import datetime,timezone
from enum import Enum
from typing import Any
from .models import CanonicalLedgerEntry,EvidenceReference
from .registries import IntegrityStatus

HASH_CONTRACT_VERSION='1.0'
_HEX_64=re.compile(r'^[0-9a-f]{64}$')

def _iso_utc(value:datetime)->str:
    if value.tzinfo is None or value.utcoffset() is None: raise ValueError('created_at must be timezone-aware')
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')

def _scalar(value:Any)->Any:
    if isinstance(value,Enum): return value.value
    if isinstance(value,datetime): return _iso_utc(value)
    return value

def _evidence_payload(ref:EvidenceReference)->dict[str,Any]:
    return {'source':ref.source,'identifier':ref.identifier,'version':ref.version,'locator':ref.locator,'uri':ref.uri}

def canonical_ledger_payload(entry:CanonicalLedgerEntry)->dict[str,Any]:
    payload={}
    for field in fields(entry):
        if field.name=='integrity_hash': continue
        value=getattr(entry,field.name)
        if field.name=='evidence_references':
            payload[field.name]=[_evidence_payload(x) for x in sorted(value,key=lambda x:(x.source,x.identifier,x.version,x.locator or '',x.uri or ''))]
        elif field.name in {'source_versions','limitations'}:
            payload[field.name]=list(sorted(value))
        elif isinstance(value,tuple): payload[field.name]=[_scalar(x) for x in value]
        else: payload[field.name]=_scalar(value)
    return payload

def canonical_json_serialize(payload:dict[str,Any])->str:
    return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)

def calculate_integrity_hash(entry:CanonicalLedgerEntry)->str:
    if entry.hash_contract_version!=HASH_CONTRACT_VERSION: raise ValueError('Unsupported hash contract version')
    data=canonical_json_serialize(canonical_ledger_payload(entry)).encode('utf-8')
    return hashlib.sha256(data).hexdigest()

def verify_integrity_hash(entry:CanonicalLedgerEntry)->IntegrityStatus:
    stored=entry.integrity_hash
    if not stored: return IntegrityStatus.MISSING_HASH
    if _HEX_64.fullmatch(stored) is None: return IntegrityStatus.MALFORMED_HASH
    return IntegrityStatus.VERIFIED if hmac.compare_digest(stored,calculate_integrity_hash(entry)) else IntegrityStatus.TAMPER_DETECTED
