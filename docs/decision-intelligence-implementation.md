# Decision Intelligence Implementation — P4.2

## 1. Purpose

P4.2 implements the bounded P4.1 integration contract as a pure package. It composes existing deterministic outputs; it does not change Phase 5–9 engines, add an API, persist results, or invoke an LLM.

## 2. Policy version

`DECISION_INTELLIGENCE_INTEGRATION_POLICY_VERSION = "1.0"`. P3, Phase 7, Phase 8, and Phase 9 retain their independent version `1.0` identifiers.

## 3. Architecture

`app.decision_intelligence` contains immutable models, the closed factor registry and readiness adapter, trace helpers, Phase 7 composition, Phase 8/9 post-result annotations, the Delay Consequence engine, and read-only orchestration. The package has no FastAPI, Starlette, Supabase, HTTP, OpenAI, SQLAlchemy, repository, clock, randomness, or global mutable state dependency.

## 4. Decision modes

`STRUCTURAL_BASELINE` is the default and abstains from readiness ordering. `READINESS_AWARE` explicitly enables the single approved readiness tie-break. Academic hard gates are identical in both modes.

## 5. Baseline preservation

The wrapper receives or invokes the unchanged Phase 7 `RecommendationResult` and retains it verbatim as `baseline_result`. Candidate membership, candidate instances, reason codes, and priority tuples are unchanged. Phase 8 and Phase 9 annotations retain the original result object and cannot feed back into search or ranking.

## 6. Factor classification

`classify_factor` implements the closed `HARD_GATE`, `ORDERING_FACTOR`, `EXPLANATION_ONLY`, and `NOT_ALLOWED` registry. All 19 P3 signals are classified. Unknown factors raise `ValueError`; raw grades, predictive risk, domain inference, demographics, and AI-generated scoring are not accepted as execution inputs.

## 7. Readiness integration

`evaluate_readiness_factor` consumes an existing P3 `IntelligenceResult`. It verifies explicit mode, bound course identity, evidence admissibility, provenance completeness, P3 policy version, capability, status, and readiness state. It never recalculates readiness.

## 8. Tie-break semantics

Candidates first remain grouped by exact Phase 7 P1–P5 values. A group is readiness-sorted only when every candidate has an applicable readiness result. Preparation evidence and not-applicable receive the same categorical preference; caution follows them. If any candidate abstains, the whole group retains baseline P6/P7 order. No numeric score or cross-group promotion exists.

## 9. Abstention

Typed reasons cover baseline mode, missing result, status, review required, identity mismatch, policy mismatch, unverified evidence, incomplete provenance, and unsupported state. Abstention has no numeric fallback and therefore cannot be misread as caution.

## 10. Decision trace

`DecisionIntelligenceTrace` records decision type/mode, base/integration/intelligence versions, baseline order, applied and ignored factor evaluations, minimized evidence references, changed relative orders, final order, limitations, and simulation provenance. It contains no generated prose or chain-of-thought and is not persisted.

## 11. Phase 7 behavior

`integrate_recommendations` provides immutable `DecisionCandidateView` objects with baseline and final ranks. The existing `RecommendationCandidate` remains unchanged. `recommend_with_decision_intelligence` invokes Phase 7 once over already-loaded catalogs/state and then composes P4.

## 12. Phase 8 annotations

`annotate_semester_plans` attaches safe categorical P3 reason codes to the courses in each already-ranked option. It cannot change the candidate window, DFS, constraints, membership, priority tuple, selected courses, or order.

## 13. Phase 9 preservation

`annotate_degree_paths` operates after Phase 9 and does not alter state keys, beam retention, branches, transitions, termination, priority tuples, or ranks. `run_degree_path_comparison` invokes unchanged Phase 9 once for each explicitly supplied immutable context and compares the results externally.

## 14. Negative-feedback safeguards

Readiness cannot remove candidates, cross structural P1–P5 differences, affect planner/path ranking, or turn difficulty/history into prohibition. Any abstention preserves baseline ordering. Required progression remains visible, and all historical signals are recomputed rather than stored as permanent penalties.

## 15. Privacy

The implementation exposes categorical states, finite reason codes, course identifiers needed for explanation, minimized evidence references, versions, and limitations. It accepts no demographic factor and copies no raw grade, prompt, credential, full transcript, or source-reference payload into P4 results.

## 16. Performance

Core integration uses zero database reads and no per-candidate network/model call. Recommendation composition is grouping plus stable sorting. The 120-course synthetic delay-chain benchmark completed its test body below pytest's 0.005-second reporting threshold on the validation host; the complete one-test command took 0.10 seconds.

## 17. Persistence decision

All results are computed on demand. P4.2 creates no migration, trace table, readiness-ranking table, delay table, scenario table, cache, or write service.

## 18. Known limitations

Only readiness may alter Phase 7 ties. Risk remains non-predictive and explanation-only. Phase 8/9 remain structural baseline. No UI/API exposes P4 yet. The path comparison adapter requires two explicit normalized contexts; creating a general scenario or persisted clone belongs to P5.

## 19. P5 entry conditions

P5 may begin only after P4.2 full regression and closure. It may reuse immutable simulation provenance, factor/trace contracts, the enhanced recommendation view, annotation contracts, Delay Consequence, and the two-context Phase 9 comparison adapter. P5 must separately define a general scenario lifecycle, cloning rules, authorization/privacy, What-If operations, comparison semantics, and any API/UI; it may not weaken P4 hard gates or retroactively mutate authoritative state.
