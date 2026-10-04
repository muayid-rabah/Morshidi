# P6 Persistence and Security Implementation Trace

Contract: P6.3 policy version 1.0 with P6.3.1 vocabulary correction. Implementation phase: P6.4. This trace credits only persistence/security evidence; API behavior remains deferred.

## Contract-to-implementation trace

| P6.3 clause | Migration/table/function/repository implementation | Runtime/unit evidence | Result |
|---|---|---|---|
| Exact period classes | Target-period CHECK uses all three full P6.1 values | Reset, constraint introspection, P6PA-020–022 | PASS |
| Institution-scoped target period | University FK plus provider/key/version uniqueness | Cross-university runtime test | PASS |
| Immutable revisions | Header/child mutation triggers; no update/delete grants | Owner CRUD and database-owner trigger tests | PASS |
| Derived current state | No pointer, `is_current`, active revision, or demand table | Schema scan | PASS |
| Exact revision uniqueness | Seven-part UNIQUE constraint | Constraint introspection and CAS tests | PASS |
| Fingerprint/idempotency | SHA-256 shape CHECK and CAS replay branch | Same-fingerprint replay test | PASS |
| Same-revision conflict | CAS distinguishes same intent ID/different fingerprint | Conflicting replay test | PASS |
| `expected_current_revision` | Nullable expected value; server derives `expected + 1` | First, next, stale, and race tests | PASS |
| Concurrent writers | Exact-key advisory transaction lock plus uniqueness | Real two-client ThreadPool race | PASS |
| Atomic header/children | One PostgreSQL RPC transaction | Invalid second child leaves no header/children | PASS |
| Withdrawal | Empty child arrays required for `WITHDRAWN` | Revision 4 withdrawal/history test | PASS |
| `REVIEW_REQUIRED` | Distinct status and nonempty reasons constraint | Review revision runtime test | PASS |
| `INVALID` no-write | Function and table status reject `INVALID` | Invalid call and absence query | PASS |
| Owner source | FK to `auth.users.id` | Constraint introspection and synthetic Auth users | PASS |
| Plan/university integrity | Revision-scope trigger over normalized catalog | Valid and mismatched scope tests | PASS |
| Child/plan integrity | Child trigger joins parent, course, and plan membership | Invalid child rollback test | PASS |
| Membership authority | Server-only table; exact analyst role | Self-create/update/read denial | PASS |
| Tenant isolation | University FKs, composite period FK, exact repository filters | University A/B runtime mismatch | PASS |
| Data minimization | Compact columns only | Information-schema privacy scan | PASS |
| Repository boundary | Frozen typed records and exact-scope methods | Focused mock transport plus real mapping tests | PASS |
| Error mapping | SQLSTATE/PostgREST codes mapped to safe stable persistence failures | Parameterized unit test | PASS |

## RLS access-matrix implementation

| Resource/actor | Implemented access | Evidence | Result |
|---|---|---|---|
| Target periods / anonymous | None | Grants and runtime anonymous denial | PASS |
| Target periods / student | No direct access or write | Grants/policy introspection | PASS |
| Target periods / analyst/advisor | No direct access | No human-role policy | PASS |
| Target periods / server | SELECT/INSERT/UPDATE, no DELETE | Grant introspection | PASS |
| Revision headers / anonymous | None | Runtime denial | PASS |
| Revision headers / owner | SELECT only | Two-user RLS runtime test | PASS |
| Revision headers / other student | No rows | Two-user RLS runtime test | PASS |
| Revision headers / analyst/advisor | No institution-wide raw policy | Analyst token returns no rows | PASS |
| Revision headers / server | Scoped SELECT; INSERT only through CAS | Grant/function introspection | PASS |
| Course children / anonymous | None | Runtime denial/grants | PASS |
| Course children / owner | Parent-owner SELECT only | Owner child runtime test | PASS |
| Course children / other student | No cross-owner rows | Two-user RLS runtime test | PASS |
| Course children / analyst/advisor | No institution-wide raw policy | Analyst raw-row test | PASS |
| Course children / server | SELECT; atomic insert only through CAS | Grant/function introspection | PASS |
| Memberships / anonymous or human user | No direct CRUD/read | Runtime self-promotion/change/read tests | PASS |
| Memberships / server authority | Controlled CRUD | Grant introspection and synthetic fixture | PASS |
| Aggregate virtual/API rows | Not implemented in P6.4 | Classified `DEFERRED_P6_5` | DEFERRED |

## Concurrency-matrix implementation

| Case | P6.4 behavior/evidence | Result |
|---|---|---|
| First submission | `null` expected creates revision 1 | PASS |
| Normal next revision | Correct N creates N+1 | PASS |
| Same revision/same fingerprint | Returns `IDEMPOTENT_REPLAY` | PASS |
| Same intent/revision/different fingerprint | Returns `PERSISTENCE_CONFLICT` without overwrite | PASS |
| Stale expected revision | Returns `REVISION_CONFLICT` | PASS |
| Two concurrent writers | Advisory lock permits exactly one insert | PASS |
| Withdraw versus submit | Uses the same CAS primitive; one-winner invariant | PASS |
| Duplicate network request | Same-fingerprint replay leaves one row | PASS |
| Database unique conflict | Constraint plus typed repository mapping | PASS |
| Child insertion failure | Entire transaction rolls back | PASS |
| Academic state changes | P6.5 service concern; evidence fields stored | DEFERRED_P6_5 |
| Review-required retry | Same CAS/replay path and stored distinct status | PASS |

## Persistence threat-model implementation

| Threat | P6.4 control | Result |
|---|---|---|
| Another owner ID | Student cannot execute CAS or insert tables; owner FK exists | PASS |
| Foreign university/plan | Normalized scope trigger | PASS |
| Replay/conflicting race | CAS lock, fingerprint, intent identity, unique key | PASS |
| Direct insert/update/delete | Explicit revokes, no policies, immutability triggers | PASS |
| Membership escalation | No human membership privileges/policies | PASS |
| Cross-university access/reference | Exact repository predicates and relational checks | PASS |
| Client-forged validation/fingerprint/period | Student cannot invoke CAS/manage periods; P6.5 must recompute | PARTIAL_P6_4 |
| Stale academic state | Compact versions stored; revalidation deferred | DEFERRED_P6_5 |
| Oversized/duplicate course set | CAS requires 1–10 unique canonical courses | PASS |
| Service credential exposure | Server-only adapter/env; source scan | PASS |
| Aggregate inference/raw bypass | No aggregate API exists | DEFERRED_P6_5 |

## P6PA 72-scenario classification

| ID | Classification | P6.4 evidence or remaining owner |
|---|---|---|
| P6PA-001 | DEFERRED_P6_5 | Current-intent service/API resolution |
| P6PA-002 | IMPLEMENTED_P6_4 | Owner RLS blocks another student |
| P6PA-003 | DEFERRED_P6_5 | API `401` mapping |
| P6PA-004 | DEFERRED_P6_5 | Auth-derived owner command mapping |
| P6PA-005 | DEFERRED_P6_5 | Service plan-scope validation before CAS |
| P6PA-006 | DEFERRED_P6_5 | Service university-scope validation before CAS |
| P6PA-007 | IMPLEMENTED_P6_4 | First CAS revision |
| P6PA-008 | IMPLEMENTED_P6_4 | Next CAS revision |
| P6PA-009 | IMPLEMENTED_P6_4 | Stale expected revision |
| P6PA-010 | IMPLEMENTED_P6_4 | Idempotent fingerprint replay |
| P6PA-011 | IMPLEMENTED_P6_4 | Same intent/revision conflicting fingerprint |
| P6PA-012 | IMPLEMENTED_P6_4 | Real concurrent writers |
| P6PA-013 | IMPLEMENTED_P6_4 | Atomic header/children |
| P6PA-014 | IMPLEMENTED_P6_4 | Child failure rollback |
| P6PA-015 | IMPLEMENTED_P6_4 | `INVALID` rejected with no row |
| P6PA-016 | IMPLEMENTED_P6_4 | Review row persists; API 202 remains P6.5 |
| P6PA-017 | IMPLEMENTED_P6_4 | Withdrawal revision |
| P6PA-018 | IMPLEMENTED_P6_4 | Shared one-winner CAS invariant |
| P6PA-019 | IMPLEMENTED_P6_4 | Explicit expired-period write rejection |
| P6PA-020 | IMPLEMENTED_P6_4 | Exact declared period enum constraint |
| P6PA-021 | IMPLEMENTED_P6_4 | Exact official-reference enum and verification constraint |
| P6PA-022 | IMPLEMENTED_P6_4 | Exact sandbox enum constraint |
| P6PA-023 | IMPLEMENTED_P6_4 | Direct authenticated INSERT denied |
| P6PA-024 | IMPLEMENTED_P6_4 | Direct authenticated UPDATE denied |
| P6PA-025 | IMPLEMENTED_P6_4 | Direct authenticated DELETE denied |
| P6PA-026 | IMPLEMENTED_P6_4 | Service-role-only CAS succeeds |
| P6PA-027 | DEFERRED_P6_5 | Institutional endpoint authorization |
| P6PA-028 | DEFERRED_P6_5 | Analyst demand service |
| P6PA-029 | DEFERRED_P6_5 | Analyst wrong-university response |
| P6PA-030 | DEFERRED_P6_5 | Advisor API behavior |
| P6PA-031 | IMPLEMENTED_P6_4 | Cross-university storage/reference rejection |
| P6PA-032 | DEFERRED_P6_5 | Institutional response surface |
| P6PA-033 | DEFERRED_P6_5 | Aggregate suppression response |
| P6PA-034 | DEFERRED_P6_5 | API raw/debug option rejection |
| P6PA-035 | LATER_EXTERNAL | Capacity provider/facts |
| P6PA-036 | LATER_EXTERNAL | Offering provider/facts |
| P6PA-037 | DEFERRED_P6_5 | Institutional response privacy |
| P6PA-038 | DEFERRED_P6_5 | Institutional response privacy |
| P6PA-039 | DEFERRED_P6_5 | Institutional response privacy |
| P6PA-040 | DEFERRED_P6_5 | Institutional response privacy |
| P6PA-041 | IMPLEMENTED_P6_4 | Network replay persistence behavior |
| P6PA-042 | DEFERRED_P6_5 | Current-state revalidation |
| P6PA-043 | DEFERRED_P6_5 | Completed-course revalidation |
| P6PA-044 | DEFERRED_P6_5 | In-progress-course revalidation |
| P6PA-045 | DEFERRED_P6_5 | Plan-version revalidation |
| P6PA-046 | DEFERRED_P6_5 | Source-version revalidation |
| P6PA-047 | DEFERRED_P6_5 | Closed-period current-demand service behavior |
| P6PA-048 | DEFERRED_P6_5 | Introduced-conflict revalidation |
| P6PA-049 | DEFERRED_P6_5 | Resolved-conflict revalidation |
| P6PA-050 | LATER_EXTERNAL | Governed legal/product retention decision |
| P6PA-051 | IMPLEMENTED_P6_4 | Database hard delete denied; no API added |
| P6PA-052 | IMPLEMENTED_P6_4 | Secret/source scan |
| P6PA-053 | DEFERRED_P6_5 | API `401` |
| P6PA-054 | DEFERRED_P6_5 | API `403` |
| P6PA-055 | DEFERRED_P6_5 | HTTP conflict mapping |
| P6PA-056 | DEFERRED_P6_5 | HTTP domain validation mapping |
| P6PA-057 | DEFERRED_P6_5 | Privacy-safe API `404` |
| P6PA-058 | DEFERRED_P6_5 | End-to-end non-binding API behavior |
| P6PA-059 | IMPLEMENTED_P6_4 | Explicit grants plus RLS |
| P6PA-060 | IMPLEMENTED_P6_4 | RLS introspection gate |
| P6PA-061 | IMPLEMENTED_P6_4 | Owner-only direct SELECT |
| P6PA-062 | IMPLEMENTED_P6_4 | Other-owner SELECT returns no rows |
| P6PA-063 | IMPLEMENTED_P6_4 | Server membership table; no metadata authority |
| P6PA-064 | DEFERRED_P6_5 | Inactive membership API denial |
| P6PA-065 | IMPLEMENTED_P6_4 | Duplicate course rejected |
| P6PA-066 | IMPLEMENTED_P6_4 | CAS 10-course structural bound |
| P6PA-067 | DEFERRED_P6_5 | Server fingerprint recomputation |
| P6PA-068 | DEFERRED_P6_5 | Server domain validation orchestration |
| P6PA-069 | IMPLEMENTED_P6_4 | Period class/source authority constraints |
| P6PA-070 | DEFERRED_P6_5 | Freshness response metadata |
| P6PA-071 | DEFERRED_P6_5 | Aggregate metric response registry |
| P6PA-072 | IMPLEMENTED_P6_4 | Unique conflict classification/mapping |

Classification totals: **34 `IMPLEMENTED_P6_4`**, **35 `DEFERRED_P6_5`**, and **3 `LATER_EXTERNAL`**; total **72** with no omission.
