# Trusted P6-to-P8 Adapter Mapping -- Mock Registration Submit

> **CURRENT STATUS (Prompt 13B.1, 2026-09-25): LOCAL MAPPING APPROVED — PROCESSING
> AND PRODUCTION NOT APPROVED.** This supersedes the original design-gate status below
> only for the exact isolated-local mapper mapping. It does not approve a database read
> grant/RPC, processor, claim/lease/retry state change, P8 append, HTTP exposure,
> frontend, production deployment, retention, or erasure.

**STATUS: PROPOSED — AWAITING HUMAN APPROVAL**

## Purpose and boundary

This is a source-grounded local design gate for one future internal adapter. It covers
only a durable, non-binding P6 `MOCK_REGISTRATION_SUBMIT` event and does not implement an
adapter, processor, claim/lease/retry operation, P8 append, HTTP route, frontend, or
production deployment.

The proposed ledger describes the fact that Morshidi persisted a student's **non-binding
declared intent** after deterministic P6 validation. It is never an official registration,
enrollment, seat reservation, approval, offering guarantee, or change of academic standing.
P8 remains explanatory; deterministic P6 rules retain decision authority.

## Verified preconditions and forward-only boundary

The actual corrective migration
`supabase/migrations/20260925113000_enforce_p6_outbox_replay_integrity.sql` adds
`mock_registration_intent_revisions.outbox_required boolean NOT NULL DEFAULT false` and
changes the P6 persistence function as follows:

- A newly inserted `SUBMITTED` revision receives `outbox_required = true` and its one
  `MOCK_REGISTRATION_SUBMIT` event in the same PostgreSQL transaction.
- A marked idempotent replay verifies event identity, scope, event type, snapshot contract,
  and exact snapshot reconstruction before it returns `IDEMPOTENT_REPLAY`.
- `false` means **LEGACY / UNVERIFIED** only. It is not evidence that a revision predates
  either outbox migration. No historical event, snapshot, provenance, or P8 trace may be
  fabricated or backfilled from current state.

The future processor must process neither a legacy/unverified revision nor a synthetic
corruption fixture. It is eligible only after all of the following are true:

1. The outbox parent revision exists and has `outbox_required = true`.
2. `event_id = revision_id`, the FK points to that exact revision, and the event type is
   exactly `MOCK_REGISTRATION_SUBMIT`.
3. The revision lifecycle is exactly `SUBMITTED`, validation status is one of the P6
   persisted submit values `VALID` or `REVIEW_REQUIRED`, and snapshot contract is `1.0`.
4. The processor reconstructs the expected snapshot from that immutable revision and its
   canonical ordered courses and compares it exactly to `source_snapshot`.
5. Outbox parent scope and snapshot identity/scope equal the immutable P6 revision.
6. The persisted P6 actor class is exactly `STUDENT_AUTHENTICATED` for this first adapter.
   Other service-side classes are not silently promoted to a student event.
7. The outbox is in a future approved claimable state; this document grants no claim or
   retry authority.

Rows intentionally inserted by owner-level Local Supabase corruption tests fail this
eligibility predicate. A database owner/superuser can bypass ordinary protections; that is
not a normal adapter authority and is not production-proof.

## Proposed fixed semantics

| Semantic | Proposed exact value | Source and stability | Classification |
| --- | --- | --- | --- |
| Ledger event | `MOCK_REGISTRATION_SUBMIT` | Existing `DecisionType` and P8 database materiality registry. | EXISTING VERIFIED CONTRACT |
| What it records | Persisted non-binding P6 declared intent and deterministic validation result. | P6 persistence policy §§1, 4, 13, 16; `MockRegistrationStudentService.submit`. | EXISTING VERIFIED CONTRACT |
| `source_engine` | `P6_MOCK_REGISTRATION_VALIDATION` | Controlled adapter literal naming existing `app.mock_registration.validation.validate_registration_intent`. It is not an institution/SIS engine. | PROPOSED DESIGN |
| `source_engine_version` | Exact persisted `p6_contract_version`. | P6 `PersistRevisionCommand` / `PersistedIntentRevision`; it identifies the P6 engine contract, **not** a binary/deployment build. Stable across retries because it is snapshot-persisted. | PROPOSED DESIGN |
| `policy_version` | Exact persisted `phase6_policy_version`. | The final Mock Registration policy version. Phase 5 and all remaining version facts remain in `source_versions`; no concatenated synthetic policy string is used. | PROPOSED DESIGN |
| `decision_status` | `VALID` -> `VALIDATED`; `REVIEW_REQUIRED` -> `FLAGGED_REVIEW`. | Exact finite transform from persisted P6 validation status. `INVALID` is not persisted by the current P6 RPC and is ineligible. | PROPOSED DESIGN |
| `outcome_reference` | `P6_NON_BINDING_INTENT:<revision_id>:<validation_status>:<content_fingerprint>` | Fixed adapter format built only from immutable snapshot/revision facts. It names neither enrollment nor approval. | PROPOSED DESIGN |
| `provenance_class` | `AUTHORITATIVE_TRANSACTION` with `scenario_id = None`. | See provenance decision below. Authority is limited to the P6 durable persistence transaction. | PROPOSED DESIGN / HUMAN APPROVAL REQUIRED |
| `replay_status` | `NOT_REPLAYABLE`. | Approved initial direction; the snapshot does not retain a frozen executable catalog/progress/engine artifact set. | APPROVED LOCAL DESIGN DIRECTION |

## Complete proposed ledger-field mapping

Every field below is hash-covered except that `integrity_hash` is the SHA-256 result over
the rest of the canonical payload. The adapter must call the existing
`create_canonical_ledger_entry`, never accept a client `CanonicalLedgerEntry`, and persist
only after the existing Slice 1 validation/hash check.

| Ledger field | Exact mapping | Real source location | Retry stability and validation | Status |
| --- | --- | --- | --- | --- |
| `ledger_entry_id` | `str(outbox.revision_id)` | Outbox `event_id = revision_id` constraint; P6 `PersistRevisionResult.revision_id`. | Must equal revision ID and outbox event ID; duplicate P8 identity must be exact payload/hash match or fail. | PROPOSED stable identity |
| `decision_type` | `DecisionType.MOCK_REGISTRATION_SUBMIT` | `decision_trace/registries.py:DecisionType`. | Finite registry; P8 materiality must resolve to required. | EXISTING |
| `materiality_class` | `materiality_for(DecisionType.MOCK_REGISTRATION_SUBMIT)` = `LEDGER_REQUIRED` | `decision_trace/registries.py:DECISION_MATERIALITY_REGISTRY`. | Never caller supplied. | EXISTING |
| `actor_class` | `ActorClass.STUDENT` | P6 `actor_class = STUDENT_AUTHENTICATED` in `mock_registration_service/student_service.py:submit`; P8 registry. | Processor rejects any non-`STUDENT_AUTHENTICATED` P6 value. | PROPOSED transform |
| `actor_id` | `str(revision.owner_user_id)` | Immutable P6 revision/snapshot `owner_user_id`. | Equal revision owner, outbox owner, snapshot owner, and the authenticated P6 workflow principal when available. | EXISTING source / PROPOSED use |
| `subject_scope_type` | `SubjectScopeType.STUDENT_INDIVIDUAL` | P8 registry and ledger constraint. | Requires nonempty student user ID. | EXISTING |
| `subject_scope_id` | `str(revision.owner_user_id)` | Immutable P6 owner. | Stable owner-derived individual scope; must equal `student_user_id`. No alternate subject-ID convention is introduced. | PROPOSED convention |
| `university_id` | `str(revision.university_id)` | Immutable revision/outbox/snapshot scope. | All three must equal; canonical UUID text. | EXISTING source / PROPOSED use |
| `student_user_id` | `str(revision.owner_user_id)` | Immutable P6 owner/snapshot. | Must equal `actor_id`, subject scope ID, and authoritative P6 owner. | EXISTING source / PROPOSED use |
| `source_engine` | `P6_MOCK_REGISTRATION_VALIDATION` | Existing deterministic function `validate_registration_intent`; fixed adapter contract above. | Fixed literal; no client or outbox override. | PROPOSED |
| `source_engine_version` | `revision.p6_contract_version` | `PersistedIntentRevision.p6_contract_version`; outbox snapshot key. | Nonblank; copied unchanged across retry. It is a contract version, not a binary hash. | PROPOSED |
| `policy_version` | `revision.phase6_policy_version` | `PersistedIntentRevision.phase6_policy_version`; snapshot key. | Nonblank and copied unchanged. Phase 5 version remains separately source-versioned. | PROPOSED |
| `source_versions` | Slice 1 normalized set of `study_plan_version`, `intent_source_version`, each `catalog_source_versions`, each `prerequisite_source_versions`, `progress_state_version`, `phase5_policy_version`, `phase6_policy_version`, `p6_contract_version`, `target_period_source_version`, and `transparency_notice_version`. | All are immutable P6 revision/snapshot facts. | All must be nonblank; factory sorts/deduplicates. No current catalog/progress lookup is permitted. | PROPOSED composition |
| `input_state_reference` | `revision.progress_state_reference` | Persisted P6 revision/snapshot. | May be `None`; if present must match snapshot exactly and is not disclosed by the current safe view. | EXISTING source / PROPOSED use |
| `scenario_id` | `None` | P8 `AUTHORITATIVE_TRANSACTION` constraint. | Must stay null. | EXISTING |
| `decision_status` | `VALIDATED` if P6 `VALID`; `FLAGGED_REVIEW` if P6 `REVIEW_REQUIRED`. | Immutable `validation_status`. | Reject every other value. | PROPOSED transform |
| `outcome_reference` | `P6_NON_BINDING_INTENT:<revision_id>:<validation_status>:<content_fingerprint>` | Immutable revision/snapshot ID/status/fingerprint. | Exact ASCII delimiter format; reject mismatch. It does not state eligibility, approval, enrollment, or registration. | PROPOSED |
| `evidence_references` | The three minimal immutable references defined below. | Revision, courses, and target period in the immutable P6/outbox record. | Factory normalizes into canonical lexical order. | PROPOSED taxonomy |
| `domain_trace_reference` | `None` | P6 stores no Slice-1 domain trace identifier. | No surrogate is invented. | EXISTING absence |
| `provenance_class` | `ProvenanceClass.AUTHORITATIVE_TRANSACTION` | Existing finite P8 enum. | Only after all processor eligibility checks; `scenario_id` remains null. | PROPOSED / approval required |
| `created_at` | `revision.created_at` / snapshot `created_at` | Database-generated immutable P6 revision timestamp. | UTC instant must exactly match snapshot; never use event timestamp or client time. | EXISTING source / PROPOSED use |
| `redaction_profile` | `RedactionProfile.STUDENT_SAFE` | Existing safe-view service accepts only stored student-safe records for students. | Viewer authority, not stored value, controls projection. | PROPOSED use of existing boundary |
| `integrity_hash` | Factory-calculated Slice 1 SHA-256. | `decision_trace.validation:create_canonical_ledger_entry`; `canonical.calculate_integrity_hash`. | Reject supplied/mismatched hashes; SHA-256 is integrity only, never provenance or authorization. | EXISTING |
| `previous_entry_hash` | `None` | No P6 revision sequence implies P8 supersession. | Must stay null in first adapter. | EXISTING fail-closed boundary |
| `supersedes_entry_id` | `None` | Same. | Must stay null in first adapter. | EXISTING fail-closed boundary |
| `replay_status` | `ReplayStatus.NOT_REPLAYABLE` | Existing P8 enum; approved initial direction. | Never claim exact/current replay until separately approved artifacts and runtime exist. | APPROVED LOCAL DESIGN DIRECTION |
| `limitations` | Exactly `NON_BINDING_DECLARED_INTENT_NOT_OFFICIAL_REGISTRATION` and `P6_HISTORICAL_REPLAY_NOT_AVAILABLE`. | First is grounded by the P6 policy/non-binding validation limitation; second by the approved replay direction. | Fixed adapter literals, sorted by Slice 1 factory; no free-form source text or client content. | PROPOSED |
| `hash_contract_version` | Existing Slice 1 default `1.0`. | `decision_trace/canonical.py:HASH_CONTRACT_VERSION`. | Factory validates. | EXISTING |
| `decision_schema_version` | Existing Slice 1 default `1.0`. | `decision_trace/validation.py:DECISION_SCHEMA_VERSION`. | Factory validates. | EXISTING |

## Provenance decision

**Proposed resolution:** use `AUTHORITATIVE_TRANSACTION`, but define its authority narrowly:
the P6 transaction authoritatively committed a Morshidi record of a non-binding declared
intent and its deterministic validation metadata. It does **not** authoritatively represent
university enrollment, prerequisite approval, seat allocation, or official registration.

This is technically compatible with the current finite P8 enum and database check: it
requires `scenario_id = None` and neither implies an academic-state mutation nor conflicts
with P6's stated semantics. It remains a **human approval requirement** because the enum's
name has not previously been approved for this bounded meaning.

If human review rejects that reading, the minimal alternative is a new finite
`PERSISTED_DECLARED_INTENT` P8 provenance value. It would require a separately approved
additive migration for the ledger provenance constraint, a Slice 1 enum/validation update,
and regression coverage. It must not rewrite the applied migrations or relabel historical
entries. No enum or migration change is made by this document.

## Minimal immutable evidence taxonomy

All `locator` and `uri` values are `None`. They are not needed for exact reconstruction,
and the current P8 safe projection exposes no evidence fields. These are P6 artifact
references only; they are not policy-document citations and do not dereference current
catalog, progress, or university portal data.

| Canonical order | Proposed `source` | `identifier` | `version` | Immutable proof | Status |
| ---: | --- | --- | --- | --- | --- |
| 1 | `P6_INTENT_COURSE_SET` | `str(revision.revision_id)` | `revision.p6_contract_version` | Normalized course rows are immutable, parent-owned, and ordered; `content_fingerprint` remains in the outcome reference. | PROPOSED |
| 2 | `P6_INTENT_REVISION` | `str(revision.revision_id)` | `revision.p6_contract_version` | Immutable P6 header/snapshot establishes the submitted revision and validation metadata. | PROPOSED |
| 3 | `P6_TARGET_PERIOD` | `str(revision.target_period_id)` | `revision.target_period_source_version` | Immutable snapshot captures exact period identity and source version used at persistence. | PROPOSED |

Canonical order is not caller controlled: `create_canonical_ledger_entry` sorts evidence
by `(source, identifier, version, locator-or-empty, uri-or-empty)`, yielding the order
above. The adapter must compare its normalized result to this exact tuple before append.

## Snapshot sufficiency and explicit gaps

The `source_snapshot` contains all per-event P6 facts used above: revision/intent IDs;
owner/university/major/plan/period scope; lifecycle and validation status; fingerprint;
intent/source/catalog/prerequisite/progress/policy/contract/period/notice versions; actor
class; database revision timestamp; and canonical courses. It is protected by outbox
immutability and required-replay reconstruction checks.

Two facts are deliberately outside the snapshot:

1. `outbox_required` is a revision-row eligibility marker, not event-source content. A
   future trusted outbox read must join/load the immutable parent revision and fail closed
   unless it is true. The existing `PersistedIntentRevision` projection does not include
   that column, so a future **code-only** trusted outbox projection is required; no schema
   correction is needed.
2. No frozen runtime build identifier exists. This proposal therefore maps
   `source_engine_version` to the stored P6 contract version and explicitly does not claim
   a binary/deployment version. If human approval requires a build-level engine identity,
   the minimal safe correction is a future forward-only outbox snapshot-contract version
   with a server-generated build/engine contract field for new events only. It must not
   fetch present-day code or infer history for existing snapshots.

The fixed proposed limitations and controlled source-engine literal are adapter contract
values, not missing historical facts. They require human approval but do not require a
snapshot migration if approved.

## Proposed processor acceptance matrix

These are **proposed tests only, not passing evidence**.

| ID | Assertion | Test class |
| --- | --- | --- |
| MAP-01 | Real eligible outbox/revision maps every field exactly and factory hash verifies. | Local Supabase integration |
| MAP-02 | A `false` legacy/unverified marker produces no ledger append and no backfill. | Local Supabase integration |
| MAP-03 | Missing/mismatched event, scope, snapshot, event type, contract, lifecycle, or actor class fails before canonical construction. | Local Supabase integration |
| MAP-04 | A fabricated client entry, hash, engine, outcome, provenance, or evidence tuple cannot enter the internal adapter path. | Unit + integration |
| MAP-05 | `VALID` and `REVIEW_REQUIRED` map only to their approved finite P8 status values; any other P6 status rejects. | Unit |
| MAP-06 | Same revision/outbox retry recreates byte-equivalent canonical payload/hash and either matches the existing ledger ID or fails on mismatch. | Unit + Local Supabase integration |
| MAP-07 | Source-version union is sorted/deduplicated without live catalog/progress access. | Unit |
| MAP-08 | Three evidence references normalize into the stated lexical order with null locator/URI; any added/current-state evidence rejects. | Unit + Local Supabase integration |
| MAP-09 | Parent/evidence round trip preserves exact canonical payload/hash and evidence order. | Local Supabase integration |
| MAP-10 | Append introduces no academic-state, enrollment, course-attempt, catalog, profile, or P6-revision mutation. | Existing-workflow integration |
| MAP-11 | Safe student projection remains metadata-only; other student, analyst, anonymous, and revoked/unassigned advisor paths remain denied by existing P8 boundaries. | Local Supabase integration |

## Human decisions required before implementation

1. Approve the controlled `source_engine` literal and P6-contract meaning of
   `source_engine_version`.
2. Approve `phase6_policy_version` as the single `policy_version` while preserving the
   full persisted set in `source_versions`.
3. Approve the P6 validation-status mapping and non-binding `outcome_reference` format.
4. Approve the narrowly defined `AUTHORITATIVE_TRANSACTION` meaning, or approve the
   separately scoped provenance-enum/migration change.
5. Approve the three-reference immutable evidence taxonomy and fixed limitation codes.
6. Approve the processor's strict `STUDENT_AUTHENTICATED` eligibility for this first
   adapter and the code-only parent/outbox projection requirement.

## Exact next implementation boundary after approval

Implement only a trusted internal outbox projection plus deterministic mapper that accepts
the eligibility-verified P6 revision/outbox pair, calls Slice 1's canonical factory, and
uses the existing P8 append RPC through a dedicated internal path. Do not reopen
`append_student` or `append_advisor`; do not add claim/lease/retry processing, a public
endpoint, frontend, or production deployment in that slice.
