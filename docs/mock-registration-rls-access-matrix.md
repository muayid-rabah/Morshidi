# Mock Registration RLS and Access Matrix

Policy version: **1.0**. Conceptual only; this file contains no SQL.

RLS and grants are separate controls. Future migrations must explicitly revoke/grant every operation, enable RLS on exposed resources, and test the effective role behavior. Server credentials bypass RLS and therefore require application authorization plus exact repository filters.

| Resource | Actor | SELECT | INSERT | UPDATE | DELETE | Scope Condition | Application-Service Required? | Rationale |
|---|---|---:|---:|---:|---:|---|---:|---|
| Target periods | Anonymous | No | No | No | No | None | Yes | Period identity/lifecycle is not public by default. |
| Target periods | Student owner | No direct table access | No | No | No | Read through owned API context only | Yes | Prevent forged official/expired period state. |
| Target periods | Institutional analyst | No direct table access | No | No | No | Authorized institution through aggregate service | Yes | Analyst needs result scope, not provider rows. |
| Target periods | Institutional advisor | No | No | No | No | None in P6 | Yes | Advisor authority is deferred. |
| Target periods | Server application/period authority | Yes | Controlled | Controlled lifecycle only | No normal delete | Exact authorized university/provider | Yes | Provider-managed period identity and explicit expiry. |
| Intent revision headers | Anonymous | No | No | No | No | None | Yes | Sensitive behavioral data. |
| Intent revision headers | Student owner | Yes | No direct | No | No | `auth.uid()` equals immutable owner | Yes for writes | Owner may read history/current source but writes need validation/CAS. |
| Intent revision headers | Other student | No | No | No | No | Ownership predicate fails | Yes | Prevent BOLA/IDOR. |
| Intent revision headers | Institutional analyst | No direct | No | No | No | No raw-row policy | Yes | Aggregate-only access. |
| Intent revision headers | Institutional advisor | No | No | No | No | None in P6 | Yes | No drill-down by implication. |
| Intent revision headers | Server application | Yes | Yes | No normal update | Governed retention only | Explicit owner or university+period filter after authorization | Yes | Atomic validated persistence and aggregation source. |
| Intent course children | Anonymous | No | No | No | No | None | Yes | Course sets are sensitive. |
| Intent course children | Student owner | Yes | No direct | No | No | Parent header owner equals `auth.uid()` | Yes for writes | Owned read; immutable atomic writes only. |
| Intent course children | Other student | No | No | No | No | Parent ownership fails | Yes | Prevent individual selection disclosure. |
| Intent course children | Institutional analyst | No direct | No | No | No | No raw-row policy | Yes | Analyst receives suppressed aggregate only. |
| Intent course children | Institutional advisor | No | No | No | No | None in P6 | Yes | Case access deferred. |
| Intent course children | Server application | Yes | Yes in same transaction | No | Governed retention only | Same authorized header transaction/scope | Yes | Exact reconstruction and atomicity. |
| Institutional memberships | Anonymous | No | No | No | No | None | Yes | Authorization records are private. |
| Institutional memberships | Student/analyst/advisor | No direct | No | No | No | Membership checked server-side | Yes | Users cannot grant or inspect role records directly. |
| Institutional memberships | Server membership authority | Yes | Controlled | Controlled | Controlled revoke | Exact subject, institution, role, source | Yes | Server-authoritative role management and audit. |
| Aggregate response (virtual/API) | Anonymous | No | N/A | N/A | N/A | None | Yes | Authentication required. |
| Aggregate response (virtual/API) | Student | No | N/A | N/A | N/A | Student role never implies analyst | Yes | Student token cannot access institution demand. |
| Aggregate response (virtual/API) | Institutional analyst | Suppressed result only | N/A | N/A | N/A | Active exact-university membership and permitted scope | Yes | Minimum required P6 institutional role. |
| Aggregate response (virtual/API) | Institutional advisor | No | N/A | N/A | N/A | None in P6 | Yes | Advisor drill-down/aggregate permission deferred. |
| Aggregate response (virtual/API) | Server application | Internal computation | N/A | N/A | N/A | Authorized membership, university, period, bounded query | Yes | Calls P6.2 and emits safe result only. |

No future view may bypass these controls. Any exposed view must preserve invoker security or remain unexposed with revoked `anon`/`authenticated` privileges. No student or analyst direct write policy is authorized.

