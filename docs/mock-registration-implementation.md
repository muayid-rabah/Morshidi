# Mock Registration V1 Implementation

## 1. Purpose

P6.2 implements deterministic, non-binding registration intent as pure domain logic. It cannot enroll, reserve, approve, or mutate an institutional system.

## 2. Contract version

The implementation is locked to P6 contract `1.0`, 30 reason codes, three lifecycle states, and three validation states.

## 3. Architecture

`app.mock_registration` separates immutable models/registries, canonicalization, fingerprinting, validation, resolution, privacy, supplied-fact matching, aggregation, and orchestration. It has no framework, database, network, provider, clock, random, or LLM dependency.

## 4. Intent model

`RegistrationIntent` carries intent/opaque-owner identity, exact university/major/plan/version, target period, positive revision, lifecycle, course tuple, source class/version, and contract version. Validation produces a separate `ValidatedIntent` with canonical courses, fingerprint, status, reasons, per-course evidence, and declared credits.

## 5. Ownership boundary

Only opaque `owner_scope_id` is accepted and must match the supplied authoritative snapshot. Authentication and authorization remain outside this pure layer; intent IDs, fingerprints, and revisions grant no authority.

## 6. Target period

`TargetPeriod` is provider/university-namespaced and supports only `DECLARED_PLANNING_PERIOD`, `OFFICIAL_PERIOD_REFERENCE`, and `SYNTHETIC_SANDBOX_PERIOD`. Official references require an explicitly verified provider source. No date is inferred.

## 7. Lifecycle

Stored lifecycle is exactly `SUBMITTED`, `WITHDRAWN`, or `EXPIRED`. Draft remains client-local; replacement is derived as `SUPERSEDED`.

## 8. Revision model

Revision is a positive caller-supplied integer. Timestamp and row order are absent from precedence.

## 9. Current-intent resolution

`resolve_current_intents` groups by exact owner/university/major/plan/version/period key and applies `LATEST_VALID_INTENT_WINS`. Lower revisions are superseded; invalid and explicitly expired records do not win.

## 10. Canonicalization

Course codes receive only whitespace trimming, then lexicographic tuple ordering. Input order is irrelevant. Duplicate raw codes remain detectable and invalidate the submission; they are never silently accepted.

## 11. Fingerprint

`calculate_intent_fingerprint` uses length-delimited SHA-256 over decision-relevant contract, plan, period, lifecycle, revision, canonical courses, and source fields. It excludes intent ID, owner ID, PII, grades, history, timestamps, and presentation data.

## 12. Phase 5 reuse

Every plan target calls `evaluate_can_take` against the same unchanged authoritative attempts. `ELIGIBLE`, `NOT_ELIGIBLE`, and `REVIEW_REQUIRED` remain distinct.

## 13. Phase 6 reuse

The supplied `AcademicProgress` and normalized progress catalog remain authoritative for completed/in-progress state, group identity, elective satisfaction, and credits. P6 implements no second progress engine.

## 14. Course validation

Exact identity and selected-plan membership precede Phase 5/6 checks. Completed and in-progress targets are invalid; failed/withdrawn history has no special restriction. Per-course output retains Phase 5 decision/reasons, group, credits, finite P6 reasons, and safe limitations.

## 15. Intent validation

Intent-level identity, version, period, revision, lifecycle, context, duplicate, 10-course, and 30.00-credit checks are atomic. `INVALID` precedes `REVIEW_REQUIRED`, which precedes `VALID`.

## 16. Elective behavior

An eligible elective in an already-satisfied Phase 6 group returns `MOCK_REG_ELECTIVE_GROUP_ALREADY_SATISFIED`; Phase 5 eligibility is not rewritten.

## 17. Zero-credit behavior

An eligible zero-credit target is selectable, counts as a course/group/owner selection, and adds exactly zero declared credits.

## 18. Referenced-only behavior

Known but non-plan identities return `MOCK_REG_TARGET_NOT_PLAN_MEMBER`. No fuzzy names, aliases, equivalencies, or inferred membership exist.

## 19. Source conflicts

Phase 5 source conflict remains `REVIEW_REQUIRED`, retains Phase 5 evidence, and excludes the whole intent from valid demand.

## 20. No partial acceptance

One invalid course invalidates the complete submission. One review course makes the complete submission review-required when no invalid reason exists. No valid-looking subset is accepted or counted.

## 21. Withdrawal/expiry

A valid withdrawal has an empty course set and removes the exact key from current demand when it is the latest revision. Expiry is accepted only as explicit lifecycle input and never inferred from the clock.

## 22. Determinism

All models are frozen dataclasses; ordering is canonical; resolution has no mutable global state, time, randomness, or row-order tie break.

## 23. Privacy

Models contain no name, email, phone, raw grade, conversation, or Digital Twin scenario. Aggregate results never expose `owner_scope_id` or individual course sets.

## 24. Persistence decision

No intent repository, table, migration, RLS policy, audit store, retention mechanism, or concurrency transaction is implemented in P6.2.

## 25. API decision

No route, transport schema, authentication flow, or institutional role enforcement is implemented.

## 26. Limitations

The engine does not prove offering availability, official eligibility approval, timetable compatibility, enrollment, adoption completeness, or legal privacy sufficiency. The fixed per-intent bounds are computational safety limits only.

## 27. Future P6.3 integration

P6.3 may add separately authorized persistence/API boundaries only after owner RLS, institutional-role isolation, concurrency/idempotency, retention, audit, and transport disclosure contracts are approved. This implementation remains the rule authority.
