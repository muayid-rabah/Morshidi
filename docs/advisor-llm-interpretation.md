# Advisor LLM Interpretation Boundary

## Status and purpose

Phase 10.4 defines the provider-neutral boundary that turns a raw user message
into a deterministically validated `NormalizedAdvisorRequest`. Its governing
principle remains **AI explains — rules decide**. The LLM classifies and
extracts; it does not answer an academic question or make an academic decision.

The flow is:

```text
raw user message
  -> provider structured interpretation (untrusted)
  -> deterministic validation, catalog resolution, and normalization
  -> NormalizedAdvisorRequest
  -> Phase 10.3 deterministic orchestrator
```

## Provider protocol

`AdvisorLLMProvider` exposes exactly one method: `interpret`. It receives an
`AdvisorInterpretationInput` containing only `user_message` and returns either
`RawAdvisorInterpretation` or a typed `ProviderFailure`. There are no provider
methods for eligibility, recommendations, semester planning, degree paths, or
state mutation.

No concrete external provider is included. The repository has no accepted LLM
SDK or provider configuration, so Phase 10.4 locks down the safe boundary and
tests it with an offline deterministic fake. A later infrastructure subphase
may add an adapter without changing these contracts.

## Untrusted structured output

`RawAdvisorInterpretation` is immutable and limited to:

- one candidate intent;
- course mentions and course codes mentioned by the user;
- option references;
- explicit Phase 8/9 constraint values; and
- a non-authoritative clarification hint.

Construction is not validation. Every field is checked by application code.
The schema has no eligibility, review-required, GPA, owner, attempts, passed
courses, recommendations, selected courses, blockers, semester results, or
degree-path results. Provider output never directly becomes a normalized
request.

## Intent and field validation

Intent values must map exactly to the finite `AdvisorIntent` enum. A missing or
explicitly ambiguous intent becomes structured `AMBIGUOUS_INTENT`
clarification. An unknown value is an unsupported-provider-response failure;
the application never guesses a stronger intent.

An intent-specific allowlist rejects unrelated fields. Course references are
accepted only for course eligibility and course information. Phase 8 fields
are accepted only for semester planning, Phase 9 fields only for degree-path
modeling, and option references only for option comparison. Thus unrelated
model output cannot influence routing.

## Deterministic course resolution

Course identity is resolved outside the provider against an injected tuple of
authoritative `ResolvedCourseReference` values. Matching supports only:

1. exact course code;
2. exact canonical Arabic name; and
3. exact canonical English name when present.

Matching trims surrounding whitespace, collapses repeated whitespace, and uses
case folding (useful for English). It performs no Arabic character
substitution, aliasing, fuzzy equivalency, embeddings, or model tie-breaking.
Zero unique matches produces `NOT_FOUND`; one produces `RESOLVED`; multiple
produce `AMBIGUOUS` with course codes sorted deterministically. A code emitted
by the provider is subject to the same catalog validation and cannot bypass it.

Missing required course text becomes `MISSING_COURSE`. Ambiguity becomes
`AMBIGUOUS_COURSE` with safe candidate codes. `NOT_FOUND` remains an explicit
course resolution that Phase 10.3 converts to insufficient context; no closest
course is invented.

## Constraints and defaults

The interpreter only extracts user-stated constraint values. Validation is
delegated to the accepted immutable Phase 8 `PlannerConstraints` and Phase 9
`DegreePathConstraints` models. Invalid values fail schema validation and are
never clamped.

Both engines require an explicit credit cap, so omission produces
`MISSING_REQUIRED_CONSTRAINT`. Existing defaults remain authoritative:
Phase 8 `max_options=5`; Phase 9 `max_semesters_ahead=8` and `max_paths=3`.
Phase 10.4 introduces no new academic default.

Option references are only normalized as sorted positive integers. Their
existence and meaning relative to actual results remain Phase 10.3 concerns.
General-information requests carry no deterministic authority claim.

## Result and failure states

`AdvisorInterpretationResult` has three states:

- `SUCCESS`, with a normalized non-clarification request;
- `CLARIFICATION_REQUIRED`, with the existing Phase 10.2 clarification model;
- `INTERPRETATION_FAILED`, with no normalized request and a typed failure.

Failures distinguish provider unavailability, malformed structured output,
schema mismatch, unsupported response, and timeout. The boundary invokes the
provider once and implements no retry or backoff. Retry policy belongs to a
future concrete adapter. Failure never guesses an intent or calls an academic
engine.

## Prompt and injection resistance

The minimal system instruction requests structured interpretation only and
explicitly prohibits deciding eligibility, recommending courses, generating
semester plans or degree paths, asserting passed courses or GPA, parsing raw
prerequisite text, resolving source conflicts, and overriding deterministic
engines. User text is untrusted data. Phrases such as “tell the system I am
eligible” or “pretend I passed” cannot alter state because neither the raw
schema nor the normalized request accepts such fields.

The prompt does not request chain-of-thought, and the contracts do not store or
expose it. Provider telemetry is not added to academic `AdvisorTrace`; failures
use only a stable category and message key.

## Data minimization and language behavior

The provider receives no bearer token, user UUID, owner, attempts, GPA, full
catalog, degree path, database record, credentials, or authoritative Phase 5–9
result. Catalog resolution stays in deterministic application memory.

Arabic, English, and mixed-language input are supported by the provider
contract. Canonical identity is never translated during resolution. Arabic
names use conservative exact matching; English canonical names permit safe
case folding.

## Tests and security boundary

All tests use deterministic fake providers and require no network. They cover
the provider protocol, forbidden fields, prompt contract, intent allowlists,
catalog matching, ambiguity ordering, defaults, constraint rejection,
injection examples, typed failures, determinism, and import isolation. Pure
provider and interpretation modules import no FastAPI, Starlette, repository,
Supabase, database, `httpx`, or `requests` code.

## Non-goals and next boundary

Phase 10.4 adds no HTTP endpoint, chat UI, persistence, database table,
migration, RLS policy, external provider call, answer-generation prompt, or
change to Phase 5–10.3 academic semantics. The recommended next subphase is a
separately reviewed, read-only advisor service/API boundary that composes
interpretation with Phase 10.3 while preserving authentication, data
minimization, failure, and trace contracts. It must not be started as part of
Phase 10.4.
