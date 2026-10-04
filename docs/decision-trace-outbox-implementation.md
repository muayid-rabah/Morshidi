# P6 transactional Decision Trace outbox foundation

**Status:** IMPLEMENTED AND VERIFIED LOCALLY — NOT PRODUCTION-APPROVED

## Scope

This document describes the actual local-only implementation in
`supabase/migrations/20260925103000_add_p6_decision_trace_outbox.sql`.
It creates durable pending source events for a future trusted P6-to-P8 adapter.
It does **not** implement an adapter, a P8 ledger append, a processor, a worker,
an HTTP route, a frontend feature, an academic decision, official registration,
enrollment, seat reservation, academic approval, or a change in academic standing.

The only event produced by this foundation is `MOCK_REGISTRATION_SUBMIT`. It represents
the persisted non-binding P6 declared intent created by a successful `SUBMITTED` P6
revision. P6 withdrawal revisions are outside this first event scope and receive no
outbox event.

## Actual migration and transaction boundary

The migration is additive and is later than the nine prior migrations. It uses
`CREATE OR REPLACE FUNCTION` with the exact pre-existing
`public.persist_mock_registration_revision` signature and return table:

```text
(result_kind text, persisted_revision_id uuid,
 persisted_revision integer, persisted_fingerprint text)
```

The redefined function remains `SECURITY DEFINER` with `SET search_path = ''`. It keeps
the P6 request validation, advisory transaction lock keyed by owner/university/major/plan/
plan-version/period, revision-slot idempotency, conflict behavior, target-period expiry
check, normalized revision/course inserts, and service-role-only execution grant.

For a newly `INSERTED` `SUBMITTED` revision, it now performs these writes in the same
PostgreSQL transaction:

1. inserts the immutable P6 revision header;
2. inserts its canonical-order normalized course rows; and
3. inserts one `decision_trace_outbox` event whose `event_id` equals the generated P6
   revision identity.

An outbox constraint/trigger failure raises from the same function call and rolls back
the revision and courses. This is P6/outbox atomicity only; P8 ledger append remains a
separate, deliberately unimplemented future operation.

## Actual outbox table

`public.decision_trace_outbox` stores:

- `event_id` UUID primary key and `revision_id` unique restrictive FK to the P6 revision;
  a check enforces `event_id = revision_id`.
- authoritative P6 owner, university, major, plan/version, target-period, and revision
  scope copied by the trusted P6 function.
- fixed `event_type = MOCK_REGISTRATION_SUBMIT` and
  `snapshot_contract_version = 1.0`.
- `source_snapshot` JSONB with structural/key and identity/scope checks.
- reserved operational fields: finite `processing_state`, `attempt_count`, next-attempt
  time, lease fields, completion timestamp/hash, and a finite sanitized error class.
- database-generated creation/update timestamps and a pending-event index.

The table has `ON DELETE RESTRICT` parent references and no cascade path. An immutable
source trigger rejects updates to identity, revision, scope, event type, snapshot
contract, snapshot, and creation time. A separate trigger rejects delete. Operational
columns are intentionally reserved for a separately approved processor; this foundation
grants no broad update authority and implements no claim/complete/retry operation.

PostgreSQL owners/superusers can alter schema, triggers, or privileges. The trigger is
not a guarantee against privileged administrators, and legal retention/erasure remains
unapproved.

## Snapshot contract `1.0`

The immutable `source_snapshot` is built by the database function from trusted P6
parameters and the inserted revision/course rows. Its required fields are revision and
intent IDs; owner/university/major/plan/period/revision scope; lifecycle and validation
status; content fingerprint; intent/source/policy/version values already persisted by P6;
optional progress-state reference; transparency notice version; actor class; database
creation time; and canonical ordered course identity/code/selection-order entries.

It contains no caller-provided P8 `CanonicalLedgerEntry`, integrity hash, P8 provenance
classification, P8 decision outcome, P8 evidence references, raw prompt, credential, or
token. It also deliberately does not freeze the still-unapproved P8 evidence taxonomy,
source-engine mapping, policy-version mapping, status mapping, outcome semantics, or
provenance selection. Consequently it is an immutable P6 event source, not a complete
P8 ledger envelope.

## Idempotency and historical compatibility

The existing P6 idempotent replay behavior is retained. A replay with the same revision
slot and content fingerprint returns the existing revision; it creates neither a second
P6 revision nor a second outbox event. The unique `revision_id` and `event_id = revision_id`
constraints enforce one event per newly inserted submit revision.

Historical revisions created before this migration have no event. Replaying one returns
the legacy `IDEMPOTENT_REPLAY` result without backfilling from current catalog, progress,
or policy data. This behavior is deliberate: no historical source facts are invented.

## RLS, grants, and service boundary

RLS is enabled on the outbox. `PUBLIC`, `anon`, `authenticated`, and `service_role` have
no direct table `SELECT`, `INSERT`, `UPDATE`, or `DELETE` grant. No outbox RPC or public
processor endpoint exists. Existing P6 persistence remains accessible only through the
restricted service-role `persist_mock_registration_revision` RPC; its function signature,
owner, fixed search path, and EXECUTE restriction were verified locally after migration.

The absence of an outbox table grant is intentional. A future server-side processor needs
a separately reviewed least-privilege claim/complete design; granting service-role direct
updates early would widen authority without an approved processor.

## Local verification

The migration was applied only to the isolated local Supabase stack with:

```text
npx --yes supabase@2.117.0 migration up --local
```

The local API was `127.0.0.1:54321` and PostgreSQL was `127.0.0.1:54322`; no hosted
project was linked, pushed, or reset. Local migration history contains the ten expected
rows ending in `20260925103000`.

Initial focused verification was:

| Command | Result |
| --- | --- |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_mock_registration_outbox_local_supabase.py -q -rs` | **2 passed, 0 failed, 0 skipped in 3.84s** |
| Same focused outbox command after Prompt 13A.1 review assertions | **2 passed, 0 failed, 0 skipped in 3.64s** |
| P6 persistence plus reviewed outbox suite | **3 passed, 0 failed, 0 skipped in 5.09s** |
| Slice 1 / 2A / 2B focused suite after review | **65 passed, 0 failed, 0 skipped in 10.33s** |
| Full backend regression after review | **1399 passed, 0 failed, 0 skipped, 2 warnings in 513.14s (8:33)** |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_mock_registration_persistence_local_supabase.py apps/api/tests/test_mock_registration_outbox_local_supabase.py -q -rs` | **3 passed, 0 failed, 0 skipped in 4.65s** |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_decision_trace.py apps/api/tests/test_decision_trace_persistence_local_supabase.py apps/api/tests/test_decision_trace_persistence.py apps/api/tests/test_decision_trace_persistence_service_local_supabase.py -q -rs` | **65 passed, 0 failed, 0 skipped in 11.58s** |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests -q -rs` | **1399 passed, 0 failed, 0 skipped, 2 warnings in 511.87s (8:31)** |

The tests use synthetic local Auth users and target periods. They verify atomic
header/course/outbox insert; a deliberate temporary local-only outbox `BEFORE INSERT`
test trigger causes a full rollback and is removed in `finally`; idempotent and concurrent
same-fingerprint behavior; conflict/invalid no-event behavior; exact snapshot sources;
historical no-backfill replay; direct client table/RPC denial; restrictive parent FK; and
source-field mutation rejection. The temporary trigger is not committed, does not disable
any production-style trigger, and is used only to prove rollback at the otherwise
unreachable required-outbox failure boundary.

The two full-suite invocations were deliberately documented accurately: the first wrapper
lost the terminal pytest summary while its child continued, so it is not counted as test
evidence. The recorded final invocation wrote temporary output/JUnit files outside the
repository and produced the 1,399-pass result above. No result is inferred from a historic
baseline.

## Prompt 13A.1 independent-review closure

### Finding A — replay distinction: BLOCKED for historic corruption detection

For a known post-foundation `SUBMITTED` revision created by the current RPC, the local
test replays its matching fingerprint and proves its one matching event remains present.
The current function does **not**, however, query and reject a missing event before it
returns `IDEMPOTENT_REPLAY`.

There is no per-revision database marker recording whether a historical `SUBMITTED` row
predates the outbox foundation. `created_at` is not a safe boundary: it is a data value,
not an authoritative migration-membership marker, and the migration history does not
bind individual existing rows to the prior schema version. Therefore a missing event on an
already-existing row cannot be safely classified today as either a legitimate pre-outbox
revision or post-migration corruption. It must not be silently accepted as healthy, and
it must not be backfilled with current source data.

**Required separate approval before a fix:** an additive migration could add an immutable
`outbox_required` provenance marker to P6 revisions, default existing history to false,
and set it true only inside the P6 insert function for future submitted revisions. Its
idempotent branch could then require exactly one matching outbox event for marked rows and
raise a deterministic integrity error if absent. That can protect forward inserts only;
it cannot prove the status of rows created between the original outbox migration and the
corrective migration. No such migration was created or applied in this review task.

### Finding B — rollback evidence: VERIFIED LOCALLY

The isolated local test now creates a valid prior submit revision/event for its synthetic
owner/period, captures both exact records, then installs a uniquely named temporary
`BEFORE INSERT` outbox trigger that raises only for the next synthetic operation. The test
always drops the trigger/function in `finally`. It proves the failed required outbox insert
leaves no new P6 revision, no normalized course rows, and no outbox event; it also proves
the prior revision and prior event are byte-for-byte unchanged as decoded database values.

### Finding C — snapshot consistency: VERIFIED LOCALLY within the current contract

The test now reloads the immutable P6 revision and compares every existing snapshot field:
revision/intent identity; owner, university, major, plan, plan version, period, and
revision; lifecycle/validation/fingerprint; intent/source/policy/contract/period/notice
versions; actor; null-capable progress reference; canonical course identities/codes/order;
and UTC timestamp instant. Table checks enforce JSON shape, required keys, selected scope
identity, and submitted lifecycle. The P6 function is the trusted constructor for the
remaining source facts. A future processor must recheck the snapshot against P6 before it
builds any ledger record; no processor exists yet.

The snapshot intentionally still has no P8 provenance, evidence, source-engine, policy
composition, outcome, or status mapping. Those are unapproved adapter contracts, not
missing test data.

### Finding D — future processor boundary: VERIFIED CURRENT DENIAL / DEFERRED DESIGN

Local database inspection confirms RLS is enabled; there are no outbox policies; and
`anon`, `authenticated`, and `service_role` have no direct outbox table privileges.
`persist_mock_registration_revision` is owned by `postgres`, is `SECURITY DEFINER`, has
fixed empty search path, is executable by `service_role` only, and has no direct P8 append.

A future processor requires separate approval for database-restricted operations that
atomically claim bounded pending/expired-lease rows; bind a random lease token and expiry;
allow completion only for that lease token after exact P8 payload/hash verification;
record only finite safe retry/error classes; and reclaim only expired leases. No broad
service-role `SELECT`/`UPDATE`, claim RPC, completion RPC, worker, or scheduler exists
in this implementation.

### Actual acceptance coverage

| Scenario | Actual test/function evidence | Classification |
| --- | --- | --- |
| New revision/header/courses/event commit together | `test_p6_transactional_outbox_atomicity_idempotency_security_and_snapshot` | REAL LOCAL POSTGRESQL + Supabase API |
| Required event failure rolls all new writes back and preserves prior history | `test_required_outbox_failure_rolls_back_and_legacy_replay_does_not_backfill` | REAL LOCAL POSTGRESQL + Supabase API |
| Same-fingerprint replay and concurrent equivalent submit | first test function | REAL LOCAL POSTGRESQL + Supabase API |
| Revision conflict/invalid submit create no new event | first test function | REAL LOCAL SUPABASE API with PostgreSQL verification |
| Direct outbox access and unauthorized P6 RPC denial | first test function | REAL LOCAL SUPABASE Auth/API |
| Missing parent and immutable event-source fields | first test function | REAL LOCAL POSTGRESQL |
| Snapshot identity/scope/version/course/timestamp consistency | first test function | REAL LOCAL POSTGRESQL |
| Synthetic legacy replay has no backfill | second test function | REAL LOCAL PostgreSQL fixture + Supabase API |
| Missing event for a previously post-migration committed revision | No safe historical discriminator exists | BLOCKED |
| Atomic claim/lease/conditional completion/retry/recovery | No processor implementation | DEFERRED |
| P8 canonical entry/append and end-to-end recovery | No adapter implementation | DEFERRED |

## Deferred / not verified

- **DEFERRED:** trusted P6-to-P8 adapter, canonical entry construction, P8 append, worker,
  leasing/claim/retry processing, public routes, frontend, and automated recovery.
- **DEFERRED:** P8 evidence taxonomy, provenance mapping, source-engine/policy/status/
  outcome mappings, and snapshot retention/erasure treatment.
- **NOT VERIFIED:** production schema/security/credentials and privileged administrator
  resistance.
- **NOT ACCEPTED:** P8 Runtime Slice 2 overall and the complete P6-to-P8 workflow.

## Prompt 13B.1 -- trusted P6 projection and deterministic mapper (2026-09-25)

### Implemented local-only mapper

`apps/api/app/decision_trace_persistence/p6_outbox_mapper.py` supplies two typed internal
source records (`TrustedP6OutboxProjection` and `P6DecisionTraceOutboxEvent`) and
`map_verified_mock_registration_submit`. It has no HTTP transport, database client,
append call, processing-state mutation, or academic-state mutation. It derives a
`CanonicalLedgerEntry` only after rechecking a typed immutable P6 parent/event/snapshot
projection. It does not accept a `CanonicalLedgerEntry`, supplied hash, actor, engine,
outcome, provenance, or evidence from a caller.

The mapper requires `outbox_required = true`, P6 `SUBMITTED`, `VALID` or
`REVIEW_REQUIRED`, exact P6 actor `STUDENT_AUTHENTICATED`, event/revision identity,
fixed event and snapshot contract `1.0`, matching scope, exact snapshot shape, canonical
ordered courses, source-version facts, and matching UTC revision/snapshot instants.
Legacy/unverified rows and synthetic corruption fixtures fail closed. It maps the locally
approved non-binding source engine, P6 contract/Phase-6 policy versions, outcome, three
P6 references, student-safe profile, narrowly defined `AUTHORITATIVE_TRANSACTION`, and
`NOT_REPLAYABLE`; it calls the sole Slice 1 factory and verifies its hash.

### Deliberate database-read blocker

The outbox migration revokes all direct table privileges from `PUBLIC`, `anon`,
`authenticated`, and `service_role`, and defines no read RPC. That least-privilege
boundary is preserved. A database-backed trusted projection is therefore **BLOCKED**;
the real-local mapper test uses the local PostgreSQL owner solely as test evidence and is
not service-role/application runtime authorization. A separately approved bounded,
service-only projection RPC with scope/eligibility/grant tests is required before a
processor can use this mapper.

### Prompt 13B.1 test evidence

| Command | Actual result | Classification |
| --- | --- | --- |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_p6_outbox_mapper.py -q` | **11 passed, 0 failed, 0 skipped in 0.79s** | UNIT |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_mock_registration_outbox_local_supabase.py -q -rs` with process-only local values | **4 passed, 0 failed, 0 skipped in 10.32s** | REAL LOCAL PostgreSQL + Supabase API |

The new local test maps a real fresh required P6 submit with actor
`STUDENT_AUTHENTICATED` twice, proves stable canonical payload/hash and three
null-locator/null-URI references, then confirms no P8 ledger row and no outbox processing
state transition. It is not a processor, append, or service-role projection-grant test.

## Prompt 13A.2 -- forward-only replay-integrity correction (2026-09-25)

### Implemented local database behavior

Additive migration `20260925113000_enforce_p6_outbox_replay_integrity.sql` adds
`mock_registration_intent_revisions.outbox_required boolean NOT NULL DEFAULT false`.
The default is deliberately a **LEGACY / UNVERIFIED marker**, not a timestamp-derived
claim that a row predates either outbox migration. Existing rows were left false; no event
was fabricated, no snapshot was rebuilt, and no academic-state data was changed.

The trusted `persist_mock_registration_revision` RPC preserves its P6.4 argument and
result schema. It writes `outbox_required = true` only when it inserts a new
`SUBMITTED` revision in the same transaction that inserts that revision's courses and
`MOCK_REGISTRATION_SUBMIT` outbox row. New `WITHDRAWN` revisions remain false and do not
create a submit outbox event. The existing immutable P6-history trigger prevents any
ordinary later update of the marker; clients have no direct mutation grant.

For an existing same-fingerprint replay, the function now performs a gate only when
`outbox_required` is true. It requires an event whose `event_id` and `revision_id` both
equal the P6 revision identity; verifies event type, owner/university/major/plan/plan
version/period/revision scope, snapshot contract version `1.0`; and reconstructs the
expected `source_snapshot` from immutable P6 revision plus canonical ordered course rows.
The stored JSONB snapshot must exactly match that reconstruction. An absent event raises
`Required P6 outbox event is missing for replay`; an invalid association, scope, event
type, contract version, or snapshot raises `Required P6 outbox event integrity mismatch
during replay`. Neither path returns `IDEMPOTENT_REPLAY`.

For `outbox_required = false`, the former legacy replay behavior is deliberately
preserved: it can return the original P6 replay result, creates no event, and makes no
claim that the missing evidence is healthy or historically complete. This leaves the gap
between the original outbox migration and this correction explicitly unverified.

### Local security and test evidence

The corrective migration was applied only through `npx --yes supabase@2.117.0 migration
up --local` to the isolated project at API port 54321 / PostgreSQL port 54322. Database
metadata after application confirmed the non-null false default, migration history ending
in `20260925113000`, `SECURITY DEFINER` P6 RPC owned by `postgres` with empty fixed
search path, and only `postgres`/`service_role` execute grants. The outbox retains RLS
enabled with no client policy and no direct `anon`, `authenticated`, or `service_role`
table grant. PostgreSQL owners/superusers remain privileged operational exceptions; this
is not absolute protection from a database administrator.

`test_mock_registration_outbox_local_supabase.py` now has three synthetic-local test
functions. It covers: false legacy marker/no backfill; true marker for fresh submits;
atomic revision/course/event insertion; compatible replay with no duplicate; explicit
missing-event rejection; mismatched scope/snapshot rejection; rollback when a uniquely
named temporary local outbox trigger fails; unchanged prior history; canonical snapshot
field consistency; immutable marker rejection; client outbox/P6 RPC denial; concurrent
equivalent submits; unchanged conflict response; compatible response keys; and withdrawal
without a submit event. The missing/mismatch fixtures are synthetic direct PostgreSQL
fixtures used only to exercise unreachable corrupted-history paths; the test neither
disables permanent triggers/RLS nor deletes a durable event.

Focused results after this correction:

| Command | Actual result |
| --- | --- |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_mock_registration_outbox_local_supabase.py -q -rs` | **3 passed, 0 failed, 0 skipped in 4.94s** |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests/test_mock_registration_persistence.py apps/api/tests/test_mock_registration_persistence_local_supabase.py apps/api/tests/test_mock_registration_outbox_local_supabase.py -q -rs` | **11 passed, 0 failed, 0 skipped in 7.25s** |
| Slice 1 / 2A / 2B focused suite | **65 passed, 0 failed, 0 skipped in 10.76s** |

Complete regression after the correction, from the repository root with process-only local
Supabase values and the local Plan ID, was:

| Command | Actual result |
| --- | --- |
| `apps/api/.venv311/Scripts/python.exe -m pytest apps/api/tests -q -rs` | **1400 passed, 0 failed, 0 skipped, 2 warnings in 511.08s** |

The warnings are existing FastAPI/Starlette `httpx` and `BlockingPortal` deprecations. An
earlier runner without `MORSHIDI_LOCAL_STUDY_PLAN_ID` produced 11 environment skips and is
not acceptance evidence. There is still no adapter, P8 append, processor, worker, public
route, or production deployment. P8 Slice 2 remains **NOT ACCEPTED**.
