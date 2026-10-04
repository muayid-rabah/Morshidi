# Morshidi Read-Only Deterministic Advisor Orchestration

## Status and purpose

- **Phase:** 10.3
- **Status:** Read-only deterministic orchestration
- **Advisor policy:** `1.0`
- **Principle:** **AI explains — rules decide.**

This phase connects `NormalizedAdvisorRequest` to already-loaded authoritative data and the existing pure Phase 5–9 engines. It produces a typed `StructuredAdvisorResult`, original authoritative payload, minimal evidence, and deterministic trace. It does not fetch data, generate natural-language text, call an LLM, expose HTTP, or persist anything.

## Architecture

```text
NormalizedAdvisorRequest
        +
AdvisorContext (preloaded immutable academic inputs)
        ↓
orchestrate_advisor_request(request, context)
        ↓
existing pure Phase 5–9 engine selected by intent
        ↓
original typed result + minimal AdvisorEvidence + AdvisorTrace
        ↓
StructuredAdvisorResult
```

The orchestrator is located in `apps/api/app/advisor/orchestrator.py`. It imports pure engines/models only. It has no dependency on routes, services, repositories, Supabase, HTTP clients, environment settings, or provider code.

## Core entrypoint

```python
def orchestrate_advisor_request(
    request: NormalizedAdvisorRequest,
    context: AdvisorContext,
) -> StructuredAdvisorResult:
    ...
```

The entrypoint is synchronous, pure relative to its inputs, deterministic, and read-only. Ordinary user-flow outcomes return structured results. `AdvisorContractError` is reserved for malformed or contradictory contract state.

## `AdvisorContext`

`AdvisorContext` is a frozen in-memory container with:

- optional `AcademicProgressCatalog`;
- optional `CanTakeCatalog`;
- immutable persisted `StudentCourseAttempt` tuple;
- optional authoritative reported GPA/scale/earned-credit facts;
- optional precomputed `RecommendationResult`, `SemesterPlannerResult`, or `DegreePathResult` for option comparison.

It contains no owner override, auth token, raw database row, repository, service, Supabase client, or write callback. If both catalogs are present, their study-plan identifiers must match. A comparison result must belong to the same available study-plan context.

Optional catalogs allow general information, clarification, out-of-scope, and safe degraded results without fabricating missing academic context.

## Intent routing

| Intent | Route | Primary payload |
|---|---|---|
| `ACADEMIC_STATUS` | Phase 6 `calculate_academic_progress` | `AcademicProgress` |
| `COURSE_ELIGIBILITY` | Phase 5 `evaluate_can_take` | `CanTakeDecision` or `CanTakeError` |
| `COURSE_RECOMMENDATIONS` | Phase 7 `recommend_courses` | `RecommendationResult` |
| `REMAINING_REQUIREMENTS` | Phase 6 `calculate_academic_progress` | `AcademicProgress` |
| `SEMESTER_PLANNING` | Phase 7 once, then Phase 8 `plan_semester` | `SemesterPlannerResult` |
| `DEGREE_PATH_MODELING` | Phase 9 `plan_degree_paths` | `DegreePathResult` |
| `OPTION_COMPARISON` | Select referenced options from one injected deterministic result | tuple of original option objects |
| `COURSE_INFORMATION` | Project fields from injected catalogs and resolved identity | `CourseInformation` |
| `GENERAL_ACADEMIC_INFORMATION` | No academic engine | no payload/evidence |
| `CLARIFICATION_REQUIRED` | Return supplied typed clarification | no payload |
| `OUT_OF_SCOPE` | Return supplied typed reason | no payload |

There is no LLM-based routing in this phase.

## Phase 5–9 reuse

The exact reuse map is:

- Phase 5: `evaluate_can_take(CanTakeCatalog, CanTakeRequest)`.
- Phase 6: `calculate_academic_progress(AcademicProgressCatalog, attempts, reported facts)`.
- Phase 7: `recommend_courses(progress_catalog, eligibility_catalog, attempts, reported facts)`.
- Phase 8: `plan_semester(progress_catalog, eligibility_catalog, attempts, RecommendationResult, PlannerConstraints, reported facts)`.
- Phase 9: `plan_degree_paths(progress_catalog, eligibility_catalog, attempts, DegreePathConstraints, reported facts)`.

The orchestrator contains no prerequisite evaluation, progress math, recommendation score, combination validation, path search, equivalency logic, or raw prerequisite parser.

## Academic status and remaining requirements

Both intents call Phase 6 exactly once. `ACADEMIC_STATUS` returns the original `AcademicProgress`. `REMAINING_REQUIREMENTS` identifies relevant course codes only by reading Phase 6 `CourseProgress.state`; it does not calculate credits or satisfaction independently. The original progress object remains the payload.

## Eligibility

The target must have a `RESOLVED` authoritative course identity before Phase 5 is invoked. The result preserves:

- `ELIGIBLE`, `NOT_ELIGIBLE`, or `REVIEW_REQUIRED`;
- exact `DecisionReason` values;
- exact `PrerequisiteLogicStatus`, including `unresolved` and `source_conflict`;
- target-attempt state and dependency-group evidence in the original payload.

`ELIGIBLE` and `NOT_ELIGIBLE` use `DETERMINISTIC`. `REVIEW_REQUIRED` uses `REVIEW_REQUIRED`. A Phase 5 typed request error uses `INSUFFICIENT_CONTEXT`. Raw prerequisite text remains metadata in the Phase 5 payload and is never parsed by the orchestrator.

## Recommendations

The Phase 7 result is returned unchanged as the authoritative payload. Candidate order, rank, reason codes, review-required separation, and excluded-in-progress codes are preserved. The orchestrator does not truncate, rerank, or apply personal preferences.

If no ranked candidates exist and review-required courses remain, answer authority is `REVIEW_REQUIRED`; otherwise the valid recommendation result is `DETERMINISTIC`.

## Semester planning and multi-engine flow

Semester planning requires existing `PlannerConstraints`. The orchestrator calls Phase 7 once because the current Phase 8 signature requires a full `RecommendationResult`, then passes that exact object to `plan_semester`. It does not call Phase 6 or Phase 5 separately; Phase 7/8 reuse those semantics internally.

The result preserves original option rank, course order, credits, reason codes, group effects, newly eligible courses, scope, limitations, and policy version. Evidence records Phase 7 as supporting authority and Phase 8 as primary authority. If no plan exists and review-required courses remain, authority is `REVIEW_REQUIRED` with exact Phase 7 review reason evidence.

## Degree-path modeling

Degree-path modeling requires existing `DegreePathConstraints` and calls Phase 9 once. Phase 9 internally owns recommendation, semester, transition, deduplication, ranking, and blocker classification. The orchestrator does not independently recreate them.

The original `DegreePathResult` preserves path order, `PathStatus`, modeled semesters, reason codes, blocker diagnostics, progress, scope, methodology, and hypothetical-pass limitations. Exact catalog prerequisite states are referenced for review-required course codes so `unresolved` and `source_conflict` remain distinguishable.

Authority becomes `REVIEW_REQUIRED` only when the requested modeled result is entirely blocked by review-required state (or has no paths and review-required courses). Other valid modeled results remain `DETERMINISTIC`, including paths that report other limitations or horizon outcomes.

## Option comparison

`OPTION_COMPARISON` accepts one precomputed deterministic result through `AdvisorContext.comparison_result` and positive normalized option ranks. It selects the original objects in deterministic rank order and returns them unchanged.

It introduces no new score, reranking, preference, or “best” choice. Missing comparison context, missing references, or unknown ranks produce `CLARIFICATION_REQUIRED` with `AMBIGUOUS_OPTION_REFERENCE`.

## Course information

`COURSE_INFORMATION` requires a resolved canonical identity and projects only facts available in the injected catalogs:

- exact course code and canonical names;
- plan credit hours when represented;
- requirement-group code when represented;
- catalog status, including `referenced_only`;
- prerequisite logic status and raw prerequisite metadata when represented.

Missing fields remain `None`. Raw text is never converted into dependency logic.

## Course resolution and clarification

- `RESOLVED`: proceed with course-specific routing.
- `AMBIGUOUS`: do not call an academic engine; return `CLARIFICATION_REQUIRED`, `INSUFFICIENT_CONTEXT`, and sorted candidates.
- `NOT_FOUND`: do not call an academic engine; preserve the safe resolution and return `INSUFFICIENT_CONTEXT`.
- Missing required course: return `MISSING_COURSE` clarification.
- Missing Phase 8/9 constraints: return `MISSING_REQUIRED_CONSTRAINT` clarification.

Ordinary clarification is never raised as a generic exception.

## General information and out-of-scope

General information returns `GENERAL_INFORMATION`, no authoritative academic source, no academic payload, and only the advisor policy version in its trace. The phase does not generate teaching text.

Out-of-scope requests return `INSUFFICIENT_CONTEXT` and the typed `OutOfScopeReason`. They contain no fabricated answer or payload.

## Evidence mapping

Evidence is deliberately small:

- Phase 5: target code plus exact decision, reason, review reason, and prerequisite-status strings.
- Phase 6: progress result reference and, for remaining requirements, codes read from Phase 6 course states.
- Phase 7: candidate/review/in-progress codes and exact recommendation/review reason strings.
- Phase 8: selected/review/in-progress codes and exact plan reason strings.
- Phase 9: selected/remaining/review/in-progress codes plus exact path status, reason, and blocker strings.
- Catalog: exact prerequisite status for review courses or canonical course-information metadata.

Evidence never copies an arbitrary result blob. The original typed result is carried separately as `authoritative_payload`.

## Trace construction and policy versions

Every result includes `PolicyVersionReference(PolicySource.AI_ADVISOR, "1.0")`. Where published, Phase 7, 8, and 9 policy versions are also recorded. Missing Phase 5/6 versions are not invented.

Trace sources, codes, references, versions, and option ranks use Phase 10.2 deterministic sorting/deduplication. Traces contain no timestamp, random identifier, owner, token, secret, prompt, or confidence percentage.

## Recompute and reuse policy

Within one call:

- Phase 6 status/remaining runs once;
- Phase 5 eligibility runs once after successful resolution;
- Phase 7 recommendation runs once;
- Phase 8 receives that same Phase 7 result;
- Phase 9 is called once and owns its internal reuse;
- option comparison consumes an injected existing result and runs no engine.

The orchestrator does not perform extra Phase 5–7 calls merely to enrich evidence when the primary upstream result already contains the needed reason/status fields.

## Read-only and no-network guarantees

All inputs and outputs are immutable domain objects. The orchestrator has no student write method, repository, persistence helper, Supabase client, HTTP client, or environment access. It cannot add attempts, change GPA/profile data, register courses, persist paths, or modify catalogs.

Structural AST tests prohibit FastAPI, Starlette, HTTP, Supabase, repository, service, and settings imports. Input snapshots and Phase 5–9 domain objects are tested unchanged after orchestration.

## Determinism

Identical `NormalizedAdvisorRequest` and `AdvisorContext` values produce equal `StructuredAdvisorResult` values. The implementation uses no clock, randomness, generated identifiers, network state, unordered output, or provider behavior.

## Failure behavior

Missing required catalog context returns `INSUFFICIENT_CONTEXT` with no fabricated payload. Invalid invariant state uses `AdvisorContractError`. Exceptions raised by Phase 5–9 for genuine catalog/engine integrity failures are not swallowed or rewritten as academic answers.

## Examples

### Eligible course

`COURSE_ELIGIBILITY` plus a resolved `0300153` calls Phase 5 and returns the original `CanTakeDecision`, Phase 5 evidence, a deterministic trace, and `DETERMINISTIC` authority.

### Review-required distinction

`1505311` retains `unresolved` and `PREREQUISITE_LOGIC_UNRESOLVED`; `1505320` retains `source_conflict` and `PREREQUISITE_SOURCE_CONFLICT`. Both use `REVIEW_REQUIRED`, but their upstream states remain distinct.

### Semester plan

A normalized request with `PlannerConstraints` calls Phase 7 once and Phase 8 once. The result retains Phase 8 course ordering/reasons and trace references for both policy versions.

### Ambiguous course

An ambiguous resolution returns a clarification with sorted candidate course codes. Phase 5 is not called.

### Referenced-only course

Canonical resolution of `0300103` can return `catalog_status="referenced_only"`; absence from plan-course rows leaves credit/group fields unset rather than inferred.

## Non-goals

This phase does not implement an LLM/provider adapter, prompts, tool/function calling, explanation text, HTTP API, authentication, UI, conversation state, persistence, database/RLS change, embeddings, RAG, or new academic logic.

## Next-phase boundary

The exact next phase is **10.4 — LLM Provider Boundary & Structured Interpretation**. It may consume these deterministic contracts but must not weaken the source hierarchy, read-only behavior, traceability, or “AI explains — rules decide” boundary.

