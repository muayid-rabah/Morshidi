STATUS: DRAFT — AWAITING HUMAN APPROVAL

# P8 trusted adapter and durable outbox design gate

## 1. Scope and status

This is a source-inspection and design document. It does **not** implement an adapter,
an outbox, a migration, an HTTP route, or a database change. It records the approved
local design directions and the remaining decisions needed before implementation.

**Approved local direction:** the first candidate is the non-binding
`MOCK_REGISTRATION_SUBMIT` event; it documents a persisted P6 declared intent, never
official registration, enrollment, academic approval, or an academic-state mutation.
The proposed ledger identity is `persisted.revision_id`; the initial replay state is
`NOT_REPLAYABLE`; the preferred durability pattern is a transactional P6 outbox followed
by a trusted P8 append.

**Existing verified invariant:** AI EXPLAINS — DETERMINISTIC RULES DECIDE. The ledger is
an append-only explanatory sidecar. Its SHA-256 value establishes canonical-payload
integrity only; it is not authorization, provenance proof, or a digital signature.

**Not approved by this draft:** production deployment; a legal retention/erasure policy;
an evidence taxonomy; a new provenance enum; a public append endpoint; generic system,
scheduler, analyst, or advisor append authority; or any change to the P6/P8 applied
migrations.

## 2. Actual source and transaction analysis

### 2.1 Selected P6 workflow

The concrete source path is:

`POST /api/v1/me/mock-registration/revisions`
→ `app.api.routes.mock_registration.submit_intent`
→ `MockRegistrationStudentService.submit`
→ `validate_registration_intent`
→ `SupabaseMockRegistrationRepository.persist_revision`
→ `public.persist_mock_registration_revision`.

The route gets `CurrentUser` from `get_current_user`; the current service itself accepts
an `owner: str`, so a future internal adapter must keep the verified route principal or
a derived trusted execution context. UUID syntax is not authentication.

`MockRegistrationStudentService.submit` builds a `RegistrationIntent` from an
owner-derived `AcademicContextSnapshot`, validates it with the deterministic P6 engine,
fails invalid intent before persistence, rechecks `snapshot_token` for an academic-state
race, then persists a `PersistRevisionCommand`. It reloads the exact
`PersistedIntentRevision` and returns a limited `StudentIntentResult`. The result is
explicitly non-binding: no seat, offering, approval, enrollment, or official university
action is guaranteed.

### 2.2 `persist_mock_registration_revision` transaction boundary

The exact function is in
`supabase/migrations/20260922134625_add_mock_registration_persistence_security.sql`,
`public.persist_mock_registration_revision(...)` (starting near line 308). It is
`LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''`; application objects are schema
qualified. Its execution grant is revoked from `PUBLIC`, `anon`, and `authenticated`,
then granted only to `service_role`.

Within one PostgreSQL statement/transaction, the function:

1. validates expected revision, finite lifecycle/validation values, SHA-256-shaped P6
   content fingerprint, and canonical course arrays;
2. acquires a transaction-scoped advisory lock keyed by owner, university, major, plan,
   plan version, and target period;
3. checks the next revision slot. If the same slot has the same fingerprint it returns
   `IDEMPOTENT_REPLAY`; otherwise it returns a persistence/revision conflict;
4. checks the expected current revision and target-period expiry;
5. inserts one immutable `mock_registration_intent_revisions` header and its normalized,
   canonical-order child `mock_registration_intent_courses`; and
6. returns `INSERTED`, the generated revision UUID, revision number, and fingerprint.

Any raised exception, including a future outbox insert failure, rolls back the work of
this function call. Existing immutable-history triggers reject ordinary revision/course
updates and deletes. The tables have RLS enabled; direct mutation grants are revoked; the
function is the current service-only write boundary.

### 2.3 What is and is not atomic today

The P6 RPC is atomic for its header and course inserts. The existing P8
`public.append_decision_trace_ledger(jsonb, jsonb)` is a distinct RPC/transaction.
Calling it after P6 from Python, even with `try/except`, cannot atomically commit or roll
back the P6 revision with the P8 ledger entry. A successful P6 revision can therefore
exist without a trace after a process/network/P8 failure. Conversely, P6 cannot be rolled
back after its RPC commits. This is the durable-recovery gap.

## 3. Feasibility and smallest additive change

### Finding: a transactional outbox is feasible in principle

A narrowly scoped P8 outbox insert can be placed in the same function immediately after
the revision and course inserts and before its final `RETURN QUERY`. The function already
has the trusted P6 parameters, generated `inserted_id`, transaction lock, and complete
rollback semantics. An additive migration would create the outbox table and amend the
function signature/body with `CREATE OR REPLACE FUNCTION`; it would not rewrite the
historical P6 revision rows or academic engine.

This is only feasible after human approval of the frozen adapter-input snapshot and the
field mappings below. It changes P6 availability semantics: a constraint or trigger
failure in the required outbox insert would cause the P6 submission to fail rather than
commit an untracked revision. The behavior is a deliberate durability trade-off requiring
approval; it must not be silently introduced.

### Minimum proposed implementation slice (not implemented)

One future additive migration would:

- create `public.decision_trace_outbox` with no client write/read privileges;
- add an immutable, versioned adapter-input snapshot to each new `INSERTED` P6 revision
  in `persist_mock_registration_revision`;
- ensure an `IDEMPOTENT_REPLAY` finds the existing one-to-one outbox event rather than
  making another one; and
- add narrowly scoped service-only atomic claim/complete/retry database operations with
  fixed `search_path`, schema-qualified names, explicit argument validation, and no
  `PUBLIC` EXECUTE.

The P8 ledger migration, `decision_trace_ledger`, `decision_trace_evidence`, append RPC,
immutability triggers, RLS, and grants must remain unchanged. No existing P6 request or
academic outcome is reinterpreted.

## 4. Proposed durable-event contract

### 4.1 Proposed `decision_trace_outbox` fields

The following table is a design proposal, not SQL. Names/types and finite values require
review against the existing migration naming and database contract.

| Field | Proposed meaning and source | Required property |
| --- | --- | --- |
| `event_id` | Stable P8 append/idempotency identity; proposed equal to P6 `revision_id` | UUID primary key; never caller supplied |
| `revision_id` | `mock_registration_intent_revisions.id` | Unique FK, `ON DELETE RESTRICT`; one event per P6 revision |
| `owner_user_id`, `university_id` | P6 persisted revision | Duplicated scope for bounded claim/verification; must equal snapshot and parent revision |
| `major_id`, `study_plan_id`, `study_plan_version`, `target_period_id`, `revision` | P6 persisted revision | Frozen P6 scope/version context, never trusted from worker input |
| `event_type` | Fixed `MOCK_REGISTRATION_SUBMIT` for this adapter only | Check constraint/finite allowlist |
| `event_contract_version` | New approved adapter-contract version, not a client value | Nonblank, immutable; literal needs human approval |
| `adapter_input_snapshot` | Versioned, minimum immutable P6-derived facts needed to build the P8 entry | Generated inside P6 RPC; never a supplied P8 envelope |
| `state` | `PENDING`, leased `PROCESSING`, `COMPLETED`, or `PERMANENT_FAILURE` | Finite state machine; immutable completed event payload |
| `attempt_count` | Incremented atomically on each lease claim | Nonnegative, bounded operationally |
| `next_attempt_at` | Earliest retry time | Non-null for retryable work; server-generated |
| `lease_owner`, `lease_expires_at`, `processing_started_at` | Short-lived worker claim | Required only while processing; no client-provided principal trust |
| `completed_at`, `ledger_integrity_hash` | Completion evidence after verified P8 append | Completion only after exact ledger/hash verification |
| `last_error_class`, `last_error_at` | Finite operational category and timestamp | No credentials, raw HTTP body, token, or student content |
| `created_at`, `updated_at` | Database timestamps | Audit/debug only; no historical P6 or P8 mutation |

Suggested finite error classes are `TRANSIENT_P8_UNAVAILABLE`, `P8_DUPLICATE_MATCHED`,
`P8_DUPLICATE_MISMATCH`, `SOURCE_INTEGRITY_FAILURE`, and `CONTRACT_FAILURE`. They are
operational design labels, not currently approved database enums. Store a bounded safe
code, not a raw exception string, because database/RPC error text can be sensitive.

### 4.2 Snapshot versus references

**Recommendation — proposed, awaiting approval:** store an immutable, versioned minimum
adapter-input snapshot *and* the stable `revision_id` reference. A references-only
outbox is inadequate for a durable historical trace:

- P6 revision/course rows are protected from ordinary mutation, but the adapter also
  depends on historic policy/catalog/progress versions and P6 validation facts;
- a later code deployment or source/catalog retention change can prevent faithful
  reconstruction from live state;
- the current P6 rows do not already contain typed P8 `EvidenceReference` values, an
  approved P8 provenance mapping, or a complete previously approved adapter contract;
- rebuilding from current `AcademicContextSnapshot` risks recording a changed source
  rather than the original persisted intent.

The snapshot must contain only the server-produced P6 facts necessary for the eventual
canonical P8 construction: persisted header values, canonical selected courses/order,
validated status/reasons, source/version facts, P6 limitations, and an approved evidence
descriptor set. It must not contain a client-produced `CanonicalLedgerEntry`, client hash,
raw prompt, credential, free-form error, or unnecessary student academic-detail payload.
If the approved evidence descriptor set is not available, the worker must classify that
event as a permanent contract failure rather than inventing evidence later.

The snapshot itself should be immutable after insertion. Retention/erasure treatment of
that durable copy is still an open legal/institutional decision.

## 5. Exact P6-to-P8 field mapping gate

All source fields below are inspected from
`MockRegistrationStudentService.submit`, `PersistRevisionCommand`,
`PersistedIntentRevision`, and the P8 `CanonicalLedgerEntry`/registries. “Compatible”
means the value can satisfy current Slice 1/P8 shape rules; it does not make an unapproved
semantic mapping approved.

| Ledger concept | Exact current source / proposed transformation | Semantics and validation | Stability/retry and status |
| --- | --- | --- | --- |
| `ledger_entry_id` | `str(persisted.revision_id)` / outbox `event_id` | P6 generated immutable UUID; compare with `PersistRevisionResult.revision_id` and stored `revision_id` | Stable. **APPROVED LOCAL DIRECTION; exact-match test required.** |
| Decision type/materiality | Fixed `DecisionType.MOCK_REGISTRATION_SUBMIT`; `materiality_for(...)` | Existing finite registry maps it to `LEDGER_REQUIRED` | Stable and **VERIFIED EXISTING CONTRACT**. |
| Actor | Fixed `ActorClass.STUDENT`, actor id = persisted owner | Verified route `CurrentUser`, snapshot owner, P6 command, persisted owner, and outbox owner must agree | Stable; new adapter assertion required. |
| Student/university scope | `PersistedIntentRevision.owner_user_id` and `.university_id`; proposed `subject_scope_id = owner_user_id`, type `STUDENT_INDIVIDUAL` | Existing individual scope requires `student_user_id`; target period and snapshot must match university | Sources verified; subject-ID convention remains **HUMAN APPROVAL REQUIRED**. |
| `source_engine` | There is no existing P8-approved identifier. Candidate must identify the concrete deterministic P6 submit/validation path, not a user claim | Must be a controlled internal constant selected by the adapter | **MISSING SOURCE INFORMATION / approval required.** |
| `source_engine_version` | Current actual P6 values include `MOCK_REGISTRATION_CONTRACT_VERSION = "1.0"` and persisted `p6_contract_version = "1.0"`; neither is explicitly an engine-version contract | Do not relabel contract version as engine version without approval | Stable once frozen; **HUMAN APPROVAL REQUIRED**. |
| `policy_version` | Persisted `phase5_policy_version = "phase5:v1"` and `phase6_policy_version = "phase6:v1"`; P6 contract is separately `"1.0"` | No existing single P8 policy-version composition contract | Snapshot must freeze chosen value; **HUMAN APPROVAL REQUIRED**. |
| `source_versions` | Persisted catalog/prerequisite arrays, `progress_state_version`, target-period source version, and relevant P5/P6 version fields | Slice 1 needs a nonempty normalized tuple. Prefix/namespacing would be a new contract and must avoid collisions | P6 values stable per immutable revision; exact representation **requires approval**. |
| `input_state_reference` | `persisted.progress_state_reference` | Optional opaque historical source reference; do not expose in safe view | Stable P6 field; retrieval remains restricted. |
| `scenario_id` | `None` | Required by current validation if `AUTHORITATIVE_TRANSACTION` is chosen | Stable and **VERIFIED**. |
| `decision_status` | P6 persists only `VALID` or `REVIEW_REQUIRED`; candidate mapping `VALID -> VALIDATED`, `REVIEW_REQUIRED -> FLAGGED_REVIEW` | A ledger trace must describe P6 validation, not official approval | Values fit existing enum; mapping is **HUMAN APPROVAL REQUIRED**. |
| `outcome_reference` | Candidate `persisted.content_fingerprint` | Existing 64-hex P6 fingerprint identifies the persisted canonical intent/result inputs; it is not enrollment status | Stable; P8 outcome-reference semantics need **HUMAN APPROVAL**. |
| Evidence | P6 has revision ID, plan/period IDs and versions, canonical course IDs/codes/order, and reason codes, but no typed P8 `EvidenceReference` taxonomy | Never fabricate source/identifier/version/locator/URI. Snapshot needs approved evidence descriptors generated from actual P6 artifacts | **BLOCKED pending evidence contract.** |
| `domain_trace_reference` | No P6-to-P8 format exists; `intent_id` is available but unapproved for this P8 field | `None` is possible only if policy accepts it | **MISSING SOURCE INFORMATION.** |
| `provenance_class` | Current enums offer `AUTHORITATIVE_TRANSACTION`, `VERIFIED_REVALIDATION`, `PERIOD_SNAPSHOT`, `GOVERNED_ASSESSMENT` | `AUTHORITATIVE_TRANSACTION` can only mean an authoritative P6 persistence transaction, never official enrollment. If that wording is not approved, current enum cannot represent declared intent honestly | **HUMAN APPROVAL REQUIRED.** Alternative needs a Slice 1 enum + P8 DB constraint change in a separately approved migration. |
| `created_at` | `persisted.created_at` | Database UTC timestamp, not client clock | Stable / **VERIFIED source**. |
| Redaction | Fixed `STUDENT_SAFE` | Existing hardening lets student view only stored student-safe entries; advisor rechecks P7 authority | Existing local boundary; disclosure policy remains limited. |
| Supersession | `previous_entry_hash = None`, `supersedes_entry_id = None` | Later P6 revision does not automatically mean P8 correction/supersession | Stable / fail closed. |
| `replay_status` | Fixed `ReplayStatus.NOT_REPLAYABLE` | Approved local initial direction; historic engine/catalog reconstruction is not guaranteed | **APPROVED LOCAL DIRECTION**. |
| Limitations | `ValidatedIntent.limitations` plus P6 `LIMITATIONS`, frozen in snapshot | Only deterministic/server-produced strings; no user free text. Safe projection currently omits limitations | Current sources exist; exact combined set/order must be frozen and tested. |
| Schema/hash versions | `create_canonical_ledger_entry` defaults (`1.0`) | Reuse Slice 1 factory/canonicalization only | **VERIFIED EXISTING CONTRACT.** |

## 6. Proposed trusted processor

This is a future internal service/process, not an HTTP handler and not a generic worker
authority. It may be invoked only by a separately authorized server-side operational
entrypoint. It must not revive `DecisionTraceService.append_student` or `append_advisor`,
which intentionally reject client-supplied envelopes with
`UNSUPPORTED_APPEND_AUTHORITY`.

1. Atomically claim a small bounded batch of `PENDING` events, or expired leases, through
   a server-only database operation. Use `FOR UPDATE SKIP LOCKED` or equivalent in one
   function/transaction; set lease owner, `PROCESSING`, expiry, start time, and increment
   attempt count atomically. A Python select-then-update is insufficient.
2. Load the outbox snapshot and bounded P6 revision/course rows by exact revision ID.
   Verify revision ID, owner, university, major, plan, period, revision number,
   content fingerprint, canonical course ordering, and all duplicated snapshot values.
   A changed/missing source is an integrity/contract failure, never a live-state rewrite.
3. Build a fresh `CanonicalLedgerEntry` solely with the Slice 1
   `create_canonical_ledger_entry` factory from approved snapshot mappings. Do not take a
   hash, actor class, provenance, outcome, or evidence from a request.
4. Reuse the existing P8 repository append RPC. Its atomic parent/evidence append and DB
   immutability remain the ledger boundary. Verify the returned identity is `event_id`.
5. If the P8 append reports duplicate identity, load only that exact entry in service
   scope, reconstruct it, and require canonical payload *and* hash equality. A matching
   duplicate is idempotent completion; a mismatch is a permanent integrity failure.
6. Mark `COMPLETED` only after the append/deduplication verification succeeds, guarded by
   the current lease token. Record only the verified hash and completion timestamp.
7. For transient transport/P8 availability failure, release/expire the lease and set an
   exponential bounded `next_attempt_at` with a finite safe error class. For mapping,
   source-integrity, or duplicate-mismatch failure, set `PERMANENT_FAILURE`; do not retry
   until separately authorized human remediation.

The worker is at-least-once with an exactly-once *ledger effect* only through deterministic
ledger identity and exact duplicate comparison. It cannot promise an atomic P6+P8 commit.

## 7. Crash-recovery matrix

| Boundary | Durable state after crash | Recovery rule | Required proof |
| --- | --- | --- |
| Before P6 transaction commit | No revision and no outbox row | No event exists; P6 retry follows existing behavior | Local Supabase rollback test |
| After P6 revision/outbox commit, before claim | Immutable revision and `PENDING` event | Processor later claims it | Local integration test |
| After claim, before P8 append | Leased `PROCESSING` event | Lease expires; another worker claims/retries | Crash/expired-lease test |
| During P8 atomic append | RPC transaction either commits parent+evidence or rolls back | Retry after lease; no partial evidence | P8 atomicity integration test |
| After P8 append, before outbox completion | Ledger exists, outbox lease remains | Retry sees same event ID, requires exact payload/hash duplicate, marks complete | Post-append crash test |
| During completion update | Ledger exists; completion state may be unfinished | Lease recovery and exact duplicate logic | Conditional completion test |
| Duplicate workers | Only one valid lease can process | `SKIP LOCKED`/lease conditional updates; non-holder cannot complete | Concurrent claim integration test |
| P6 idempotent replay | Existing revision/outbox row | Never make a second outbox event or ledger row | Replay uniqueness test |

## 8. Security boundaries

- P6 authenticated request identity must originate from `get_current_user`; a future
  adapter receives a verified principal/internal execution context, never a body/query
  UUID.
- The P6 transaction derives owner, university, plan, and source facts from authoritative
  context and persists them. The worker rechecks all scope equality; it cannot accept a
  forged owner, university, actor, evidence, provenance, or hash.
- The outbox has no direct client reads/writes. RLS, table grants, and any claim/complete
  RPC must deny `anon`, `authenticated`, and `PUBLIC`; service-role bypass is limited by
  server-side code and fixed database functions. `SECURITY DEFINER` functions require a
  safe fixed `search_path`, qualified objects, validated typed arguments, and restricted
  `EXECUTE` grants.
- No raw P8 ledger/evidence row is returned. Existing student/advisor retrieval and
  visibility hardening remain unchanged; no analyst/auditor individual read, no evidence
  endpoint, and no direct client append is added.
- P6 declared intent is not an academic-state write. The outbox and P8 append must not
  call enrollment, course-attempt, plan, progress, recommendation, or advisor queue
  mutation paths.
- The P8 evidence maximum and canonical ordering/Unicode round-trip protections remain
  applicable. A future snapshot larger than the existing repository bound must fail closed
  rather than append a partial record.

## 9. Proposed executable acceptance tests

All tests are proposals and **not evidence of passing behavior**.

| ID | Scenario | Type | Key assertion |
| --- | --- | --- | --- |
| OUTBOX-01 | Successful P6 submit creates one revision and one durable event in the same DB transaction | Local Supabase integration | Both commit or neither does |
| OUTBOX-02 | P6 validation/constraint rollback leaves no outbox event | Local Supabase integration | No orphan event |
| OUTBOX-03 | Identical P6 replay returns existing revision/event | Local Supabase integration | No duplicate row/ledger ID |
| OUTBOX-04 | P8 temporary failure leaves retryable durable event | Unit + Local Supabase integration | P6 revision remains; event remains pending/retryable |
| OUTBOX-05 | Worker crashes before append | Local Supabase integration | Lease expiry permits safe retry |
| OUTBOX-06 | Worker crashes after append before completion | Local Supabase integration | Exact duplicate verification completes without a second trace |
| OUTBOX-07 | Concurrent workers claim one event | Local Supabase integration | Single lease/effect |
| OUTBOX-08 | Same ledger ID with matching canonical payload/hash | Local Supabase integration | Idempotent completion only |
| OUTBOX-09 | Same ledger ID with different payload/hash | Local Supabase integration | Permanent integrity failure, no overwrite |
| OUTBOX-10 | Changed/missing P6 revision/source or fingerprint | Unit + Local Supabase integration | Fail closed, classify source integrity failure |
| OUTBOX-11 | Forged principal, owner, university, actor, or scope | Unit + existing-workflow integration | Adapter refuses before append |
| OUTBOX-12 | Unsupported provenance/evidence/mapping | Unit | No fabricated ledger envelope |
| OUTBOX-13 | `NOT_REPLAYABLE` classification | Unit | Entry uses approved replay status and no replay endpoint |
| OUTBOX-14 | P8 RLS, grants, append-RPC denial | Local Supabase integration | anon/authenticated cannot use raw outbox/P8 writes |
| OUTBOX-15 | Real factory parent/evidence round trip | Local Supabase integration | Canonical payload, order, hash all equal |
| OUTBOX-16 | No academic state mutation from outbox/worker | Existing workflow + Local Supabase integration | Only intent/outbox/ledger rows change |
| OUTBOX-17 | Source-version and snapshot mismatch | Unit + Local Supabase integration | No append from changed/live source |
| OUTBOX-18 | Retry exhaustion/permanent class | Unit | Safe bounded error, no secret/raw error persisted |

Existing P6/P7/P8 tests are useful prerequisites but do not prove this outbox design until
these tests execute against the isolated local database.

## 10. Remaining decisions requiring human approval

1. Approve whether required outbox insertion may cause the otherwise-valid P6 submit
   transaction to fail, in exchange for no committed untracked revision.
2. Approve the immutable minimum adapter-input snapshot and retention/erasure treatment.
3. Approve a controlled P8 `source_engine` name and the distinction between engine,
   P5/P6 policy, P6 contract, and source-version values.
4. Approve the `VALID`/`REVIEW_REQUIRED` to P8 status mapping and the semantics of
   `outcome_reference = content_fingerprint`.
5. Approve an evidence-reference taxonomy or explicitly defer this event until one exists.
6. Decide whether `AUTHORITATIVE_TRANSACTION` may mean “authoritative persistence of a
   non-binding declared intent.” If not, approve a separately scoped P8 enum/DB constraint
   expansion; do not misuse the existing enum.
7. Approve the P8 student subject-scope ID convention and safe disclosure implications.
8. Approve finite outbox state/error codes, retry/backoff/lease bounds, operational owner,
   and permanent-failure review process.
9. Approve the new service-only claim/complete/retry RPC/grant design and local-only
   migration scope before implementation.

## 11. Exact next implementation slices after approval

1. **P6 transactional outbox foundation:** one reviewed additive migration, typed P6
   outbox models/repository support, exact rollback/idempotency/RLS tests. No P8 worker.
2. **Trusted adapter processor:** internal-only processor, frozen approved mapping,
   deterministic P8 factory append, exact duplicate verification, lease/retry tests.
3. **End-to-end local acceptance:** real authenticated P6 submit → durable event → P8
   append plus adversarial and crash-recovery tests; retain P8 safe retrieval boundaries.

P8 Runtime Slice 2 remains **NOT ACCEPTED** until those approved slices and their real
local database security/integrity tests complete. No production deployment is authorized.
