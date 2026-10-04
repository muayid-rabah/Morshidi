# Institutional Demand Authorization Policy

Policy version: **1.0**  
Phase: **P6.3 — policy and contracts only**

## 1. Purpose

Define least-privilege access to privacy-suppressed P6.2 institutional demand without exposing individual intent records or weakening tenant isolation.

## 2. Role model

P6 V1 adds one product permission only: `INSTITUTIONAL_ANALYST`. `STUDENT` remains an ownership context, not an institutional role. `INSTITUTIONAL_ADVISOR` and `INSTITUTION_ADMIN` are not granted P6 demand access and remain future contracts.

## 3. Institutional membership authority

Authorization comes from a server-managed, auditable membership record binding authenticated user, exact university/provider, role, active state, source, and version. User-editable JWT/user metadata is forbidden. A verified institutional IdP claim may seed or reconcile membership later, but never bypass reviewed server mapping.

## 4. Tenant isolation

Membership, requested university, periods, plans, catalog, intents, and optional facts must share one exact university. Queries bind university before loading rows. No default cross-tenant query or post-load in-memory tenant filtering is permitted.

## 5. Student-token boundary

A normal authenticated student token grants no institutional-demand permission, including at the student's own university. Enrollment/profile membership is not analyst authorization.

## 6. Analyst access

An active `INSTITUTIONAL_ANALYST` membership may request only approved aggregate scopes for its exact university and declared purpose. It receives the already-suppressed P6.2 result, never source rows, owner identifiers, or arbitrary cohort slices.

## 7. Advisor boundary

Advisor access to individual students or review queues requires a separate purpose, delegated-access, consent, and audit contract. P6 V1 grants advisors neither raw intent access nor aggregate permission by implication.

## 8. Raw-intent access

Raw persisted intent rows are application-internal aggregation inputs. No anonymous, student, analyst, advisor, or ordinary authenticated Data API policy exposes institution-wide rows. Only the trusted application aggregation path may read them after membership and scope authorization.

## 9. Aggregate-only API

The analyst API emits typed status, approved metrics, coverage, suppression, quality, facts, provenance, versions, and limitations only. It has no student drill-down, export of course sets, or raw-list mode.

## 10. University scoping

Requested university must exactly match an active authorized membership. Multi-university users require distinct memberships and one university per request/result. No combined result exists.

## 11. Period scoping

The period must belong to the authorized university and be an approved exact-period record. V1 has no trends or cross-period query.

## 12. Plan scoping

An optional plan filter must resolve through the catalog to the authorized university. Major/plan/version identities are server-validated; arbitrary client IDs are rejected before source-row loading.

## 13. RLS defense-in-depth

All intent resources enable RLS even when direct Data API grants are revoked. Student SELECT is owner-scoped; student INSERT/UPDATE/DELETE is denied. Institutional human roles have no raw-table policies. Application/service access is constrained by explicit server authorization and repository filters despite privileged database credentials.

## 14. Service-role boundary

Supabase secret/service-role credentials remain server-only and never use `NEXT_PUBLIC_*`, browser storage, logs, or responses. Because privileged keys bypass RLS, every repository call must receive explicit owner or university/period scope from an already-authorized service; unrestricted convenience methods are forbidden.

## 15. Cross-university prohibition

Any mixed university across membership, intent, period, plan, catalog, offering, or capacity input fails closed before aggregation. Sandbox and real institutions never mix.

## 16. Privacy/suppression

Authorization does not bypass P6.2 suppression. No role gets `include_raw`, threshold override, unsuppressed debug output, or hidden-count metadata. Production threshold, allowed dimensions, repeated-query controls, and release review require institutional privacy governance.

## 17. Threat model

Primary threats are owner/scope forgery, direct table access, membership escalation, cross-tenant reads, small-group inference, raw bypass, privileged-key exposure, and stale authorization. Controls are server-derived identity/scope, explicit grants plus RLS, server-managed membership, exact pre-query filters, whole-result suppression, no raw mode, secret isolation, and membership re-check per request.

## 18. Future IdP/SSO

University SSO/OIDC/SAML and machine identities remain WC-036/PROP-074 dependencies. Future claims must be issuer/audience/expiry validated and mapped into server-managed membership. User-editable metadata and stale unrefreshed claims are not role authority.

## 19. P6.4 authorization contract

P6.4 must establish and runtime-test grants/RLS for period/header/course resources and a minimal server-authoritative institutional membership foundation before P6.5 institutional APIs. It must explicitly test anonymous, owner, other student, analyst, advisor, and server actors. No current status claim is advanced by this policy.

