# Mock Registration Service Error Matrix

Policy version: **1.0**. The P6.3 service registry contains exactly **14** stable codes. P6.2 reason codes may be attached as typed details only where indicated.

| Error Code | Layer | Trigger | HTTP Status | Persisted? | Retryable? | Student-Safe Message Meaning | Institution-Safe Meaning | Domain Reason Attached? | Security Notes |
|---|---|---|---:|---:|---:|---|---|---:|---|
| `AUTH_REQUIRED` | Auth | Missing/invalid/expired verified session | 401 | No | After re-auth | Sign in is required. | Authentication failed. | No | No token/provider detail. |
| `OWNER_SCOPE_MISMATCH` | Authorization | Internal command/resource owner differs from verified subject | 403 internally; external 404 when existence-sensitive | No | No | Resource is unavailable. | Owner scope did not match. | No | Never confirms another owner's row. |
| `ACADEMIC_CONTEXT_UNAVAILABLE` | Service | Required profile/catalog/progress/source context cannot be loaded | 503 | No | Yes | Academic context is temporarily unavailable. | Validation context incomplete. | Optional context reason | No invented fallback. |
| `ACADEMIC_STATE_CHANGED` | Service | State/version changes between validation and CAS commit | 409 | No | Yes after refresh | Academic information changed; review and retry. | Revalidation required before commit. | No | Prevents time-of-check/time-of-use write. |
| `INVALID_INTENT` | Domain mapping | P6.2 returns `INVALID` | 422 | No | After correction | The intent cannot be accepted as submitted. | Domain validation failed atomically. | Yes | Safe finite reasons only. |
| `REVIEW_REQUIRED` | Domain mapping | P6.2 returns `REVIEW_REQUIRED` and revision is stored | 202 | Yes | Not as same content unless instructed | Academic review is required; this is not valid demand. | Stored in separate review state. | Yes | Never represented as valid. |
| `REVISION_CONFLICT` | Concurrency | Stale expected revision or same revision/different fingerprint | 409 | No new write | Yes after refresh | Intent changed elsewhere; reload before retrying. | CAS/revision conflict. | No | No overwrite or row-order winner. |
| `PERIOD_INVALID` | Scope | Unknown, foreign, forged-official, or disallowed period | 422 | No | After correction | Target period is unavailable. | Period scope/authority invalid. | Optional P6 period reason | Hides foreign sensitive details. |
| `PLAN_SCOPE_INVALID` | Scope | Payload/request cannot resolve to owner's active authorized plan | 422 | No | After correction/context update | Academic plan context is invalid. | Owner/plan/university mismatch. | Optional P6 plan reason | Client plan IDs are not authority. |
| `PERSISTENCE_CONFLICT` | Repository/DB | Unexpected uniqueness/integrity conflict not safely classed as replay | 409 | Rolled back | Yes after reload | Intent could not be saved because state changed. | Integrity conflict; no partial commit. | No | Do not leak schema/constraint names. |
| `PERSISTENCE_UNAVAILABLE` | Repository/DB | Timeout, transport failure, or transaction failure | 503 | Rolled back | Yes | Intent could not be saved right now. | Storage unavailable. | No | No credentials or raw DB errors. |
| `INSTITUTIONAL_ACCESS_DENIED` | Authorization | Authenticated caller lacks active analyst membership for university | 403 | No | No | You do not have access to this institutional view. | Membership/role denied. | No | University parameter alone grants nothing. |
| `AGGREGATION_SCOPE_INVALID` | Institutional service | Invalid/foreign/unsupported institution-period-plan-course scope | 422 | No | After correction | Requested demand scope is invalid. | Exact authorized scope validation failed. | Optional demand reason | No cross-tenant load before rejection. |
| `RESOURCE_NOT_FOUND` | Read service | Owned current intent absent or sensitive resource unavailable | 404 | No | No | Requested resource was not found. | Missing or intentionally concealed resource. | No | Same shape for missing and foreign-owned records. |

Authentication/authorization errors never contain P6 academic reason codes. Database exception text, constraint names, tokens, fingerprints, owner IDs, and hidden aggregate counts are never returned.

