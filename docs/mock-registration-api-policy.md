# Mock Registration Student API Policy

Policy version: **1.0**  
Phase: **P6.3 — policy and contracts only**

## 1. Purpose

This document defines a future authenticated student API over the immutable P6 persistence and unchanged P6.2 domain engine. It creates non-binding intent only and performs no official registration action.

## 2. Auth boundary

All routes use the existing verified Supabase bearer-token dependency. Missing, malformed, expired, or unverifiable authentication returns `401 AUTH_REQUIRED`. The browser never sends a service-role/secret key or performs authorization by decoding JWT claims.

## 3. Owner derivation

The service derives `owner_user_id` from the verified Supabase Auth subject. No request body, path, or query accepts owner ID. Intent ID, fingerprint, and revision are identifiers, not authority.

## 4. Current-intent read

`GET /api/v1/me/mock-registration/current?target_period_id={id}` returns only the authenticated owner's resolved current state for the server-derived active plan key and exact requested period. Absence returns privacy-safe `404 RESOURCE_NOT_FOUND`; another owner's existence is never disclosed.

## 5. Submit/replace command

`POST /api/v1/me/mock-registration/revisions` accepts exactly `target_period_id`, ordered-or-unordered `course_codes`, `expected_current_revision` (`null` for first submission), and `transparency_notice_version`. The server derives owner, university, major, active plan/version, next revision, lifecycle `SUBMITTED`, provenance, source versions, validation, and fingerprint.

## 6. Withdraw command

`POST /api/v1/me/mock-registration/withdrawals` accepts `target_period_id`, `expected_current_revision`, and `transparency_notice_version`; it accepts no courses or owner/scope fields. The server derives the key and creates the next empty `WITHDRAWN` revision.

## 7. Revision/CAS

The service requires the client's last observed current revision. It atomically compares server current revision and assigns the next positive revision. A mismatch returns `409 REVISION_CONFLICT` with safe current-revision metadata only when the caller owns the logical resource.

## 8. Idempotency

Key+server-assigned revision+server fingerprint is sufficient for V1 retry safety because immutable content and the unique revision key identify one logical operation. A separate `Idempotency-Key` header is deferred. A byte/logically equivalent retry returns the original success body; conflicting content returns `409`.

## 9. Validation sequence

Authenticate → derive owner → load the owner's current academic and period context → validate command shape → invoke P6.2 → check academic-state/version token → execute CAS transaction → map safe response. No persistence occurs before successful domain evaluation.

## 10. REVIEW_REQUIRED behavior

A structurally valid `REVIEW_REQUIRED` result is persisted as a review-required revision and returns `202 Accepted` with status, finite P6 reasons, limitations, and explicit exclusion from normal demand. It is not labeled valid, enrolled, or advisor-approved.

## 11. Conflict behavior

Stale expected revision, same revision/different fingerprint, concurrent-writer loss, or immutable uniqueness conflict maps to stable `409` codes. No timestamp fallback, overwrite, merge, or partial write occurs.

## 12. Error taxonomy

The finite 14-code service registry is defined in `mock-registration-service-error-matrix.md`. Domain reason codes remain nested typed evidence only for `INVALID_INTENT` or `REVIEW_REQUIRED`; they are never substituted for authentication, authorization, concurrency, or persistence errors.

## 13. Privacy

Student responses include only owned intent data and no institutional demand. Logs omit bearer tokens and course sets; safe correlation/intent IDs and error codes are sufficient. Cross-owner requests resolve as generic not-found or forbidden without confirming existence.

## 14. Response language

Responses say “Mock Registration”, “declared intent”, “current intent”, and “review required”. They never say “registered”, “enrolled”, “approved”, “reserved”, or “guaranteed offering”. Every current/write response includes the non-binding limitation.

## 15. No official registration

These routes cannot mutate attempts, progress, SIS state, official registration, offerings, or capacity. Withdrawal affects only current Mock Registration demand participation.

## 16. P6.4 implementation contract

P6.4 implements persistence/security only. P6.5 may add these typed routes after P6.4 runtime RLS/CAS validation and after the existing authentication boundary is reconfirmed. History, advisor drill-down, batch/machine access, official registration, and frontend remain separate phases.

