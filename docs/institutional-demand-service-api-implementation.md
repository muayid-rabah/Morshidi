# Institutional Demand Service/API Implementation

## 1. Purpose

P6.5 implements authenticated, descriptive, aggregate-only Institutional Demand over current Mock Registration intent.

## 2. Auth boundary

The route reuses verified Supabase Auth. A student session alone grants no institutional permission.

## 3. Membership authorization

The service loads an active server-managed `INSTITUTIONAL_ANALYST` membership for the authenticated subject and exact requested university. JWT user metadata is ignored.

## 4. Tenant isolation

Membership authorization occurs before period, plan, or candidate loading. One request and result contain exactly one university and period.

## 5. Candidate loading

The repository receives the already-authorized university, target period, and optional validated plan. A course filter is accepted only with a validated plan scope.

## 6. Current-intent resolution

P6.2 `resolve_current_intents` selects current immutable records; superseded, withdrawn, expired, invalid, and conflicted history cannot inflate demand.

## 7. Revalidation

Each current candidate is evaluated against current owner academic context and explicit period state. Historical submission evidence remains immutable.

## 8. P6.2 aggregation

The service passes revalidated current records and normalized plan-course facts to unchanged `aggregate_institutional_demand`.

## 9. Nine metrics

The API serializes only the closed nine-ID P6.2 registry. It adds no forecast, stale, confidence, trend, priority, bottleneck, section, or staffing metric.

## 10. Coverage

Coverage remains observed-intents-only with no invented population denominator. Partial/unknown coverage semantics come directly from P6.2.

## 11. Suppression

The versioned disclosure threshold is server configuration. The value `3` is a development/synthetic default only; non-development startup requires explicit privacy and workload settings before the institutional service is exposed. Suppressed output preserves P6.2 whole-result removal of metrics, populations, category identities, facts, and capacity arithmetic.

## 12. Review metric

The existing `REVIEW_REQUIRED_INTENT_OWNER_COUNT` may be included under the same suppression boundary. Review owners never enter valid demand metrics.

## 13. Freshness

Service metadata is only `COMPLETE` or `INCOMPLETE` plus `stale_records_excluded`; it exposes neither excluded count nor identity. `generated_at` is audit time only.

## 14. Offering/capacity absence

No provider adapter is implemented. Missing offering/capacity facts remain unavailable, never zero or inferred not offered.

## 15. Response fields

The response allowlist contains exact scope/period, nine metrics, suppression, coverage, seven quality flags, reasons, provenance, source versions, freshness, generated time, and limitations.

## 16. Forbidden fields

No owner/student ID, name, email, phone, course-set list, grade, attempt, transcript, recommendation trace, Digital Twin scenario, Advisor conversation, token, threshold population, or debug row is serialized.

## 17. Error mapping

No auth is `401`; missing/inactive/wrong-university membership is `403`; invalid authorized scope is `422`; required storage/context unavailability is safe `503`.

## 18. Runtime authorization tests

Tests cover anonymous, ordinary student, active analyst, absent/inactive-equivalent membership, wrong university, and authorization-before-candidate-load behavior.

## 19. Privacy tests

Tests cover aggregate-only serialization, suppressed metrics/population/coverage, no raw bypass parameter, no identity fields, and absence of grades, scenarios, and conversations.

## 20. Performance

Synthetic in-process measurements (excluding network/database latency) recorded: submit 0.533 ms, current read 0.324 ms, revalidation 0.116 ms, 100-intent service-plus-domain aggregation 9.058 ms with 0.503 ms in the pure domain aggregation, and 500-intent service-plus-domain aggregation 37.764 ms with 1.849 ms in the pure domain aggregation. These are local engineering observations, not production latency claims.

## 21. Limitations

Repeated overlapping-query auditing/rate controls, production privacy threshold approval, real adoption denominators, cache/history/trends, machine access, and institutional validation remain open.

## 22. Future provider/UI integration

Future providers may supply exact authorized offerings/capacity without changing demand meaning. Future UI must preserve observed-intent and suppression language and cannot expose raw records.
