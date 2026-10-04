# Delay Consequence Intelligence Policy

Contract version: **1.0**

Phase: **P4.1 — policy and contract only**

## 1. Definition

Delay Consequence Intelligence is deterministic modeling of structural academic consequences when a selected plan course is not completed or not selected at a modeled point. V1 compares the same immutable starting state under a baseline structural scenario and a target-delayed scenario. It reports verified dependency, requirement, progress, and optional Phase 9 modeled-path differences.

“Delay” means omission of the target from the first modeled registration set in which the baseline scenario selects it. The target may be selected in a later modeled set. It does not mean the course is unavailable, failed, withdrawn, or postponed by a real calendar term.

## 2. Non-goals

V1 does not predict a graduation date, course offering, seat, timetable, student outcome, failure probability, calendar duration, official registration eligibility, or institutional decision. It does not implement a general What-If Simulator or Digital Twin, modify Phase 7–9 policy, mutate records, persist scenarios, or parse unresolved prerequisite text.

## 3. Inputs

The pure V1 contract consumes:

```text
DelayConsequenceInput
  target_course_code
  academic_state_snapshot
  study_plan_id
  plan_membership_and_requirement_groups
  verified_course_dependency_graph
  phase5_eligibility_catalog
  phase6_current_progress
  phase7_baseline_recommendation_context
  optional_phase9_constraints
  source_versions[]
  simulation_provenance
```

The academic state contains explicit attempt outcomes and reported facts already accepted by the owning engines. Live offerings are not required. Inputs are normalized and plan-scoped; Plan 12 may be a fixture but no course code is hardcoded.

## 4. Current-state vs modeled-state semantics

`CURRENT_FACT` is the unchanged authoritative starting snapshot: recorded attempts, current Phase 5 decisions, and current Phase 6 progress. `MODELED_CONSEQUENCE` is a derived difference between two pure simulations and never overwrites current facts.

The result labels every field as current, baseline-modeled, or delayed-modeled. Hypothetical `PASSED` outcomes use Phase 9 semantics only inside cloned in-memory state. The result retains `AUTHORITATIVE` or `SIMULATED` provenance plus parent snapshot/scenario references.

## 5. Direct dependency impact

A course is directly affected only when the target is an option in one of its verified prerequisite dependency groups and omitting the target leaves that group unsatisfied in the delayed scenario while the baseline scenario satisfies it. OR alternatives are evaluated: if another verified option satisfies the same group, that dependent is not directly affected. Direct impact means a verified dependency transition, not a semester delay.

Outputs include sorted directly affected course codes, each affected group, whether the affected course is a plan member, its requirement type when applicable, and evidence edges.

## 6. Transitive dependency impact

Transitive impact is the verified graph closure starting from direct impacts. A course is transitively affected only when at least one verified path of dependency transitions is supported by scenario evaluation. The result reports the minimum dependency depth and supporting course-code path. Depth counts graph edges, not semesters or calendar units. Cycles or inconsistent graph structure are integrity failures; unresolved/conflicting edges do not become inferred paths.

## 7. Requirement impact

Requirement impact is computed through Phase 6 semantics, not by treating every listed course as mandatory. The result compares requirement-group satisfaction, remaining modeled need, mandatory-course completion, and elective substitutes between baseline and delayed scenarios. It reports only groups whose modeled state differs.

## 8. Progress impact

Current completed credits and current requirement states never change. Modeled deltas compare baseline versus delayed snapshots and may include modeled completed-plan-credit difference, remaining-plan-credit difference, groups newly not satisfied, and required zero-credit completion differences. A zero credit delta does not imply no structural impact.

## 9. Degree-path comparison

When complete Phase 9 inputs and constraints are available, the delay engine invokes the unchanged Phase 9 engine twice: once for the baseline state and once with the target excluded from the first modeled registration set in which baseline selects it. It never recreates beam search.

Safe comparison fields are modeled registration-set count delta when both comparable paths reach `MODELED_COMPLETE`, modeled completed-credit delta at the same horizon, newly introduced blockers, path termination-status differences, and canonical path differences. “+1 modeled registration set” is not “one semester of guaranteed graduation delay.” If Phase 9 context is absent, structural analysis still succeeds and path comparison is explicitly unavailable.

## 10. Electives

Delaying one elective has no requirement-progress impact when the group can still be satisfied by another verified eligible option in the modeled comparison. Dependency impacts specific to that elective may still exist and are reported separately. If no substitute remains and the group need cannot be satisfied, requirement impact is reported. The engine never treats every listed elective as mandatory.

## 11. Zero-credit requirements

Required zero-credit courses participate in mandatory-course and dependency semantics exactly like positive-credit required courses. Delay may block requirement-group satisfaction or downstream courses even when modeled credit delta is zero. Credit-only logic cannot suppress the impact.

## 12. Referenced-only courses

A referenced-only course is not a valid plan target and creates no plan progress or requirement impact. It may appear as a dependency node or evidence path when canonical data explicitly references it. A request to delay a referenced-only target returns `INSUFFICIENT_DATA` with the target-not-plan-member reason; the engine does not invent plan membership.

## 13. Source conflicts

If target semantics or a material downstream relation relies on `unresolved`, `source_conflict`, or an incomplete purportedly verified rule, the engine does not assert that consequence. It returns `REVIEW_REQUIRED`, lists the affected edges/courses, and preserves the exact Phase 5 review evidence. Verified independent impacts may be listed as facts, but the overall status remains conservative.

## 14. Missing data

Missing target identity, plan membership, current progress, dependency graph, or required source versions returns `INSUFFICIENT_DATA`; no zero-impact claim is made. Missing optional Phase 9 context omits only path comparison. Partial inputs identify exactly which facet is unavailable. An already passed target produces a valid no-new-delay result because current completion is not reversed. An `IN_PROGRESS` target preserves current Phase 9 conservative semantics and reports review/limitation rather than assuming pass or failure.

## 15. Reason codes

V1 has exactly twelve finite decision reason codes:

| Code | Meaning |
|---|---|
| `DELAY_TARGET_ALREADY_COMPLETED` | Current completion is preserved; no new modeled omission is asserted. |
| `DELAY_TARGET_IN_PROGRESS_UNRESOLVED` | Current in-progress outcome is not assumed to pass or fail. |
| `DELAY_NO_MODELED_STRUCTURAL_IMPACT` | Complete available comparison found no structural difference. |
| `DELAY_DIRECT_DEPENDENCY_AFFECTED` | At least one verified direct dependent changes state. |
| `DELAY_TRANSITIVE_DEPENDENCY_AFFECTED` | At least one verified downstream path changes state. |
| `DELAY_REQUIREMENT_PROGRESS_AFFECTED` | Requirement satisfaction or remaining need differs. |
| `DELAY_MODELED_CREDIT_PROGRESS_AFFECTED` | Modeled plan-credit progress differs. |
| `DELAY_MODELED_PATH_CHANGED` | Phase 9 comparison differs in a permitted path metric. |
| `DELAY_MODELED_PATH_UNCHANGED` | Complete Phase 9 comparison has no permitted path difference. |
| `DELAY_ELECTIVE_SUBSTITUTE_AVAILABLE` | Another verified option preserves requirement progress. |
| `DELAY_RULE_REVIEW_REQUIRED` | A material rule is unresolved, conflicting, or incomplete. |
| `DELAY_CONTEXT_INSUFFICIENT` | Required input for a reliable result is absent or mismatched. |

No free-form text decides status. Presentation text is derived from codes and structured facts.

## 16. Evidence

Evidence references include target plan membership, dependency group/option identifiers, exact Phase 5 decision/review codes, Phase 6 group and course states, Phase 7 baseline context, Phase 9 result/path references when invoked, source versions, and policy versions. Raw grades, prompts, source documents, and unnecessary student history are excluded. Evidence collections are stably sorted.

## 17. Result contract

The smallest coherent top-level state vocabulary is:

- `NO_MODELED_STRUCTURAL_IMPACT`
- `MODELED_STRUCTURAL_IMPACT`
- `REVIEW_REQUIRED`
- `INSUFFICIENT_DATA`

Specific impact types are orthogonal facets, not competing states:

```text
DelayConsequenceResult
  contract_version
  status
  target_course_code
  current_facts
  baseline_scenario_reference
  delayed_scenario_reference
  directly_affected_courses[]
  transitively_affected_courses[] {course_code, minimum_depth, evidence_path}
  requirement_impacts[]
  progress_impact
  optional_degree_path_comparison
  reason_codes[]
  evidence_references[]
  missing_inputs[]
  limitations[]
  source_and_policy_versions[]
  simulation_provenance
```

`REVIEW_REQUIRED` takes precedence over impact/no-impact when ambiguity is material. `INSUFFICIENT_DATA` applies when required context is absent before a reliable comparison. Otherwise any verified facet difference yields `MODELED_STRUCTURAL_IMPACT`; no differences across every available required facet yields `NO_MODELED_STRUCTURAL_IMPACT`.

## 18. Determinism

Identical normalized snapshots, catalogs, constraints, source versions, and policy versions produce an identical result and stable ordering. The engine has no time, randomness, network, repository, LLM, or write operation. It reuses already-loaded context, Phase 5/6 outputs, and optional Phase 9 results; no per-course database query or model call is allowed.

## 19. Privacy

The result exposes safe codes, course/group identifiers necessary for explanation, aggregate deltas, minimized evidence references, limitations, and versions. It does not copy raw grades, full transcript rows, private source references, protected attributes, prompts, or chain-of-thought. Owner and advisor authorization are orchestration responsibilities outside the pure engine.

## 20. Digital Twin reuse

Delay Consequence is a specialized pure analysis reusable by the future Academic Digital Twin and general What-If Simulator. It accepts either authoritative or cloned state through the same snapshot contract and always propagates scenario provenance. It remains independent of scenario persistence, UI, and transaction execution.

## 21. P4.2 implementation contract

P4.2 may implement immutable input/result/evidence models, verified graph indexing, pure direct/transitive analysis, Phase 6 requirement/progress comparison, optional Phase 9 dual invocation, reason/status mapping, and on-demand orchestration. It must reuse Phase 5/6/9 semantics, never duplicate their decision logic, and implement every case in `delay-consequence-test-matrix.md`.

No live-offering claim, general What-If framework, Digital Twin, migration, persistence table, endpoint, advisor change, or frontend is authorized by this policy. A later API or UI requires separate authentication, privacy, and presentation contracts.
