STATUS: PROPOSED DECISION REGISTER — NOT APPROVED

# P8 Contract Decision Register

## Reading rule

`VERIFIED EXISTING CONTRACT` records an already-supported boundary; it is not a new decision. `PROPOSED`, `BLOCKED`, and `AWAITING HUMAN APPROVAL` require review. P6/P7 controls are precedents, not permission to copy their implementation.

## Category A — required before Decision Trace Ledger Persistence & Security

### A-00 — Deterministic authority and no-write boundary

- **Capability / sources:** WC-040; P8 umbrella §§1, 4–5; Slice 1 domain implementation Scope/Deferred.
- **Verified requirement:** AI explains only; deterministic engines decide. Ledger is an append-only side-car, never an academic-state mutation.
- **Decision / options / consequence:** No open choice. Any schema/API that lets an LLM or trace write decide eligibility, progress, registration, or graduation violates the existing contract.
- **Status / acceptance:** `VERIFIED EXISTING CONTRACT`; tests and review must show no decision authority or unintended student/catalog write.

### A-01 — Material event scope

- **Sources:** `decision_trace/registries.py` materiality map; P8 umbrella §2; ledger draft “Verified” and “Open contracts”.
- **Verified requirement:** closed materiality classes and decision mappings exist; routine P7.5 tool reads are ephemeral/domain-only.
- **Missing requirement:** which `LEDGER_REQUIRED` and optional events first call persistence, and whether a formal advisor action exists in first scope.
- **Options:** (1) persist every mapped required type; (2) enable an approved finite subset; (3) delay all production callers while landing generic storage.
- **Proposed option:** (2), an explicitly listed finite subset with no new decision types, because it is the smallest coherent slice and avoids pretending unavailable callers exist.
- **Consequence / human decision / acceptance:** broad scope increases integration and security surface; approve eligible event list and actor classes. Tests prove domain-only types never persist and each enabled event has exact materiality/version evidence. `AWAITING HUMAN APPROVAL`.

### A-02 — Parent/evidence persistence schema

- **Sources:** `CanonicalLedgerEntry`, `EvidenceReference`; umbrella §§1, 5–6; ledger draft.
- **Verified requirement:** parent envelope and typed evidence references are immutable Slice 1 records.
- **Missing requirement:** table columns/types/keys, parent-to-evidence cardinality, identifier generation, and database constraints.
- **Options:** (1) JSON evidence embedded in parent; (2) normalized immutable `decision_trace_ledger` + `decision_trace_evidence`; (3) defer evidence persistence.
- **Proposed option:** (2), because typed references exist and evidence needs inherited authorization; table names remain proposed, not implemented.
- **Consequence / human decision / acceptance:** normalization enables scoped evidence reads but adds FK/append enforcement work. Approve shape and minimum retained fields. Migration design must preserve all hash-covered Slice 1 fields and prove evidence cannot exist without its authorized parent. `AWAITING HUMAN APPROVAL`.

### A-03 — Immutable history, retention, and deletion

- **Sources:** umbrella §5; Slice 1 frozen models/supersession; P6 threat model direct-update/delete controls.
- **Verified requirement:** historic entries must never be rewritten; correction is a new superseding entry.
- **Missing requirement:** operational retention, legal erasure/anonymization process, privileged maintenance authority, and whether any physical delete is ever permitted.
- **Options:** (1) deny all update/delete with separate future governed erasure contract; (2) allow operational update/delete; (3) soft-delete visible history.
- **Proposed option:** (1), because it preserves the existing immutable audit premise; it does not decide a legal retention period.
- **Consequence / human decision / acceptance:** no client or normal service update/delete path; human owner must approve retention/erasure policy. Local tests must reject update/delete for owner, advisor, analyst, and unauthorized roles. `AWAITING HUMAN APPROVAL`.

### A-04 — Individual viewer authorization and tenant isolation

- **Sources:** umbrella §6; P7.4 advisor policy §2 and `authorize_advisor_for_student`; advisor migration; P6 RLS matrix.
- **Verified requirement:** student owner may receive student-safe trace; advisor requires authenticated active `ACADEMIC_ADVISOR`, exact student, active assignment, and same authoritative university; analyst has zero individual access.
- **Missing requirement:** exact database policy versus service-only split and returned projection per viewer.
- **Options:** (1) service role fetches everything with application checks; (2) direct authenticated RLS reads for owner plus server-authorized advisor read; (3) no direct client reads, all reads through a service.
- **Proposed option:** `BLOCKED` pending owner decision. Existing P7 uses service-side advisor authorization, while P6 shows owner RLS precedent; choosing requires a reviewed threat model.
- **Consequence / human decision / acceptance:** direct-read choice changes grants/RLS exposure. Real local tests must deny cross-student/cross-university/unassigned/revoked advisor/analyst access and avoid existence disclosure. `AWAITING HUMAN APPROVAL`.

### A-05 — Service append and RPC/SECURITY DEFINER boundary

- **Sources:** P6 migration `persist_mock_registration_revision`, grants/revokes; P6 threat model; ledger draft.
- **Verified requirement:** service credentials are server-only, bypass RLS, and still require exact application predicates; P6 restricts privileged RPC execution to `service_role`.
- **Missing requirement:** whether P8 uses an RPC, direct service-role insert, or a repository transaction; function ownership/search path/parameter validation if RPC.
- **Options:** (1) SECURITY DEFINER append RPC granted only to service role; (2) direct service-role database inserts behind repository; (3) authenticated-client append.
- **Proposed option:** reject (3). Choose (1) only if atomic parent/evidence/hash enforcement cannot safely reside in the repository; otherwise (2) is simpler. The owner must choose after schema review.
- **Consequence / human decision / acceptance:** any definer function needs fixed safe search path, fully qualified references, strict parameter validation, least EXECUTE grants, and no caller-controlled owner/tenant scope. Local tests must prove anon/authenticated cannot execute or spoof actor/student/university. `BLOCKED`.

### A-06 — Evidence ownership and projection

- **Sources:** `EvidenceReference`; `project_trace_metadata`; umbrella §6; ledger draft access matrix.
- **Verified requirement:** evidence is typed provenance, and redaction must protect student scope.
- **Missing requirement:** whether evidence content is stored versus references only; how restricted source locators/URIs are projected; evidence retention/version lifecycle.
- **Options:** (1) references only; (2) cached source excerpts; (3) external source pointer plus controlled cache.
- **Proposed option:** (1) for smallest Slice 2, because Slice 1 already models references and no approved policy corpus exists.
- **Consequence / human decision / acceptance:** references still require parent-inherited authorization; no independent evidence enumeration. Human approval required for any excerpt/cache. Tests prove evidence cannot be fetched by a user who cannot view parent and does not leak restricted URI/locator. `AWAITING HUMAN APPROVAL`.

### A-07 — Integrity-hash verification boundary

- **Sources:** `canonical.py`, `validation.py`, tests 009–014/028/039; ledger draft.
- **Verified requirement:** hash contract `1.0`, deterministic canonical serialization, valid lowercase SHA-256 shape, and tamper detection are implemented; hash is not authorization/signature.
- **Missing requirement:** persistence-time recomputation location and response behavior for a stored mismatch.
- **Options:** (1) trust caller hash; (2) server recomputes against validated Slice 1 payload; (3) database-only recomputation with a separately duplicated serializer.
- **Proposed option:** (2), to preserve the existing canonicalization algorithm without divergent SQL serialization.
- **Consequence / human decision / acceptance:** stored hash mismatch must be reported as integrity failure and never silently repaired. Approve mismatch operational handling. Unit/integration tests must reject malformed/tampered persistence payloads and prove round-trip verification. `PROPOSED`.

### A-08 — Supersession-chain semantics

- **Sources:** `create_superseding_entry`; tests 015–019; umbrella §5.
- **Verified requirement:** correction is a new identity referencing predecessor ID/hash; no self-supersession or predecessor mutation.
- **Missing requirement:** one-to-one versus branching corrections, status transition policy, predecessor existence/tenant checks, and chain traversal limit.
- **Options:** (1) allow multiple valid corrections from one predecessor; (2) one current successor enforced; (3) no corrections in first slice.
- **Proposed option:** `BLOCKED`; Slice 1 allows construction of a successor but does not settle branching/current semantics.
- **Consequence / human decision / acceptance:** selection affects unique constraints and viewer semantics. Local tests must reject missing/cross-tenant/self predecessor, mutated predecessor, invalid prior hash, and unauthorized correction. `AWAITING HUMAN APPROVAL`.

### A-09 — Replay persistence requirements

- **Sources:** `ReplayRequest`, replay helpers, tests 029–035; ledger draft.
- **Verified requirement:** exact replay fails closed on unavailable source/engine/policy versions; current recomputation is distinct; not-replayable is explicit.
- **Missing requirement:** which immutable references/artifacts are retained, who may invoke replay, and whether Slice 2 persists replay results or only entry metadata.
- **Options:** (1) persist metadata/references only and defer orchestration; (2) persist executable snapshots; (3) disable replay fields.
- **Proposed option:** (1), preserving Slice 1 semantics while limiting scope; no replay endpoint in first slice.
- **Consequence / human decision / acceptance:** human approval needed for artifact retention. Tests prove historic outcome never changes, unavailable versions return explicit failure, and unauthorized caller cannot replay. `PROPOSED`.

### A-10 — RLS/grants and adversarial acceptance gate

- **Sources:** umbrella §6; P6 RLS matrix/migration; P7 migration; test matrix TRACE-15.
- **Verified requirement:** grants and RLS are separate; service role bypass needs application filters; current environment has no P8 DB evidence.
- **Missing requirement:** exact policies/grants/functions and test fixture identities.
- **Options:** (1) unit-only acceptance; (2) real local Supabase acceptance including role-specific direct database/API attempts.
- **Proposed option:** (2), required by `AGENTS.md` and existing security policy.
- **Consequence / human decision / acceptance:** install Supabase CLI/Docker and local-only values. Acceptance has zero skipped P8 security tests and covers insert/update/delete, cross-owner/tenant, advisor assignment revocation, analyst denial, evidence, grants, definer boundary, tamper, supersession, and replay authorization. `BLOCKED`.

## Category B — later P8 capabilities; defer from smallest Slice 2

### B-01 — Regulation RAG source governance

- **Sources:** umbrella §§1, 4, 8–9; RAG draft; source map.
- **Verified requirement:** cited retrieval may explain but cannot decide computable academic facts; missing/conflicting evidence must abstain.
- **Missing/options/consequence:** source authority/hierarchy, ingestion, chunking, licensing, provider, vector store, conflict resolution. No evidence supports choosing a vendor or university corpus.
- **Human decision / acceptance / status:** approve source governance before any RAG runtime; test citations, conflicts, injection, abstention, and deterministic handoff. `AWAITING HUMAN APPROVAL`.

### B-02 — Explainability graph registry and projection

- **Sources:** WC-007/WC-040 roadmap rows; graph draft.
- **Verified requirement:** intended typed DAG and privacy-safe explanation; no graph runtime exists.
- **Missing/options/consequence:** node/edge registry, identity, cycles, depth, storage, projections. Defer from ledger persistence to avoid coupling graph design to trace storage.
- **Human decision / acceptance / status:** approve registry and viewer projections before runtime; cycle/scope/redaction tests required. `AWAITING HUMAN APPROVAL`.

### B-03 — Change-impact semantics

- **Sources:** umbrella §5/§8; impact draft.
- **Verified requirement:** analysis-only; no automatic advisor queues/writes.
- **Missing/options/consequence:** authoritative delta submitter, affected definition, population scan, reporting/retention. Defer; it must not cause ledger schema expansion absent an approved event scope.
- **Human decision / acceptance / status:** approve delta types and user workflows; prove no-write/tenant/suppression behavior. `AWAITING HUMAN APPROVAL`.

### B-04 — Institutional AI metric catalog

- **Sources:** umbrella §1/§6/§8; P6 suppression and tenant policy; query draft.
- **Verified requirement:** aggregate-first, suppression-safe, no arbitrary SQL or student drill-down.
- **Missing/options/consequence:** finite metric list, dimensions, rates, differencing controls, provider/Arabic semantics. Defer; it is not necessary to append traces securely.
- **Human decision / acceptance / status:** approve catalog and operational controls before query runtime; test allowlist, tenant binding, suppression, injection, and grounding. `AWAITING HUMAN APPROVAL`.
