# Read-Only Advisor Service and API Boundary

## Purpose and authority

Phase 10.5 exposes the accepted advisor pipeline through an authenticated,
stateless backend boundary. The governing rule remains **AI explains — rules
decide**: provider interpretation is untrusted, deterministic Phase 5–9 output
is authoritative, and the endpoint returns structured data without generating
final assistant prose.

## Endpoint and authentication

`POST /api/v1/me/advisor` is the only advisor operation. It uses the existing
`HTTPBearer` dependency:

```text
Bearer token
  -> server-side Supabase /auth/v1/user verification
  -> CurrentUser.user_id
  -> AdvisorService.advise(owner_user_id, message)
```

JWT claims are not trusted locally. There is no student identifier in the URL
or request body, and the bearer token is never passed to the provider or
returned in the response.

## Request contract

The request has exactly one field:

```json
{"message": "..."}
```

`message` must be a strict string, is trimmed, must remain non-empty, and is
limited to 4,000 characters. `extra="forbid"` rejects ownership, student
state, attempts, GPA, study-plan, provider/model, prompt, credentials,
deterministic results, and engine-search controls.

The use of POST is query-like: a body is needed for the message, but the
operation performs no mutation.

## Service and provider injection

`apps/api/app/services/advisor.py` defines `AdvisorService`. Its constructor
receives the student-state reader, academic-catalog reader, and an
`AdvisorLLMProvider`. Provider selection is server-controlled; the client has
no provider, model, temperature, tool, prompt, token, or API-key field.

The repository currently has no accepted external LLM adapter. Production
wiring therefore uses `UnconfiguredAdvisorLLMProvider`, which returns a typed
provider-unavailable failure. It does not pretend to interpret messages and
does not use regex heuristics. Tests inject deterministic fake providers.

Each request invokes `interpret` exactly once. There is no retry, backoff, or
second answer-generation call.

## Staged orchestration flow

The service performs:

```text
authenticated owner + validated message
  -> one provider interpretation
  -> inspect exact candidate intent only for loading selection
  -> batch-load canonical resolution catalog when a course reference exists
  -> deterministic Phase 10.4 normalization
  -> return early for clarification, out-of-scope, general info, or not-found
  -> load the authenticated student's authoritative state once
  -> batch-load intent-required catalogs
  -> construct immutable AdvisorContext
  -> Phase 10.3 orchestrator
  -> StructuredAdvisorResult
  -> minimized AdvisorResponse
```

Provider output never supplies the owner, study plan, attempts, GPA, catalog,
or engine result. The provider's candidate intent only selects which reads may
be necessary; the Phase 10.4 normalizer still validates the intent and all
fields before orchestration.

## Intent-specific loading

| Intent/outcome | Student state | Resolution catalog | Progress catalog | Eligibility catalog |
|---|---:|---:|---:|---:|
| General information | No | No | No | No |
| Clarification / out-of-scope | No | No | No | No |
| Option comparison without stored comparison context | No | No | No | No |
| Course not found | Once | Once | No | No |
| Academic status / remaining requirements | Once | No | Once | No |
| Course eligibility | Once | Once | No | Once |
| Recommendations / semester plans / degree paths | Once | No | Once | Once |
| Course information | Once | Once | Once | Once |

The current student repository loads the profile and attempts as one accepted
aggregate, so course-information resolution also obtains that aggregate even
though attempts are not used by the course-information projection. This is a
known current repository-granularity limitation; none of those facts are sent
to the provider or unnecessarily exposed by the response.

## Canonical course resolution

`load_advisor_course_catalog` batch-loads canonical course code, Arabic name,
and optional English name for the authenticated profile's university. The
resolver remains the exact deterministic Phase 10.4 resolver. Provider codes
are validated against this catalog, names cannot override canonical values,
and no fuzzy/model equivalency exists.

The repository uses one study-plan/university lookup plus one university
course query. Academic context loaders operate on complete snapshots. No
per-course query occurs inside service or engine loops.

## `AdvisorContext`

The service builds the existing frozen Phase 10.3 `AdvisorContext` from only:

- preloaded progress and/or eligibility catalogs required by the intent;
- persisted attempts from the authenticated profile;
- stored reported GPA/scale/earned-credit facts.

It contains no owner, token, repository, database client, provider, mutable
state, or client override.

## Valid outcomes

All valid domain authorities return HTTP 200:

- `DETERMINISTIC`;
- `REVIEW_REQUIRED`;
- `GENERAL_INFORMATION`;
- `INSUFFICIENT_CONTEXT`.

Clarification and course not-found are valid insufficient-context results, not
HTTP validation errors. Out-of-scope is also a typed valid result.
`REVIEW_REQUIRED` retains exact decision references and prerequisite status,
including the distinction between `unresolved` and `source_conflict`.

`IN_PROGRESS` behavior, raw-prerequisite policy, ranking, planning, and path
semantics are unchanged because Phase 10.3 still invokes the original engines.

## Provider and data failure mapping

| Failure | HTTP | Public error code |
|---|---:|---|
| Provider unavailable/not configured | 503 | `ADVISOR_PROVIDER_UNAVAILABLE` |
| Provider timeout | 503 | `ADVISOR_PROVIDER_TIMEOUT` |
| Malformed/schema/unsupported provider response | 502 | `ADVISOR_PROVIDER_RESPONSE_INVALID` |
| Advisor service not configured | 503 | `ADVISOR_SERVICE_UNAVAILABLE` |

No failure triggers a guessed intent or academic result. Error details contain
no provider payload or exception stack.

Repository and deterministic-engine failures retain established handlers:
missing student resources return 404, catalog/student transport failures 503,
and integrity failures 500. They are not converted into academic answers.

## Response contract and minimization

`AdvisorResponse` exposes:

- advisor policy version;
- intent and answer authority;
- canonical course resolution;
- typed clarification or out-of-scope reason;
- minimized evidence;
- a safe trace subset;
- an optional discriminated, typed academic result.

The result discriminator supports eligibility, academic request errors,
progress, recommendations, semester plans, degree paths, and course
information. Payloads preserve canonical codes/names, ordering, reason/status
codes, constraints, review states, path blockers, and published policy/scope
values while omitting internal search tuples, full trace internals, and
unnecessary repository facts.

The public trace contains only authoritative sources, course codes, decision
references, policy versions, and option references. Evidence omits internal
result-reference strings.

Responses never contain bearer tokens, owner/user UUIDs, Supabase details,
provider credentials, system prompts, raw provider output, model controls,
token usage, chain-of-thought, internal stack traces, or provider telemetry.

## Read-only and stateless guarantees

The advisor service calls only load methods. It cannot create, update, or
delete profiles or attempts; edit GPA; change a study plan; write an advisor
result; register a course; or persist a proposed plan/path. No table,
migration, RLS policy, audit record, conversation, thread, or session storage
is introduced.

Each request is independent. Option comparison therefore returns structured
clarification unless a deterministic comparison result is supplied by a
future explicitly accepted stateless/context mechanism; the client cannot
inject an engine result.

## Network architecture and limitations

Authentication and repository adapters may perform server-side network reads.
Provider invocation is injectable, but the configured production placeholder
performs no external call. Pure interpretation normalization and Phase 10.3
orchestration remain network-free.

There is no final natural-language academic explanation, production LLM
adapter, conversation memory, UI, registration action, offering/timetable
model, or write capability in this phase.

## Next phase boundary

The recommended next subphase is **Phase 10.6 — Arabic-First Conversation
Experience**. It may add UI and carefully bounded conversational continuity,
but must not convert user claims into academic state, expose secrets, weaken
authentication, or replace structured Phase 5–9 authority. Phase 10.6 is not
implemented here.
