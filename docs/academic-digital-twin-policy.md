# Academic Digital Twin Policy

Policy version: **1.0**

Phase: **P5.1 — policy and contracts only**

## 1. Purpose

The Academic Digital Twin is a non-destructive, reproducible academic-state clone used to evaluate explicit hypothetical operations through Morshidi's existing deterministic engines. AI may explain a result; rules and auditable models produce it. P5.1 authorizes no application code, API, persistence, migration, UI, or transaction.

## 2. Proposal/WC traceability

| Classification | IDs | Relationship |
|---|---|---|
| `DIRECT_P5` | PROP-023, PROP-050, PROP-062 | Explicit delay consequences, planner separation, and comparison of existing alternatives are directly exercised by the P5 scenario contract. |
| `ENABLED_BY_P5` | PROP-001, PROP-014, PROP-017, PROP-021 | A unified personal modeled state and trace enable later delivery of readiness-aware decisions and student planning. |
| `LATER_DEPENDENCY` | PROP-018, PROP-078 | Predictive-risk ranking and continuous lifecycle modeling still require governed data, validation, and later lifecycle work. |
| `DIRECT_P5` | WC-001, WC-002, WC-003 | Digital Twin, What-If, and factual Scenario Comparison are the P5 contract outcomes. |
| `ENABLED_BY_P5` | WC-004, WC-005, WC-025, WC-040, WC-046 | P5 reuses Delay Consequence and enables later graduation audit, goal modes, trace ledger, and change-impact delivery. |
| `LATER_DEPENDENCY` | WC-008, WC-018, WC-027, WC-037, WC-054 | Mock Registration, predictive risk, transfer, live offerings, and institutional simulation require later data or governance. |

Documentation is policy evidence only. It changes no proposal or WC implementation status.

## 3. Digital Twin definition

A V1 twin is an immutable, plan-scoped projection of the minimum academic facts required by deterministic engines:

- normalized university, major, study-plan, and plan-version identity;
- immutable authoritative attempts with outcome, ordering evidence where available, admissible provenance, and verification state;
- academic-profile context used by existing engines, excluding unnecessary identity fields;
- canonical plan membership, requirement groups, verified dependency rules, and source versions;
- current Phase 5 eligibility and Phase 6 progress inputs/results where supplied as validated context;
- an explicit scenario identity, operation tuple, constraints, engine/policy versions, and simulation provenance.

Raw performance metadata may remain in an internal authorized base snapshot only when an existing engine requires it. V1 modeled operations never read, copy, interpret, or emit raw grades. Names, email, phone, demographic attributes, and unrelated PII are excluded.

The twin is not an authoritative student record, alternate SIS, registration transaction, grade prediction, graduation forecast, LLM simulation, or mechanism for rewriting history.

## 4. Non-goals

V1 does not persist scenarios; modify profiles or attempts; create offerings, sections, grades, dates, equivalencies, majors, or plan transitions; implement predictive risk; change Phase 5–9/P3/P4 policy; perform registration; or let an LLM calculate a consequence. Mock Registration, institutional demand, transfer simulation, live availability, and saved scenarios remain separate capabilities.

## 5. Authoritative vs modeled state

Exactly two state classes exist:

- `AUTHORITATIVE_STATE`: current authorized academic context loaded from accepted sources and preserved unchanged.
- `MODELED_STATE`: a clone of one authoritative base plus an explicit valid V1 operation set and derived deterministic outputs.

Every modeled result retains its base-state reference and fingerprint. A modeled state is never silently promoted, written back, reconciled as official, or presented without modeled language.

## 6. Immutability

Scenario evaluation must not mutate student attempts, profile data, database rows, repository entities, canonical catalogs, cached authoritative objects, or prior engine results. P5.2 must construct new immutable tuples/models, pass them to pure engines, and prove structural equality of every authoritative input before and after evaluation. Mutable shallow copies are insufficient; nested academic collections must be isolated or immutable.

## 7. Scenario identity

`ScenarioIdentity` contains:

```text
scenario_id                 opaque ephemeral UUID/value
scenario_contract_version   "1.0"
base_state_fingerprint      deterministic change detector
scenario_version            positive integer, V1 fixed at 1
operations                  canonical typed tuple
constraint_bundle           optional typed validated bundle
```

`scenario_name` may be optional presentation metadata but is not part of academic semantics. Identity contains no owner email, student number, or raw grade. A V1 scenario is rooted directly in one authoritative state; scenario-from-scenario branching is deferred.

The V1 base-state fingerprint is required. P5.2 must SHA-256 hash a canonical, length-delimited serialization of normalized plan/version identity, exact authoritative attempt course codes/outcomes/ordering evidence, admissible provenance and verification states, canonical catalog/source versions, and relevant engine-policy versions. It excludes names, contact identifiers, raw grades, reported GPA, credentials, timestamps that do not affect decisions, and presentation fields. The digest is a deterministic stale-state/change detector and cache/comparison key—not authentication, authorization, encryption, or proof of source authenticity.

## 8. Scenario lifecycle

The finite V1 lifecycle is:

- `CREATED`: typed input assembled but not evaluated;
- `EVALUATED`: validation and deterministic evaluation completed;
- `REVIEW_REQUIRED`: a material source conflict or unresolved rule prevents a definitive affected facet;
- `INVALID`: the operation set or required context violates the contract;
- `STALE_BASE_STATE`: the supplied base fingerprint no longer matches current authoritative state.

There is no persisted draft, saved, published, approved, or deleted lifecycle. Stale scenarios are not silently rerun against a new base; the caller must create a new scenario identity.

## 9. Supported operation taxonomy

### `SUPPORTED_V1`

| Operation ID | Meaning |
|---|---|
| `TWIN_OP_MODEL_COURSE_COMPLETION` | Add one dedicated modeled completion for an eligible, incomplete, non-`IN_PROGRESS` plan course. |
| `TWIN_OP_OMIT_NEXT_PLAN_COURSE` | Analyze omission of one valid plan target from the first modeled registration set where the baseline selects it, by delegating to P4 Delay Consequence. |
| `TWIN_OP_SET_PLANNING_CONSTRAINTS` | Replace an explicitly supplied planner/path constraint bundle within existing Phase 8/9 validation bounds. |

V1 allows at most one structural operation (`MODEL_COURSE_COMPLETION` or `OMIT_NEXT_PLAN_COURSE`) plus at most one constraint-bundle operation.

### `DEFERRED`

`TWIN_OP_PREFER_ELECTIVE_OPTION`, modeled failure, modeled withdrawal, current-course outcome assumptions, live unavailability, major transfer, plan-version transition, equivalency changes, goal-mode ranking, and scenario branching are deferred until their owning policy/data exists.

### `FORBIDDEN`

Invented grade/grade point, mutation or deletion of authoritative history, forced eligibility, unofficial prerequisite/equivalency creation, predictive success/failure, fabricated offering/timetable, official add/drop/registration, and LLM-created operations outside the finite registry are forbidden.

## 10. Hypothetical completion

`TWIN_OP_MODEL_COURSE_COMPLETION` answers “What changes in the modeled academic structure if course X is treated as completed?” It creates a `ModeledCourseCompletion`, not a persisted `StudentCourseAttempt`. The target must be an exact selected-plan member, incomplete, not currently `IN_PROGRESS`, and Phase 5 `ELIGIBLE` at the base state. A Phase 5 `REVIEW_REQUIRED` target makes the scenario `REVIEW_REQUIRED` without applying completion; a `NOT_ELIGIBLE` target is invalid for this V1 operation. An incomplete, plan-listed elective that is Phase 5 `ELIGIBLE` is nevertheless invalid as a P5 V1 completion target when its owning elective requirement group is already satisfied under current Phase 6 semantics. That case returns `TWIN_ELECTIVE_GROUP_ALREADY_SATISFIED`; the operation is rejected before application, no modeled completion is created, no engine is recomputed, no delta is emitted, authoritative state remains unchanged, and modeled state is not applied. The operation carries no grade, term, registration, probability, or promise of future success.

The modeled completion participates only in structural Phase 5/6/7/8/9 recomputation. Existing failures and withdrawals remain in authoritative history and are never collapsed.

## 11. Delay reuse

`TWIN_OP_OMIT_NEXT_PLAN_COURSE` delegates to the existing P4 Delay Consequence contract and its four statuses and twelve reason codes. “Omit” means omission from the first baseline-modeled registration set that selects the target. It never means unavailable, failed, withdrawn, dropped, or delayed by a real calendar term.

## 12. Constraint changes

The constraint bundle reuses existing validation exactly:

- Phase 8 `max_credit_hours`: `0.00..30.00`; `max_courses`: `1..10` or `None`; `max_options`: `1..10`;
- Phase 9 `max_credit_hours_per_semester`: `0.00..30.00`; `max_courses_per_semester`: `1..10` or `None`; `max_semesters_ahead`: `1..16`; `max_paths`: `1..10`.

These are user modeling preferences and computational bounds, not institutional registration limits.

## 13. Elective semantics

Preference is not completion. P5 V1 does not add an elective preference operation because Phase 8/9 have no approved course-pinning or preference factor. A modeled completion may target an eligible elective only while its requirement group has remaining need. If the group is already satisfied, the scenario is `INVALID` with `TWIN_ELECTIVE_GROUP_ALREADY_SATISFIED`; this does not change the Phase 5 decision or relabel the target `NOT_ELIGIBLE`. Phase 5 eligibility answers whether the course may be taken under academic prerequisite rules, while Digital Twin operation validation answers whether the hypothetical is supported and meaningful within bounded P5 V1 scope. The rejection makes no claim that the target is completed, lacks academic value, or cannot be registered in the future, and it does not alter requirement-group or elective policy outside Digital Twin V1. Existing Phase 6 elective caps still apply; selection never marks an elective passed.

## 14. State cloning

P5.2 must normalize and freeze the authorized base snapshot, calculate its fingerprint, create a separately typed modeled overlay, and recompute outputs from a newly materialized modeled input. The overlay may add only the approved modeled completion or omission/constraint instruction. It may not remove or replace base attempts. Engine-specific adapters must preserve exact plan identity and policy/source versions.

## 15. Simulation provenance

Every fact is labeled with exactly one provenance class:

- `AUTHORITATIVE_INPUT`: copied unchanged from the authorized base;
- `MODELED_OPERATION`: the explicit user-requested hypothetical instruction;
- `DERIVED_FROM_MODELED_STATE`: deterministic output calculated from the clone.

Official provenance labels must not be assigned to synthetic facts. Traces carry scenario ID, base fingerprint, operation ID, engine/policy/source versions, and safe evidence references.

## 16. Modeled attempts

Modeled completion uses a dedicated representation:

```text
ModeledCourseCompletion
  course_code
  operation_id = TWIN_OP_MODEL_COURSE_COMPLETION
  outcome = PASSED
  provenance = MODELED_OPERATION
  scenario_id
```

It cannot contain persistence IDs, raw grade, term, source-record label, or `OFFICIAL_VERIFIED` provenance. An adapter may translate it to an ephemeral Phase 5/6 `PASSED` input only inside the evaluation call while retaining the separate provenance in scenario output.

## 17. In-progress handling

Persisted `IN_PROGRESS` is authoritative and protected. V1 cannot pass, fail, withdraw, omit, remove, or duplicate that target. A completion operation targeting it is `INVALID`; delay analysis preserves P4's `REVIEW_REQUIRED` semantics. Downstream eligibility remains conservative until an authoritative outcome exists.

## 18. Repeated attempts

Full authoritative history remains intact. `FAILED`, `FAILED` plus a modeled completion is reported as authoritative failed history plus a separate `MODELED PASSED`; it is never reported as an official fail/fail/pass sequence. The modeled pass does not become recovery, strength, preparation, or trend evidence.

## 19. Zero-credit

Eligible required zero-credit plan courses may be modeled complete. They can satisfy a mandatory-course condition and unlock dependencies while completed-credit delta remains zero. Deltas and explanations must never infer “no effect” solely from a zero credit delta.

## 20. Referenced-only

Referenced-only courses may remain authoritative dependency evidence but cannot be scenario targets, plan progress dimensions, requirement completions, or elective choices. V1 does not model their completion. Unknown/referenced-only target requests are `INVALID`, while P4 delay retains its defined insufficient-context result where applicable.

## 21. Source conflicts

The twin never resolves unresolved prerequisite text, source conflicts, incomplete verified structures, or ambiguous equivalency. When a material affected fact depends on such a rule, the scenario or affected facet is `REVIEW_REQUIRED`; independent verified deltas may remain visible with conservative status precedence.

Only verified existing equivalencies may ever be consumed by an owning engine. P5 V1 creates none and performs no name/code substitution.

## 22. Student Intelligence boundary

Structural modelable facts—eligibility, progress, requirement state, and dependency exposure—may be recomputed. P3 history-based performance, strength, difficulty, recovery, withdrawal, and readiness evidence remains bound to authoritative history. A modeled pass is not preparation or recovery evidence. Predictive risk stays `BLOCKED_BY_EXTERNAL_DATA`.

## 23. Decision Intelligence boundary

P4 may compose modeled structural Phase 7 outputs and annotate planner/path results. Any readiness factor must come from admissible authoritative-history evidence for the same target and base; when the modeled operation would be necessary to establish that readiness evidence, the factor abstains. P4 hard gates, exact-tie semantics, baseline preservation, and trace rules remain unchanged.

## 24. Privacy

Scenario inputs and outputs use minimum necessary owner-scoped academic data. No raw grades, credentials, protected attributes, full source payloads, prompts, or unnecessary transcript rows appear in scenario results, traces, or logs. Diagnostic logging uses scenario ID, safe codes, versions, and redacted correlation only.

## 25. Authorization

A student scenario may use only the authenticated student's authorized academic state. Scenario IDs are not authority tokens. Future advisor use requires explicit advisor authorization and purpose scope. Cross-student cloning, comparison, or scenario reference resolution is prohibited.

## 26. Persistence

P5 V1 scenarios are `EPHEMERAL_ON_DEMAND`. No scenario, clone, result, or trace table is authorized; no migration is required. Saved scenarios, expiry storage, sharing, and result references require a later retention, authorization, stale-state, and deletion policy.

## 27. Determinism

Identical normalized base state, fingerprint, canonical operations, constraints, catalogs, source versions, and policy/engine versions must yield byte-equivalent ordered results. No clock, randomness, network lookup, LLM, hidden preference, or mutable global state may affect evaluation.

## 28. Computational limits

- one authoritative base per scenario;
- no scenario chaining;
- at most one structural operation plus one constraint bundle;
- at most two scenarios in one comparison;
- existing Phase 8 top-15 candidate window and `max_options <= 10`;
- existing Phase 9 horizon `<= 16`, `max_paths <= 10`, beam width 3, semester branch width 3, and candidate window 15;
- no arbitrary operation sequences, recursive branches, or unbounded comparisons.

## 29. P5.2 implementation contract

Implement, in order: (1) immutable scenario/domain models and enums; (2) normalized authoritative snapshot and safe fingerprint; (3) deep clone/overlay isolation; (4) finite operation validation; (5) dedicated modeled-completion adapter and P4 delay composition; (6) deterministic Phase 5 → Phase 6 → P3-authoritative-context → Phase 7/P4 → Phase 8 → Phase 9 orchestration; (7) typed delta extraction; (8) evaluation result; (9) bounded comparison; (10) the complete policy matrix and immutability/determinism tests; (11) implementation trace documentation.

P5.2 remains a pure/domain-only package. It adds no API, database, service persistence, frontend, LLM decisioning, or P5.3 work.

### Exact P5 V1 scope decision

- `SUPPORTED_OPERATIONS`: `TWIN_OP_MODEL_COURSE_COMPLETION`, `TWIN_OP_OMIT_NEXT_PLAN_COURSE`, and `TWIN_OP_SET_PLANNING_CONSTRAINTS` under the one-structural-plus-one-constraint rule.
- `SUPPORTED_COMPARISONS`: authoritative baseline versus one scenario; scenario A versus scenario B on the same base fingerprint. At most two sides.
- `DEFERRED_OPERATIONS`: failure, withdrawal, in-progress outcome assumptions, elective preference, live unavailability, major/plan transition, and scenario branching/saving.
- `FORBIDDEN_OPERATIONS`: grade/GPA invention, authoritative mutation, forced eligibility, invented equivalency/prerequisite/offering, predictive outcome, and official registration/add/drop.

### Portability and product separation

Contracts use normalized university, major, study-plan, and version identity and contain no Zarqa/Plan-12 course code. They must behave identically with Morshidi Sandbox University synthetic provenance and real authorized provider data. The Digital Twin is the private scenario mechanism; Sandbox University is a synthetic institutional environment. A modeled plan is not Mock Registration intent and is never automatically converted into intent. Neither a twin nor a What-If plan is official registration, add/drop, enrollment, degree clearance, or an SIS update.
