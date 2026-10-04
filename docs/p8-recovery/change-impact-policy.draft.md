STATUS: RECONSTRUCTED DRAFT — NOT APPROVED

# P8 Change Impact Engine — Recovery Draft

## Verified existing requirements

- P8 defines change impact as analysis-only evaluation of catalog, policy, and curriculum updates without authoritative writes (P8 umbrella policy §§1, 5, 8).
- It may identify affected decisions and flag recomputation; it must not create automatic advisor queues, registration operations, or student-state mutations.
- Existing Digital Twin/What-If boundaries are immutable, scoped, and non-authoritative; existing decision traces preserve historical versions and support exact/current/not-replayable comparison.

## Requirements derived from existing implementation

No Change Impact package, API, migration, queue, graph runtime, or test exists. Slice 1 provides version and supersession fields that a later impact evaluator could reference, but it does not determine affected populations or persist results.

## Proposed analysis contract — requires approval

1. Input is a typed proposed or observed version delta: policy, curriculum, prerequisite, or plan revision. It includes old/new identifiers and versions, authoritative source/provenance, and declared scope.
2. Evaluation is read-only and bounded. It produces an impact report separating: affected catalog entities; potentially affected student plans; affected deterministic decisions/recommendations; affected traces whose historic basis differs; unknown/unavailable scope.
3. A report distinguishes historical facts from current recomputation. A history row is never rewritten; a later approved process may create a separate superseding trace only through the ledger boundary.
4. An impact claim must cite the deterministic engine/version and input delta that produced it. Missing source versions or unresolved prerequisites yield explicit uncertainty/review, never inferred eligibility.
5. Individual-level results require owner or P7 advisor authorization. Institutional results must be aggregate-first and comply with minimum-disclosure suppression.

## Security and privacy boundaries

- No automatic write to student profile, attempt, catalog, registration, assignment, advisor queue, or notification system.
- No cross-university candidate scan; repository/service predicates must bind every query to the authorized university.
- Analysts do not drill into individual students, plans, or trace IDs. Suppressed aggregates remain suppressed after filtering.

## Open contracts / requires human approval

- Which actor may submit a change delta; authoritative catalog/policy source of truth; scope enumeration strategy; retention; batching/rate limits; legal/operational notification workflow; and whether impact reports are ledger-material.
- Exact definitions of “affected”, materiality thresholds, and any advisor-facing workflow are OPEN CONTRACTS.

## Explicit non-goals

No automatic remediation, plan migration, recommendation rewrite, enrollment transaction, advisor queue, notification, prediction, or production synchronization.

## Acceptance criteria for later implementation

Approved delta schema and authorization matrix; deterministic fixtures for each change class; tests for no writes, version attribution, uncertainty propagation, owner/advisor scope, analyst suppression, tenant isolation, and historic-versus-current separation.
