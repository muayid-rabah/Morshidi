STATUS: RECONSTRUCTED DRAFT — NOT APPROVED

# P8 Candidate Verification Matrix — Recovery Draft

## Status and method

The original matrix was empty; these are not recovered original scenarios. They are candidate coverage derived from the P8 umbrella policy, Slice 1 code/tests, and existing P6/P7 security contracts. `Existing` means an executable test currently exists; all other rows are proposed and require approval before implementation.

Source codes: `U` = P8 umbrella policy; `S1` = Slice 1 model/canonical/validation/replay and `test_decision_trace.py`; `P6` = mock-registration RLS/threat contracts; `P7` = advisor authorization policy/service/migration; `CAP` = capability matrix.

## Verified existing requirements and coverage

Slice 1 has 40 executable focused tests for canonical entry validation, hashing, tamper detection, supersession, scope checks, replay, and structural redaction. The root backend suite has 13 Local Supabase skips; none is a P8 Slice 2 test because Slice 2 has no files.

## Requirements derived from implementation

The existing registries, immutable records, canonicalization, validation, replay helpers, and redaction projection determine the existing TRACE rows. P6/P7 authorization and suppression documents determine the draft database/security boundaries but do not constitute P8 runtime coverage.

## Proposed requirements and unresolved contracts

All rows marked `DRAFT` are proposed candidate verification only. Source onboarding, persistence schema, graph registry, impact semantics, approved metric catalog, RAG retrieval mechanics, and query-provider controls remain **OPEN CONTRACT / REQUIRES HUMAN APPROVAL**.

## Security and privacy boundaries

Candidate security rows require real local-Supabase tests where data access, grants, RLS, RPC, ownership, advisor assignment, tenant isolation, or suppression is involved. No unit-only evidence can accept those boundaries.

## Explicit non-goals

This matrix creates no executable test, migration, policy promotion, RAG corpus, graph runtime, impact engine, or institutional query engine.

| ID | Capability | Source | Input / precondition | Expected behavior | Security boundary | Test type | Existing coverage | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TRACE-01 | Envelope | S1 | Valid material entry | Canonical entry validates and hashes | No hidden reasoning | Unit | `P8_TRACE_001` | VERIFIED existing |
| TRACE-02 | Immutability | S1 | Existing entry | Historical object cannot mutate | Append-only precursor | Unit | `P8_TRACE_002` | VERIFIED existing |
| TRACE-03 | Materiality required | S1 | Required decision type | Maps to required | Closed registry | Unit | `003` | VERIFIED existing |
| TRACE-04 | Materiality optional | S1 | Formal policy consultation | Maps optional | Closed registry | Unit | `004` | VERIFIED existing |
| TRACE-05 | Domain-only | S1/U | Routine query | Not ledger-required | No accidental persistence | Unit | `005` | VERIFIED existing |
| TRACE-06 | Unsupported type | S1 | Unknown value | Fails closed | No arbitrary decision | Unit | `006` | VERIFIED existing |
| TRACE-07 | Canonical hash | S1 | Same logical payload | Stable canonical hash | Integrity only | Unit | `009-011,028` | VERIFIED existing |
| TRACE-08 | Tamper signal | S1 | Modified hashed entry | `TAMPER_DETECTED` | Integrity | Unit | `012-014` | VERIFIED existing |
| TRACE-09 | Scope validation | S1 | Missing/mis-scoped student | Fails validation | Student scope | Unit | `020-024,038` | VERIFIED existing |
| TRACE-10 | Evidence normalization | S1 | Reordered/duplicate refs | Canonical evidence ordering | Provenance | Unit | `026` | VERIFIED existing |
| TRACE-11 | Supersession | S1 | Correction to entry | New ID; predecessor unchanged | No historical rewrite | Unit | `015-019` | VERIFIED existing |
| TRACE-12 | Exact replay | S1 | All historic versions available | Historical result available | Version integrity | Unit | `029` | VERIFIED existing |
| TRACE-13 | Replay fail-closed | S1 | Missing source/engine/policy | No substitute output | No fabricated replay | Unit | `030-035` | VERIFIED existing |
| TRACE-14 | Structural redaction | S1/U | Public aggregate projection | Student scope redacted | Privacy | Unit | `036,040` | VERIFIED existing |
| TRACE-15 | Persisted append boundary | U/P6/P7 | Service attempts valid append | Insert only; browser denied | RLS/RPC/tenant | Local Supabase adversarial | None | DRAFT |
| RAG-01 | Verified source admission | U | Unverified source | Reject/hold source | Provenance | Integration | None | DRAFT |
| RAG-02 | Citation anchor | U/S1 | Verified passage | Response names ID/version/locator | Evidence integrity | Integration | None | DRAFT |
| RAG-03 | Missing evidence | U | No matching passage | Explicit abstention | No fabrication | Integration | None | DRAFT |
| RAG-04 | Conflicting evidence | U | Conflicting verified sources | Preserve conflict/abstain | No silent authority | Integration | None | DRAFT |
| RAG-05 | Eligibility handoff | U | Eligibility question | Deterministic engine owns result | AI non-authority | Integration | None | DRAFT |
| RAG-06 | Progress handoff | U | Progress/graduation question | Deterministic engine owns result | AI non-authority | Integration | None | DRAFT |
| RAG-07 | Prompt injection in source | U | Malicious retrieved text | Ignore embedded instructions | Retrieval isolation | Security | None | DRAFT |
| RAG-08 | Prompt injection in query | U | User asks override/exfiltration | Reject unsafe request | Tool/secret boundary | Security | None | DRAFT |
| RAG-09 | Restricted source | Proposed | Restricted document | Citation/content policy enforced | Source classification | Integration | None | DRAFT |
| RAG-10 | Versioned source | U/S1 | Superseded source version | Cite exact version | Replay provenance | Integration | None | DRAFT |
| RAG-11 | Arabic locator | OPEN | Arabic source passage | Exact approved locator returned | Citation accuracy | Integration | None | DRAFT |
| RAG-12 | Student data exclusion | U | Policy query with student ID | No record retrieval | Ownership | Security | None | DRAFT |
| RAG-13 | Advisor case scope | U/P7 | Advisor combines policy + student | P7 predicate first | Assignment/tenant | Local integration | None | DRAFT |
| RAG-14 | Unsupported question | U | Outside corpus/metric | Abstain with limitation | Grounding | Integration | None | DRAFT |
| RAG-15 | No raw reasoning | S1/U | Generated answer/log | No CoT/raw prompt stored | Privacy/security | Unit/integration | `P8_TRACE_036` partial | DRAFT |
| IMPACT-01 | Policy delta | U | Versioned policy change | Read-only affected report | No write | Unit | None | DRAFT |
| IMPACT-02 | Curriculum delta | U | Curriculum revision | Affected plans reported | Tenant/scope | Unit | None | DRAFT |
| IMPACT-03 | Prerequisite delta | U | Rule change | Recompute candidates with uncertainty | Deterministic precedence | Unit | None | DRAFT |
| IMPACT-04 | Plan revision | U | Plan version change | Historic/current separated | No history rewrite | Unit | None | DRAFT |
| IMPACT-05 | Missing versions | S1/U | Historic source absent | Not-replayable limitation | No fabricated impact | Unit | `030-035` partial | DRAFT |
| IMPACT-06 | Owner/advisor scope | P7 | Individual impact request | Owner/P7 predicate enforced | BOLA/tenant | Local integration | None | DRAFT |
| IMPACT-07 | Analyst aggregate | P6/U | Small cohort impact | Suppress result | Privacy | Local integration | None | DRAFT |
| IMPACT-08 | No queue/write | U | Any impact run | No mutations/notifications | No side effect | Unit/audit | None | DRAFT |
| GRAPH-01 | Typed decision node | U/CAP | Material decision | Closed node kind/provenance | No raw reasoning | Unit | None | DRAFT |
| GRAPH-02 | Rule/course/requirement links | U/CAP | Deterministic outcome | Typed causal edges | Engine precedence | Unit | None | DRAFT |
| GRAPH-03 | Evidence/source links | U/S1 | Evidence reference | Versioned source edge | Provenance | Unit | None | DRAFT |
| GRAPH-04 | Cycle rejection | U/CAP | Edge closes cycle | Builder rejects | DAG integrity | Unit | None | DRAFT |
| GRAPH-05 | Scope mismatch | U/P7 | Cross-tenant edge | Reject | Tenant isolation | Unit | None | DRAFT |
| GRAPH-06 | Missing evidence | U | Missing source | Explicit limitation node/state | No fabrication | Unit | None | DRAFT |
| GRAPH-07 | Student projection | U/S1 | Owner graph | Student-safe projection | Ownership | Local integration | None | DRAFT |
| GRAPH-08 | Advisor/analyst projection | U/P7 | Advisor or analyst request | Assigned advisor allowed; analyst denied individual graph | Assignment/privacy | Local integration | None | DRAFT |
| QUERY-01 | Metric allowlist | U | Approved metric request | Typed permitted metric executes | No arbitrary query | Integration | None | DRAFT |
| QUERY-02 | Unsupported metric | U | Unknown metric | Abstain/reject | Allowlist | Integration | None | DRAFT |
| QUERY-03 | SQL injection | U | SQL-like natural language | No SQL execution | Database boundary | Security | None | DRAFT |
| QUERY-04 | Tenant binding | P6 | Analyst changes university | Server membership scope wins | Cross-tenant | Local integration | None | DRAFT |
| QUERY-05 | Suppression | P6/U | Below threshold cohort | Suppressed output/no raw counts | Inference resistance | Local integration | Existing P6 tests only | DRAFT |
| QUERY-06 | No student drill-down | U/P6 | Ask for student records | Reject/no identifiers | Privacy | Security | None | DRAFT |
| QUERY-07 | Grounded response | U/CAP | Metric/policy answer | Evidence, version, limitation shown | No hallucinated metric | Integration | None | DRAFT |
| QUERY-08 | Prompt injection | U | Override/debug/exfiltration request | Reject; no secret/SQL/raw rows | Model/tool boundary | Security | None | DRAFT |

## Draft acceptance gate

The 54 rows are candidate coverage only: 14 trace rows have existing executable unit evidence, while `TRACE-15` and all RAG/IMPACT/GRAPH/QUERY rows require approved design and future tests. P8.1 remains PARTIAL and P8 Slice 2 remains NOT ACCEPTED.
