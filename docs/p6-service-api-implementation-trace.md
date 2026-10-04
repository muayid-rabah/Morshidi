# P6 Service/API Implementation Trace

Contract: P6.3 policy 1.0. Phase: P6.5. P6.2 remains domain authority and P6.4 remains persistence/security authority.

## Contract implementation

| P6.3 requirement | Implementation | Automated evidence | Result |
|---|---|---|---|
| Four routes | Typed FastAPI routers and schemas | Route inventory/OpenAPI test | PASS |
| Verified owner | Existing `get_current_user`; no owner field | Auth and forged-field tests | PASS |
| Academic scope | `SupabaseAcademicContextLoader` | Unit and local integration | PASS |
| Validation/fingerprint | Unchanged P6.2 validation/fingerprint | Valid/invalid/review/replay tests | PASS |
| CAS/idempotency | P6.4 repository RPC | Unit CAS plus real local flow | PASS |
| Withdrawal | Empty immutable next revision | Unit/local history tests | PASS |
| Current validity | `revalidation.revalidate` | Matrix transition tests | PASS |
| Membership/tenant | Membership before candidate load | Spy and local Auth tests | PASS |
| Current resolution | P6.2 resolver | Supersession/withdrawal regressions | PASS |
| Demand/privacy | P6.2 aggregation/suppression | Aggregate and leakage tests | PASS |
| Safe errors | Closed 14-code registry/handler | Registry and HTTP tests | PASS |
| No raw bypass | No route or schema option | OpenAPI/source/response tests | PASS |

## Revalidation matrix

| Case | Result |
|---|---|
| No academic change | `CURRENT_VALID`; included |
| Course completed | `CURRENT_INVALID`; excluded; history unchanged |
| Course in progress | `CURRENT_INVALID`; excluded; history unchanged |
| Source/policy changes | Fresh P6.2 result controls eligibility |
| Plan version changes | `STALE_REQUIRES_REVALIDATION`; excluded |
| Period closes | `EXPIRED`; excluded |
| Course removed | Current P6.2 plan-scope invalid; excluded |
| Conflict introduced | `REVIEW_REQUIRED`; excluded from valid demand |
| Conflict resolved | Fresh P6.2 result may restore current validity |
| Context unavailable | Freshness `INCOMPLETE`; excluded without count |

## Service errors

All and only these 14 codes are implemented: `AUTH_REQUIRED`, `OWNER_SCOPE_MISMATCH`, `ACADEMIC_CONTEXT_UNAVAILABLE`, `ACADEMIC_STATE_CHANGED`, `INVALID_INTENT`, `REVIEW_REQUIRED`, `REVISION_CONFLICT`, `PERIOD_INVALID`, `PLAN_SCOPE_INVALID`, `PERSISTENCE_CONFLICT`, `PERSISTENCE_UNAVAILABLE`, `INSTITUTIONAL_ACCESS_DENIED`, `AGGREGATION_SCOPE_INVALID`, and `RESOURCE_NOT_FOUND`.

## P6PA final classification

| Classification | IDs | Result |
|---|---|---|
| `IMPLEMENTED_P6_4` | 002, 007–026, 031, 041, 051, 052, 059–063, 065, 066, 069, 072 | PASS (34) |
| `IMPLEMENTED_P6_5` | 001, 003–006, 027–030, 032–034, 037–040, 042–049, 053–058, 064, 067, 068, 070, 071 | PASS (35) |
| `LATER_EXTERNAL` | 035, 036, 050 | OPEN (3) |

The P6.5 scenarios are covered by focused service/API, OpenAPI, revalidation, authorization, privacy/suppression, and real local Supabase integration tests. The three external scenarios remain real offering provider, capacity provider, and governed retention decisions; no evidence is fabricated.

## Boundaries

No frontend, official registration, SIS mutation, provider import, forecast, ML, section recommendation, bottleneck rank, faculty workload, raw analyst list, Digital Twin/planner/recommendation conversion, Advisor submission, LLM call, or P7 work was added.

## Performance evidence

Synthetic in-process benchmark, excluding network/database latency: submit 0.533 ms; current read 0.324 ms; revalidation 0.116 ms; 100-intent institutional service plus domain 9.058 ms (pure domain 0.503 ms); 500-intent service plus domain 37.764 ms (pure domain 1.849 ms). These figures bound local implementation behavior only and make no production claim.
