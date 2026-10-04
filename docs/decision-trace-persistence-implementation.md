# P8 Runtime Slice 2A — Decision Trace Ledger Persistence Foundation

**Status:** IMPLEMENTED AND LOCALLY VERIFIED — NOT PRODUCTION-APPROVED
**Scope:** database-only persistence foundation. This document does not mark P8 Runtime Slice 2 as accepted.

## Authority and scope

This implementation follows the approved local-only Slice 2A direction and preserves the Slice 1 domain contract in `apps/api/app/decision_trace/`. It neither changes the Slice 1 canonicalization/hash algorithm nor creates a competing SQL serializer.

Implemented in `supabase/migrations/20260924163500_add_decision_trace_ledger.sql`:

- `public.decision_trace_ledger`, the immutable parent record.
- `public.decision_trace_evidence`, ordered typed evidence references owned by one parent record.
- structural constraints, foreign keys, indexes, append-only triggers, RLS, grants, and the restricted append RPC.
- local integration coverage in `apps/api/tests/test_decision_trace_persistence_local_supabase.py`.

It does not implement a Python repository or service, HTTP route, frontend, RAG, graph, impact, institutional query runtime, retention job, hosted deployment, or an official academic-state mutation.

## Stored domain representation

The parent has 28 columns and preserves the storage representation required to losslessly rebuild a Slice 1 entry: ledger identity; decision/materiality/actor; subject scope; university and optional student subject; engine/policy/source versions; input/scenario; status/outcome; domain trace/provenance; created time; redaction profile; integrity and prior hashes; supersession identifier; replay status; limitations; hash-contract version; and decision-schema version.

The migration admits only the approved finite material-event scope:

- `MOCK_REGISTRATION_SUBMIT`
- `MOCK_REGISTRATION_WITHDRAW`
- `MOCK_REGISTRATION_REVALIDATE`
- `ADVISOR_FORMAL_GUIDANCE`
- `INSTITUTIONAL_PERIOD_DEMAND_SNAPSHOT`
- `INSTITUTIONAL_BOTTLENECK_SNAPSHOT`
- `INSTITUTIONAL_ALERT_TRIGGERED`
- `CHANGE_IMPACT_EVALUATION`
- `FORMAL_POLICY_CONSULTATION`

The source version and limitation arrays reject null or empty elements. The entry validates the finite actor, subject-scope, status, provenance, redaction, and replay registries; it requires appropriate student scope and rejects a scenario identifier for an authoritative transaction. A 64-character lowercase SHA-256-shaped value is required for the integrity fields, but this is a format check only.

The child has seven columns: parent ledger identity, one-based `evidence_position`, source, identifier, version, optional locator, and optional URI. Its primary key fixes cardinality and order, while its null-aware uniqueness constraint prevents duplicate evidence references within a parent. It cannot exist independently because its foreign key is `ON DELETE RESTRICT`.

No raw prompts, model completions, hidden reasoning, credentials, passwords, or full policy-document bodies are stored by this schema.

## Append, integrity, and supersession

`public.append_decision_trace_ledger(p_entry jsonb, p_evidence jsonb)` is a `SECURITY DEFINER` function with fixed `search_path = pg_catalog, public`. It:

1. accepts only the exact expected parent/evidence JSON keys;
2. validates required values, JSON array shape, and source-version ordering/uniqueness;
3. inserts one parent and its ordered evidence in a single transaction; and
4. relies on ordinary database exception rollback when any child or constraint validation fails.

The RPC does **not** calculate or verify the Slice 1 canonical SHA-256 value. The trusted future Slice 2B backend is responsible for building a validated Slice 1 `CanonicalLedgerEntry`, verifying its canonical hash before calling this RPC, and enforcing request-level authorization. SHA-256 is neither authorization nor a digital signature.

Supersession is insertion-only. A proposed successor must reference an existing predecessor, supply that predecessor's exact integrity hash, match its university, subject type, subject identifier, and student identity, and not self-supersede. The partial unique index on `supersedes_entry_id` permits at most one successor, including concurrent append attempts, without changing the predecessor. This establishes the approved local single-current-successor storage rule; the future business/current-view meaning and broader chain policy remain subject to the accepted P8 contract and Slice 2B work.

## Immutability and limitations

Database triggers reject ordinary `UPDATE` and `DELETE` on both tables with an append-only error. The new record must be superseded rather than changed. This is stronger than RLS alone and was verified by issuing owner-level SQL update/delete attempts in the local database.

It is not absolute protection against a PostgreSQL superuser, table owner, migration author, or other privileged administrator who can alter triggers, grants, or schema. Legal retention, legal erasure, and exceptional administrative process are explicitly deferred and require human/institutional approval.

## RLS, grants, and service boundary

RLS is enabled on both tables. There are deliberately no `anon` or `authenticated` row policies and no direct user-facing projection in Slice 2A. Direct authenticated raw reads/writes, evidence enumeration, and RPC execution are denied.

The migration revokes direct table privileges from `PUBLIC`, `anon`, `authenticated`, and `service_role`; it then grants only `SELECT` on both tables and `EXECUTE` on the append RPC to `service_role`. `PUBLIC`, `anon`, and `authenticated` have no append-RPC execute grant. The RPC does not take or trust a caller-supplied identity claim.

Supabase `service_role` bypasses RLS. That capability is intentionally confined to the future trusted backend and is not evidence of end-user authorization. Slice 2B must provide server-side owner, active academic-advisor + same-university + active exact assignment, and analyst aggregate-only authorization before any safe projection/read API is introduced. Evidence must always inherit parent authorization.

## Local verification

The migration was applied only to the verified isolated Local Supabase project with `npx --yes supabase@2.117.0 migration up --local`. The target had local API `127.0.0.1:54321`, local PostgreSQL `127.0.0.1:54322`, no linked hosted project, and eight pre-existing migrations. The ninth migration-history row and all objects/triggers/grants listed above were inspected through local PostgreSQL. No reset, `supabase link`, `supabase db push`, or production resource was used.

Executed results:

| Command | Result |
| --- | --- |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_decision_trace_persistence_local_supabase.py -q -rs` | **9 passed, 0 failed, 0 skipped in 5.27s** |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_decision_trace.py -q` | **40 passed in 0.23s** |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests -q -rs` | **1381 passed, 0 failed, 0 skipped, 2 warnings in 1242.45s (20:42)** |

The 9 Slice 2A local tests exercised authorized service append, atomic parent/evidence rollback, invalid finite values/required fields, duplicate identity, malformed evidence, direct authenticated read/write/RPC denial, cross-student and analyst raw-row denial, predecessor/hash/scope validation, concurrent successor conflict, and trigger-enforced parent/evidence update/delete denial. They do not prove the deferred Slice 2B Python hash verification or end-user role-scoped read service.

## Deferred and not verified

- **DEFERRED:** Python persistence repository, canonical-hash verification service, replay persistence/read service, and HTTP APIs.
- **DEFERRED:** student-safe/advisor-safe projections and their P7 active-assignment authorization.
- **DEFERRED:** policy-driven retention/erasure process, production migration/deployment, and human approval of remaining P8.1 reconstruction items.
- **NOT VERIFIED:** production security, production service credentials, legal retention/erasure requirements, and P8 Slice 2B security acceptance.
- **NOT ACCEPTED:** P8 Runtime Slice 2 overall.

The next permitted implementation step is Slice 2B only after human review: implement the trusted Python persistence service and safe retrieval authorization while retaining this migration's immutable append boundary and executing new real Local Supabase adversarial tests.

## Slice 2B — trusted Python persistence, authorization, and safe retrieval

**Status:** IMPLEMENTED AND LOCALLY VERIFIED — NOT PRODUCTION-APPROVED

Slice 2B adds no migration, route, frontend feature, or academic decision engine. It is implemented by:

- app.decision_trace_persistence.repository.SupabaseDecisionTraceRepository
- app.decision_trace_persistence.service.DecisionTraceService
- app.decision_trace_persistence.models.DecisionTraceSafeView
- app.decision_trace_persistence.models.SafeEvidenceReference

### Exact hash and storage trust gates

Before the repository invokes append_decision_trace_ledger, the service calls the existing Slice 1 validate_entry and verify_integrity_hash functions. It rejects missing, malformed, or mismatched hashes; it never replaces a caller-supplied invalid hash. The repository repeats this verification as a defense-in-depth boundary and serializes with the existing canonical_ledger_payload implementation rather than a new serializer.

The repository rejects values that the existing SQL RPC would trim or UUID-normalize before persistence, because such mutation would break hash-covered round-trip compatibility. It writes evidence in the canonical payload order. Retrieval queries a single parent constrained by ledger ID, student ID, university ID, and STUDENT_INDIVIDUAL, then requests its child evidence explicitly by evidence_position.asc. It reconstructs a CanonicalLedgerEntry, verifies the stored hash against the reconstructed payload, and fails closed with INTEGRITY_FAILURE on malformed or mismatched historical storage.

SHA-256 remains integrity evidence only. It is not a signature and does not authorize a caller.

### Trusted append authority

append_student accepts only the finite student event types MOCK_REGISTRATION_SUBMIT, MOCK_REGISTRATION_WITHDRAW, and MOCK_REGISTRATION_REVALIDATE, with STUDENT actor, LEDGER_REQUIRED materiality, STUDENT_INDIVIDUAL scope, STUDENT_SAFE projection, and exact authenticated actor/student UUID. It derives the university from the authoritative student profile through the existing P7 persistence adapter and rejects payload university, actor, or student spoofing.

append_advisor accepts only ADVISOR_FORMAL_GUIDANCE with ACADEMIC_ADVISOR actor, LEDGER_REQUIRED materiality, STUDENT_INDIVIDUAL scope, and ADVISOR_SAFE profile. It invokes the existing P7 AdvisorAuthorizationService before appending; therefore active advisor membership, authoritative student university, and exact active assignment are all required. System/scheduler/analyst/auditor append entrypoints are not exposed in this slice.

For a superseding entry, the service loads the bounded, same-student/same-university predecessor, verifies its canonical integrity hash, compares the supplied previous hash and complete subject scope, then delegates final concurrent one-successor enforcement to the Slice 2A database constraint.

### Safe retrieval and evidence

get_student_trace authenticates the requester, derives the requester's authoritative university, and performs only an exact owner/tenant query. get_advisor_trace re-runs the P7 advisor predicate before every lookup, so assignment revocation or inactive membership immediately removes access. Institutional individual trace retrieval has an explicit denial method; no analyst or system/audit viewer permission is introduced.

Returned values are allowlisted DecisionTraceSafeView objects, not database rows. Student and advisor metadata use the existing Slice 1 redaction projection selected by verified viewer authority. Evidence is included only after the parent is authorized, and only exposes source, identifier, and version. Locator and URI are deliberately omitted because the current contracts do not approve their individual-viewer disclosure. No independent evidence retrieval operation exists.

### Slice 2B verification evidence

| Command | Result |
| --- | --- |
| apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_decision_trace_persistence.py -q | **8 passed, 0 failed, 0 skipped in 0.21s** |
| apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_decision_trace_persistence_local_supabase.py apps/api/tests/test_decision_trace_persistence_service_local_supabase.py -q -rs | **13 passed, 0 failed, 0 skipped in 9.03s** |

The unit suite uses a controlled httpx.MockTransport storage double to prove that a persisted payload altered after hashing fails closed; it does not disable a local database trigger. The local suite uses synthetic local Auth users, profiles, P7 memberships, and assignments. It verifies canonical Unicode/microsecond/evidence round-trip, duplicate identity, forged/correctly-shaped hash rejection, payload tampering, actor/student/university spoof rejection, direct evidence mutation and RPC denial, anonymous raw access denial, assigned/unassigned/cross-tenant/revoked/inactive advisor cases, analyst denial, canonical atomic rollback, and canonical supersession concurrency.

### Slice 2B deferred/limitations

- There are no HTTP routes, frontend features, automatic integration with registration workflows, replay execution, retention/deletion jobs, or production deployment.
- subject_scope_id remains an opaque trace field because no approved canonical subject-ID syntax exists; it is never used as proof of student authority. Student UUID plus authoritative profile university establish access.
- PostgreSQL owner/superuser bypass and legal retention/erasure remain outside the append-only trigger guarantee.
- Production service credentials, production RLS acceptance, legal/institutional approval, and P8 Slice 2 overall acceptance remain **NOT VERIFIED / NOT ACCEPTED**.

## Prompt 10 â€” Slice 2B security hardening before HTTP exposure

**Status:** LOCAL-ONLY HARDENING IMPLEMENTED â€” P8 Slice 2 remains NOT ACCEPTED.

### Confirmed boundary defects and correction

The prior service proved a supplied Slice 1 hash but accepted a complete caller-supplied
`CanonicalLedgerEntry` through `append_student`/`append_advisor`. A valid SHA-256 hash
establishes payload integrity only; it does not prove that a deterministic academic
workflow produced the outcome, engine, provenance, or evidence assertions. No existing
approved P6 deterministic-result-to-ledger adapter was found, and this task does not
integrate Mock Registration automatically. Consequently both user-submitted append
methods now fail closed with `UNSUPPORTED_APPEND_AUTHORITY` and make no repository call.
The repository remains an internal, server-key adapter for a future explicitly approved
deterministic-event adapter; it is not an HTTP or client boundary.

Service read methods now accept only `app.core.auth.CurrentUser`, the value produced by
the existing `get_current_user` Supabase Auth dependency. A raw UUID/string is rejected
with `AUTH_REQUIRED`; UUID parsing is not token verification. A future route must obtain
the principal exclusively from `get_current_user`, must not accept a principal ID from
body/query/header input, and must keep the service-role key backend-only.

### Viewer visibility and conservative projections

The stored entry classification is now checked before projection. A student may view only
an entry stored as `STUDENT_SAFE`. An already P7-authorized advisor may view
`STUDENT_SAFE` or `ADVISOR_SAFE`; all other/ambiguous profiles fail closed. P7 active
membership, exact active assignment, and same-university checks still run before advisor
lookup, so revoked/inactive authority is denied at each request. Analysts retain no
individual trace interface.

`RedactedTraceMetadata` and `SafeEvidenceReference` were not sufficient disclosure
contracts: their opaque/free-form strings can carry private data. The local safe view is
therefore reduced to stable metadata only: ledger identity, finite decision type, finite
decision status, creation timestamp, and finite replay status. It intentionally omits
student ID, university ID, subject scope ID, engine/policy/source versions, outcome,
provenance, limitations, and all evidence. No evidence locator, URI, source, identifier,
version, cardinality, or independent evidence interface is exposed pending an approved
field-level disclosure policy.

### Evidence bound and Unicode interoperability

The repository rejects append inputs with more than 1,000 evidence references. Reads ask
for 1,001 rows and fail with `PERSISTENCE_INTEGRITY_FAILURE` if an extra row exists, so a
server-side limit cannot silently return a trusted partial historical entry. Python Slice
1 canonicalization orders evidence by Unicode code point. PostgreSQL is never asked to
sort evidence: the database stores canonical `evidence_position`, and reads order solely
by that position. Unit and real Local Supabase tests cover `a`, `é`, `漢`, and `😀` and
verify exact canonical payload round-trip. This evidence applies to the tested UTF-8/
PostgreSQL local stack only; it is not a universal cross-driver/collation guarantee.

### Prompt 10 test evidence (checkpoint)

| Command | Result |
| --- | --- |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_decision_trace_persistence.py -q` | **11 passed, 0 failed, 0 skipped in 0.66s** |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_decision_trace_persistence_local_supabase.py apps/api/tests/test_decision_trace_persistence_service_local_supabase.py -q -rs` with process-only isolated local variables | **14 passed, 0 failed, 0 skipped in 13.99s** |

The first local test command initially failed because `supabase status -o env` emits
quoted values and the process wrapper passed the quotes into the URL. The wrapper was
corrected to trim quotes only in process memory; no project configuration, environment
file, database schema, or credential storage changed. Docker containers showed the API,
Auth, and PostgreSQL services running. Full regression results are recorded in the
permanent progress log after its completion.

**Completed full regression:** with local-only values generated by
`npx --yes supabase@2.117.0 status -o env`, quote-trimmed in process memory, and the
existing application Supabase settings plus a local study-plan ID supplied to the test
process only, `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests -q -rs
--junitxml=<temporary-outside-worktree>` recorded **1397 passed, 0 failed, 0 errors,
0 skipped in 632.802s**. The temporary JUnit report does not encode pytest's terminal
warning summary, so this run does not claim a warning count; the earlier baseline's two
deprecation warnings are historical evidence only. No skip marker was changed.

### Remaining gates

- **BLOCKED / requires approval:** a concrete trusted deterministic workflow adapter and
  its result-to-ledger mapping. User requests remain distinct from deterministic outcomes.
- **DEFERRED:** HTTP routes, frontend, user-facing evidence disclosure, replay execution,
  retention/erasure, system append actors, and workflow integration.
- **NOT VERIFIED:** production identities/credentials, production database security,
  privileged database-administrator resistance, legal/institutional approvals, and P8
  Slice 2 overall acceptance.

## Prompt 13B.1 -- mapper-only trusted source boundary (2026-09-25)

**IMPLEMENTED locally:** `p6_outbox_mapper.py` is an internal deterministic mapping
layer only. It validates a typed P6 revision/outbox/snapshot projection before using the
sole Slice 1 canonical factory and integrity verifier. It cannot append or retrieve a P8
ledger record, and `append_student`/`append_advisor` remain fail-closed with
`UNSUPPORTED_APPEND_AUTHORITY`.

**VERIFIED locally:** unit coverage rejects legacy, missing, mismatched, malformed,
unsupported-lifecycle/status/actor/contract projections and proves source/evidence/hash
stability. A real local P6 submit maps without P8 ledger/evidence insertion or a pending
outbox state transition.

**BLOCKED:** the outbox has no service-role table `SELECT` grant and no approved read
RPC. This implementation deliberately does not evade that boundary. A later processor
requires a separately approved bounded service-only projection RPC and adversarial
grant/scope tests. No worker, retry, lease, HTTP endpoint, frontend change, or P8 append
is implemented here.
