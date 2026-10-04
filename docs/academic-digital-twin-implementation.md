# Academic Digital Twin Implementation

## 1. Purpose

P5.2 implements the P5.1/P5.1.1 Academic Digital Twin V1 contract as a pure Python domain package. It evaluates explicit, ephemeral academic scenarios without mutating authoritative records or adding a service, API, database, migration, frontend, or LLM dependency.

## 2. Contract version

The implementation uses contract version `1.0` and scenario version `1`.

## 3. Architecture

`app.academic_digital_twin` is split into immutable contracts (`models.py`), canonical SHA-256 fingerprinting (`fingerprint.py`), finite validation (`validation.py`), unchanged-engine orchestration (`engine.py`), closed-registry delta extraction (`deltas.py`), and bounded factual comparison (`comparison.py`).

## 4. Authoritative snapshot

`AuthoritativeAcademicSnapshot` contains normalized plan identity, immutable attempts with ordering/provenance/verification facts, Phase 5 and Phase 6 catalogs, the validated current Phase 6 result, existing Phase 8/9 constraints, safe source/policy versions, and optional authoritative readiness inputs. Names, email, phone, credentials, raw grades, and source documents are absent.

## 5. Modeled state

A modeled state is created only after atomic validation. It uses a new attempt tuple and an explicit `ModeledCourseCompletion`; it never replaces or appends to the authoritative tuple. Omission composes the existing P4 Delay result. Constraint scenarios use the existing Phase 8/9 constraint types.

## 6. Immutability

All public P5 contracts are frozen dataclasses and collections are tuples. Tests deep-copy and compare the complete nested snapshot before and after evaluation, including attempts, catalogs, dependencies, requirement structures, constraints, current progress, and versions.

## 7. Fingerprint

`calculate_base_state_fingerprint` SHA-256 hashes canonical JSON containing normalized plan/version identity, exact attempt outcome/order/provenance/verification facts, catalog membership/status, verified dependency groups, requirement structures, course credits/order, constraints, and source/engine-policy versions. Every set-like collection is sorted and JSON keys are canonical. Owner identity, presentation names, raw grade, GPA, contact data, credentials, timestamps, and arbitrary input order are excluded. The digest detects change; it is not authentication or proof of source authority.

## 8. Scenario identity

`ScenarioIdentity` carries caller-supplied opaque ID, contract/version, base fingerprint, immutable operations, optional typed constraint bundle, and optional presentation name. No random value or clock is used.

## 9. Scenario lifecycle

Exactly five statuses exist: `CREATED`, `EVALUATED`, `REVIEW_REQUIRED`, `INVALID`, and `STALE_BASE_STATE`. Evaluation returns the latter four as appropriate; `CREATED` is the typed pre-evaluation state.

## 10. Supported operations

Exactly three operation IDs execute: `TWIN_OP_MODEL_COURSE_COMPLETION`, `TWIN_OP_OMIT_NEXT_PLAN_COURSE`, and `TWIN_OP_SET_PLANNING_CONSTRAINTS`. One structural operation plus one constraint operation is the maximum.

## 11. Validation

Validation is closed and atomic. It handles unknown/deferred/forbidden operations, duplicates/conflicts/bounds, base identity and freshness, missing targets/context, plan membership, completed/in-progress targets, Phase 5 eligibility/review decisions, constraints, and the P5.1.1 `TWIN_ELECTIVE_GROUP_ALREADY_SATISFIED` case. Invalid or stale scenarios apply nothing and run no recomputation.

## 12. Modeled completion

`ModeledCourseCompletion` contains only course code, operation ID, synthetic structural `PASSED`, scenario ID, and `MODELED_OPERATION` provenance. It has no persistence ID, term, grade, source-record label, or official provenance.

## 13. Delay reuse

Omission calls P4 `evaluate_delay_consequence` with the exact authoritative attempts, catalogs, current progress, versions, and simulated provenance. P5 contains no dependency-impact implementation.

## 14. Constraint operation

`PlanningConstraintBundle` materializes existing `PlannerConstraints` and `DegreePathConstraints`. Their current bounds reject invalid input; P5 neither duplicates constants nor clamps values.

## 15. Engine recomputation

Valid modeled state follows Phase 5 → Phase 6 → authoritative P3 context → Phase 7/P4 → Phase 8 → Phase 9. The implementation directly invokes existing evaluators and engines. Phase 8 consumes the unchanged Phase 7 baseline result, as required.

## 16. Student Intelligence boundary

Modeled attempts never enter the authoritative snapshot or P3 history. Failed/withdrawn history remains intact. P3 strength, difficulty, recovery, performance, and preparation evidence is not recalculated from modeled completion. Predictive risk remains `BLOCKED_BY_EXTERNAL_DATA`.

## 17. Decision Intelligence boundary

P4 receives modeled structural state plus only the optional readiness evidence supplied from authoritative history. No new factor, eligibility override, planner ranking rule, or modeled preparation evidence is created.

## 18. Delta extraction

The `DeltaType` enum contains all and only the 16 committed values. Extraction compares preserved base and modeled outputs, records exact source engine and values, uses fixed registry/target ordering, and emits no free-form category.

## 19. Scenario comparison

Baseline-versus-scenario and scenario-versus-scenario comparison are supported. Scenario pairs require the same owner scope, normalized plan identity, fingerprint, and engine-policy versions. Invalid/stale results are rejected. Output is factual and has no score, utility, winner, or automatic recommendation.

## 20. Simulation provenance

The three provenance classes are `AUTHORITATIVE_INPUT`, `MODELED_OPERATION`, and `DERIVED_FROM_MODELED_STATE`. Results retain scenario ID, fingerprint, operation IDs, and safe version references. Existing P4 provenance is adapted explicitly without calling modeled facts authoritative.

## 21. Privacy

Public P5 result contracts contain safe identifiers, aggregate progress, typed engine results, codes, versions, and limitations. The package performs no logging and accepts no raw grades, contact details, credentials, prompts, or source payloads.

## 22. Persistence decision

Scenarios are `EPHEMERAL_ON_DEMAND`. P5.2 adds no table, repository, cache, migration, saved scenario, retention policy, or write channel.

## 23. API decision

There is no P5 API route or transport schema. Authorization remains the future caller's responsibility; the domain snapshot carries an owner scope only to prevent cross-owner comparison.

## 24. Determinism

No clock, random source, network, database order, mutable global, or LLM affects evaluation. Fingerprints canonicalize collection order; deltas and operations use finite stable ordering. Repeated and reordered-input tests prove equal logical results.

## 25. Performance

P5 adds linear canonicalization/validation and delegates bounded search to existing Phase 8/9 limits (candidate window 15, beam width 3, branch width 3, horizon at most 16, paths/options at most 10). It introduces no new combinatorial search.

## 26. Limitations

V1 has no live offerings, seats, timetable, calendar duration, grades, GPA prediction, transfer/equivalency creation, institutional holds, registration authority, saved scenarios, or predictive risk. Registration-set counts are never calendar-semester or graduation promises.

## 27. Future API/UI integration

A later authorized service may load an owner-scoped snapshot and expose typed results. A later Arabic UI may render the same codes and modeled wording. Neither may weaken fingerprint, no-write, privacy, comparison, or academic-authority boundaries.

## 28. P6 entry conditions

P6 may start only after P5.2 code, focused matrix coverage, Phase 5–10/P3/P4 regressions, full pytest, compilation, privacy scan, and documentation are accepted and committed. P6 must preserve the separation between modeled planning and registration intent.

