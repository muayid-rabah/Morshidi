# Mock Registration Persistence Implementation

## 1. Purpose

P6.4 implements the persistence and database-security foundation for non-binding Mock Registration intent. It adds no public route, frontend, official registration action, forecast, or institutional aggregate response.

## 2. P6.3 contract version

The implementation targets the committed P6.3 policy version 1.0, including the P6.3.1 target-period vocabulary correction. P6.2 remains the sole domain authority.

## 3. Schema overview

Migration `20260922134625_add_mock_registration_persistence_security.sql` adds four normalized tables and one atomic persistence function. No mutable current pointer, current-demand table, cache, transcript snapshot, or API schema is added.

## 4. Target periods

`mock_registration_target_periods` stores UUID identity, university, provider namespace, provider-namespaced key, exact class, provider-verification fact, source version, explicit expiration state/evidence, and audit timestamps. Its identity fields are immutable; expiration is explicit and irreversible in this contract.

## 5. Revision headers

`mock_registration_intent_revisions` stores the opaque intent/revision identities, trusted Auth owner, normalized academic scope, target-period reference, positive revision, lifecycle, submission validation status, SHA-256 fingerprint, intent provenance, compact versions/reasons, transparency evidence, actor class, and server timestamp.

## 6. Course children

`mock_registration_intent_courses` stores one normalized catalog course identity, its canonical code snapshot, and canonical selection order under one revision. A trigger verifies the course/code/university/study-plan relationship.

## 7. Institutional memberships

`institutional_memberships` is the minimal server-managed foundation: Auth subject, exact university/provider namespace, the sole role `INSTITUTIONAL_ANALYST`, active state, authority source/version, and audit timestamps. It is not a general RBAC system.

## 8. Immutable revision model

Header and child UPDATE or DELETE always raise SQLSTATE `55000`, including for privileged ordinary application access. Changes append a new revision. Future governed retention requires a separately approved schema change or controlled administrative operation.

## 9. Revision uniqueness

The database uniquely enforces `(owner_user_id, university_id, major_id, study_plan_id, study_plan_version, target_period_id, revision)`. `intent_id` is independently unique.

## 10. Fingerprint/idempotency

The database accepts only lowercase 64-character hexadecimal fingerprints produced before persistence by the P6.2/application boundary. Same proposed revision and fingerprint returns `IDEMPOTENT_REPLAY`; no duplicate is inserted.

## 11. CAS/concurrency

`persist_mock_registration_revision` takes mandatory nullable `expected_current_revision`, obtains a transaction-scoped advisory lock over the exact logical key, derives the next revision, classifies replay/conflict, and inserts one winner. `null` succeeds only when no current revision exists.

## 12. Atomic transaction

The PostgreSQL function inserts the header and every child in one RPC transaction. Any shape, scope, reference, uniqueness, or child failure aborts the call and removes all partial work.

## 13. Withdrawal

A withdrawal is a new `WITHDRAWN` revision with an empty course array. It does not delete history or mutate official registration.

## 14. Review-required persistence

`REVIEW_REQUIRED` is a distinct stored validation status, allowed only with `SUBMITTED` and at least one compact reason code. P6.5 must continue excluding it from normal valid demand.

## 15. Invalid submission behavior

The function rejects `INVALID`; the header constraint also excludes it. P6.5 must validate through P6.2 before invoking persistence.

## 16. Audit metadata

Server timestamps record creation, transparency acknowledgement, period-state change, and membership update. They never determine revision precedence or academic validity.

## 17. Version/evidence storage

Stored compact evidence includes intent source, catalog sources, prerequisite sources, progress state/reference, Phase 5 policy, Phase 6 policy, P6 contract, target-period source, finite validation reasons, and transparency notice version. No full engine trace is stored.

## 18. RLS

RLS is enabled on all four tables. `authenticated` has owner-only header SELECT and parent-owner child SELECT. Target periods and memberships have no client policy. There are no authenticated INSERT, UPDATE, or DELETE policies.

## 19. Grants

All default object access is explicitly revoked from `PUBLIC`, `anon`, `authenticated`, and `service_role`, then minimum privileges are re-granted. `authenticated` receives only header/child SELECT. `service_role` receives controlled period and membership maintenance plus read access; header/child insertion occurs only through the CAS function.

## 20. Service-role boundary

The server key remains environment-only. Service role bypass of RLS is not treated as authorization; repository methods require explicit owner or institution/period scope.

## 21. Tenant isolation

Header scope is checked against the normalized plan-major-faculty-university chain. A composite period/university foreign key and trigger prevent cross-university periods. Child scope is checked against the parent revision, normalized course university, and study-plan membership.

## 22. Data minimization

The schema contains no student name, email, phone, raw grade, GPA, transcript/attempt snapshot, Advisor conversation, Digital Twin scenario, recommendation trace, credential, offering, capacity, or official registration field.

## 23. Repository adapter

`app.mock_registration_persistence` provides frozen typed persistence records and an HTTP/PostgREST adapter for CAS, exact owner history, exact institution-period candidates, target-period loading, and active membership loading. It maps expected database failures without returning raw PostgreSQL details.

## 24. Runtime validation

Clean migration replay, schema/constraint/index/RLS/grant/function introspection, Data API owner isolation, direct-write denial, anonymous denial, membership self-promotion denial, a real two-client race, CAS/replay/conflict, withdrawal, review persistence, invalid rejection, rollback, tenant isolation, and privileged immutability were executed against local Supabase.

## 25. Limitations

P6.4 does not authorize callers, rerun academic rules, compute current validity, aggregate demand, expose HTTP APIs, implement rate limiting, persist offerings/capacity, create retention jobs, or provide UI. Explicit period/membership management services are also deferred.

## 26. P6.5 entry conditions

P6.5 may begin only after both clean resets, schema/RLS introspection, focused runtime tests, security advisors, P6.2 and Phase 5–P5/Advisor regressions, full pytest, compilation, secret scan, and diff/scope checks pass. P6.5 must derive the owner from verified auth, rerun P6.2 before CAS, enforce institutional membership before candidate loading, revalidate current state, preserve suppression, and add no raw bypass.
