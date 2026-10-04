# What-If Simulator Policy

Policy version: **1.0**

Phase: **P5.1 — policy and contracts only**

## 1. Purpose

The What-If Simulator is an orchestration boundary that applies one finite hypothetical operation to an immutable Academic Digital Twin and delegates all academic decisions to existing deterministic engines. It is not a second eligibility, progress, recommendation, planning, path, intelligence, or delay implementation.

## 2. Supported V1 queries

| Query | V1 classification | Contract |
|---|---|---|
| What if I model completion/pass of X? | `SUPPORTED_V1` | `TWIN_OP_MODEL_COURSE_COMPLETION`; structural completion only. |
| What if I omit/delay X from the next modeled plan? | `SUPPORTED_V1` | `TWIN_OP_OMIT_NEXT_PLAN_COURSE`; P4 Delay Consequence. |
| What if I plan for N credits/courses/options/horizon? | `SUPPORTED_V1` | `TWIN_OP_SET_PLANNING_CONSTRAINTS`; existing Phase 8/9 bounds. |
| What changes between current state and scenario A? | `SUPPORTED_V1` | Factual baseline-versus-scenario comparison. |
| Compare scenario A and scenario B. | `SUPPORTED_V1` | Factual two-scenario comparison on the same base fingerprint. |
| What happens to my modeled path if X is omitted? | `SUPPORTED_V1` | P4 delay plus optional unchanged Phase 9 dual-run comparison. |

## 3. Deferred queries

Hypothetical fail/withdrawal, assume current `IN_PROGRESS` passes, elective preference/pinning, “X is not offered,” transfer/major change, plan-version change, equivalency creation, grade/GPA scenarios, timetable/seat scenarios, goal optimization, and saved/shared scenarios are deferred. “Course not offered” may later become a modeled exclusion constraint only with explicit terminology; V1 omission makes no availability claim.

## 4. Operation validation

Validation is finite and deterministic. It checks exact plan/base identity, fingerprint freshness, operation registry membership, target identity/membership/state, Phase 5 decision where completion is requested, P4 target semantics for omission, existing constraint ranges, duplicates, and cross-operation conflicts. Invalid input returns typed `ScenarioValidationIssue` values; it never partially applies valid operations from an invalid set.

Canonical invalid codes are:

`TWIN_UNKNOWN_OPERATION`, `TWIN_UNKNOWN_COURSE`, `TWIN_TARGET_NOT_PLAN_MEMBER`, `TWIN_TARGET_ALREADY_COMPLETED`, `TWIN_TARGET_IN_PROGRESS`, `TWIN_TARGET_NOT_ELIGIBLE`, `TWIN_TARGET_REVIEW_REQUIRED`, `TWIN_ELECTIVE_GROUP_ALREADY_SATISFIED`, `TWIN_INVALID_CONSTRAINT`, `TWIN_DUPLICATE_OPERATION`, `TWIN_CONFLICTING_OPERATIONS`, `TWIN_TOO_MANY_STRUCTURAL_OPERATIONS`, `TWIN_BASE_IDENTITY_MISMATCH`, `TWIN_STALE_BASE_STATE`, and `TWIN_REQUIRED_CONTEXT_MISSING`.

`TWIN_ELECTIVE_GROUP_ALREADY_SATISFIED` applies only to `TWIN_OP_MODEL_COURSE_COMPLETION` when the target is an incomplete, valid plan-listed elective option, Phase 5 may return `ELIGIBLE`, and the owning elective requirement group is already satisfied under current Phase 6 semantics. The scenario is `INVALID` and the operation is rejected atomically before an overlay is applied: no modeled completion is created, no engine recomputation occurs, no delta is emitted, authoritative state remains unchanged, and modeled state is not applied.

This code does not alter Phase 5 eligibility, relabel the target `NOT_ELIGIBLE`, claim that the target is completed or has no academic value, infer future registration, change requirement-group semantics, or affect actual recommendations or planning. It states only that this hypothetical completion is outside supported P5 V1 scenario scope because the elective requirement is already satisfied. The outcome is `INVALID`, not `REVIEW_REQUIRED`, because the system has sufficient deterministic information; `REVIEW_REQUIRED` remains reserved for an academic-source ambiguity or conflict requiring review.

## 5. Recompute graph

The dependency order is:

```text
Authorized normalized base snapshot
→ validate fingerprint, identity, operation, and constraints
→ clone state and apply modeled overlay
→ Phase 5 eligibility catalog
→ Phase 6 academic progress
→ retain/re-evaluate only structurally modelable P3 context
→ Phase 7 baseline recommendations
→ P4 Decision Intelligence composition/trace
→ Phase 8 semester plans
→ Phase 9 degree paths
→ P4 Delay Consequence where requested
→ typed delta extraction and comparison trace
```

Phase 5 and Phase 6 are recomputed from the same modeled snapshot before dependent engines. P3 history-based evidence is held from the authoritative base, not regenerated from synthetic facts. P4 consumes the resulting structural outputs and admissible base-history factors. Phase 8 uses the approved Phase 7 baseline behavior; Phase 9 reuses Phase 8. Delay is composed, not duplicated. There is no circular feedback.

| Operation | Exact reuse map |
|---|---|
| `TWIN_OP_MODEL_COURSE_COMPLETION` | Validate with Phase 5 → add dedicated modeled completion → recompute Phase 5 catalog and Phase 6 progress → recompute structural/dependency context while retaining authoritative P3 history evidence → Phase 7 → P4 composition/trace → Phase 8 → Phase 9. |
| `TWIN_OP_OMIT_NEXT_PLAN_COURSE` | Invoke P4 Delay Consequence, which reuses Phase 5 transitions, Phase 6 requirement/progress comparison, and optional unchanged Phase 9 baseline/delayed runs. Do not run a duplicate P5 delay graph. |
| `TWIN_OP_SET_PLANNING_CONSTRAINTS` | Validate through Phase 8/9 constraint contracts → rerun Phase 8 for next-set results and Phase 9 when path constraints/results are requested; Phase 9 owns its Phase 5–8 calls. |

## 6. Scenario evaluation

An evaluation validates the complete operation set atomically, preserves the base result, builds a modeled result, invokes only required downstream engines, and emits explicit unavailable facets when context is absent. One operation does not force irrelevant subresults. `REVIEW_REQUIRED` takes precedence for materially ambiguous affected facts; invalid or stale input prevents evaluation.

## 7. Result structure

```text
DigitalTwinEvaluationResult
  contract_version
  scenario_identity
  lifecycle_status
  base_state_reference_and_summary
  modeled_state_reference_and_summary
  operation_results[]
  optional_eligibility_changes
  optional_progress_changes
  optional_recommendation_changes
  optional_semester_plan_changes
  optional_degree_path_changes
  optional_delay_consequence
  deltas[]
  decision_traces[]
  warnings[]
  missing_inputs[]
  limitations[]
  source_engine_policy_versions[]
  simulation_provenance
```

Every comparison preserves `BASE_CURRENT_FACT`, `MODELED_RESULT`, and `DELTA`; modeled values never replace base facts.

## 8. Change/delta model

The closed V1 delta registry contains exactly 16 types:

1. `NEWLY_MODELED_ELIGIBLE`
2. `NO_LONGER_MODELED_ELIGIBLE`
3. `NEWLY_MODELED_COMPLETED_REQUIREMENT`
4. `NO_LONGER_MODELED_SATISFIED_REQUIREMENT`
5. `COMPLETED_PLAN_CREDIT_DELTA`
6. `REMAINING_PLAN_CREDIT_DELTA`
7. `RECOMMENDATION_MEMBERSHIP_CHANGE`
8. `RECOMMENDATION_ORDER_CHANGE`
9. `MODELED_PLAN_CHANGE`
10. `MODELED_PATH_CHANGE`
11. `MODELED_REGISTRATION_SET_COUNT_DELTA`
12. `NEWLY_MODELED_BLOCKED`
13. `NEWLY_MODELED_UNLOCKED`
14. `STRUCTURAL_WARNING_CHANGE`
15. `REVIEW_STATE_CHANGE`
16. `DELAY_CONSEQUENCE_CHANGE`

Each delta identifies its owning engine, base value, modeled value, safe evidence, versions, and limitations. No free-form UI diff creates academic meaning.

## 9. Planning constraints

Constraint changes reuse Phase 8/9 models and validation without new ranges. `0..30` credits is a computational/user-preference bound; `max_courses` is `None` or `1..10`; planner options are `1..10`; path horizon is `1..16`; returned paths are `1..10`. Invalid constraints invalidate the scenario rather than being clamped.

## 10. Degree-path modeling

Phase 9 results remain `MODELED_DEGREE_PATH_ONLY`, bounded by beam width 3, branch width 3, candidate window 15, and the supplied horizon. They are non-global-optimal, know no live offerings or calendars, and provide no graduation guarantee. Allowed wording is “this modeled path contains N modeled registration sets,” never “you will graduate in N semesters.”

## 11. Delay integration

Omission invokes P4 `analyze_delay` and optionally its two-context Phase 9 adapter. P5 preserves the four statuses, twelve reason codes, OR/AND semantics, zero-credit behavior, referenced-only limits, source-conflict precedence, and current-versus-modeled separation. P5 does not recalculate dependency closure independently.

## 12. Missing data

Required missing context produces `INVALID` with `TWIN_REQUIRED_CONTEXT_MISSING` before reliable evaluation. Optional missing Phase 9 context makes path/delay-path comparison unavailable without erasing verified structural delay facts. Missing P3 evidence causes factor abstention, never loss of baseline recommendations.

## 13. Review-required behavior

Material unresolved prerequisite, source conflict, incomplete verified model, or ambiguous existing equivalency produces `REVIEW_REQUIRED` for the affected scenario/facet. Verified independent deltas can remain visible, but the simulator cannot infer the ambiguous consequence or label it no-impact.

## 14. Grade boundary

The simulator never invents a numeric/letter grade, grade point, GPA, threshold, or grade-derived quality. Modeled completion has only synthetic structural `PASSED` semantics. Authoritative raw grades remain unchanged and are neither copied to public results nor interpreted.

## 15. Predictive-risk boundary

Predictive academic risk remains `BLOCKED_BY_EXTERNAL_DATA`. No scenario emits probability of passing/failing, expected grade, success likelihood, calibrated risk, or inferred future performance. Structural warnings remain deterministic and explanation-only.

## 16. AI boundary

A future Advisor may parse a question into a supported operation, ask clarification, invoke the deterministic simulator, and explain its typed output. It cannot invent targets, constraints, operations, offerings, grades, prerequisites, results, or mutations. The deterministic scenario request must be inspectable before execution.

## 17. Privacy

Evaluation is owner-scoped and minimum-necessary. Results omit raw grades, PII, protected attributes, credentials, prompts, full transcript rows, and private source payloads. Logs contain no scenario academic payload by default.

## 18. Determinism

Input order is canonicalized. Equal base fingerprints, operations, constraints, catalogs, and versions produce identical status, deltas, ordering, trace, and limitations. There is no time/random/model/provider input.

## 19. Limitations

V1 uses no live offering, timetable, seat, calendar, registration, transfer, equivalency, grading, or institutional-hold data. It performs bounded structural modeling, not global optimization or prediction. Current `IN_PROGRESS` is not resolved. Scenario outputs expire conceptually when the base fingerprint changes.

## 20. P5.2 implementation contract

P5.2 implements the pure immutable models, validation registry, cloning/overlay, orchestration graph, delta extraction, evaluation, and bounded comparison with no API or persistence. Tests must prove engine reuse, input immutability, current/modeled separation, history preservation, P3 evidence isolation, P4 delay reuse, determinism, conflict rejection, bounds, plan isolation, and safe limitations.
