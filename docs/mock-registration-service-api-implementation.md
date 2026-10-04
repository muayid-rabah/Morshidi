# Mock Registration Service/API Implementation

## 1. Purpose

P6.5 implements the authenticated, non-binding student Mock Registration service and HTTP boundary. It performs no official registration, enrollment, reservation, SIS write, provider import, prediction, or frontend work.

## 2. Architecture

The path is route → verified Auth dependency → application service → authoritative academic-context loader → unchanged P6.2 domain engine → P6.4 repository/CAS → allowlist response mapper. Domain, persistence, service, and transport remain separate.

## 3. Auth boundary

All three student routes reuse `get_current_user`, which verifies the bearer token with Supabase Auth `/auth/v1/user`; no local unverified JWT decode is used.

## 4. Owner derivation

The verified `auth.users.id` subject is the only owner input. Request schemas forbid extra fields and contain no owner, student, or user ID.

## 5. Academic-scope derivation

The server loads the owner's profile, active plan, major, university, normalized catalogs, attempts, and compact plan/source/progress versions. Clients cannot choose university, major, plan, version, validation, or fingerprint.

## 6. Target-period validation

Only `target_period_id` is accepted. The P6.4 repository loads it under the derived university and preserves the exact three period classes. Missing, foreign, or expired write targets fail safely.

## 7. Current-intent service

`GET /api/v1/me/mock-registration/current` loads exact owner/active-plan/period history, reuses P6.2 resolution, and derives current validity. Absence is privacy-safe `404 RESOURCE_NOT_FOUND`.

## 8. Submit service

`POST /api/v1/me/mock-registration/revisions` accepts only period, course codes, expected revision, and notice version. It creates one immutable submitted revision through the P6.4 CAS function.

## 9. Withdraw service

`POST /api/v1/me/mock-registration/withdrawals` accepts no courses and appends an empty immutable `WITHDRAWN` revision. Withdrawing no active logical intent returns `404`.

## 10. Validation-before-write

The service authenticates, derives scope, loads the period and current academic state, invokes P6.2, recomputes a compact state token immediately before CAS, and writes only after successful validation.

## 11. CAS/concurrency mapping

P6.4 `INSERTED`, `IDEMPOTENT_REPLAY`, `REVISION_CONFLICT`, and `PERSISTENCE_CONFLICT` are mapped without raw database text. Stale or losing writes return stable `409` errors.

## 12. Idempotency

Equivalent retry content produces the same P6.2 fingerprint for the proposed revision and returns the existing immutable representation without duplicate rows.

## 13. Review-required behavior

Structurally valid `REVIEW_REQUIRED` intent is persisted, returns HTTP `202`, retains finite P6.2 reasons, and is excluded from normal valid demand.

## 14. Domain-invalid behavior

P6.2 `INVALID` maps to `422 INVALID_INTENT` with safe reason codes and no persistence call.

## 15. Revalidation

Every current read can rerun unchanged P6.2 validation against current attempts, progress, plan, catalog/source, policy, and explicit period state. Immutable submission evidence is never rewritten.

## 16. Current validity

The closed service states are `CURRENT_VALID`, `CURRENT_INVALID`, `REVIEW_REQUIRED`, `STALE_REQUIRES_REVALIDATION`, and `EXPIRED`. Withdrawal has no active current validity.

## 17. Error mapping

The exact 14 P6.3 service codes are implemented separately from the 30 P6.2 domain reasons. HTTP semantics preserve 401, 403, privacy-safe 404, 409, 422, and 503.

## 18. Privacy

Responses contain owned intent only. Logs contain no course payload, academic history, grade, token, key, or raw database exception. There is no history-by-ID or cross-owner route.

## 19. Response language

Responses identify Mock Registration as declared, non-binding intent and explicitly deny enrollment, approval, seat reservation, offering, or official university action.

## 20. OpenAPI/routes

The only student routes are the committed current, revisions, and withdrawals paths. OpenAPI exposes no owner authority, fingerprint, service key, database field, plan authority, scenario, planner result, or recommendation result.

## 21. Runtime tests

Focused tests cover auth, empty/current/review/withdrawn states, valid/invalid/review writes, CAS/replay/conflict, academic-state race, revalidation, owner/scope minimization, OpenAPI, and a real local Auth/API/CAS flow.

## 22. Limitations

There is no frontend, official registration, SIS integration, offering/capacity provider, history API, advisor submission, general idempotency key, or distributed transaction across external academic sources.

## 23. Frontend integration contract

A future frontend must obtain the current revision, require explicit student course confirmation, submit only the minimal command, display review and non-binding language, and refresh on conflicts. It must never receive or use a service key.

## 24. Next phase

The next authorized product slice may build the Arabic-first frontend over these APIs. Real providers, institutional rollout, query governance, and official registration remain separately governed.

