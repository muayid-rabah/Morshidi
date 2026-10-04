STATUS: PROPOSED — NOT APPROVED

# P8 Runtime Slice 2 — Decision Trace Ledger Persistence & Security Plan

## 1. Entry criteria

Human approval of Category A decisions A-01 through A-10 in `contract-decision-register.md`; approved promotion or explicit accepted replacement of the ledger canonical policy; a real local Supabase environment with Docker/CLI and local-only credentials; no unrelated working-tree changes accepted by implication.

## 2. Authoritative existing components

- Slice 1 `app.decision_trace`: registries, immutable models, canonicalization/hash contract 1.0, validation, redaction, supersession, replay availability.
- P7 `AdvisorAuthorizationService` and advisor assignment/membership persistence predicate.
- P6 owner RLS, immutable revision, least-grant, and service-RPC security precedents.
- P8 umbrella policy's deterministic precedence, no-write, and individual/aggregate privacy boundaries.

## 3. Smallest coherent proposed scope

Persist approved material Slice 1 entries and typed evidence references only. Preserve canonical payload/hash and immutable history; support authorized retrieval of redacted metadata/references only. Do not add RAG, graph, impact, institutional query, UI, replay orchestration, retention jobs, exports, or new decision engines.

## 4. Required database objects — proposed, not implemented

- A parent ledger relation (candidate name `decision_trace_ledger`) preserving every required `CanonicalLedgerEntry` field, immutable identity, university and conditional student scope, stored canonical integrity hash, predecessor references, and replay metadata.
- A child evidence relation (candidate name `decision_trace_evidence`) with parent key and Slice 1 `EvidenceReference` fields. Parent authorization must govern evidence visibility.
- Constraints/indexes selected only after A-02/A-08 approval. No schema is supplied by this plan.

## 5. Proposed persistence interfaces

- A typed backend repository maps only validated `CanonicalLedgerEntry` and `EvidenceReference` objects to persistence.
- A service-side append operation validates materiality, validates/recomputes the existing Slice 1 hash, applies approved actor/event scope, and performs one atomic parent/evidence append.
- Viewer operations return role-safe metadata/references; they do not expose raw hidden reasoning or bypass established authorization.

## 6. Authentication and authorization

- Student viewer: verified owner only.
- Advisor viewer: call P7 authorization before loading individual traces; active `ACADEMIC_ADVISOR` membership, exact active assignment, and same authoritative university are conjunctive.
- Analyst: no individual trace or evidence access. Future aggregate capability is out of scope.
- Service: server-only credential/persistence boundary with exact scope predicates; it is not blanket user authorization.

## 7. Intended RLS access matrix — requires approved implementation detail

| Actor | Parent/evidence read | Append | Update/delete |
| --- | --- | --- | --- |
| Owner | Approved owner-safe projection only | No direct client write | Denied |
| Other student | Denied | Denied | Denied |
| Assigned same-university advisor | Service-authorized advisor-safe projection | No direct client write | Denied |
| Unassigned/cross-university advisor | Denied | Denied | Denied |
| Institutional analyst | Denied for individual rows | Denied | Denied |
| Anonymous | Denied | Denied | Denied |
| Trusted service | Narrow approved append/read | Controlled service append | No historical mutation |

## 8. RPC security boundary

No decision is made here whether to use direct service-role persistence or a SECURITY DEFINER RPC. If an RPC is approved, it must have fixed safe search path, strict typed/canonical parameter validation, fully qualified database references, least `EXECUTE` grants, no browser-role execution, and tests for spoofed actor/owner/university input. If direct service persistence is approved, the repository transaction has equivalent atomicity and least-access requirements.

## 9. Integrity, supersession, and replay

- Reuse the Slice 1 canonicalization and hash algorithm unchanged; server recomputes hash before append.
- Reject malformed/tampered hash payloads; do not use a hash for authorization or signature claims.
- Corrections create new immutable rows; predecessor and prior digest must be scope-valid. Branching/current-successor policy is blocked pending A-08.
- Store exact/current/not-replayable metadata and immutable version references. Replay execution/result persistence is deferred; exact replay must fail closed when versions are unavailable.

## 10. Local Supabase prerequisites

Install Supabase CLI and Docker; replay only a local database; configure local-only URL/server key/anonymous key and Plan context required by existing suites. Never point tests at production or expose key values.

## 11. Adversarial security tests

At minimum: direct anon/authenticated insert/update/delete denial; owner versus other-student isolation; assigned/unassigned/revoked/cross-university advisor cases; analyst denial; no evidence enumeration; cross-tenant parent/predecessor rejection; unauthorized RPC execute denial; spoofed service-input denial; hash tamper/malformed rejection; immutable supersession; exact replay availability and unauthorized replay denial.

## 12. Regression and exit criteria

Run focused Slice 1 plus new Slice 2 unit tests; run Local Supabase security tests with **zero skips**; manually inspect effective tables/RLS/policies/functions/grants; run root backend regression; verify disk sizes/diffs. Exit only after every Category A decision is approved, all tests pass, no production resource is touched, and a human accepts the evidence.

## 13. Explicit non-goals and human approval

No migrations/code are created by this plan. Human approval is required for event scope, schema, access split, RPC strategy, evidence lifecycle, retention/erasure, supersession semantics, replay artifacts, and the test environment before implementation begins.
