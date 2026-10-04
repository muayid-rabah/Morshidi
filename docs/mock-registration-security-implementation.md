# Mock Registration Security Implementation

## 1. Threat model implementation

P6.4 implements database controls for owner/scope forgery, direct Data API mutation, cross-owner access, revision races, replay conflicts, partial writes, membership self-promotion, cross-university references, forged period class, duplicate courses, and privileged accidental history mutation. API inference and response threats remain P6.5.

## 2. Student ownership

Revision ownership references `auth.users.id`. The CAS function is inaccessible to student roles, and future P6.5 must supply the owner derived from verified authentication.

## 3. Cross-owner isolation

The only student read policies compare `(select auth.uid())` with header `owner_user_id`; child reads require an owned parent. Runtime tests with two synthetic users produced no cross-owner rows.

## 4. Direct-write denial

`authenticated` has no INSERT, UPDATE, or DELETE grant on periods, revisions, children, or memberships and no write policy. Runtime Data API requests for header INSERT/UPDATE/DELETE were denied.

## 5. Historical immutability

Database triggers reject header and child UPDATE/DELETE with SQLSTATE `55000`, independently of RLS. Database-owner runtime attempts confirmed the trigger boundary.

## 6. Membership authority

Only `service_role` receives membership maintenance privileges. The only stored role is `INSTITUTIONAL_ANALYST`; no JWT user metadata participates. Authenticated analyst self-create, update, or enumeration attempts were denied.

## 7. Cross-university isolation

Normalized catalog checks, a period/university composite FK, revision scope validation, and child plan/university validation fail closed. A synthetic University A intent referencing a University B period failed atomically.

## 8. RPC/function security if applicable

`persist_mock_registration_revision` is narrowly `SECURITY DEFINER`, fixes `search_path` to empty, fully qualifies database objects, accepts no caller-selected revision, and performs only persistence/CAS work. `PUBLIC`, `anon`, and `authenticated` EXECUTE are revoked; only `service_role` may execute it.

## 9. RLS/grants defense in depth

All new tables have RLS and explicit grants. The current Supabase opt-in exposure model is not assumed: migrations revoke first and grant only the intended operations. Security advisors report no mutable-search-path warning for any P6.4 function.

## 10. Anonymous behavior

`anon` has no table privilege, policy, or CAS execution permission. Runtime sensitive-table access was rejected.

## 11. Service credential boundary

No key is stored in source, docs, fixtures, browser code, `NEXT_PUBLIC_*`, logs, or error messages. Local tests inject synthetic local-only credentials through environment variables.

## 12. Runtime security tests

Runtime evidence covers owner/cross-owner SELECT, denied authenticated CRUD, denied anonymous access, denied membership self-promotion/change/read, analyst raw-intent denial, function execute privileges, RLS/policy catalogs, cross-university references, duplicate courses, atomic rollback, concurrent writers, and privileged immutable-history triggers.

## 13. Residual risks

P6.5 must implement authentication, owner derivation, membership authorization, state revalidation, request limits, suppression, response allowlists, and safe HTTP mapping. Repeated aggregate-query inference, real IdP membership reconciliation, operational key compromise, and governed retention remain later controls.

## 14. P6.5 authorization requirements

Verify the Supabase session; derive owner from the subject; never accept owner authority from payloads; look up active server-managed membership before any institutional candidate query; require an exact university intersection; apply period/plan filters before loading; rerun P6.2/current-state validation; keep student tokens out of institutional demand; and return only suppressed aggregate output.
