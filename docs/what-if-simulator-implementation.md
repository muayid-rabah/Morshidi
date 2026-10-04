# What-If Simulator Implementation

## Supported V1 query classes

The pure evaluator supports modeled completion, next-plan omission/delay, planning-constraint changes, baseline-versus-scenario comparison, and same-base scenario-versus-scenario comparison. It adds no general natural-language or Advisor integration.

## Operation mapping

`TWIN_OP_MODEL_COURSE_COMPLETION` creates one isolated structural modeled pass. `TWIN_OP_OMIT_NEXT_PLAN_COURSE` delegates to P4 Delay Consequence. `TWIN_OP_SET_PLANNING_CONSTRAINTS` materializes current Phase 8/9 constraint types. Constraint validation precedes the optional structural overlay regardless of caller order.

## Validation

The finite `ValidationCode` enum implements the policy registry plus operation-matrix deferred/forbidden outcomes. `TWIN_ELECTIVE_GROUP_ALREADY_SATISFIED` returns `INVALID` for an eligible incomplete plan elective whose Phase 6 group is already satisfied. It creates no completion, recomputation, delta, or modeled state and does not change Phase 5 eligibility.

## Engine reuse

The simulator invokes existing Phase 5 eligibility, Phase 6 progress, Phase 7 recommendation, P4 composition/delay, Phase 8 planner, and Phase 9 path functions. It contains no replacement prerequisite, progress, ranking, planning, path, intelligence, or delay algorithm.

## Result composition

`DigitalTwinEvaluationResult` preserves separate base and modeled summaries, typed operation results, optional engine subresults, optional P4 delay result, closed deltas, safe traces, issues, missing inputs, limitations, versions, and simulation provenance. Invalid/stale results contain no modeled output.

## Comparison

Comparison consumes evaluated typed results only. It enforces status, owner, plan, fingerprint, and version compatibility and preserves caller side order. The contract contains no overall score or winner fields.

## Missing/review behavior

Required missing context returns `INVALID`; stale fingerprint returns `STALE_BASE_STATE`; material prerequisite/source ambiguity returns `REVIEW_REQUIRED`. No case silently becomes an ordinary modeled result.

## Grade boundary

Modeled completion has only structural `PASSED` semantics. It carries no grade, grade point, term, GPA effect, probability, or official attempt provenance.

## Predictive boundary

No scenario calculates future success, failure, grade, risk, offering likelihood, or graduation date. Predictive risk remains blocked by external governed data and validation.

## Modeled-language boundary

Results are explicitly authoritative-base or modeled-state facts. Plans remain modeled registration sets, not official schedules or registrations. Omission never claims unavailability, withdrawal, failure, or real-calendar delay.

## Future Advisor integration

A later Advisor adapter may translate a user request into an inspectable supported operation and explain the typed result. It must not invent operations, courses, constraints, prerequisites, offerings, or outcomes, and P5.2 exposes no Advisor/API integration.

