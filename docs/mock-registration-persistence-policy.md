# Mock Registration Persistence Policy

Policy version: **1.0**  
Phase: **P6.3 — policy and contracts only**

## 1. Purpose

This policy defines future persistence for student-declared, non-binding Mock Registration intent. Storage never turns intent into enrollment, approval, a reserved seat, or an institutional registration fact.

## 2. Data model

V1 uses three normalized resources: `mock_registration_target_periods`, immutable `mock_registration_intent_revisions` headers, and `mock_registration_intent_courses` children. The period resource owns provider/university namespace, period class, source/version, and explicit operational expiry. The header reconstructs the exact P6.2 intent and compact validation provenance; children preserve its canonical course tuple. No current-pointer or aggregate table is stored.

## 3. Intent revision immutability

Every accepted submission, replacement, review-required submission, or withdrawal creates a new immutable revision. Historical headers and course sets are never rewritten. `SUPERSEDED` and `CURRENT` remain derived dispositions, not mutable stored lifecycle values.

## 4. Header/course structure

The header stores intent ID, owner user ID, university/major/plan/version, period reference, positive revision, P6 lifecycle, server-computed fingerprint, intent provenance/source version, submission validation status, compact reason codes, P6 contract version, validation-basis versions, transparency-notice version, actor class, and server creation time. Children store only header identity plus canonical course identity/order. Submitted/review-required headers have 1–10 unique children; withdrawals have none.

## 5. Ownership

`owner_user_id` uses the existing canonical Supabase Auth subject, `auth.users.id`, also used by `student_academic_profiles.owner_user_id`. No second student-owner namespace is created. The service derives it from verified authentication; payloads cannot provide or override it.

## 6. Target period

A dedicated period entity is required because official/synthetic provider identity and explicit expiry are shared authorization facts, not student-controlled header text. It is institution-scoped, versioned, and immutable in identity. Its period class preserves the exact P6.1 closed values `DECLARED_PLANNING_PERIOD`, `OFFICIAL_PERIOD_REFERENCE`, and `SYNTHETIC_SANDBOX_PERIOD`; persistence introduces no shortened alias or replacement enum. Operational expiry may be changed only by an authorized period-provider/institutional path and must retain audit metadata.

## 7. Revision uniqueness

The exact uniqueness key is `(owner_user_id, university_id, major_id, study_plan_id, study_plan_version, target_period_id, revision)`. Revision is unique within that logical key. Intent ID is independently unique and cannot substitute for this constraint.

## 8. Fingerprint/idempotency

The server computes the P6.2 fingerprint after deriving scope and canonicalizing courses. Same logical key, revision, and fingerprint is a successful idempotent replay returning the existing representation. Same logical key/revision with a different fingerprint is a conflict; nothing is overwritten or inserted.

## 9. Concurrency

Writes use one database transaction with exact-key serialization, compare-and-insert, and the revision uniqueness constraint. `expected_current_revision` is mandatory (`null` only for first submission). The server reads/resolves current state inside the transaction, compares it, assigns `current + 1`, and inserts atomically. A stale expectation or losing concurrent writer receives a conflict; timestamps never choose a winner.

## 10. Atomicity

Header, every child course, fingerprint, lifecycle, validation evidence, notice version, and audit metadata commit together. Validation failure, CAS mismatch, uniqueness conflict, child failure, or database failure rolls back the entire operation. Header-without-courses and partial course sets are impossible successful states.

## 11. Withdrawal

Withdrawal is an explicit immutable `WITHDRAWN` revision with zero child courses. It preserves prior history, becomes current when its CAS succeeds, and immediately removes the key from active demand. It does not delete records or cancel official registration.

## 12. Expiration

Students cannot create `EXPIRED` authority. An authorized period-provider/institutional operation explicitly marks the period expired; service reconstruction then supplies P6.2 expiry semantics. No clock, client timestamp, or student payload infers expiration.

## 13. Validation-before-write

The future write sequence is: verify session; derive owner; load authorized profile/catalog/progress/period context; validate command shape; invoke P6.2; verify current academic-state/version token; begin serialized CAS transaction; persist atomically. Client-supplied validation, scope, fingerprint, or revision is never authoritative.

## 14. Review-required persistence

V1 persists a structurally valid, explicitly submitted `REVIEW_REQUIRED` revision with compact P6 reason codes and validation versions. It can become the current candidate and may support the separately authorized review workload metric, but is excluded from every normal valid-demand metric. It receives no implicit advisor assignment or approval.

## 15. Invalid submission behavior

`INVALID` submissions are returned as structured domain validation and are not stored as intent revisions. Request/security telemetry may record a safe event code later, but never the full invalid course payload by default. Legacy or corrupt persisted rows fail closed during reconstruction/revalidation and are excluded from all aggregates.

## 16. Audit metadata

Minimum metadata is server `created_at`, actor identity class (`STUDENT_AUTHENTICATED`, `APPLICATION_SERVICE`, or authorized period authority), immutable revision/lifecycle, contract version, provenance/source versions, validation status, and notice version. Time is audit metadata only, never ordering authority.

## 17. Source/policy versions

Persist exact plan version, catalog/prerequisite source version(s), progress-state version/reference, Phase 5 policy version, Phase 6 policy version, P6 contract version, target-period source version, and intent source version. Persist compact reason codes, not full engine traces or academic snapshots.

## 18. Revalidation

Stored validation means `SUBMISSION_VALIDITY_AT_TIME_OF_SUBMISSION`. Current reads and institutional aggregation derive `CURRENT_VALIDITY` against current authorized state. Revalidation never edits history. Changed critical versions or student state require re-evaluation; unavailable context yields `STALE_REQUIRES_REVALIDATION` and exclusion.

## 19. Retention

Active/current intent is retained while needed for the disclosed product purpose. Historical revisions use an institution-configured, documented minimum retention schedule. This policy sets no legal duration. Withdrawal stops current contribution but does not promise immediate erasure.

## 20. Hard-delete boundary

No student API hard-deletes revisions or courses. A future verified privacy/legal deletion is a separate governed administrative workflow with authorization, audit, dependency handling, and disclosure; it is not withdrawal.

## 21. Data minimization

Persist no name, email, phone, raw grade, transcript snapshot, attempt payload, recommendation result, Digital Twin scenario, Advisor conversation, demographic attribute, or credential. Store only reconstruction, resolution, aggregation, provenance, transparency, and audit fields.

## 22. Database responsibilities

The database enforces non-null identities, positive revision, finite stored lifecycle/status/provenance, SHA-256 fingerprint shape, exact uniqueness, unique child course per header, foreign/reference integrity, immutable-row protection, transaction integrity, grants, and RLS. It does not implement eligibility, progress, credit limits, elective need, recommendations, revalidation meaning, suppression, or demand arithmetic.

## 23. P6.4 migration contract

P6.4 may implement only period/header/child structures, explicit grants, owner RLS, immutable protections, exact-key/revision indexes, atomic CAS persistence, repository mapping, and migration/runtime security tests. It must verify current Supabase Data API grant defaults explicitly, never rely on automatic exposure, and keep student direct INSERT/UPDATE/DELETE revoked. Services and public APIs belong to P6.5.

## Exact implementation sequence and phase split

The risk-based split is mandatory. P6.4 is persistence/security: (1) migration, (2) constraints and indexes, (3) explicit grants and RLS, (4) immutable persistence repository, (5) exact-key CAS transaction/RPC if required, (6) minimal server-authoritative institutional membership foundation, (7) anonymous/owner/cross-owner/role/tenant runtime tests, and (8) persistence documentation. P6.5 is service/API integration: (1) student application service, (2) institutional authorization service, (3) revalidation and demand service, (4) student API, (5) institutional API, (6) typed/OpenAPI and error mapping, (7) service/API/privacy/concurrency tests, and (8) API documentation. P6.5 cannot begin its data-facing work until P6.4's clean migration replay, RLS isolation, CAS, and secret-boundary gates pass.

## P6.3 traceability

| Classification | IDs | Policy contribution |
|---|---|---|
| Direct P6.3 proposal evidence | `PROP-050` | Locks explicit owner-controlled, non-binding intent persistence distinct from planner output and official registration |
| Enabled by P6.3 proposal evidence | `PROP-032`, `PROP-033`, `PROP-066`, `PROP-088` | Defines future authorized, aggregate-only demand delivery and sandbox-testable controls without claiming outcomes |
| Later proposal dependency preserved | `PROP-031`, `PROP-073`, `PROP-074`, `PROP-078`, `PROP-089`, `PROP-090`, `PROP-091`, `PROP-098` | Keeps advisor, SIS/SSO, continuous lifecycle, multi-plan/university, and regional validation outside this policy slice |
| Direct P6.3 WC evidence | `WC-008`, `WC-009`, `WC-044` | Defines persistence, authorization/privacy, suppression, and API contracts for the existing pure domain capabilities |
| Enabled by P6.3 WC evidence | `WC-015` | Establishes a governed aggregate boundary for later institutional analytics |
| Later WC dependency preserved | `WC-010`, `WC-011`, `WC-035`, `WC-036`, `WC-037` | Leaves capacity, bottleneck validation, provider integration, SSO, and offerings behind their own gates |

These are policy relationships only. No proposal or WC status changes in P6.3.
