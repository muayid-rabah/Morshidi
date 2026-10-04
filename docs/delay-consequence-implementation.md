# Delay Consequence Implementation — P4.2

## 1. Purpose

`analyze_delay` implements specialized deterministic structural consequence analysis for one plan target. It is not a general What-If engine and performs no I/O or mutation.

## 2. Policy version

`DELAY_CONSEQUENCE_POLICY_VERSION = "1.0"` with exactly four states and twelve `DELAY_*` reason codes.

## 3. Inputs

`DelayConsequenceInput` carries target and plan identity, immutable attempts, progress and eligibility catalogs, current Phase 6 progress, source versions, simulation provenance, and optional baseline/delayed Phase 9 results. Required context is validated before analysis.

## 4. Target semantics

The target must be an actual member of both normalized plan catalogs. Unknown and referenced-only targets return `INSUFFICIENT_DATA`. `COMPLETED` returns no modeled impact without rewriting history. `IN_PROGRESS` returns `REVIEW_REQUIRED`. An unresolved/source-conflict target also returns review.

## 5. Direct impact

For each dependent containing the target in an explicit dependency group, the engine invokes Phase 5 against a baseline hypothetical target pass and the unchanged delayed state. Direct impact exists only for an `ELIGIBLE` to non-eligible transition.

## 6. OR prerequisites

Because direct impact delegates to Phase 5, a currently passed alternative in the same OR group prevents a false impact. An unsatisfied second AND group likewise prevents a false transition. Raw prerequisite text is never parsed.

## 7. Transitive impact

The engine performs a sorted, cycle-safe breadth-first traversal over verified dependency groups starting from direct transitions. It records the canonical minimum depth and evidence path. An unimpacted OR option conservatively prevents a certain transitive claim. Depth is graph structure, not time.

## 8. Requirement/progress impact

Phase 6 is invoked over baseline hypothetical completion and delayed state. The result compares group satisfaction, remaining need, completed-plan credits, remaining credits, and affected group codes. Current progress remains a separate unchanged input.

## 9. Electives

For an elective target, eligible alternatives in the same group are simulated through Phase 5/6. When an alternative preserves the target scenario's satisfaction and remaining need, it becomes the delayed modeled substitute and prevents false requirement impact.

## 10. Zero-credit

Required zero-credit targets participate in Phase 6 mandatory completion and dependency analysis. They can create requirement or dependency impact while modeled credit delta remains zero.

## 11. Referenced-only

Referenced-only identities may remain prerequisite evidence but cannot become plan targets, progress courses, or requirement groups. They receive no plan-credit effect.

## 12. Source conflicts

A material downstream rule explicitly connected to the target and marked unresolved/source-conflict causes `REVIEW_REQUIRED`. No direct certainty is fabricated. Independently verified requirement/progress facts may remain in the result with the conservative overall state.

## 13. Degree-path comparison

`compare_degree_path_results` compares outputs from two unchanged Phase 9 runs. `run_degree_path_comparison` owns those two calls over explicit baseline and delayed contexts; it does not reproduce or modify beam search.

## 14. Result states

The only states are `NO_MODELED_STRUCTURAL_IMPACT`, `MODELED_STRUCTURAL_IMPACT`, `REVIEW_REQUIRED`, and `INSUFFICIENT_DATA`. Review takes precedence over otherwise modeled impacts; missing required context prevents a no-impact conclusion.

## 15. Reason codes

The enum implements exactly: `DELAY_TARGET_ALREADY_COMPLETED`, `DELAY_TARGET_IN_PROGRESS_UNRESOLVED`, `DELAY_NO_MODELED_STRUCTURAL_IMPACT`, `DELAY_DIRECT_DEPENDENCY_AFFECTED`, `DELAY_TRANSITIVE_DEPENDENCY_AFFECTED`, `DELAY_REQUIREMENT_PROGRESS_AFFECTED`, `DELAY_MODELED_CREDIT_PROGRESS_AFFECTED`, `DELAY_MODELED_PATH_CHANGED`, `DELAY_MODELED_PATH_UNCHANGED`, `DELAY_ELECTIVE_SUBSTITUTE_AVAILABLE`, `DELAY_RULE_REVIEW_REQUIRED`, and `DELAY_CONTEXT_INSUFFICIENT`. Output uses enum declaration order.

## 16. Evidence/trace

Typed evidence covers target, dependency group, requirement group, progress delta, and path comparison. A result also carries baseline/delayed scenario references, direct/transitive paths, reason codes, missing inputs, versions, limitations, and simulation provenance.

## 17. Determinism

Collections are sorted canonically. Tests reverse course, dependency, attempt, and evidence inputs. There is no clock, randomness, set-order output, database, HTTP, LLM, or mutation.

## 18. Performance

Direct evaluation is bounded by plan size and reuses in-memory Phase 5. Transitive traversal is cycle-safe. A synthetic 120-course chain completed the benchmark test body in less than 0.005 seconds on the validation host. Phase 9 retains its existing bounded search.

## 19. Limitations

Results are modeled structural differences, not offering, calendar, registration, outcome, or graduation-date predictions. The engine makes no global-optimality claim. Optional path comparison is unavailable unless both explicit Phase 9 contexts/results exist.

## 20. Digital Twin reuse

`SimulationProvenance` distinguishes `AUTHORITATIVE` and `SIMULATED` states and requires parent/scenario identity for clones. The engine consumes normalized snapshots without assuming database origin.

## 21. P5 reuse contract

P5 may call the pure delay engine from a general immutable scenario framework and may supply two Phase 9 contexts for comparison. It must preserve the omission meaning, finite states/reasons, current-versus-modeled separation, and no-write boundary. Scenario CRUD, persistence, What-If API, and UI are not implemented here.
