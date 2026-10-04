Status: **APPROVED POLICY CONTRACT**

# P8 Grounded Knowledge Verification Matrix

## Status and method

This remains a normative coverage matrix; it is not a claim that every row is
implemented. The historical recovery origin of the matrix remains relevant, but
the repository now includes later runtime slices for Decision Trace and structured
Policy Retrieval. `Existing` means an executable test currently exists; all other
rows remain proposed unless their implementation evidence is explicitly named.

Source codes: `U` = P8 umbrella policy; `S1` = Slice 1 model/canonical/validation/replay and `test_decision_trace.py`; `P6` = mock-registration RLS/threat contracts; `P7` = advisor authorization policy/service/migration; `CAP` = capability matrix.

## Current implementation evidence

The historical Student Decision History V1 backend baseline was **1,582 passed,
0 failed, 0 skipped** against Local Supabase. In addition to
the original Slice 1 evidence, the repository contains executable coverage for
Decision Trace persistence, P6 outbox mapping/processing boundaries, policy
domain/retrieval, atomic policy ingestion, student policy API, and Local Supabase
policy persistence/security, hybrid retrieval, grounded-answer guards, and
student-owner Decision History list/detail, redaction, integrity, and Local
Supabase browser-denial checks. That
evidence establishes implemented slices only. The subsequent clean-reset
backend baseline collected and passed 1,705 tests with zero failures or skips;
the 2026-09-29 focused replay, ledger, and cited-retrieval run passed 131 tests
with zero failures or skips. These results do not accept every matrix row or
complete every WC Definition of Done.

## Verified existing requirements and coverage

Slice 1 has executable focused tests for canonical entry validation, hashing,
tamper detection, supersession, scope checks, replay, and structural redaction.
The current audited root backend suite has zero skipped tests. Later P8 runtime
tests supplement, rather than replace, the original policy requirements.

## Requirements derived from implementation

The existing registries, immutable records, canonicalization, validation, replay helpers, and redaction projection determine the existing TRACE rows. P6/P7 authorization and suppression documents determine the draft database/security boundaries but do not constitute P8 runtime coverage.

## Proposed requirements and unresolved contracts

The RAG rows below are reconciled against executable domain, API, and real Local
Supabase tests. A verified local contract is not institutional source approval.
Structured policy persistence, ingestion, semantic and hybrid retrieval, and a
bounded grounded-answer runtime are implemented. WC-046 V1 change-impact
semantics are owner-approved and implemented within the stated V1 limits;
document-source onboarding, broader graph registries, published-change
authority, general plan revision, representative institutional query
intent/metric validation, and repeated-query governance remain open.

## Security and privacy boundaries

Candidate security rows require real local-Supabase tests where data access, grants, RLS, RPC, ownership, advisor assignment, tenant isolation, or suppression is involved. No unit-only evidence can accept those boundaries.

## Explicit non-goals

This matrix creates no executable test, migration, policy promotion, RAG corpus, graph runtime, impact engine, or institutional query engine.

| ID | Capability | Source | Input / precondition | Expected behavior | Security boundary | Test type | Existing coverage | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TRACE-01 | Envelope | S1 | Valid material entry | Canonical entry validates and hashes | No hidden reasoning | Unit | `P8_TRACE_001` | VERIFIED |
| TRACE-02 | Immutability | S1 | Existing entry | Historical object and stored rows cannot mutate | Append-only | Unit + Local Supabase | `002`, persistence trigger tests | VERIFIED |
| TRACE-03 | Materiality required | S1 | Required decision type | Maps to required | Closed registry | Unit | `003`; producer coverage remains separate | VERIFIED |
| TRACE-04 | Materiality optional | S1 | Formal policy consultation | Maps optional | Closed registry | Unit | `004` | VERIFIED |
| TRACE-05 | Domain-only | S1/U | Routine query | Not ledger-required | No accidental persistence | Unit | `005` | VERIFIED |
| TRACE-06 | Unsupported type | S1 | Unknown value | Fails closed | No arbitrary decision | Unit | `006` | VERIFIED |
| TRACE-07 | Canonical hash | S1 | Same logical payload | Stable canonical hash | Integrity only | Unit | `009-011,028` | VERIFIED |
| TRACE-08 | Tamper signal | S1 | Modified hashed entry | `TAMPER_DETECTED` | Integrity | Unit + viewer | `012-014`, history tamper tests | VERIFIED |
| TRACE-09 | Scope validation | S1 | Missing/mis-scoped student | Fails validation | Student scope | Unit + Local Supabase | `020-024,038`, owner/advisor tests | VERIFIED |
| TRACE-10 | Evidence normalization | S1 | Reordered/duplicate refs | Canonical evidence ordering | Provenance | Unit + Local Supabase | `026`, stored evidence-order tests | VERIFIED |
| TRACE-11 | Supersession | S1 | Correction to entry | New ID; predecessor unchanged | No historical rewrite | Unit + Local Supabase | `015-019`, persisted supersession tests | VERIFIED |
| TRACE-12 | Exact replay availability | S1 | All historic versions available | New replay-contract P6 submits rerun historical P6 V1; legacy traces remain unavailable | Version integrity | Unit + Local Supabase | `029`, availability helper plus distinct P6 executor and real outbox-to-ledger replay | VERIFIED |
| TRACE-13 | Replay fail-closed | S1 | Missing source/engine/policy | No substitute output | No fabricated replay | Unit + Local Supabase | `030-035`, missing/tampered/unknown-version artifact probes | VERIFIED |
| TRACE-14 | Structural redaction | S1/U | Public aggregate projection | Student scope redacted | Privacy | Unit | `036,040`; no public viewer runtime | PARTIALLY VERIFIED |
| TRACE-15 | Persisted append boundary | U/P6/P7 | Service attempts valid append | Insert only; browser denied | RLS/RPC/tenant | Local Supabase adversarial | persistence, outbox, history local tests | VERIFIED |
| RAG-01 | Verified source admission | U | Unverified source | Reject/hold source | Provenance | Integration | `test_institutional_policy.py::test_02_unverified_source_rejected_or_held`; `test_institutional_policy_local_supabase.py` | VERIFIED |
| RAG-02 | Citation anchor | U/S1 | Verified passage | Response names ID/version/locator | Evidence integrity | Integration | `test_institutional_policy.py::test_03_exact_citation_version_preserved`; `test_policy_answer_local_supabase.py::test_local_synthetic_verified_passage_produces_exact_server_citation` | VERIFIED |
| RAG-03 | Missing evidence | U | No matching passage | Explicit abstention | No fabrication | Integration | `test_policy_answer_local_supabase.py::test_local_empty_tenant_abstains_without_embedding_or_generation`; `test_policy_answering.py::test_no_retrieved_evidence_abstains_without_generation` | VERIFIED |
| RAG-04 | Conflicting evidence | U | Conflicting verified sources | Preserve conflict/abstain | No silent authority | Integration | `test_institutional_policy.py::test_05_conflicting_verified_sources_triggers_conflict_and_abstention`; `test_policy_answering.py::test_conflicting_versions_and_unverified_rows_abstain_before_generation` | VERIFIED |
| RAG-05 | Eligibility handoff | U | Eligibility question | Deterministic engine owns result | AI non-authority | Integration | `test_institutional_policy.py::test_06_deterministic_eligibility_question_routes_to_engine_handoff`; `test_policy_answering.py::test_computable_questions_handoff_before_retrieval_or_generation` | VERIFIED |
| RAG-06 | Progress handoff | U | Progress/graduation question | Deterministic engine owns result | AI non-authority | Integration | `test_institutional_policy.py::test_07_deterministic_progress_question_routes_to_engine_handoff`; `test_policy_answering.py::test_computable_questions_handoff_before_retrieval_or_generation` | VERIFIED |
| RAG-07 | Prompt injection in source | U | Malicious retrieved text | Ignore embedded instructions | Retrieval isolation | Security | `test_policy_answering.py::test_passage_prompt_injection_cannot_authorize_personalized_decision` | VERIFIED |
| RAG-08 | Prompt injection in query | U | User asks override/exfiltration | Reject unsafe request | Tool/secret boundary | Security | `test_policy_answering.py::test_user_prompt_injection_stops_before_retrieval_and_provider` | VERIFIED |
| RAG-09 | Restricted source | Proposed | Restricted document | Citation/content policy enforced | Source classification | Integration | No approved restricted-source classification/licensing rule or executable access test | BLOCKED |
| RAG-10 | Versioned source | U/S1 | Superseded source version | Cite exact version | Replay provenance | Integration | `test_institutional_policy.py::test_09_superseded_source_does_not_silently_replace_exact_version`; `test_policy_semantic_local_supabase.py::test_real_semantic_rpc_filters_ranks_and_preserves_citations` | VERIFIED |
| RAG-11 | Arabic locator | OPEN | Arabic source passage | Exact approved locator returned | Citation accuracy | Integration | `test_institutional_policy.py::test_03_exact_citation_version_preserved`; synthetic Arabic locator round-trip, but no institution-approved locator corpus | PARTIALLY VERIFIED |
| RAG-12 | Student data exclusion | U | Policy query with student ID | No record retrieval | Ownership | Security | Policy API is tenant-scoped and does not query student records, but no explicit student-identifier-in-query adversarial case | PARTIALLY VERIFIED |
| RAG-13 | Advisor case scope | U/P7 | Advisor combines policy + student | P7 predicate first | Assignment/tenant | Local integration | No combined advisor policy/student-case endpoint or executable P7-predicate test for it | BLOCKED |
| RAG-14 | Unsupported question | U | Outside corpus/metric | Abstain with limitation | Grounding | Integration | `test_institutional_policy.py::test_08_unsupported_question_emits_explicit_limitation`; `test_policy_answering.py::test_empty_corpus_abstains_without_embedding_or_answer_provider` | VERIFIED |
| RAG-15 | No raw reasoning | S1/U | Generated answer/log | No CoT/raw prompt stored | Privacy/security | Unit/integration | `test_institutional_policy.py::test_13_no_hidden_chain_of_thought_or_raw_reasoning_fields`; no end-to-end log/prompt-storage audit | PARTIALLY VERIFIED |
| IMPACT-01 | Policy delta | U | Versioned policy change | Read-only affected report | No write | Unit + Local Supabase | policy review and audit-only persistence tests | VERIFIED |
| IMPACT-02 | Curriculum delta | U | Curriculum revision | Affected plans reported | Tenant/scope | Unit + Local Supabase | requirement/plan-course credit V1; general plan-version revision absent | PARTIALLY VERIFIED |
| IMPACT-03 | Prerequisite delta | U | Rule change | recompute affected paths with uncertainty | Deterministic precedence | Unit + Local Supabase | add/remove/replace, OR/AND, downstream, overflow, eligibility recomputation and local plan-scoped API; request-specific path recomputation unavailable | PARTIALLY VERIFIED |
| IMPACT-04 | Plan revision | U | Plan version change | Historic/current separated | No history rewrite | Unit | current/proposed basis and immutable ledger; no PLAN_VERSION_CHANGE V1 type | PARTIALLY VERIFIED |
| IMPACT-05 | Missing versions | S1/U | Historic source absent | Not-replayable limitation | No fabricated impact | Unit + Local Supabase | `NOT_REPLAYABLE`, ephemeral report, source-version-unverified limitation | VERIFIED |
| IMPACT-06 | Owner/advisor scope | P7 | Individual impact request | Owner/P7 predicate enforced | BOLA/tenant | Local Supabase | assigned advisor and denial matrix; owner delta submission intentionally absent in approved V1 | PARTIALLY VERIFIED |
| IMPACT-07 | Analyst aggregate | P6/U | Small cohort impact | Suppress result | Privacy | Local Supabase | structural-only analyst report, no student scan/count; population suppression not exercised | PARTIALLY VERIFIED |
| IMPACT-08 | No queue/write | U | Any impact run | No mutations/notifications | No side effect | Unit + Local Supabase | academic-table snapshots identical; only required trace appended and retry idempotent | VERIFIED |
| GRAPH-01 | Typed decision node | U/CAP | Material decision | Closed node kind/provenance | No raw reasoning | Unit | eligibility decision plus typed recommendation/planner/path nodes; no material-ledger adapter | PARTIALLY VERIFIED |
| GRAPH-02 | Rule/course/requirement links | U/CAP | Deterministic outcome | Typed causal edges | Engine precedence | Unit | closed reason, course, prerequisite, requirement, constraint, semester, path, and version edges tested; no general rule or ledger adapter | PARTIALLY VERIFIED |
| GRAPH-03 | Evidence/source links | U/S1 | Evidence reference | Versioned source edge | Provenance | Unit | exact engine policy versions linked; academic source-document versions absent and disclosed | PARTIALLY VERIFIED |
| GRAPH-04 | Cycle rejection | U/CAP | Edge closes cycle | Builder rejects | DAG integrity | Unit | `test_explainability_graph.py` | VERIFIED |
| GRAPH-05 | Scope mismatch | U/P7 | Cross-tenant edge | Reject | Tenant isolation | Unit | real owner and exact assigned-advisor tenant gate; no persisted cross-tenant graph-edge namespace | PARTIALLY VERIFIED |
| GRAPH-06 | Missing evidence | U | Missing source | Explicit limitation node/state | No fabrication | Unit | exact-version limitation and review uncertainty tests | VERIFIED |
| GRAPH-07 | Student projection | U/S1 | Owner graph | Student-safe projection | Ownership | Local integration | authenticated student eligibility, recommendation, planner, degree-path graph routes and real Local Supabase owned-profile tests | VERIFIED |
| GRAPH-08 | Advisor/analyst projection | U/P7 | Advisor or analyst request | Assigned advisor allowed; analyst denied individual graph | Assignment/privacy | Local integration | P7 authorization-before-load API and real Local Supabase assigned/unassigned/inactive/cross-tenant/analyst tests; no advisor UI | VERIFIED |
| QUERY-01 | Metric allowlist | U | Approved metric request | Typed permitted metric executes | No arbitrary query | Unit + Local Supabase | exact 13-ID catalog, controlled Arabic/English interpretation, one-signal P7 parity; representative live intent quality open | PARTIALLY VERIFIED |
| QUERY-02 | Unsupported metric | U | Unknown metric | Abstain/reject | Allowlist | Unit + API | unknown/multiple/malformed provider selections abstain; unsupported individual/GPA examples | VERIFIED |
| QUERY-03 | SQL injection | U | SQL-like natural language | No SQL execution | Database boundary | Unit + source review | SQL-like questions abstain; provider has no SQL tool or executor and output only validates to catalog ID | VERIFIED |
| QUERY-04 | Tenant binding | P6 | Analyst changes university | Server membership scope wins | Cross-tenant | Local integration | real analyst, inactive, wrong-role, cross-university denial before provider | VERIFIED |
| QUERY-05 | Suppression | P6/U | Below threshold cohort | Suppressed output/no raw counts | Inference resistance | Local integration | real P6 one-intent cohort maps to `SUPPRESSED`/null; single-signal response has no hidden count | VERIFIED |
| QUERY-06 | No student drill-down | U/P6 | Ask for student records | Reject/no identifiers | Privacy | Unit + Local integration | individual-data questions abstain; serialized response excludes student IDs, rows, traces | VERIFIED |
| QUERY-07 | Grounded response | U/CAP | Metric/policy answer | Evidence, version, limitation shown | No hallucinated metric | Unit + frontend | exact selected P7 signal, typed scope/version/flags/limitations/fingerprint displayed; representative source-version authority open | PARTIALLY VERIFIED |
| QUERY-08 | Prompt injection | U | Override/debug/exfiltration request | Reject; no secret/SQL/raw rows | Model/tool boundary | Unit + provider | injection corpus abstains; strict structured response and post-validation prevent widened metric/scope/output fields | VERIFIED |

## Specification acceptance gate

The 54 rows remain the normative scenario inventory. The repository now has additional
runtime and Local Supabase evidence for the implemented Decision Trace and
grounded Policy Retrieval slices. `TRACE-14` remains partially verified because
only the structural public-redaction helper exists; no public viewer is approved.
WC-007 now has eligibility and material recommendation/planner/path projections
with student and assigned-advisor API evidence. GRAPH-01/02/03/05 remain
partial for broader decision/source/scope contracts. WC-040 also remains partial
because six `LEDGER_REQUIRED` decision types lack trusted runtime producers;
new replay-contract P6 submits are `REPLAYABLE_EXACT`, while legacy P6 and
WC-046 impact traces remain `NOT_REPLAYABLE`. The partially verified
and blocked RAG/IMPACT/GRAPH/QUERY rows retain the limitations stated in their
row evidence; locally verified rows do not certify institutional data.
WC-039 V1 has local finite-metric, tenant, suppression, safe provider, frontend,
and no-write evidence, but representative real-data language and source-version
validation remain open. The reconciled row counts are **37 VERIFIED, 15
PARTIALLY VERIFIED, 2 BLOCKED, 0 NOT APPLICABLE = 54**. Verified rows establish
their stated bounded contracts, not full WC completion. The two roadmap P8
local exit paths are now verified: cited policy retrieval and new trusted P6
submit -> outbox -> ledger -> exact historical replay. The phase is locally
delivered, pending owner closure; broader producer coverage and institutional/
production validation remain incomplete.

### Roadmap P8 phase-blocker classification of non-verified rows

`P8_PHASE_BLOCKER` assesses the roadmap's local cited-retrieval and replayable-
ledger exit evidence, not the full WC Definition of Done. The P8.1 policy gate
requires the 54-scenario matrix to be documented and verified as a coverage
inventory; it does not say that every scenario must be implemented or marked
VERIFIED before the narrower roadmap delivery gate can close. Statuses above
remain unchanged. All 17 non-verified rows are classified below.

| ID | Status | P8_PHASE_BLOCKER | One-line reason |
| --- | --- | --- | --- |
| TRACE-14 | PARTIALLY VERIFIED | NO | Public aggregate viewer is unapproved; private replayable ledger path exists. |
| RAG-09 | BLOCKED | NO | Restricted-source licensing/classification is external governance, not required for verified/current cited local sources. |
| RAG-11 | PARTIALLY VERIFIED | NO | Institution-approved Arabic locator corpus is external; exact synthetic locator and citation are tested. |
| RAG-12 | PARTIALLY VERIFIED | NO | Dedicated identifier-in-query adversarial case remains, while policy retrieval has no student-record access. |
| RAG-13 | BLOCKED | NO | Combined advisor policy/student-case surface is future work; student cited retrieval is implemented. |
| RAG-15 | PARTIALLY VERIFIED | NO | End-to-end log audit remains; bounded answer shape excludes raw reasoning. |
| IMPACT-02 | PARTIALLY VERIFIED | NO | General plan-version delta exceeds the approved four-type WC-046 V1 and P8 roadmap exit. |
| IMPACT-03 | PARTIALLY VERIFIED | NO | Request-specific path recomputation exceeds approved V1 impact scope. |
| IMPACT-04 | PARTIALLY VERIFIED | NO | PLAN_VERSION_CHANGE is outside approved V1; history is not rewritten. |
| IMPACT-06 | PARTIALLY VERIFIED | NO | Owner delta submission is outside approved V1; assigned-advisor scope is tested. |
| IMPACT-07 | PARTIALLY VERIFIED | NO | Population suppression for hypothetical aggregate impact is not exercised; current analyst report is structural-only. |
| GRAPH-01 | PARTIALLY VERIFIED | NO | Material-ledger adapter is broader WC-007 work; current deterministic decision graphs are typed. |
| GRAPH-02 | PARTIALLY VERIFIED | NO | General rule/ledger adapters are broader WC-007 work; current causal edges are tested. |
| GRAPH-03 | PARTIALLY VERIFIED | NO | Academic source-document versions are unavailable and disclosed; current engine versions are linked. |
| GRAPH-05 | PARTIALLY VERIFIED | NO | Persisted cross-tenant edge namespace does not exist; current owner/advisor tenant gates are tested. |
| QUERY-01 | PARTIALLY VERIFIED | NO | Representative live language quality is external; exact 13-signal allowlist is tested locally. |
| QUERY-07 | PARTIALLY VERIFIED | NO | Representative source-version authority is external; bounded grounded metric response is tested. |
