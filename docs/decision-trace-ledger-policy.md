# Decision Trace Ledger — Approved Canonical Contract

Status: **APPROVED POLICY CONTRACT**

This document reconstructs a missing canonical companion contract from the P8
umbrella policy, the recovery draft, current deterministic/security contracts,
and repository implementation evidence. It does not retroactively establish
lost historical requirements or approve a new product capability.

## 1. Purpose and governing authority

The Decision Trace Ledger is an append-only, privacy-preserving audit sidecar
for material academic decisions. It records governed evidence and versions so a
decision can be inspected or replay-assessed without rewriting academic state.
It is governed by **AI EXPLAINS — DETERMINISTIC RULES DECIDE**: an LLM, a hash,
or a trace never authorizes or determines eligibility, progress, graduation,
registration, or another academic outcome.

Routine read-only domain/advisor operations may remain ephemeral. A trace is not
an official university record, enrollment transaction, or authorization grant.

## 2. Normative trace requirements

- A canonical typed entry carries identity, materiality, actor and subject scope,
  university scope, conditional student scope, deterministic engine/policy/source
  versions, outcome and input/scenario references, evidence references,
  provenance, timestamp, redaction, replay, supersession, limitations, and
  schema/hash versions.
- Materiality is a closed registry. Existing classes are `LEDGER_REQUIRED`,
  `LEDGER_OPTIONAL`, `DOMAIN_TRACE_ONLY`, and `NOT_LEDGERED`; changes require
  explicit policy approval.
- Canonicalization is deterministic: compact sorted-key UTF-8 JSON, normalized
  UTC timestamps, canonical enum values, and sorted set-like fields. The
  integrity hash is excluded from its own canonical payload and uses SHA-256.
  A SHA-256 digest is integrity evidence, not authorization or a signature.
- Evidence is typed and versioned. It must not contain chain-of-thought, raw
  prompts/completions, scratchpads, reasoning tokens, service credentials, or
  unnecessary student data.
- A student-individual entry requires the student scope; an institutional-period
  entry forbids it. Every tenant-scoped entry preserves university scope.
- Corrections append a new entry that supersedes the predecessor. Historical
  entries and their evidence are never rewritten.
- `EXACT_REPLAY` fails closed when historical source, engine, or policy versions
  are unavailable. `CURRENT_RECOMPUTATION` remains visibly distinct and cannot
  overwrite history. `NOT_REPLAYABLE` is explicit rather than inferred.
- Structural redaction removes or projects identity according to the permitted
  audience. A public/aggregate projection must disclose its redaction limitation.

## 3. Access and persistence boundaries

No browser client may arbitrarily write, update, or delete ledger/evidence
history. A trusted server-side persistence boundary may append only after the
authoritative deterministic result has been determined and validated. Evidence
inherits the authorization scope of its parent and cannot become an independent
enumeration path.

The Student Decision History V1 surface requires the verified student owner and
authoritative university, displays only `STUDENT_SAFE` entries, and provides
read-only allowlisted list/detail projections after canonical integrity
verification. The advisor read API reuses the P7 predicate: verified identity,
active `ACADEMIC_ADVISOR` membership in the student's authoritative university,
and active exact advisor-student assignment. It permits `STUDENT_SAFE` and
`ADVISOR_SAFE` only. `FULL_AUDIT`, `AGGREGATE_ANALYST`, and `PUBLIC_REDACTED`
are not implicitly visible. `INSTITUTIONAL_ANALYST` has **zero student-level
Decision Trace access**, even when it holds unrelated institutional permissions.
Cross-tenant and unknown-scope access fail closed without existence disclosure.

**RETENTION V1: NO AUTOMATIC DELETION.** Retention remains governed; no automatic
deletion mechanism is enabled in V1. There is no TTL, background cleanup, or
student/advisor/analyst browser deletion control. This is not a legal claim to
retain forever. Any future institutional/legal retention or erasure operation
requires explicit policy approval, legal/institutional basis, an auditable
operation, and preservation of required integrity/audit obligations.

**EXPORT V1: DISABLED / NOT IMPLEMENTED.** No PDF, CSV, JSON dump, public/share
link, or bulk download is approved. Export requires a separate authorization,
redaction, privacy, audit, and institutional governance contract. Bounded
list/detail APIs do not constitute export authority.

## 4. Current implementation status

**PARTIAL.** The repository contains a canonical decision-trace domain model,
validation, hashing, replay availability checks, typed evidence, immutable
PostgreSQL ledger/evidence persistence, a service-role append RPC, P6 outbox
records, and service-only outbox claim/complete/release/fail RPC boundaries.
Student Decision History V1 and the advisor's assignment-scoped read API provide
bounded newest-first list/detail projections, safe evidence, per-entry canonical
hash verification, stored replay-status display, and read-only supersession
labels. No viewer executes arbitrary replay or mutates history. Exact replay
availability checks require the historical source, engine, and policy versions;
the comparison helper is not evidence that the historical executable ran.
`CURRENT_RECOMPUTATION` is distinct and does not change the historical entry.

WC-040 remains **PARTIAL** because registry acceptance requires every required
material decision to have a trusted runtime producer. `MOCK_REGISTRATION_SUBMIT`
has the P6 outbox-to-ledger producer, and `CHANGE_IMPACT_EVALUATION` now has the
trusted WC-046 evaluator producer. The
other required types cannot be called covered merely because the domain model
accepts them or a fixture can be appended. No unrelated producer is added by
this viewer closure. Test outcomes and the full registry coverage assessment
are recorded in `CODEX_PROGRESS.md`.
Older P6 submit traces remain `NOT_REPLAYABLE` with the
`P6_HISTORICAL_REPLAY_NOT_AVAILABLE` limitation. New submit revisions using
`P6_REPLAY_ARTIFACT_V1` atomically persist a private, immutable copy of the
validation-consumed historical inputs and output. Their trusted ledger entries
are `REPLAYABLE_EXACT` only after artifact integrity and identity verification.
An internal-only V1 adapter reconstructs those inputs and actually reruns P6
validation; missing artifacts, tampering, and unavailable engine versions fail
closed. Current student/catalog state is never substituted. Neither existing
replay helper executes that historical validation; no ledger history is rewritten.

### Material-event coverage at this closure

`Trusted producer` means a real approved runtime event adapter, not a test
fixture or an on-demand domain trace. `Persistence` means that producer reaches
the immutable ledger. `Viewer compatible` means an existing individual-safe
projection can show a correctly scoped entry; it does not assert that one is
produced. Institutional/aggregate traces have no approved student-level viewer.

| Decision type | Materiality | Trusted producer | Persistence | Viewer compatible |
| --- | --- | --- | --- | --- |
| `MOCK_REGISTRATION_SUBMIT` | `LEDGER_REQUIRED` | YES | YES | YES |
| `MOCK_REGISTRATION_WITHDRAW` | `LEDGER_REQUIRED` | NO | NO | YES |
| `MOCK_REGISTRATION_REVALIDATE` | `LEDGER_REQUIRED` | NO | NO | YES |
| `ADVISOR_FORMAL_GUIDANCE` | `LEDGER_REQUIRED` | NO | NO | YES |
| `INSTITUTIONAL_PERIOD_DEMAND_SNAPSHOT` | `LEDGER_REQUIRED` | NO | NO | NO |
| `INSTITUTIONAL_BOTTLENECK_SNAPSHOT` | `LEDGER_REQUIRED` | NO | NO | NO |
| `INSTITUTIONAL_ALERT_TRIGGERED` | `LEDGER_REQUIRED` | NO | NO | NO |
| `CHANGE_IMPACT_EVALUATION` | `LEDGER_REQUIRED` | YES | YES | PARTIAL: advisor individual safe; no analyst structural viewer |
| `FORMAL_POLICY_CONSULTATION` | `LEDGER_OPTIONAL` | NO | NO | YES |
| `CHECK_ELIGIBILITY` | `DOMAIN_TRACE_ONLY` | NO | NO | NO |
| `GET_PROGRESS` | `DOMAIN_TRACE_ONLY` | NO | NO | NO |
| `GET_RECOMMENDATIONS` | `DOMAIN_TRACE_ONLY` | NO | NO | NO |
| `GET_SEMESTER_PLANS` | `DOMAIN_TRACE_ONLY` | NO | NO | NO |
| `GET_DEGREE_PATHS` | `DOMAIN_TRACE_ONLY` | NO | NO | NO |
| `GET_STUDENT_INTELLIGENCE` | `DOMAIN_TRACE_ONLY` | NO | NO | NO |
| `CHECK_DELAY_CONSEQUENCE` | `DOMAIN_TRACE_ONLY` | NO | NO | NO |
| `RUN_WHAT_IF` | `DOMAIN_TRACE_ONLY` | NO | NO | NO |
| `GET_CURRENT_MOCK_REGISTRATION` | `DOMAIN_TRACE_ONLY` | NO | NO | NO |
| `EXPLAIN_RECOMMENDATION_DECISION` | `DOMAIN_TRACE_ONLY` | NO | NO | NO |
| `INSTITUTIONAL_AD_HOC_QUERY` | `NOT_LEDGERED` | NO | NO | NO |
| `POLICY_AD_HOC_CHAT` | `NOT_LEDGERED` | NO | NO | NO |

### P8 closure-audit classification of missing required producers (2026-09-29)

This classification describes observed runtime events; it does not change the
approved materiality registry. `MOCK_REGISTRATION_WITHDRAW` is an existing
immutable P6 transaction without a trusted ledger producer (**D: existing
runtime audit gap**). It blocks full WC-040 material-event coverage, but is
**not a blocker to the roadmap P8 local phase exit**, which requires a
replayable trace-ledger path rather than every material producer. The withdrawal
gap must remain visible and be closed before claiming full WC-040 acceptance.
`ADVISOR_FORMAL_GUIDANCE` depends on the unimplemented formal advisor-decision
workflow WC-013 (**B: later capability**). `MOCK_REGISTRATION_REVALIDATE` is
currently a read-time current-validity calculation, not a committed revalidation
event (**C: registry over-scoped for the current operation**). The institutional
period-demand and bottleneck “snapshot” values and alert `emitted` flags are
currently read-time deterministic projections, not published or triggered
material milestones (**C: registry over-scoped for those current operations**).
If a future workflow commits a snapshot, trigger, or formal revalidation, its
`LEDGER_REQUIRED` producer must exist before that workflow is accepted.
`CHANGE_IMPACT_EVALUATION` is an implemented trusted WC-046 producer with an
immutable ledger entry but remains `NOT_REPLAYABLE`; the P6 submit producer is
implemented and its new replay-contract entries are `REPLAYABLE_EXACT`.

New replay-contract P6 submit traces are exactly replayable through the trusted
internal executor, which compares the full rerun output with the immutable
historical output and persisted revision. Older P6 traces and WC-046 impact
traces remain `NOT_REPLAYABLE`. Canonical hash checks alone are integrity checks,
not replay. This provides bounded technical runtime evidence for the roadmap's
“replayable trace ledger” gate, but does not complete material-producer coverage,
the wider P8 matrix, or institutional validation. It supports local P8 phase
delivery without claiming full WC-040 completion or production deployment.

## 5. Open contracts — requires human approval

- Eligible material event registry expansion, future retention/legal-erasure
  process, and any viewer beyond the approved student/advisor boundaries.
- Any export capability beyond the V1 disabled boundary.
- Source/engine/policy-version preservation obligations for exact replay.
- Any additional chain/period integrity model beyond per-entry integrity.
- Any new persistence surface, grant, RLS policy, or external integration not
  already represented by the current audited implementation.

## 6. Non-goals and acceptance

The ledger does not grant academic authority, mutate recommendations/registration/
progress/catalog state, expose hidden reasoning, or replace official systems.
Future completion requires approved open contracts plus real local-Supabase
security evidence for grants/RLS/RPC, ownership/advisor/tenant isolation,
append-only behavior, evidence scope, integrity tamper handling, and replay.
