# Advisor Provider and Grounded Explanation

Phase 10.6 adds one production LLM integration while retaining the system rule: **AI
explains; deterministic rules decide**. Phase 5–9 outputs and the Phase 10.3
structured result remain authoritative. Generated prose is additive and can be
discarded without losing any academic meaning.

## Provider and configuration

The selected provider is the OpenAI Responses API. It has native strict JSON Schema
output and works through the project's existing `httpx.AsyncClient`, so no provider
SDK or additional dependency is needed. The replaceable `AdvisorLLMProvider` and
`AdvisorExplanationProvider` protocols isolate provider-specific transport.

Server configuration uses `ADVISOR_LLM_API_KEY` and `ADVISOR_LLM_MODEL`. There is no
client-controlled provider, model, prompt, or base URL. Both values must be nonblank
before the concrete adapter is wired. Otherwise interpretation uses the explicit
unconfigured provider and fails safely; explanation is unavailable. Credentials are
used only in the provider transport authorization header and are never added to
inputs, results, traces, responses, or logs.

## Interpretation adapter

Interpretation sends only the trimmed user message, the accepted Phase 10.4
instruction, and a strict schema to `/v1/responses` with storage disabled. The
schema contains only intent, course mentions/codes, option references, explicit
planner constraints, and a clarification hint. It forbids additional fields.
Provider output is still untrusted and passes through all Phase 10.4 normalization,
resolution, and validation before orchestration. Interpretation timeout or
unavailability remains request-blocking with HTTP 503; malformed/unsupported
structured output remains HTTP 502. No intent is guessed.

## Explanation contract and authority

Explanation occurs only after authoritative orchestration. Its immutable input
contains the original message, normalized intent, answer authority, a recursively
serialized answer payload, minimized evidence/trace facts, deterministic language,
and an allowed-course-code set. It contains no user ID, auth token, provider secret,
repository, raw database row, unrelated history, full catalog, or chain-of-thought.
The immutable output contains only `text` and `language`; provider metadata and
confidence percentages are excluded.

The explanation prompt says that it is explaining an authoritative structured
result and must not change, recompute, or invent facts. It preserves canonical
codes/names, ordering, reason/status meanings, and review distinctions. Semester
plans are described as academic-structure-only. Degree paths disclose hypothetical
PASS transitions, bounded search, status and blockers; they are not promises or
registration decisions.

## Language and review behavior

Language is selected before the provider call: a message containing Arabic script
uses Arabic, including mixed messages; otherwise it uses English. Arabic is thus the
default for local mixed-language use, while canonical English names and identifiers
remain unchanged.

`REVIEW_REQUIRED` prose must say that Morshidi cannot make a deterministic decision
and official academic review is necessary. It must retain `unresolved` versus
`source_conflict` and cannot declare the student eligible or not eligible.
`INSUFFICIENT_CONTEXT` clarification, ambiguous candidates, not-found catalog
matches, and out-of-scope responses use deterministic localized templates, avoiding
an unnecessary second provider call. General information may use the provider but
cannot make student-specific claims or invent university rules.

## Grounding and degraded mode

After generation, deterministic guards reject:

- course-code-like tokens outside authoritative facts, safe evidence, or the user's
  quoted message;
- contextual GPA, credit, or semester numbers absent from supplied input;
- obvious eligibility contradictions and any eligibility claim under
  `REVIEW_REQUIRED`;
- loss of the `unresolved`/`source_conflict` review distinction;
- guaranteed/definite graduation, global-optimality, or fastest-path claims.

These checks are deliberately narrow defense-in-depth, not another AI verifier. A
failed, malformed, timed-out, language-mismatched, or guard-rejected explanation
does not destroy the academic result. The API returns the unchanged structured
result, `explanation: null`, and `UNAVAILABLE` or `REJECTED_BY_GUARD`.

## Calls, logging, testing, and limits

A normal generated answer makes exactly one interpretation call and at most one
post-orchestration explanation call. There are no retries or hidden calls. Template
paths make one call. Safe warnings identify interpretation/explanation failure or a
guard rejection without logging prompts, academic state, credentials, or raw
provider responses. Provider request IDs and usage are intentionally ignored and
never enter academic trace.

Tests use mocked providers and `httpx.MockTransport`; no paid/live call is made.
They cover schema transport, timeout/error/refusal handling, configuration and
wiring, both languages, review distinctions, result-family grounding, hallucinated
codes/numbers, contradictions, prompt injection, degradation, exact call count,
API/OpenAPI shape, and secret exclusion.

Current limitations are intentionally conservative: language selection detects any
Arabic script rather than doing linguistic classification, numeric checking targets
academic numeric contexts, and contradiction checks catch narrow explicit phrases
rather than attempting semantic verification. The service remains stateless with no
conversation persistence, vector store, frontend, database migration, or RLS
change. A later phase may add user experience around this stable API contract; Phase
10.6 does not start that work.
