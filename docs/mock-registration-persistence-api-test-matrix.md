# Mock Registration Persistence and API Future Test Matrix

These are policy-only acceptance scenarios for P6.4 persistence/security and P6.5 services/APIs. They do not assert that an endpoint, migration, or role store exists today. Every scenario must run against clean local Supabase migrations where database behavior is involved.

| ID | Area | Scenario | Expected contract result |
|---|---|---|---|
| P6PA-001 | Student read | Authenticated student reads own current intent for a permitted target period | Latest revision for the exact owner/scope is returned |
| P6PA-002 | Student read | Student attempts to read another student's intent | No data; privacy-safe denial/not-found |
| P6PA-003 | Authentication | Anonymous caller reads current intent | `401 AUTH_REQUIRED` |
| P6PA-004 | Ownership | Student includes another `owner_user_id` in submit payload | Field rejected/ignored as untrusted; no foreign write |
| P6PA-005 | Scope | Student submits a foreign study plan | `422 PLAN_SCOPE_INVALID`; no revision |
| P6PA-006 | Scope | Student submits a foreign university | Scope validation fails; no revision |
| P6PA-007 | Revision | First submission with `expected_current_revision: null` | Immutable revision 1 is committed |
| P6PA-008 | Revision | Normal next submission with expected revision N | Immutable revision N+1 is committed |
| P6PA-009 | CAS | Submission uses a stale expected revision | `409 REVISION_CONFLICT`; no write |
| P6PA-010 | Replay | Same exact revision and server fingerprint is retried | Existing outcome is returned; no duplicate rows |
| P6PA-011 | Replay | Same revision key has a different server fingerprint | `409 PERSISTENCE_CONFLICT`; no overwrite |
| P6PA-012 | Concurrency | Two writers race with the same expected revision | Exactly one commits; one receives `409 REVISION_CONFLICT` |
| P6PA-013 | Atomicity | Header and all course children are valid | Header, children, fingerprint, evidence, and metadata commit together |
| P6PA-014 | Atomicity | A child insert fails after header work begins | Whole transaction rolls back; no partial revision |
| P6PA-015 | Validation | Domain result is `INVALID` | `422 INVALID_INTENT`; no persisted revision |
| P6PA-016 | Review | Domain result is `REVIEW_REQUIRED` and structurally valid | Revision persists with review evidence; API returns `202`; normal demand excludes it |
| P6PA-017 | Withdrawal | Student withdraws current intent with correct expected revision | New immutable empty revision commits; history remains |
| P6PA-018 | Withdrawal race | Withdraw and submit race from the same expected revision | One commits; loser receives `409 REVISION_CONFLICT` |
| P6PA-019 | Period | Explicitly expired/closed period is submitted | `422 PERIOD_INVALID`; no write |
| P6PA-020 | Period class | Declared period is valid | Class is preserved exactly as `DECLARED_PLANNING_PERIOD`, never promoted |
| P6PA-021 | Period class | Provider-verified official period is valid | Class is preserved exactly as `OFFICIAL_PERIOD_REFERENCE` |
| P6PA-022 | Period class | Sandbox period is valid in sandbox context | Class is preserved exactly as `SYNTHETIC_SANDBOX_PERIOD`; never presented as official |
| P6PA-023 | Direct DB | Student Supabase client attempts INSERT | Explicit grant/RLS denies write |
| P6PA-024 | Direct DB | Student Supabase client attempts UPDATE | Explicit grant/RLS denies write |
| P6PA-025 | Direct DB | Student Supabase client attempts DELETE | Explicit grant/RLS denies write |
| P6PA-026 | Service write | Authorized application service submits a valid command | Exact-owner/scoped transaction succeeds |
| P6PA-027 | Aggregate auth | Student token calls institutional demand endpoint | `403 INSTITUTIONAL_ACCESS_DENIED` |
| P6PA-028 | Aggregate auth | Active analyst requests own university | Authorized request enters aggregation pipeline |
| P6PA-029 | Tenant | Analyst requests a different university | `403 INSTITUTIONAL_ACCESS_DENIED`; no aggregate |
| P6PA-030 | Advisor | Institutional advisor without analyst role requests demand | Denied; no implicit advisor privilege |
| P6PA-031 | Tenant | Cross-university query/filter is attempted | Denied before data retrieval/aggregation |
| P6PA-032 | Privacy | Institutional caller requests a raw student intent list | No route/option; no raw rows returned |
| P6PA-033 | Suppression | Eligible cohort is below P6.2 threshold | Suppressed response exposes no bypassable count/detail |
| P6PA-034 | Privacy | Caller supplies `include_raw=true` or debug option | Unsupported; raw bypass remains unavailable |
| P6PA-035 | Optional fact | Capacity data is unavailable | Capacity-dependent metric is unavailable/flagged per P6.2; other metrics continue |
| P6PA-036 | Optional fact | Offering data is unavailable | Offering-dependent metric is unavailable/flagged per P6.2; other metrics continue |
| P6PA-037 | Privacy | Institutional response is serialized | Contains no student identifiers |
| P6PA-038 | Privacy | Institutional response is serialized | Contains no grades or transcript snapshot |
| P6PA-039 | Privacy | Institutional response is serialized | Contains no digital-twin scenario/prediction data |
| P6PA-040 | Privacy | Institutional response is serialized | Contains no advisor conversation data |
| P6PA-041 | Network | Client retries after response loss | Server fingerprint/revision rules make retry idempotent |
| P6PA-042 | Revalidation | Academic state and authoritative versions are unchanged | Current valid intent remains eligible; freshness `COMPLETE` |
| P6PA-043 | Revalidation | Intended course is completed after submission | Current intent is invalid for demand and excluded; history unchanged |
| P6PA-044 | Revalidation | Intended course becomes in progress after submission | Current intent is invalid for demand and excluded; history unchanged |
| P6PA-045 | Revalidation | Study-plan version changes | Intent is stale/excluded pending current-scope validation/new revision |
| P6PA-046 | Revalidation | Prerequisite/source version changes | Fresh domain validation determines eligibility; old evidence remains |
| P6PA-047 | Revalidation | Target period closes by explicit authority | Intent is expired/excluded; history unchanged |
| P6PA-048 | Revalidation | Authoritative source conflict is introduced | Current state becomes `REVIEW_REQUIRED`; normal valid demand excludes it |
| P6PA-049 | Revalidation | Authoritative source conflict is resolved | Current validation result controls eligibility without history mutation |
| P6PA-050 | Retention | Historical revisions cross a product retention review boundary | No invented automatic purge; governed policy is required before deletion |
| P6PA-051 | Deletion | Student tries a hard-delete API or database delete | No such API; database denies direct delete |
| P6PA-052 | Secret | Browser bundle/config/log is scanned for service credentials | Service-role/secret key is absent |
| P6PA-053 | HTTP 401 | Missing, malformed, or invalid auth token | `401 AUTH_REQUIRED` |
| P6PA-054 | HTTP 403 | Valid identity lacks institutional membership/role | `403 INSTITUTIONAL_ACCESS_DENIED` |
| P6PA-055 | HTTP 409 | Expected revision or academic state changed | Stable conflict code; no partial write |
| P6PA-056 | HTTP 422 | Domain validation or scope validation fails | Stable error plus separate domain reasons where applicable; no write |
| P6PA-057 | Privacy 404 | Caller probes a foreign sensitive resource | Same privacy-safe `404 RESOURCE_NOT_FOUND` as absent resource |
| P6PA-058 | Non-binding | Student submits/withdraws mock intent | No official registration/enrollment mutation occurs |
| P6PA-059 | Grants | Future tables exist in an exposed schema | Access depends on explicit grants and RLS, not platform default exposure |
| P6PA-060 | RLS | RLS is disabled or missing on an exposed future table | Security test fails deployment/migration validation |
| P6PA-061 | Owner SELECT | Student directly selects owned header/course rows | Only exact owned rows are visible when SELECT is intentionally granted |
| P6PA-062 | Other-owner SELECT | Student directly selects non-owned header/course rows | Zero rows; no existence signal |
| P6PA-063 | Membership source | Caller puts analyst role/university in editable user metadata | Authorization ignores it; server-managed membership controls access |
| P6PA-064 | Membership state | Analyst membership is inactive/revoked | Institutional endpoint returns `403` |
| P6PA-065 | Course integrity | Submitted payload repeats the same course | `422 INVALID_INTENT`; no duplicate child rows |
| P6PA-066 | Resource limits | Payload exceeds configured course/body limit | Rejected before persistence; no partial work |
| P6PA-067 | Fingerprint | Client supplies a forged fingerprint | Ignored/rejected; server recomputes canonical fingerprint |
| P6PA-068 | Validation evidence | Client supplies forged `VALID` status/reasons | Ignored/rejected; server domain result is authoritative |
| P6PA-069 | Period authority | Client labels a declared/sandbox period as official | Server period record wins; forged class is rejected/ignored |
| P6PA-070 | Freshness | Revalidation dependency is unavailable | Affected record is excluded; response says `INCOMPLETE` and `stale_records_excluded: true` without a count |
| P6PA-071 | Metrics | Institutional response registry is inspected | Exactly the P6.2 nine metrics; no stale-intent tenth metric |
| P6PA-072 | Transaction | Database unique conflict occurs after concurrent creation | Mapped deterministically to conflict/replay behavior; no unhandled error or duplicate |

## Coverage gate

The 72 scenarios are the minimum future contract suite. P6.4 owns migration, explicit grants, RLS, repository, transaction/CAS, membership-foundation, and database-isolation coverage. P6.5 owns service/API serialization, HTTP semantics, authorization, revalidation orchestration, aggregate privacy, and end-to-end coverage. Both phases must retain existing P6.1/P6.2 domain regression suites.
