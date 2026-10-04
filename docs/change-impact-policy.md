Status: **APPROVED POLICY CONTRACT**

# P8 Change Impact Engine

## Verified existing requirements

- P8 defines change impact as analysis-only evaluation of catalog, policy, and curriculum updates without authoritative writes (P8 umbrella policy Â§Â§1, 5, 8).
- It may identify affected decisions and flag recomputation; it must not create automatic advisor queues, registration operations, or student-state mutations.
- Existing Digital Twin/What-If boundaries are immutable, scoped, and non-authoritative; existing decision traces preserve historical versions and support exact/current/not-replayable comparison.

## Requirements derived from existing implementation

WC-046 V1 now has a pure proposed-delta evaluator, authenticated institutional and assigned-advisor APIs, a focused institutional form, and a required Decision Trace producer. It creates no migration, report table, queue, notification, or authoritative academic-state write. It does not enumerate a student population.

## Operational specification requirements

1. V1 input is a typed **proposed analyst change**, not a published university change. The four closed types are prerequisite group, requirement group required credits, plan-course credit hours, and policy version. It includes old/new values and versions, bounded provenance, and declared scope. An authorized analyst may evaluate a proposal but cannot publish it.
2. Evaluation is read-only and bounded. It produces an ephemeral impact report separating directly affected facts, bounded downstream course dependencies, potentially affected deterministic decision classes, safe recomputations, and unavailable scope. It never scans students or reports cohort counts.
3. A report distinguishes historical facts from current recomputation. A history row is never rewritten; a later approved process may create a separate superseding trace only through the ledger boundary.
4. An impact claim must cite the deterministic engine/version and input delta that produced it. Missing source versions or unresolved prerequisites yield explicit uncertainty/review, never inferred eligibility.
5. V1 individual results require the exact P7 assigned-advisor predicate; no student delta-submission endpoint exists. Institutional results are structural-only with no student scan or counts, so no aggregate suppression is invoked.

## Security and privacy boundaries

- No automatic write to student profile, attempt, catalog, registration, assignment, advisor queue, or notification system.
- No cross-university cohort scan; repository/service predicates must bind every query to the authorized university.
- Analysts do not drill into individual students, plans, or trace IDs. Suppressed aggregates remain suppressed after filtering.

## Owner-approved V1 governance

- **Authority:** `PROPOSED_ANALYST_CHANGE`; active institutional membership authorizes tenant-scoped analysis, not publication. Advisor analysis requires the P7 active-role, exact-assignment, and same-university predicate before student data load.
- **Affected:** an item directly depends on the changed fact, consumes the changed entity/version, changes under safe deterministic recomputation, or becomes unresolved because of the changed fact. Same-plan membership alone does not qualify.
- **Statuses:** `UNCHANGED`, `CHANGED`, `REVIEW_REQUIRED`, and `UNKNOWN` are closed. Baseline mismatch, unresolved evidence, fan-out overflow, unmapped policy prose, and unavailable recomputation inputs are explicit limitations.
- **Simulation:** immutable request-scoped catalog copies; existing eligibility and progress engines recompute only with complete inputs. Recommendation, planner, and path effects remain structural where exact constraints are absent. Fan-out is capped at 100 courses and depth 20.
- **Provenance:** old/new versions are proposed input values. V1 verifies computable old baseline facts but cannot prove every declared source version is the current published version. Client provenance text is digested in the response; policy prose never infers an academic-rule change.
- **No write:** student and catalog state, registration, assignment, queue, and notifications remain unchanged. The only allowed persistence is the required trusted `CHANGE_IMPACT_EVALUATION` Decision Trace sidecar; an append or retry-reconciliation failure makes the API fail closed.
- **Human review:** `requires_human_review=true` is the owner-approved V1 meaning of “queues required human review.” It creates no queue row, staff assignment, task, or notification.
- **Report lifecycle:** the report is ephemeral and `NOT_REPLAYABLE` with `CHANGE_IMPACT_V1_EPHEMERAL_REPORT`. Determinism alone cannot reconstruct historical inputs. The ledger uses deterministic retry identity and remains append-only.
- **Surfaces:** analyst receives structural facts only, no student drill-down or population scan. Assigned advisor receives only the authorized student's safe recomputations. No advisor frontend or student delta-submission endpoint is added.

## Remaining future contracts / requires human approval

- Trusted published-change providers, exact source-version verification, plan-version transition, broader batching/rate limits, and operational notification workflow require separate approval. Reports have no persistence table; ledger retention remains under the existing ledger contract.
- A persisted advisor review queue or additional materiality threshold is not approved in V1.

## Explicit non-goals

No automatic remediation, plan migration, recommendation rewrite, enrollment transaction, advisor queue, notification, prediction, or production synchronization.

## Acceptance criteria for later implementation

V1 requires typed-delta, baseline, fan-out, immutable-copy, safe recomputation, authorization, audit-failure/idempotency, and Local Supabase no-write/tenant tests. Future student-owner or population analytics require a separately approved access and suppression contract.
