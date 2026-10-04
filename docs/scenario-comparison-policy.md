# Scenario Comparison Policy

Policy version: **1.0**

Phase: **P5.1 — policy and contracts only**

## Purpose and scope

Scenario comparison presents explicit factual differences between immutable results produced from the same authoritative base. V1 supports exactly:

1. authoritative baseline versus one evaluated scenario; and
2. scenario A versus scenario B, where both share the same base-state fingerprint and compatible engine/policy/source versions.

One request compares at most two sides. Multi-scenario ranking, tournaments, saved portfolios, and automatic winner selection are deferred.

## Preconditions

Both sides must be evaluated, non-stale, authorized to the same student context, plan-scoped to the same normalized university/major/plan/version, and version-compatible. `INVALID` or `STALE_BASE_STATE` results cannot be compared. `REVIEW_REQUIRED` results may be compared only with the unresolved facets explicitly marked non-comparable.

## Allowed metrics

Comparison may show only typed values owned by existing engines or the approved delta registry:

- eligibility transitions and review-state changes;
- completed/remaining plan credits and requirement-group satisfaction;
- recommendation membership and order, retaining baseline and final ranks;
- semester-plan course sets, modeled credits, group completions, and unlocks;
- Phase 9 modeled registration-set count only for comparable modeled-complete paths, plus termination, blockers, canonical path differences, and modeled progress at equal horizon;
- P4 Delay Consequence statuses, affected dependency paths, requirement/progress deltas, and optional path differences;
- structural warnings and explicit missing inputs/limitations;
- source, policy, engine, scenario, and provenance references.

## Disallowed metrics

V1 prohibits an overall score, “best” scenario, hidden weighted utility, predicted graduation date, expected grade/GPA, success/failure probability, predictive risk, course-offering likelihood, timetable/seat claims, institutional registration permission, and untyped LLM preference. Missing values never become zero.

## No overall score or hidden preference

There is no `Scenario Score`, composite percentage, or default winner. Comparison is factual. A future typed objective requires a separately versioned policy defining its admissible inputs, precedence, and tests. V1 does not add `STRUCTURAL_PROGRESS`, minimize-set, maximize-unlock, or other objective ranking.

## Deterministic ordering

Sides remain in caller-declared order (`BASELINE`, then scenario; or scenario A, then B). Delta categories use the fixed registry order in `digital-twin-delta-matrix.md`, then stable target/group/course/path identifiers. The comparison never reorders sides based on values.

## Missing-data and review handling

Each metric is `COMPARABLE`, `NOT_COMPARABLE`, or `REVIEW_REQUIRED`. A missing optional subresult affects only its metric. Material source conflict carries exact review evidence and cannot produce a positive, negative, equal, or “better” conclusion. Version mismatch is a comparison validation failure unless an explicit future compatibility contract exists.

## Comparison trace

```text
ScenarioComparisonTrace
  comparison_contract_version
  comparison_type: BASELINE_VS_SCENARIO | SCENARIO_VS_SCENARIO
  base_state_fingerprint
  left_scenario_reference
  right_scenario_reference
  left_operations[]
  right_operations[]
  compared_metrics[] {delta_type, source_engine, status, left_value, right_value}
  excluded_metrics[] {reason_code}
  source_engine_policy_versions[]
  simulation_provenance[]
  limitations[]
```

The trace states which operation was applied, which owning engine changed, which versions produced both values, which facts remained authoritative, and which outputs are modeled. It contains no chain-of-thought.

## Modeled language

Use “under this modeled academic scenario,” “modeled result,” “modeled registration set,” “structural difference,” and “comparison unavailable.” Never use “will graduate,” “will pass/fail,” “official schedule,” “registered,” “course will be offered,” or “best choice.”

## Determinism, privacy, and authorization

Equal normalized result pairs produce identical comparisons. Comparison performs no engine recalculation, persistence, network request, or LLM call. Both sides must be authorized to the same owner; scenario references do not grant access. Output is minimized and excludes raw grades, PII, prompts, protected attributes, and source payloads.

## P5.2 contract

Implement comparison after scenario evaluation and delta extraction. It consumes typed evaluation results only, enforces same-base/version preconditions, emits the closed metric/delta vocabulary, and is covered by identical, changed, review, missing, stale, reordered-input, and cross-base rejection tests.
