# Decision Intelligence Integration Policy

Policy version: **1.0**

Phase: **P4.1 — policy and contract only**

## 1. Purpose

This policy defines how approved P3 Student Intelligence may later influence Phase 7 recommendations and annotate Phase 8 semester plans and Phase 9 degree paths. It changes no engine today. The governing rule is **AI explains; deterministic rules and auditable models decide**.

P4 V1 introduces no blended score. It preserves the published Phase 7–9 policy version 1.0 behaviors as `BASELINE_V1`, adds one narrowly bounded readiness ordering factor to the future enhanced Phase 7 mode, and keeps all other P3 outputs factual or explanatory.

## 2. Proposal/WC traceability

| Classification | IDs | P4 relationship |
|---|---|---|
| `DIRECT_P4` | PROP-017, PROP-018, PROP-023, PROP-050, PROP-054, PROP-055 | Recommendation intelligence, planner separation, and delay consequence are direct P4 obligations. P4.1 defines safe policy; implementation remains open. |
| `ENABLED_BY_P4` | PROP-001, PROP-013, PROP-014, PROP-021, PROP-063, PROP-081, PROP-082, PROP-085, PROP-095, PROP-100 | P4 supplies integration, trace, safety, and version foundations. It does not complete UI, predictive risk, or continuous lifecycle claims. |
| `LATER_DEPENDENCY` | PROP-004, PROP-011, PROP-012, PROP-058, PROP-078 | Strength/difficulty explanations and future risk explanations consume P4 traces, but broader construct validation, UI, and lifecycle work remain later. |
| `DIRECT_P4` | WC-004, WC-017 | Delay Consequence Intelligence and structural early-warning integration are P4 outcomes. |
| `ENABLED_BY_P4` | WC-001, WC-002, WC-003, WC-007, WC-011, WC-012, WC-025, WC-040, WC-046 | Unified decision facts and traces become reusable foundations; these capabilities are not completed by P4.1. |
| `LATER_DEPENDENCY` | WC-005, WC-008, WC-018, WC-020 | Graduation audit, mock registration, predictive risk, and student-facing strength/difficulty experiences remain outside P4.1. |

## 3. Decision authority hierarchy

Highest authority wins; a lower layer cannot override an earlier layer:

1. **Canonical identity, provenance, and verification admissibility.** Unsupported, unverified, or conflicting facts abstain or require review.
2. **Phase 5 academic legality.** `ELIGIBLE`, `NOT_ELIGIBLE`, and `REVIEW_REQUIRED` are the prerequisite hard gate.
3. **Phase 6 academic requirement state.** Completion, in-progress state, group need, effective credit, and modeled requirement satisfaction remain authoritative.
4. **Phase 7–9 structural policy.** Published candidate filters, baseline semantic priority dimensions, planner constraints, simulations, and bounded path search remain authoritative.
5. **Approved deterministic Student Intelligence.** Only a factor explicitly allowed by this policy may act, only at its declared insertion point.
6. **User optimization preferences.** Existing typed constraints are honored where their owning engine already allows them; they cannot relax layers 1–5.
7. **AI explanation.** AI may verbalize the structured result and limitations but cannot calculate, reorder, or override it.

## 4. Hard gates

- Only Phase 5 `ELIGIBLE` plan members may enter normal recommendation or planner ranking.
- `NOT_ELIGIBLE` can never become `ELIGIBLE`, selected, or recommended through Student Intelligence.
- `REVIEW_REQUIRED` can never become `ELIGIBLE`; it stays separately visible for academic review.
- Phase 6 `COMPLETED` and `IN_PROGRESS` exclusion rules remain unchanged.
- Phase 8 credit/course constraints and prohibition on same-semester prerequisite chaining remain unchanged.
- Phase 9 completion, horizon, blocker, and hypothetical-pass semantics remain unchanged.
- A hard gate is never optional and never subject to a personalization mode.

## 5. Allowed intelligence factors

V1 allows one new P3 ordering factor: **target-specific academic readiness state**. It may affect only Phase 7 enhanced recommendation ordering, only after all five semantic dimensions of the existing Phase 7 tuple match, and before the existing catalog-only tie-breakers.

The enhanced comparison key is conceptually:

```text
(
  BASELINE P1 required_mandatory_priority,
  BASELINE P2 group_has_remaining_need,
  BASELINE P3 effective_credit_contribution,
  BASELINE P4 completes_requirement_group,
  BASELINE P5 newly_eligible_count,
  P4 readiness_tie_break,
  BASELINE P6 display_order,
  BASELINE P7 course_code
)
```

`readiness_tie_break = 1` for `PREPARATION_EVIDENCE_AVAILABLE` or `NOT_APPLICABLE`, `0` for `CAUTION_EVIDENCE_AVAILABLE`, and absent when the factor abstains. An absent factor causes the baseline P6/P7 ordering to apply; it is never converted to zero.

P3 performance observations, strength evidence, difficulty signals, and structural-risk signals are allowed as minimized explanation context only. Structural warning facts may also annotate scenario comparisons and planner/path diagnostics without changing membership or order.

## 6. Forbidden factors

The following are `NOT_ALLOWED` in V1 ordering or selection: raw numeric/letter grades or grade points; inferred GPA; predictive risk; probabilities; domain strengths/weaknesses; unverified evidence; model output treated as truth; free-form LLM judgments; course-name-derived taxonomy; personality, motivation, wellbeing, or ability labels; and gender, nationality, age, financial status, disability, location, or any other demographic attribute.

Existing Phase 5 eligibility is `HARD_GATE`. Existing Phase 6/7 requirement urgency, remaining group need, effective credit contribution, group completion, direct unlock impact, and published recommendation rank are existing structural `ORDERING_FACTOR` inputs. Student preference is allowed only through an existing typed constraint or a separately approved future policy; free-form preference never silently changes V1 ranking.

## 7. Readiness integration

V1 chooses **bounded deterministic tie-breaking** for the standalone Phase 7 enhanced result. Readiness answers what preparation evidence exists, not whether a course may be taken and not whether the student will succeed.

- It cannot change candidate membership.
- It cannot cross any baseline semantic difference P1–P5.
- It cannot push a mandatory bottleneck behind a structurally lower-value course.
- It never hides a caution course; both original baseline rank and enhanced rank remain visible in the trace.
- `PREPARATION_EVIDENCE_AVAILABLE` and `NOT_APPLICABLE` are equal; a course without prerequisites is not penalized.
- A caution state is a bounded tie-break only, not a prohibition or permanent penalty.
- Phase 8 and Phase 9 do not consume enhanced ordering in V1.

The default P4 mode is `STRUCTURAL_BASELINE`. `READINESS_AWARE` is an explicit, user-selectable future mode for the Phase 7 result. Hard rules are identical in both modes. No third mode is justified for V1.

## 8. Difficulty integration

P3 difficulty signals are `EXPLANATION_ONLY`. They may support a non-punitive workload/preparation warning but may not change course rank, candidate membership, semester combination order, path search, or path rank. They are not course difficulty scores or student ability scores.

## 9. Structural-risk integration

P3 structural risk is `EXPLANATION_ONLY`. It may identify a verified bottleneck, repeated required-course history, or concentrated dependency blockage in recommendation explanations, scenario comparison, and planner/path diagnostics. It may not create probability, a “likely to fail” label, candidate exclusion, or ranking change. Predictive risk remains forbidden and blocked by external data.

## 10. Performance integration

Explicit outcomes, repeat history, recovery history, requirement completion, and dependency exposure are `FACTUAL_CONTEXT`. Only facts already owned by Phase 5/6/7 continue to act through those baseline engines. P3-derived performance observations add explanation and trace evidence; they do not become a second decision factor. Raw grades, GPA, trends, and causal interpretations are not used.

## 11. Strength integration

The two V1 strength rules—successful required completion and recovery evidence—are `EXPLANATION_ONLY`. They cannot change ranking. No domain taxonomy exists, and routing a student toward prior strengths could create a self-reinforcing course bubble or distort mandatory progression.

## 12. Factor isolation

Every enhanced result must retain:

```text
base_result
+ exactly identified factor application
= final_result
```

The trace records the baseline ordered candidates, each factor input/status, the insertion position, candidates whose relative order changed, and the enhanced result. No factor may alter an unlisted field. P4.2 tests must run baseline, exactly-one-factor, all-abstain, and permitted multi-factor cases. Because V1 has only one ordering factor, no interaction score exists.

## 13. Baseline preservation

Phase 7 recommendation policy 1.0, Phase 8 semester planner policy 1.0, and Phase 9 degree-path policy 1.0 are each named `BASELINE_V1`. Their existing functions, tuple fields, reasons, constraints, and output order remain callable and unchanged. P4 must wrap or compose them; it must not rewrite their internal rankings.

Mandatory baseline-equivalence test: when all intelligence factors abstain or mode is `STRUCTURAL_BASELINE`, enhanced recommendation ordering and membership, semester-plan selection/order, and degree-path selection/order must equal the corresponding baseline outputs. Only the separately namespaced P4 trace may be additive.

## 14. Factor precedence

Precedence is:

1. Phase 5 hard gate and Phase 6 candidate-state exclusions.
2. Phase 7 baseline semantic dimensions P1–P5.
3. P4 readiness tie-break when enabled and applicable.
4. Phase 7 baseline catalog tie-breakers P6 display order and P7 course code.

Phase 8 and Phase 9 receive no P4 ordering factor in V1. Future factors require a policy-version increment and an exact insertion point; weighted blending is prohibited.

## 15. Abstention

Readiness must abstain when the P3 result is missing, `INSUFFICIENT_DATA`, `REVIEW_REQUIRED`, `NOT_SUPPORTED`, or `BLOCKED_BY_EXTERNAL_DATA`; evidence is unverified or inadmissible; the target/result identity or policy version mismatches; provenance is incomplete; or the mode is `STRUCTURAL_BASELINE`. Difficulty, strength, performance, and structural-risk factors always abstain from ordering in V1. Raw grades, predictive risk, and domain intelligence are recorded as blocked/forbidden, never silently ignored.

## 16. Missing data

Missing, stale, partial, or unavailable intelligence does not suppress a recommendation, semester plan, or degree path. The system returns the exact owning Phase 7–9 baseline result and records an ignored factor plus reason. “No intelligence data” never means “no recommendation.”

## 17. Negative feedback-loop safeguards

- Failure, withdrawal, difficulty, and caution never exclude an eligible course.
- Required progression and bottleneck courses remain visible.
- Readiness can move a course only inside an exact P1–P5 tie and only in opt-in mode.
- Readiness cannot alter Phase 8 selection or Phase 9 search in V1.
- No historical signal is permanent; results recompute from current admissible evidence.
- Baseline rank is always retained and users can return to `STRUCTURAL_BASELINE`.
- Strength evidence never narrows the candidate universe to familiar domains.

## 18. Privacy/fairness

Only minimum, owner-scoped reason codes, categorical status, safe evidence references, limitations, and policy versions may be exposed. Raw grades, source references, full attempts, protected attributes, prompts, or private reasoning are not copied into the decision result. P4 V1 contains no demographic ranking. Any future predictive or group-sensitive factor requires separate validation, fairness review, approval, monitoring, and appeal.

## 19. Decision trace

The conceptual immutable trace is:

```text
DecisionIntelligenceTrace
  decision_type
  decision_mode
  base_policy_name
  base_policy_version
  integration_policy_version
  intelligence_policy_version
  base_result_reference_or_snapshot
  applied_factors[]
  ignored_factors[]
  factor_reasons[]
  evidence_references[]
  changed_relative_orders[]
  final_result_reference_or_snapshot
  limitations[]
  simulation_provenance
```

An applied or ignored factor includes factor ID, source capability, categorical input, insertion point, reason code, and evidence references. It contains no chain-of-thought. The trace is compatible with future WC-040 but is computed on demand in P4 V1 rather than persisted.

## 20. Versioning

`DECISION_INTELLIGENCE_INTEGRATION_POLICY_VERSION = "1.0"`. P3 Student Intelligence policy version and P4 integration version are separate and both appear in traces. Any change to applicability, ordering category, categorical mapping, insertion point, precedence, or abstention increments P4 policy version. Existing Phase 7–9 policy versions remain unchanged.

## 21. Phase 7 integration contract

P4.2 may compose the unchanged Phase 7 baseline result with preloaded P3 readiness results. `STRUCTURAL_BASELINE` returns baseline membership and order exactly. `READINESS_AWARE` applies the readiness tie-break only within candidates equal on baseline P1–P5; existing reasons remain, and P4 adds finite trace reasons `P4_READINESS_PREPARATION_TIE_BREAK`, `P4_READINESS_CAUTION_TIE_BREAK`, `P4_READINESS_NOT_APPLICABLE_TIE_BREAK`, or an abstention reason. It exposes baseline rank and final rank. No P3 factor changes eligibility, structural tuple values, or zero-value elective policy.

## 22. Phase 8 integration contract

P4 V1 does not alter Phase 8 candidates, top-M window, combinations, constraints, priority tuple, or option ranks. Phase 8 consumes `BASELINE_V1` Phase 7 ordering. A separate annotation layer may attach readiness, difficulty, or structural-warning summaries after plans are produced. These annotations may warn about concentrated caution evidence but cannot invent workload, remove an option, or reorder options.

## 23. Phase 9 integration contract

P4 V1 does not alter Phase 9 beam search, path transitions, termination, priority tuples, ranks, or hypothetical-pass assumptions. It may attach intelligence annotations and later compare an unchanged baseline path to a delay scenario by invoking Phase 9 as defined in the delay policy. Warnings do not create artificial modeled semesters or blockers.

## 24. AI boundary

The AI Advisor may later receive the final deterministic result, safe trace subset, readiness category, structural warnings, delay result, reason codes, evidence references, limitations, and versions. It may explain why or why not, but cannot invoke hidden ranking, reinterpret raw grades, resolve review cases, change factor status, or reorder output. No advisor code changes are authorized in P4.1.

## 25. Digital Twin compatibility

Contracts consume a normalized immutable academic-state snapshot, not a database identity or Plan 12 course code. The snapshot declares `AUTHORITATIVE` or `SIMULATED`, source state reference, parent state when simulated, and scenario identifier. The same pure factor and delay contracts operate on either state; outputs retain simulation provenance and never write back.

The contracts are also sandbox- and multi-plan-compatible: synthetic evidence is labeled, provider-independent normalized models are used, and no university, major, plan ID, requirement code, or course code is hardcoded in policy.

## 26. P4.2 implementation contract

Implement in this exact order:

1. Shared immutable integration version, mode, factor-result, abstention, evidence, and trace models.
2. Pure adapters that accept already-loaded P3 results; no database or LLM calls.
3. Pure Delay Consequence engine and contracts from `delay-consequence-policy.md`.
4. A Phase 7 composition layer implementing only the readiness tie-break and retaining baseline/final ranks.
5. A Phase 8 post-result annotation layer with no membership or ordering change.
6. A Phase 9 annotation and delay-comparison layer that calls, never duplicates, Phase 9.
7. Read-only orchestration that loads each required snapshot once and reuses it; no per-candidate query and no per-course LLM call.
8. Baseline-equivalence, single-factor isolation, abstention, precedence, eligibility-invariance, privacy, determinism, performance, and delay-matrix tests; then full Phase 5–10 regressions.
9. Documentation and validation evidence updates only after tests pass.

P4.2 exact scope is on-demand pure integration plus trace, the optional Phase 7 readiness tie-break, Phase 8/9 annotations, and the specialized Delay Consequence engine. It adds no general Digital Twin, What-If framework, predictive model, grade interpretation, new taxonomy, advisor change, frontend, migration, or persistence table. Results are computed on demand; persistence requires later evidence and approval.
