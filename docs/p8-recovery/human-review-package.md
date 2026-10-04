STATUS: HUMAN REVIEW PACKAGE — NO CONTRACT APPROVAL GRANTED

# P8.1 Contract Audit: Human Review Package

## What is actually verified

- Repository baseline on `chore/p8-recovery-baseline` at `721b317fbb73e6de0cadc8201c6ea1f6849433dc` is **1359 passed, 13 Local Supabase skips** from repository root. Slice 1 focused tests are **40 passed**. No P8 database security test exists.
- Slice 1 (`apps/api/app/decision_trace/`) provides immutable typed records, closed materiality registry, deterministic canonical JSON/SHA-256 integrity verification, validation, supersession helpers, replay availability, and structural redaction. See [domain implementation](../decision-trace-domain-implementation.md) and `apps/api/tests/test_decision_trace.py`.
- Existing P7 advisor access is a strict conjunction: verified identity, active `ACADEMIC_ADVISOR`, exact active advisor-student assignment, and authoritative same-university scope. See [advisor authorization policy](../advisor-authorization-persistence.md) and `apps/api/app/advisor_service/authorization.py`.
- Existing P6 establishes security precedents: grants and RLS are distinct, client writes are denied, service credentials remain server-only, and institutional results are aggregate/suppression-safe. See [RLS matrix](../mock-registration-rls-access-matrix.md) and [threat model](../mock-registration-threat-model.md).

## What is missing

Six canonical P8 companion files remain zero bytes and were not overwritten:

- `docs/decision-trace-ledger-policy.md`
- `docs/institutional-policy-retrieval-policy.md`
- `docs/academic-explainability-graph-policy.md`
- `docs/change-impact-policy.md`
- `docs/institutional-ai-query-policy.md`
- `docs/p8-grounded-knowledge-test-matrix.md`

Their original detailed content is unavailable in Git history. The nonempty [P8 umbrella policy](../p8-grounded-knowledge-decision-trace-policy.md) is real but cannot substitute for the missing detailed contracts.

## What was reconstructed for review

The original recovery set contains six review-only drafts (ledger, RAG, graph, impact, institutional query, and a 54-scenario candidate matrix) plus the [source map](reconstruction-source-map.md). This package adds the decision register, proposed Slice 2 plan, and this review document. None is a restored original or approved policy. They preserve existing Slice 1/P6/P7 boundaries and explicitly label unknowns.

The [decision register](contract-decision-register.md) separates required Slice 2 choices (Category A) from later P8 work (Category B). The [proposed Slice 2 plan](slice2-implementation-plan.draft.md) defines only the smallest candidate persistence/security scope and supplies no schema or code.

## Decisions required before Slice 2

1. Which approved material events persist first.
2. Parent/evidence schema and whether references only or cached content are stored.
3. Retention, deletion/erasure, and privileged operational authority.
4. Owner/advisor read architecture and exact database versus service authorization split.
5. Direct service persistence versus a narrowly granted SECURITY DEFINER RPC.
6. Evidence projection and restricted locator/URI handling.
7. Hash mismatch operational behavior.
8. Supersession branching/current-successor semantics.
9. Exact replay artifact retention and viewer scope.
10. Local Supabase security acceptance gate, including required fixtures and zero-skipped P8 tests.

## Decisions that may be deferred

University Regulation RAG source governance/runtime, Explainability Graph registry/runtime, Change Impact semantics/runtime, and Institutional AI metric catalog/runtime. Deferral must preserve existing P8 umbrella constraints; none is needed to append an approved ledger entry securely.

## What begins only after approval

After Category A decisions, approved canonical policy promotion, and local Supabase readiness, implementation may begin on the smallest ledger persistence slice: append-only parent/evidence storage, a service-side append boundary, owner/advisor-safe retrieval, and adversarial database security tests. It must not add RAG, graph, impact, institutional query, UI, exports, retention jobs, or new academic decision logic.

## Required acceptance evidence

- Approved Category A register entries and canonical policy decision.
- Local-only migration replay; no production database operation.
- Manual inspection of effective tables, constraints, RLS, grants, and any RPC/SECURITY DEFINER function.
- Tests for direct insert/update/delete denial, owner isolation, advisor assignment/revocation/same-university checks, analyst denial, evidence inheritance, cross-tenant denial, hash tamper rejection, supersession, replay scope, and no hidden reasoning storage.
- All Slice 2 local database security tests executed with zero skips; focused and root regression tests pass.

## Current status

P8.1 is **PARTIAL / AWAITING HUMAN APPROVAL**. P8 Runtime Slice 2 is **NOT ACCEPTED**. No claim of production-ready security or completed contracts is supported.
