STATUS: DRAFT — AWAITING HUMAN APPROVAL

# P8 trusted deterministic result-to-ledger adapter contract

## 1. Purpose and status

This is a source-grounded contract proposal, not an implementation and not a recovered
original policy. It names the first candidate workflow that could create a P8 ledger
record without accepting a client-supplied `CanonicalLedgerEntry`. It does not authorize
an HTTP endpoint, change deterministic academic logic, or remove the current fail-closed
`append_student` / `append_advisor` protections.

**EXISTING VERIFIED CONTRACT:** Morshidi's invariant is **AI EXPLAINS — DETERMINISTIC
RULES DECIDE**. A P8 trace is an immutable explanatory sidecar, never an academic-state
decision or write authority.

**PROPOSED DESIGN:** introduce one internal adapter only after the human decisions in
section 11. It receives trusted in-process P6 execution objects, creates one Slice 1
canonical entry, verifies its hash, and calls the existing restricted P8 repository/RPC.

## 2. Selected first workflow

### Selected candidate: validated Mock Registration submission

The proposed first adapter is limited to a successful P6 Mock Registration **submit**:

`POST /api/v1/me/mock-registration/revisions`
→ `MockRegistrationStudentService.submit`
→ `validate_registration_intent`
→ `persist_mock_registration_revision`
→ verified persisted revision.

It maps only to existing finite `DecisionType.MOCK_REGISTRATION_SUBMIT`, whose registry
materiality is `LEDGER_REQUIRED`.

| Item | Actual evidence | Classification |
| --- | --- | --- |
| Authenticated entrypoint | `app.api.routes.mock_registration.submit_intent`; route dependency is `get_current_user` | EXISTING VERIFIED CONTRACT |
| Request model | `SubmitIntentRequest`: target period, course codes, expected revision, transparency notice | User request data; untrusted as ledger authority |
| Authoritative context | `SupabaseAcademicContextLoader.load_owner_context` returns `AcademicContextSnapshot` | EXISTING VERIFIED CONTRACT |
| Deterministic engine | `app.mock_registration.validation.validate_registration_intent` calls Phase 5 `evaluate_can_take` and context-bound Phase 6 progress | EXISTING VERIFIED CONTRACT |
| Trusted persisted result | `SupabaseMockRegistrationRepository.persist_revision` followed by `MockRegistrationStudentService._persisted_row` returning `PersistedIntentRevision` | EXISTING VERIFIED CONTRACT |
| Result exposed to client | `StudentIntentResult` via `student_response` | Not sufficient alone for ledger construction |
| Academic write scope | P6 writes a **non-binding declared-intent revision**, not enrollment, a seat, an approval, a catalog row, or student academic standing | EXISTING VERIFIED CONTRACT |

### Why this candidate and not another

It is the narrowest material event with all of the following already present: verified
student route authentication, authoritative owner/university/plan context, a pure
deterministic validation function, a typed persisted result, an existing server-only
atomic P6 persistence RPC, and documented idempotent revision behavior. The authoritative
result remains explicitly limited: it is a validated, non-binding registration intent,
not an official academic registration decision.

Advisor guidance, institutional snapshots, change impact, RAG, graph, and ordinary
read-only engines are excluded. They lack an equally narrow approved result-to-ledger
source contract for this first adapter.

## 3. Source references inspected

- `apps/api/app/api/routes/mock_registration.py`: authenticated route and
  `submit_intent` call path.
- `apps/api/app/core/auth.py`: `get_current_user` calls Supabase Auth and returns
  `CurrentUser`; UUID parsing alone is not authentication.
- `apps/api/app/mock_registration_service/student_service.py`:
  `MockRegistrationStudentService.submit`, `_context`, `_persist`, `_persisted_row`,
  `_student_result`, and the two non-binding limitations.
- `apps/api/app/mock_registration_service/context.py`:
  `SupabaseAcademicContextLoader.load_owner_context`, `domain_context`, `_map_plan`.
- `apps/api/app/mock_registration/validation.py`:
  `validate_registration_intent` and its Phase 5 eligibility invocation.
- `apps/api/app/mock_registration_service/models.py`: `AcademicContextSnapshot` and
  `StudentIntentResult`.
- `apps/api/app/mock_registration_persistence/models.py`: `PersistRevisionCommand`,
  `PersistRevisionResult`, and `PersistedIntentRevision`.
- `apps/api/app/mock_registration_persistence/repository.py` and
  `supabase/migrations/20260922134625_add_mock_registration_persistence_security.sql`:
  server-only `persist_mock_registration_revision` and revision idempotency.
- `apps/api/app/decision_trace/{models,registries,canonical,validation}.py` and
  `apps/api/app/decision_trace_persistence/{repository,service}.py`: canonical envelope,
  finite registries, hash gate, immutable append RPC, and current fail-closed append API.
- Existing P6/P8 unit and Local Supabase tests named in section 10.

## 4. Trusted execution boundary

| Boundary | Allowed input/output | Required rule |
| --- | --- | --- |
| A. User request | `SubmitIntentRequest` only | Course codes, period, expected revision, and notice version are requests, never trace authority. |
| B. Authenticated backend context | `CurrentUser` from `get_current_user`, then owner-derived `AcademicContextSnapshot` | The route supplies the principal; P6 also verifies that loaded `owner_user_id` matches it. The client cannot provide university, actor class, plan, or owner scope. |
| C. Deterministic execution | `RegistrationIntent` constructed inside `submit` plus `domain_context(snapshot, period)` | `validate_registration_intent` derives canonical courses, fingerprint, status, reason codes, and limits from authoritative context. |
| D. Trusted result | P6 `PersistRevisionResult` and reloaded `PersistedIntentRevision`, plus the in-process validated intent/snapshot/period | Trust begins only after P6 persistence succeeds and the exact persisted revision is reloaded in the same service execution. `StudentIntentResult` alone loses required scope/version detail. |
| E. Canonical ledger construction | Proposed internal adapter | It derives every ledger field from C/D or fixed finite registry values, then calls `create_canonical_ledger_entry`; it never accepts a client entry, hash, provenance, evidence, engine version, or outcome reference. |
| F. Atomic ledger append | `SupabaseDecisionTraceRepository.append` → `public.append_decision_trace_ledger` | Existing P8 RPC atomically appends parent plus evidence. It does not make the earlier P6 transaction atomic with P8. |

No `trusted=True` field, magic source string, user-provided `integrity_hash`, or direct
call to the disabled append methods establishes trust. The trust claim is the concrete
server-side call graph and typed execution objects above.

## 5. Proposed internal adapter interface

The following is an interface contract, not code:

```text
append_after_verified_mock_registration_submit(
  principal: CurrentUser,
  snapshot: AcademicContextSnapshot,
  period: PersistedTargetPeriod,
  validated: ValidatedIntent,
  persisted: PersistedIntentRevision,
  persistence_result: PersistRevisionResult,
) -> ledger_entry_id
```

The adapter is invoked only inside `MockRegistrationStudentService.submit`, after
`_persist` returns an inserted/idempotent result and `_persisted_row` returns the matching
revision. It independently verifies that principal, snapshot, validated intent, persisted
revision, and persistence result have one owner, university, plan, target period, revision,
and content fingerprint. A future adapter must not be exported as a request-facing service.

**MISSING SOURCE INFORMATION:** the current P6 `submit(owner: str, ...)` signature accepts
a string after the route has authenticated it. The existing P6 route call path is safe, but
the service signature alone is not proof of transport authentication. The future change
must either thread `CurrentUser` internally or introduce an internal trusted execution
object at the authenticated route/service boundary. This is a design requirement, not
permission to treat arbitrary service callers as authenticated.

## 6. Proposed ledger field mapping

All `CanonicalLedgerEntry` payload fields except `integrity_hash` are hash-covered by
Slice 1 canonicalization. `integrity_hash` is also stored and verified against that payload.
The adapter must use `create_canonical_ledger_entry`, not hand-write a hash.

| Ledger field | Source/value or transformation | Authority / validation | Status |
| --- | --- | --- | --- |
| `ledger_entry_id` | `str(persisted.revision_id)` | P6 persisted UUID; on retry must equal `persistence_result.revision_id` | PROPOSED stable idempotency key |
| `decision_type` | fixed `DecisionType.MOCK_REGISTRATION_SUBMIT` | Existing finite registry | VERIFIED |
| `materiality_class` | `materiality_for(MOCK_REGISTRATION_SUBMIT)` | Must not be caller supplied | VERIFIED |
| `actor_class` | fixed `ActorClass.STUDENT` | Principal must equal persisted owner | PROPOSED mapping |
| `actor_id` | `str(persisted.owner_user_id)` | Must equal `CurrentUser.user_id` and snapshot owner | VERIFIED source; proposed use |
| `subject_scope_type` | fixed `STUDENT_INDIVIDUAL` | Existing P8 individual-scope contract | VERIFIED |
| `subject_scope_id` | Candidate `str(persisted.owner_user_id)` | Stable owner-derived student scope; no approved P8 subject-ID convention exists | HUMAN APPROVAL REQUIRED |
| `university_id` | `str(persisted.university_id)` | Must equal snapshot university and target-period university | VERIFIED source |
| `student_user_id` | `str(persisted.owner_user_id)` | Must equal verified principal and snapshot owner | VERIFIED source |
| `source_engine` | Candidate controlled identifier for `MockRegistrationStudentService.submit` | No approved P6 engine-name registry | MISSING SOURCE INFORMATION |
| `source_engine_version` | Candidate controlled value derived from P6 contract/engine policy | P6 has `p6_contract_version` and context has `p6:v1`, but no single engine-version contract | HUMAN APPROVAL REQUIRED |
| `policy_version` | Candidate P6 contract version | Phase 5/6 versions are separately persisted; choose no arbitrary concatenation | HUMAN APPROVAL REQUIRED |
| `source_versions` | Normalized union of persisted catalog/prerequisite versions, progress-state version, Phase 5/6/P6 versions, and target-period source version | All are P6 persisted fields; sorted/unique only through Slice 1 factory | PROPOSED mapping |
| `input_state_reference` | `persisted.progress_state_reference` | Optional authoritative profile reference; never exposed in safe projection | VERIFIED source |
| `scenario_id` | `None` | Required because authoritative-transaction validation forbids a scenario id | VERIFIED |
| `decision_status` | Candidate `VALIDATED` for P6 `VALID`; candidate `FLAGGED_REVIEW` for `REVIEW_REQUIRED` | P6→P8 status map does not exist | HUMAN APPROVAL REQUIRED |
| `outcome_reference` | Candidate `persisted.content_fingerprint` | It is a persisted deterministic-input/result fingerprint, but no P8 outcome-reference semantic contract exists | HUMAN APPROVAL REQUIRED |
| `evidence_references` | Candidate references only to persisted revision, study plan, and target period using their real IDs and persisted version fields | No approved P8 evidence-source taxonomy/identifier/locator policy exists; no URI/locator may be invented | BLOCKED |
| `domain_trace_reference` | `None` initially | P6 has `intent_id` and revision ID but no approved P8 domain-trace-reference format | MISSING SOURCE INFORMATION |
| `provenance_class` | Candidate `AUTHORITATIVE_TRANSACTION` only for a persisted non-binding P6 revision | P8 enum has no explicit declared-intent provenance; must not imply official enrollment | HUMAN APPROVAL REQUIRED |
| `created_at` | `persisted.created_at` | Existing persisted UTC timestamp; do not use client timestamp | VERIFIED source |
| `redaction_profile` | `STUDENT_SAFE` | P8 policy permits student-safe own trace; advisor access remains separate P7 check | VERIFIED policy boundary |
| `integrity_hash` | calculated by `create_canonical_ledger_entry` then rechecked by service/repository | Never accept supplied hash | VERIFIED |
| `previous_entry_hash` | `None` for first adapter | P6 revision sequence is not automatically P8 correction/supersession | VERIFIED fail-closed scope |
| `supersedes_entry_id` | `None` for first adapter | A P6 next revision is not evidence of P8 supersession semantics | VERIFIED fail-closed scope |
| `replay_status` | Candidate `NOT_REPLAYABLE` | Existing P6 revalidation supports current evaluation, but it does not retain all immutable historical engine/catalog artifacts for exact replay | PROPOSED conservative mapping |
| `limitations` | Existing `validated.limitations` plus `MockRegistrationStudentService.LIMITATIONS`; canonical factory sorts/deduplicates | Do not add narrative text or client content | VERIFIED source; proposed composition |
| `hash_contract_version` | Slice 1 default `1.0` | Factory validates current contract | VERIFIED |
| `decision_schema_version` | Slice 1 default `1.0` | Factory validates current schema | VERIFIED |

### Required cross-object assertions before construction

1. `CurrentUser.user_id == snapshot.owner_user_id == persisted.owner_user_id`.
2. `snapshot.university_id == persisted.university_id == period.university_id`.
3. `snapshot.study_plan_id`, version, and major equal persisted values.
4. `validated.intent` identity, lifecycle, canonical course codes, fingerprint, and status
   agree with the persisted revision and persistence result.
5. `persistence_result.kind` is only `INSERTED` or `IDEMPOTENT_REPLAY`; its revision ID,
   revision number, and fingerprint agree with the reloaded row.
6. The event remains non-binding; no adapter field may reclassify it as enrollment,
   eligibility clearance, graduation, or official registration.

## 7. Append timing, failure, retry, and concurrency

The P6 academic operation is a deterministic validation plus a write of a non-binding P6
intent revision. It becomes a trusted adapter input only after the P6 RPC completes and
the exact persisted revision is reloaded. An invalid submit or stale context fails before
P6 persistence and must create no ledger record.

`persist_mock_registration_revision` and `append_decision_trace_ledger` are distinct
server-side RPC transactions. **EXISTING FACT:** P6 has stable revision idempotency using
owner/university/major/plan/version/period/revision and content fingerprint. **NOT TRUE:**
there is no current cross-RPC transaction, no outbox, and no distributed atomic commit.

| Case | Required future behavior | Status |
| --- | --- | --- |
| P6 validation/persistence fails | Return existing P6 error; do not construct/append a trace | EXISTING-compatible |
| P6 succeeds; first ledger append succeeds | Return current P6 result unchanged; immutable trace exists | PROPOSED |
| P6 succeeds; ledger append conflicts | Load exact bounded ledger ID/owner/university; accept only if canonical payload/hash exactly match; otherwise fail closed as integrity/conflict | PROPOSED |
| P6 succeeds; ledger transport/RPC fails | Do not claim P6 rollback. A durable retry/outbox or explicitly approved recovery process is required | BLOCKED |
| P6 idempotent replay | Reconstruct same entry from reloaded revision and use same `ledger_entry_id`; no second historical trace | PROPOSED |
| Concurrent same request | P6 revision conflict/idempotent behavior remains authority; P8 identity uniqueness resolves duplicate append only after exact comparison | PROPOSED |

**HUMAN APPROVAL REQUIRED:** choose the durable missing-ledger strategy before enabling the
adapter. Returning a generic P6 failure after the P6 revision has committed is misleading;
silently accepting a missing required trace is also insufficient. A transactional P6 outbox
would require a separately approved additive schema/migration and is outside this draft.

## 8. Security invariants

- Keep `DecisionTraceService.append_student` and `append_advisor` disabled for caller-
  supplied entries. The adapter calls the repository through a new internal-only path after
  all section-6 assertions; it does not reopen either method.
- The service-role key remains backend-only. The adapter never gives clients direct ledger,
  evidence, or append-RPC access.
- Reuse Slice 1 `create_canonical_ledger_entry`, `validate_entry`, and
  `verify_integrity_hash`; SHA-256 remains integrity evidence, not authorization/signature.
- Preserve P6 owner checks and P7 retrieval authorization. This first student event grants
  no advisor append authority, analyst access, system/scheduler append, or evidence endpoint.
- Use the P8 repository's existing bounded parent/evidence retrieval and immutable database
  RPC. Safe projections remain field-minimal under Prompt 10.

## 9. Proposed executable acceptance matrix

All rows below are proposed and **not passing evidence**.

| ID | Scenario | Type | Required fixture/change |
| --- | --- | --- | --- |
| ADAPT-01 | Real authenticated P6 submit produces a trace only from in-process validated/persisted objects | EXISTING WORKFLOW + LOCAL SUPABASE INTEGRATION | Adapter integration and synthetic local user/plan/period |
| ADAPT-02 | Fabricated client `CanonicalLedgerEntry` remains rejected by current public append methods | UNIT + LOCAL SUPABASE INTEGRATION | Existing hardening suite extension |
| ADAPT-03 | Valid hash carrying false outcome/engine/provenance/evidence cannot enter adapter path | UNIT | Trusted-object boundary fixture |
| ADAPT-04 | Snapshot/persisted source-version or fingerprint mismatch fails closed | UNIT | Construct mismatched typed execution objects |
| ADAPT-05 | Missing/ambiguous provenance or evidence taxonomy blocks construction | UNIT | Approved mapping decision or negative fixture |
| ADAPT-06 | Principal/owner/student mismatch and university/period mismatch are denied | UNIT + LOCAL SUPABASE INTEGRATION | Cross-tenant synthetic fixtures |
| ADAPT-07 | Same P6 idempotent replay yields same ledger ID/hash and no duplicate trace | EXISTING WORKFLOW + LOCAL SUPABASE INTEGRATION | Adapter plus exact-load-on-conflict |
| ADAPT-08 | P8 append failure after P6 success follows approved durable recovery; P6 state is not misreported as rolled back | LOCAL SUPABASE INTEGRATION | Requires approved failure/recovery design |
| ADAPT-09 | Invalid/stale P6 submit creates neither P6 revision nor ledger record | EXISTING WORKFLOW + LOCAL SUPABASE INTEGRATION | Existing failure fixtures plus trace assertion |
| ADAPT-10 | Concurrent duplicate/revision-conflict requests create at most one matching ledger trace | LOCAL SUPABASE INTEGRATION | Concurrent authenticated requests |
| ADAPT-11 | Parent/evidence canonical round trip preserves actual adapter-built payload/hash | LOCAL SUPABASE INTEGRATION | Approved evidence mapping |
| ADAPT-12 | Existing P8 RLS/RPC direct-write/evidence protections remain denied | LOCAL SUPABASE INTEGRATION | Existing Slice 2A suite plus adapter regression |
| ADAPT-13 | Owner receives only student-safe projection; other student is denied | LOCAL SUPABASE INTEGRATION | Existing Slice 2B retrieval fixtures |
| ADAPT-14 | Assigned/revoked advisor retrieval follows P7 after adapter record creation | LOCAL SUPABASE INTEGRATION | Advisor membership/assignment fixture |
| ADAPT-15 | Adapter append causes no attempt/catalog/profile/official enrollment mutation beyond the existing P6 intent revision | EXISTING WORKFLOW + LOCAL SUPABASE INTEGRATION | Before/after authoritative-state assertions |
| ADAPT-16 | Exact replay is unavailable or current-only exactly as approved; no replay endpoint is added | DEFERRED | Requires replay contract and artifacts |

## 10. Explicit non-goals

- No HTTP route, frontend, direct evidence interface, client append, advisor append, system
  append, RAG, graph, impact, institutional query, replay execution, retention job, SIS,
  SSO, or production deployment.
- No change to P6 deterministic validation, P6 request/response semantics, P8 canonical hash
  algorithm, P8 database migration, RLS, grants, immutability triggers, or supersession rules.
- No assertion that the P6 non-binding intent is an official registration or degree decision.

## 11. Decisions required before implementation

1. Approve the selected first event as a ledger-worthy non-binding P6 submit and confirm its
   `ProvenanceClass` does not imply official enrollment.
2. Approve controlled `source_engine`, engine/policy-version, status-map, outcome-reference,
   subject-scope-ID, and evidence-source taxonomy contracts.
3. Decide whether `NOT_REPLAYABLE` is accepted initially or define current-recomputation
   artifacts/authority separately.
4. Approve durable behavior when P6 has committed but P8 append fails (outbox/recovery versus
   another explicitly safe design). No current architecture offers cross-RPC atomicity.
5. Approve the internal trust-boundary shape for threading `CurrentUser` and P6 typed execution
   objects without exposing a public append interface.
6. Approve the proposed Local Supabase acceptance tests and synthetic fixtures.

## 12. Exact next implementation boundary

After and only after the six decisions above, implement one internal P6-submit adapter and
its focused unit/Local Supabase tests. It may change the P6 service's internal composition
only as required to pass trusted execution objects; it must not change P6 academic decisions
or public routes. If durable append recovery needs an outbox, stop and request separate
approval for that additive design before adding schema.
