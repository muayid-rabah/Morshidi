STATUS: RECONSTRUCTED DRAFT — NOT APPROVED

# P8 Decision Trace Ledger — Recovery Draft

## Purpose and authority

This is a review-only reconstruction of the missing companion contract. It does not restore lost approved text, create a database schema, authorize persistence, or change the existing Slice 1 hash algorithm. The governing invariant is **AI EXPLAINS — DETERMINISTIC RULES DECIDE**.

## Verified existing requirements

- P8 is an append-only, privacy-preserving, cryptographically verifiable side-car for material decisions; it must not rewrite historical academic state ([P8 umbrella policy, §§1, 5–6](../p8-grounded-knowledge-decision-trace-policy.md)).
- Routine P7.5 read-only tools remain ephemeral and are not permanent ledger entries.
- Individual traces are available only to the student owner or an actively assigned, same-university academic advisor. Institutional analysts receive no individual trace.
- `CanonicalLedgerEntry` retains identity, materiality, actor, subject scope, university and conditional student scope, engine/policy/source versions, input/scenario and outcome references, typed evidence, provenance, UTC timestamp, redaction/replay/supersession fields, limitations, and schema/hash versions.
- Existing materiality classes are closed: `LEDGER_REQUIRED`, `LEDGER_OPTIONAL`, `DOMAIN_TRACE_ONLY`, and `NOT_LEDGERED`. Existing decision-type mapping is authoritative until formally revised.
- Slice 1 uses compact sorted-key UTF-8 JSON, enum values, UTC timestamp normalization, sorted set-like fields, excludes `integrity_hash` from its own payload, and calculates SHA-256. SHA-256 is integrity evidence only: it is neither authorization nor a digital signature.
- Existing models contain no chain-of-thought, raw prompt, raw completion, scratchpad, reasoning-token, or hidden-reasoning field.

## Requirements derived from existing implementation

1. An entry must pass `validate_entry`: nonblank required identifiers, exact materiality mapping, UTC timestamp, nonempty source versions, supported schema/hash versions, valid hash shapes, scope invariants, no self-supersession.
2. Student-individual scope requires `student_user_id`; institutional-period scope forbids it.
3. A correction has a new `ledger_entry_id`, immutable historical predecessor, `supersedes_entry_id`, and optionally the predecessor digest as `previous_entry_hash`.
4. `EXACT_REPLAY` fails closed if a historic source, engine, or policy version is unavailable. `CURRENT_RECOMPUTATION` reports a separately recomputed result and never overwrites history. `NOT_REPLAYABLE` is explicit.
5. Structural redaction removes student identity and redacts a student subject ID for aggregate/public projections; public projection adds `PUBLIC_REDACTED` to limitations.

## Proposed persistence and security requirements — requires approval

- Persist one immutable parent trace record and zero-or-more typed evidence-reference records; no raw LLM text or hidden reasoning may be persisted.
- Append may occur only through a narrowly scoped service-side boundary after the material decision is already determined by its authoritative deterministic engine.
- Every persisted payload must be validated against the existing Slice 1 contract and hash recomputed server-side before insert. The database must reject invalid/missing digest shapes and client-supplied changes to integrity-relevant fields.
- Existing rows and evidence must reject `UPDATE` and `DELETE` for browser roles; corrections use a new superseding row, never mutation.
- Evidence records inherit the authorization scope of their parent trace and cannot be independently enumerated.
- The persistence boundary must record no broader personal data than the canonical envelope permits and must preserve `university_id` on every tenant-scoped record.

## Draft access matrix — requires approval and real integration validation

| Actor | Individual trace/evidence read | Append | Update/delete | Required predicate |
| --- | --- | --- | --- | --- |
| Student owner | Draft: permitted, student-safe projection | No direct | Denied | Verified `auth.uid()` equals immutable `student_user_id` |
| Other student | Denied | Denied | Denied | Ownership fails |
| Assigned advisor | Draft: permitted, advisor-safe projection | No direct | Denied | Verified identity + active `ACADEMIC_ADVISOR` membership + authoritative same university + active exact assignment |
| Unassigned advisor | Denied | Denied | Denied | Assignment fails without existence disclosure |
| Advisor from other university | Denied | Denied | Denied | Student, membership, and assignment university must match |
| Institutional analyst | Denied for individual traces/evidence; aggregate-only future output is separate | Denied | Denied | Analyst role never grants student-level access |
| Anonymous/unauthorized | Denied | Denied | Denied | Authentication and scope fail |
| Trusted service boundary | Draft: narrowly scoped operational read/append | Draft: controlled | No historical mutation | Server-side authorization, exact owner/tenant predicates, least grants |

## Open contracts / requires human approval

- Which material events are first eligible to persist, their retention period, legal erasure process, and whether institutional snapshot entries have a viewer role beyond existing policy.
- Exact table names, evidence cardinality, database constraint design, ordering/chain semantics, service API shape, and whether an advisory formal-guidance event is introduced in the first persistence slice.
- The authoritative storage/availability policy for source, engine, and policy versions required for exact replay.
- Whether integrity is solely per-entry or additionally needs a transaction/period chain. No chain requirement is inferred from Slice 1.

## Explicit non-goals

- No SQL migration, RLS policy, RPC, repository, route, UI, retention job, export, or Slice 2 implementation.
- No authorization by hash and no AI decision authority.
- No automatic mutation of recommendations, registration, progress, catalog, or student state.

## Acceptance criteria for a later approved Slice 2

Approved canonical policy; migration review; unit proof of canonical/hash/supersession behavior; real local-Supabase proof of effective grants, RLS, RPC execution boundary, owner/advisor/tenant isolation, analyst denial, append-only rejection, evidence inheritance, integrity tamper detection, and replay availability. Zero skipped Slice 2 security tests is required for acceptance.
