from dataclasses import FrozenInstanceError,fields,replace
from datetime import datetime,timedelta,timezone
import pytest
from app.decision_trace import *
NOW=datetime(2026,9,24,12,0,tzinfo=timezone.utc)

def _entry(**o):
    d=dict(ledger_entry_id='00000000-0000-0000-0000-000000000001',decision_type=DecisionType.MOCK_REGISTRATION_SUBMIT,materiality_class=MaterialityClass.LEDGER_REQUIRED,actor_class=ActorClass.STUDENT,actor_id='actor-1',subject_scope_type=SubjectScopeType.STUDENT_INDIVIDUAL,subject_scope_id='student-scope-1',university_id='11111111-1111-1111-1111-111111111111',student_user_id='22222222-2222-2222-2222-222222222222',source_engine='mock_registration',source_engine_version='6.5',policy_version='P8.1',source_versions=('catalog-v1','rules-v1'),input_state_reference='state-ref',scenario_id=None,decision_status=DecisionStatus.VALIDATED,outcome_reference='outcome-a',evidence_references=(EvidenceReference('catalog','C1','v1','row:1'),EvidenceReference('rules','R1','v1','rule:1')),domain_trace_reference='trace:1',provenance_class=ProvenanceClass.VERIFIED_REVALIDATION,created_at=NOW,redaction_profile=RedactionProfile.STUDENT_SAFE,integrity_hash='',previous_entry_hash=None,supersedes_entry_id=None,replay_status=ReplayStatus.REPLAYABLE_EXACT,limitations=('NONE',),hash_contract_version='1.0',decision_schema_version='1.0')
    d.update(o); return create_canonical_ledger_entry(**d)

def test_p8_trace_001_valid_entry(): assert verify_integrity_hash(_entry()) is IntegrityStatus.VERIFIED
def test_p8_trace_002_frozen():
    e=_entry()
    with pytest.raises(FrozenInstanceError): e.outcome_reference='x'
def test_p8_trace_003_required(): assert materiality_for(DecisionType.MOCK_REGISTRATION_SUBMIT) is MaterialityClass.LEDGER_REQUIRED
def test_p8_trace_004_optional(): assert materiality_for(DecisionType.FORMAL_POLICY_CONSULTATION) is MaterialityClass.LEDGER_OPTIONAL
def test_p8_trace_005_domain_only(): assert materiality_for(DecisionType.RUN_WHAT_IF) is MaterialityClass.DOMAIN_TRACE_ONLY
def test_p8_trace_006_not_ledgered(): assert materiality_for(DecisionType.POLICY_AD_HOC_CHAT) is MaterialityClass.NOT_LEDGERED
def test_p8_trace_007_bad_enum():
    with pytest.raises(ValueError): DecisionType('NOPE')
def test_p8_trace_008_bad_materiality():
    with pytest.raises(ValueError): _entry(materiality_class=MaterialityClass.NOT_LEDGERED)
def test_p8_trace_009_json_deterministic():
    e=_entry(); assert canonical_json_serialize(canonical_ledger_payload(e))==canonical_json_serialize(canonical_ledger_payload(e))
def test_p8_trace_010_hash_reproducible():
    e=_entry(); assert calculate_integrity_hash(e)==calculate_integrity_hash(e)
def test_p8_trace_011_change_changes_hash(): assert _entry().integrity_hash!=_entry(outcome_reference='b').integrity_hash
def test_p8_trace_012_tamper(): assert verify_integrity_hash(replace(_entry(),outcome_reference='bad')) is IntegrityStatus.TAMPER_DETECTED
def test_p8_trace_013_missing_hash(): assert verify_integrity_hash(replace(_entry(),integrity_hash='')) is IntegrityStatus.MISSING_HASH
def test_p8_trace_014_malformed_hash(): assert verify_integrity_hash(replace(_entry(),integrity_hash='abc')) is IntegrityStatus.MALFORMED_HASH
def test_p8_trace_015_previous_hash():
    a=_entry(); b=create_superseding_entry(a,ledger_entry_id='00000000-0000-0000-0000-000000000002'); assert b.previous_entry_hash==a.integrity_hash
def test_p8_trace_016_bad_previous_hash():
    with pytest.raises(ValueError): _entry(previous_entry_hash='abc')
def test_p8_trace_017_self_supersede():
    with pytest.raises(ValueError): _entry(supersedes_entry_id='00000000-0000-0000-0000-000000000001')
def test_p8_trace_018_new_identity():
    a=_entry(); b=create_superseding_entry(a,ledger_entry_id='00000000-0000-0000-0000-000000000003'); assert b.ledger_entry_id!=a.ledger_entry_id and b.supersedes_entry_id==a.ledger_entry_id
def test_p8_trace_019_previous_unchanged():
    a=_entry(); before=canonical_ledger_payload(a); create_superseding_entry(a,ledger_entry_id='00000000-0000-0000-0000-000000000004',outcome_reference='new'); assert canonical_ledger_payload(a)==before
def test_p8_trace_020_student_requires_id():
    with pytest.raises(ValueError): _entry(student_user_id=None)
def test_p8_trace_021_period_forbids_student():
    with pytest.raises(ValueError): _entry(subject_scope_type=SubjectScopeType.INSTITUTIONAL_PERIOD,subject_scope_id='2026-FALL',student_user_id='x')
def test_p8_trace_022_authoritative_forbids_scenario():
    with pytest.raises(ValueError): _entry(provenance_class=ProvenanceClass.AUTHORITATIVE_TRANSACTION,scenario_id='s')
def test_p8_trace_023_naive_time():
    with pytest.raises(ValueError): _entry(created_at=datetime(2026,9,24,12,0))
def test_p8_trace_024_non_utc_time():
    with pytest.raises(ValueError): _entry(created_at=datetime(2026,9,24,15,0,tzinfo=timezone(timedelta(hours=3))))
def test_p8_trace_025_source_order(): assert _entry(source_versions=('rules-v1','catalog-v1','rules-v1')).source_versions==('catalog-v1','rules-v1')
def test_p8_trace_026_evidence_order(): assert [x.source for x in _entry(evidence_references=(EvidenceReference('z','2','v1'),EvidenceReference('a','1','v1'))).evidence_references]==['a','z']
def test_p8_trace_027_limitations_order(): assert _entry(limitations=('Z','A','A')).limitations==('A','Z')
def test_p8_trace_028_reordered_hash_same(): assert _entry(source_versions=('rules-v1','catalog-v1')).integrity_hash==_entry(source_versions=('catalog-v1','rules-v1')).integrity_hash
def test_p8_trace_029_exact_available():
    r=ReplayRequest(ReplayMode.EXACT_REPLAY,('catalog-v1','rules-v1'),('6.5',),('P8.1',)); assert check_exact_replay_availability(_entry(),r).available
def test_p8_trace_030_missing_source():
    r=ReplayRequest(ReplayMode.EXACT_REPLAY,('catalog-v1',),('6.5',),('P8.1',)); assert check_exact_replay_availability(_entry(),r).reason_code=='SOURCE_VERSION_UNAVAILABLE'
def test_p8_trace_031_missing_engine():
    r=ReplayRequest(ReplayMode.EXACT_REPLAY,('catalog-v1','rules-v1'),('x',),('P8.1',)); assert check_exact_replay_availability(_entry(),r).reason_code=='ENGINE_VERSION_UNAVAILABLE'
def test_p8_trace_032_missing_policy():
    r=ReplayRequest(ReplayMode.EXACT_REPLAY,('catalog-v1','rules-v1'),('6.5',),('x',)); assert check_exact_replay_availability(_entry(),r).reason_code=='POLICY_VERSION_UNAVAILABLE'
def test_p8_trace_033_current_recompute():
    r=ReplayRequest(ReplayMode.CURRENT_RECOMPUTATION,current_outcome_reference='new',current_decision_status=DecisionStatus.FLAGGED_REVIEW); assert evaluate_replay_comparison(_entry(),r).changed
def test_p8_trace_034_not_replayable():
    e=_entry(replay_status=ReplayStatus.NOT_REPLAYABLE); assert check_exact_replay_availability(e,ReplayRequest(ReplayMode.EXACT_REPLAY)).reason_code=='TRACE_NOT_REPLAYABLE'
def test_p8_trace_035_no_substitute():
    r=ReplayRequest(ReplayMode.EXACT_REPLAY,(),('6.5',),('P8.1',),current_outcome_reference='current'); assert evaluate_replay_comparison(_entry(),r).recomputed_outcome_reference is None
def test_p8_trace_036_no_cot_fields():
    names={f.name for f in fields(CanonicalLedgerEntry)}; assert names.isdisjoint({'chain_of_thought','reasoning_tokens','scratchpad','raw_prompt','raw_completion','hidden_reasoning'})
def test_p8_trace_037_domain_ref(): assert _entry(domain_trace_reference='domain:abc').domain_trace_reference=='domain:abc'
def test_p8_trace_038_university_required():
    with pytest.raises(ValueError): _entry(university_id=' ')
def test_p8_trace_039_hash_shape(): assert validate_sha256_hash('a'*64)=='a'*64
def test_p8_trace_040_redaction():
    p=project_trace_metadata(_entry(),RedactionProfile.PUBLIC_REDACTED); assert p.student_user_id is None and p.subject_scope_id=='REDACTED'
