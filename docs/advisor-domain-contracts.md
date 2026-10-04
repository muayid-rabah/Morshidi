# Morshidi Advisor Domain, Intent & Trace Contracts

## Status and purpose

- **Phase:** 10.2
- **Policy:** `AI_ADVISOR_POLICY_VERSION = "1.0"`
- **Boundary:** Pure domain contracts only
- **Principle:** **AI explains — rules decide.**

This document records the immutable Python contracts that translate the accepted Phase 10.1 policy into types suitable for Phase 10.3 orchestration. It introduces no LLM, provider, prompt, HTTP endpoint, repository operation, persistence, or academic decision logic.

The implementation lives in `apps/api/app/advisor/models.py` and is exported by `apps/api/app/advisor/__init__.py`.

## Relationship to Phase 10.1

The contracts preserve the accepted hierarchy: canonical catalog, authenticated student state, Phase 5 eligibility, Phase 6 progress, Phase 7 recommendations, Phase 8 semester plans, Phase 9 degree paths, then advisor explanation. The advisor types reference evidence from that hierarchy and never replace upstream models or rules.

## Package boundary

The advisor domain package may depend only on Python's standard library and stable pure model types. It imports `PlannerConstraints` and `DegreePathConstraints` rather than duplicating their validation or semantics.

It must not import FastAPI, Starlette, HTTP clients, Supabase clients, application settings, routes, services, or repositories. It contains no network, database, environment, authentication, provider, prompt, or orchestration code.

## Policy constant

`AI_ADVISOR_POLICY_VERSION = "1.0"` versions the advisor policy contract. Upstream policy versions are recorded only where those subsystems already publish a version.

## Enums

### `AdvisorIntent`

| Member | Routing meaning |
|---|---|
| `ACADEMIC_STATUS` | Current progress or stored academic-state explanation. |
| `COURSE_ELIGIBILITY` | Phase 5 decision or explanation for one course. |
| `COURSE_RECOMMENDATIONS` | Phase 7 ranking or explanation. |
| `REMAINING_REQUIREMENTS` | Incomplete requirements from Phase 6. |
| `SEMESTER_PLANNING` | Phase 8 generation, explanation, or comparison. |
| `DEGREE_PATH_MODELING` | Phase 9 generation, explanation, or comparison. |
| `OPTION_COMPARISON` | Comparison of already-generated deterministic options without reranking. |
| `COURSE_INFORMATION` | Canonical catalog facts. |
| `GENERAL_ACADEMIC_INFORMATION` | General education without student-specific decisions. |
| `CLARIFICATION_REQUIRED` | Intent/entity/option/constraint ambiguity. |
| `OUT_OF_SCOPE` | Unsupported or unauthorized request. |

Explanation is not a separate academic intent: a “why” request stays with the subsystem that owns the explained result.

### `AnswerAuthority`

- `DETERMINISTIC`: grounded in authoritative catalog/state or Phase 5–9 output.
- `REVIEW_REQUIRED`: verified state explicitly requires academic/manual review.
- `GENERAL_INFORMATION`: non-student-specific educational explanation.
- `INSUFFICIENT_CONTEXT`: an authoritative answer cannot safely be produced.

These values are semantic source classifications, not probabilities. No numeric confidence field exists.

### `AuthoritativeSource`

The exact sources are `ACADEMIC_CATALOG`, `STUDENT_ACADEMIC_STATE`, `PHASE5_ELIGIBILITY`, `PHASE6_PROGRESS`, `PHASE7_RECOMMENDATIONS`, `PHASE8_SEMESTER_PLANNER`, and `PHASE9_DEGREE_PATH`. An LLM is never an authoritative source.

### Other finite classifications

- `EntityResolutionStatus`: `RESOLVED`, `NOT_FOUND`, `AMBIGUOUS`.
- `ClarificationReason`: `AMBIGUOUS_COURSE`, `MISSING_COURSE`, `AMBIGUOUS_INTENT`, `MISSING_REQUIRED_CONSTRAINT`, `AMBIGUOUS_OPTION_REFERENCE`.
- `OutOfScopeReason`: `UNSUPPORTED_CAPABILITY`, `REQUIRES_OFFICIAL_AUTHORITY`, `REQUIRES_UNMODELED_DATA`.

## Course entity resolution

`ResolvedCourseReference` carries only authoritative `course_code`, `canonical_arabic_name`, and optional `canonical_english_name`. Empty or whitespace-padded identities are invalid. It has no fuzzy-equivalence or inferred-identity flag.

`CourseResolution` represents the resolver outcome:

- `RESOLVED` requires exactly one `ResolvedCourseReference` and no candidates;
- `NOT_FOUND` carries neither a course nor candidates;
- `AMBIGUOUS` carries no chosen course and at least two sorted unique candidate codes.

Ordinary ambiguity/not-found outcomes are domain results, not exceptions.

## Decision and policy references

`DecisionReference(source, code)` preserves an exact upstream decision, reason, status, prerequisite state, or blocker string. It does not rename or reinterpret it. For example:

```python
DecisionReference(
    source=AuthoritativeSource.PHASE5_ELIGIBILITY,
    code="PREREQUISITE_SOURCE_CONFLICT",
)
```

The lowercase upstream prerequisite state can be retained separately and exactly:

```python
DecisionReference(
    source=AuthoritativeSource.PHASE5_ELIGIBILITY,
    code="source_conflict",
)
```

`PolicyVersionReference` tags a version with the source that published it. `PolicySource.AI_ADVISOR` records the Phase 10 policy without incorrectly treating the advisor as an authoritative academic source. No missing Phase 5–9 version is invented.

## Evidence contract

`AdvisorEvidence` is a minimal reference, not a second academic model. It contains:

- one `AuthoritativeSource`;
- a controlled `result_reference`;
- sorted unique relevant course codes;
- sorted unique exact `DecisionReference` values from the same source;
- an optional existing upstream policy version.

It deliberately has no arbitrary payload, metadata, raw JSON, summary blob, model reasoning, or student-history copy. The authoritative Phase 5–9 result remains the source of truth.

## Trace contract

`AdvisorTrace` is internal and immutable. It records:

- `advisor_intent`;
- `answer_authority`;
- sorted unique authoritative sources;
- sorted unique relevant course codes;
- sorted unique decision references;
- sorted unique policy-version references;
- an optional existing Phase 8 or Phase 9 constraint object;
- sorted unique positive option ranks/references.

Decision and version sources must be present in `authoritative_sources_used`. A `GENERAL_INFORMATION` trace cannot claim student-specific deterministic sources. The trace contains no raw prompt, owner identifier, authentication token, secret, arbitrary personal data, or confidence percentage.

## Normalized request contract

`NormalizedAdvisorRequest` represents the internal request after intent interpretation and entity resolution. It contains:

- non-empty `user_message`;
- one `AdvisorIntent`;
- optional `CourseResolution`;
- optional existing `PlannerConstraints` or `DegreePathConstraints`;
- sorted unique positive option references.
- an optional typed `ClarificationRequest` only for `CLARIFICATION_REQUIRED`;
- an optional `OutOfScopeReason` only for `OUT_OF_SCOPE`.

`PlannerConstraints` are valid only for `SEMESTER_PLANNING`; `DegreePathConstraints` are valid only for `DEGREE_PATH_MODELING`. The request has no owner, token, student-attempt, GPA, study-plan, or engine-state override fields.

## Structured result contract

`StructuredAdvisorResult` is the future orchestration result before natural-language generation. It contains intent, authority, trace, optional course resolution, minimal evidence, optional clarification, optional out-of-scope category, and an optional typed `authoritative_payload`. The payload is limited to existing Phase 5–9 result/option types or `CourseInformation`; it is not a generic blob and preserves the original deterministic ordering and status fields. The result has no provider name, temperature, token usage, generated answer text, or API fields.

Validation requires:

- result and trace intent/authority agree;
- evidence sources appear in the trace;
- `DETERMINISTIC` has authoritative evidence;
- `REVIEW_REQUIRED` has evidence retaining upstream decision references;
- `GENERAL_INFORMATION` has no student-specific evidence;
- `CLARIFICATION_REQUIRED` uses `INSUFFICIENT_CONTEXT` and has clarification data;
- `OUT_OF_SCOPE` uses `INSUFFICIENT_CONTEXT` and has an out-of-scope reason.

## Clarification contract

`ClarificationRequest` uses a finite reason and a controlled `message_key`; it does not contain AI-generated clarification prose. Only `AMBIGUOUS_COURSE` can contain candidate course codes, and it requires at least two sorted unique candidates.

## Review-required and insufficient-context behavior

`AnswerAuthority.REVIEW_REQUIRED` does not collapse upstream distinctions. Evidence can retain both `PREREQUISITE_SOURCE_CONFLICT` and `source_conflict`, or the corresponding unresolved codes, exactly as emitted/recorded upstream.

`AnswerAuthority.INSUFFICIENT_CONTEXT` safely represents absent or ambiguous context. Course not-found and ambiguity are expressed through `CourseResolution`; clarification is expressed through `ClarificationRequest`. These ordinary outcomes do not require exceptions.

## Determinism and immutability

All domain models are frozen dataclasses. Input tuples representing sources, codes, references, versions, evidence, and option references are sorted and deduplicated during construction. Ordering follows the declared source-of-truth enum order and then exact string values. Identical logical input therefore creates stable equal structures independent of input ordering.

`AdvisorContractError` is reserved for malformed or contradictory contract states, not normal clarification or not-found outcomes.

## Security boundary

The contracts structurally exclude authentication tokens, owner overrides, attempt overrides, arbitrary GPA/plan overrides, secrets, raw prompts in traces, provider fields, and generic data blobs. The package has no privileged dependencies or write behavior. A source-import audit enforces its pure boundary.

## Contract examples

### A. Resolved eligibility request

“بقدر آخذ 1501221؟” normalizes to `COURSE_ELIGIBILITY` with a `RESOLVED` course reference for `1501221`. Phase 10.3 may later call Phase 5. A successful result will use `DETERMINISTIC` and carry Phase 5 evidence.

### B. Review-required course

For `1505320`, a result can use `REVIEW_REQUIRED`, source `PHASE5_ELIGIBILITY`, and exact decision references such as `REVIEW_REQUIRED`, `PREREQUISITE_SOURCE_CONFLICT`, and `source_conflict`. The contract does not choose a prerequisite interpretation.

### C. Recommendation versus semester request

“شو بتنصحني أنزل؟” is interpreted as either `COURSE_RECOMMENDATIONS` or `SEMESTER_PLANNING` according to the requested artifact and constraints. If that distinction materially changes the operation and cannot be resolved safely, the normalized outcome becomes `CLARIFICATION_REQUIRED` with `AMBIGUOUS_INTENT`.

### D. Ambiguous course

Multiple authoritative name matches produce `AMBIGUOUS`, sorted candidate codes, `CLARIFICATION_REQUIRED`, `AMBIGUOUS_COURSE`, and `INSUFFICIENT_CONTEXT`. No candidate is silently selected.

### E. General question

“شو يعني متطلب سابق؟” uses `GENERAL_ACADEMIC_INFORMATION` and `GENERAL_INFORMATION`, with no student-specific evidence or deterministic-source claim.

## Non-goals

This phase does not implement intent interpretation, entity matching, engine/service calls, evidence collection, explanation generation, providers, prompts, HTTP endpoints, authentication, persistence, database/RLS changes, or UI. It contains no prerequisite evaluation, progress calculation, recommendation scoring, semester validation/ranking, degree-path search/ranking, equivalency logic, or raw prerequisite parsing.

## Next-phase boundary

The exact next phase is **10.3 — Read-Only Deterministic Advisor Orchestration**. It may consume `NormalizedAdvisorRequest`, call existing authorized services, construct `AdvisorEvidence` and `AdvisorTrace`, and return `StructuredAdvisorResult`. It must not require these contracts to absorb transport, provider, persistence, or duplicated academic logic.
