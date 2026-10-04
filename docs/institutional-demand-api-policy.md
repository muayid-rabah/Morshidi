# Institutional Demand API Policy

Policy version: **1.0**  
Phase: **P6.3 — policy and contracts only**

## 1. Purpose

Define a future aggregate-only HTTP boundary over persisted, currently revalidated Mock Registration intent and the unchanged P6.2 demand engine.

## 2. Authentication

The endpoint requires the existing verified Supabase session boundary. Missing or invalid authentication returns `401 AUTH_REQUIRED`.

## 3. Authorization

The service loads an active server-authoritative `INSTITUTIONAL_ANALYST` membership for the requested university before loading intent rows. No role is trusted from user metadata or a university query parameter alone.

## 4. Scope

Minimal route: `GET /api/v1/institutional/demand`. Required query dimensions are `university_id` and `target_period_id`; one exact institution/period result is returned.

## 5. Period requirement

The period must be a known, institution-matching target-period record. Closed/expired periods produce no current contribution; invalid or foreign periods return a typed scope error. No wall-clock inference occurs.

## 6. Optional plan/course filters

Optional exact `study_plan_id` and `course_code` filters may narrow an authorized result only after catalog ownership validation. Arbitrary cohorts, demographics, campuses, cross-period slices, and filter combinations not explicitly approved are rejected. Each permitted filter remains suppression-governed and audit-visible.

## 7. Aggregation pipeline

Verify membership → validate institution/period/optional filters → load institution-and-period candidate revisions only → reconstruct immutable P6 records → revalidate current candidates → resolve with P6.2 → exclude stale/invalid/review records as governed → call P6.2 aggregation/suppression → map the typed result without recomputation.

## 8. Revalidation/freshness

Every aggregate request verifies critical source versions and current student/plan/period state. Changed state is re-evaluated. Unavailable context excludes affected candidates and marks safe `revalidation_status=INCOMPLETE` plus `stale_records_excluded=true`; no excluded count is exposed. `generated_at` is audit freshness only, not academic truth.

## 9. Nine-metric registry reuse

The API exposes all and only the existing nine P6.2 metric IDs when present in the domain result. P6.3 adds no stale, forecast, confidence, bottleneck, or operational metric.

## 10. Coverage

Coverage fields come directly from P6.2 and remain labeled observed intent. Unknown denominator produces no population percentage; partial adoption remains explicit.

## 11. Suppression

The response is exactly the already-suppressed domain result. Suppressed values, category identities, counts, coverage numbers, offerings, and capacity arithmetic stay absent. Authorization never lowers the configured threshold.

## 12. Quality flags

The seven P6.2 quality flags remain unchanged. API freshness metadata is separate typed service metadata and does not masquerade as an additional domain quality flag.

## 13. Offering/capacity behavior

Offering/capacity persistence and real adapters are deferred. If no exact authorized facts are supplied by a future provider boundary, demand still computes and the existing unavailable states are returned. No zero filling or inference occurs.

## 14. Response fields

Allowed fields: API/contract version, demand status, exact authorized scope and period, approved metrics, suppressed metric IDs, coverage, seven quality flags, finite reasons, intent/fact provenance, source versions, revalidation status, stale-exclusion boolean, generated-at audit time, and limitations.

## 15. Forbidden fields

No owner/student ID, name, email, phone, individual course set, raw intent row, grade, GPA, attempt, transcript, Advisor conversation, recommendation trace, Digital Twin scenario, credential, raw threshold population, or unsuppressed debug field.

## 16. Error semantics

`401` means unauthenticated; `403 INSTITUTIONAL_ACCESS_DENIED` means authenticated without required membership; `404 RESOURCE_NOT_FOUND` hides foreign/missing sensitive resources where necessary; `409` is reserved for consistency conflicts; `422 AGGREGATION_SCOPE_INVALID` covers invalid authorized query shape; `503` covers unavailable required context/storage. Domain reasons remain separate.

## 17. Rate-limit future

P6.5 must provide configurable abuse/query-cost and repeated-overlapping-query controls before broad analyst access. P6.3 invents no numeric rate. Rate limiting never replaces authorization or suppression.

## 18. No forecasting

Responses say observed/current declared intent only. They contain no predicted enrollment, probability, confidence, trend, bottleneck rank, section estimate, staffing recommendation, or automated decision.

## 19. No raw bypass

There is no `include_raw`, debug query, privileged analyst flag, alternate unsuppressed serializer, or direct raw-table endpoint. Future operational debugging is separate server-only tooling with its own audit contract.

## 20. P6.4 implementation contract

P6.4 supplies persistence/RLS/membership foundations and repository queries only. P6.5 may implement this endpoint after runtime isolation and concurrency closure. Aggregate caching, history/trends, machine access, real offering/capacity providers, dashboards, and SIS integration remain deferred.

