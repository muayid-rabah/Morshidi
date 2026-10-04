# Institutional Intelligence Authenticated Service & API Specification

**Phase**: P7.3  
**Status**: Implemented & Verified  
**Parent Contract**: Phase P7.1 / P7.2 (`0455ed5`, `aaf6f40`)  
**Route**: `GET /api/v1/institutional/intelligence`  
**Security**: Bearer JWT (`CurrentUser`), server-side active `INSTITUTIONAL_ANALYST` membership mandatory  
**Scope**: Read-Only Course-Level Institutional Intelligence Evaluation  

---

## 1. Overview & Architecture

Phase P7.3 implements the authenticated application/service/API layer that exposes course-level Institutional Intelligence to authorized institutional analysts without modifying or compromising the locked P7.2 pure-domain engine.

```
Client (Institutional Analyst)
        │
        ▼  [Bearer JWT]
FastAPI Route: GET /api/v1/institutional/intelligence
        │
        ▼  1. Authenticate & Authorize (`INSTITUTIONAL_ANALYST` role via `institutional_memberships`)
InstitutionalIntelligenceService
        │
        ├─► 2. Resolve & Validate Tenant Scope (Target Period & Study Plan scope validation)
        ├─► 3. Validate Course Code & Load Academic Catalogs (Progress Catalog & CanTakeCatalog)
        ├─► 4. In-Process P6 Demand Loading (`InstitutionalDemandService.demand(...)`)
        ├─► 5. Authoritative Fact Loading (`OfferingFactProvider`, `CapacityFactProvider`)
        │
        ▼  6. Pure-Domain Evaluation (`evaluate_institutional_intelligence`)
P7.2 Engine (13 signals, 6 alerts, decision traces, quality flags)
        │
        ▼  7. Allowlist Response Mapping (`map_institutional_intelligence_response`)
Allowlisted JSON Response DTO (Zero Student Identities, Value=None on Suppression)
```

---

## 2. Security & Tenant Isolation Model

### 2.1 Authority Minimization
- The client **never** acts as an unverified authority primitive.
- The `university_id` query parameter is **optional**:
  - If omitted: the server queries `load_active_memberships_for_user(subject, role="INSTITUTIONAL_ANALYST")`. If exactly one active membership exists, tenant scope is automatically bound to that university. If multiple active analyst memberships exist across institutions, the server safely rejects with `422 AGGREGATION_SCOPE_INVALID`.
  - If provided: the server validates that the authenticated analyst has an active membership matching that exact `university_id`. If not, access is rejected with `403 INSTITUTIONAL_ACCESS_DENIED`.

### 2.2 Authorization Call-Order Invariant
- **Authorization occurs BEFORE any sensitive academic loads**:
  1. The user's active membership in the target institution is verified first.
  2. No study plan, catalog, target period, candidate intent, demand aggregation, offering fact, or capacity fact is queried until authorization succeeds.
  3. Probing non-existent or foreign resources without analyst membership yields `403 INSTITUTIONAL_ACCESS_DENIED` rather than leaking resource existence or metadata.

### 2.3 Cross-Tenant Isolation
- Target periods belong to a specific university (`university_id`) and provider namespace. Querying a period outside the analyst's authorized scope raises `404 TARGET_PERIOD_UNAVAILABLE` or `403 INSTITUTIONAL_ACCESS_DENIED`.
- Study plans belong to a specific university faculty. Scope validation (`validate_plan_scope`) ensures cross-tenant study plans cannot be evaluated, raising `404 STUDY_PLAN_UNAVAILABLE`.

---

## 3. In-Process P6 Institutional Demand Reuse

P7.3 enforces zero duplication of Mock Registration demand processing:
- Institutional Intelligence **never** queries raw intent tables (`mock_registration_intents`, `mock_registration_intent_revisions`, `mock_registration_intent_courses`).
- Institutional Intelligence **never** re-implements revalidation, resolution, or aggregation math.
- It directly calls `InstitutionalDemandService.demand(...)` in-process.
- When `course_code` is a plan-member course, P6 unconstrained demand is loaded with complete privacy guarantees.
- When `course_code` is a referenced-only prerequisite outside the plan, P6 demand is gracefully bypassed (`demand_result=None`), evaluating the curricular and gateway topology cleanly without false aggregation errors.
- **Privacy Suppression Propagation**: When P6 demand is suppressed (`SignalStatus.SUPPRESSED`), signals derived from demand (`INST_SIG_DECLARED_DEMAND_COUNT`, `INST_SIG_DEMAND_TO_CAPACITY_RATIO`, `INST_SIG_DECLARED_CAPACITY_DEFICIT`) have:
  - `status = "SUPPRESSED"`
  - `value = None` (strictly stripped)
  - `quality_flags` includes `SUPPRESSED_FOR_PRIVACY`

---

## 4. Offering & Capacity Fact Providers

External SIS offering and capacity data are retrieved via clean, read-only protocols:
- `OfferingFactProvider.get_offering_fact(university_id, period_key, course_code, study_plan_id) -> OfferingFact | None`
- `CapacityFactProvider.get_capacity_fact(university_id, period_key, course_code, study_plan_id) -> CapacityFact | None`

### Data Hygiene & Missing Facts Handling
Missing offering or capacity facts are **not** treated as HTTP 500 errors:
- If offering data is missing: evaluation succeeds with HTTP 200, emitting `INST_ALERT_OFFERING_DATA_MISSING: true`.
- If capacity data is missing: evaluation succeeds with HTTP 200, emitting `INST_ALERT_CAPACITY_DATA_MISSING: true`. Capacity signals evaluate to `status: "INSUFFICIENT_DATA"`, `value: null`.
- If both are missing: evaluation succeeds with HTTP 200, emitting both data hygiene alerts.

---

## 5. API Endpoint Specification

### `GET /api/v1/institutional/intelligence`

#### Query Parameters
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `target_period_id` | UUID | Yes | Target planning period ID |
| `study_plan_id` | UUID | Yes | Authoritative study plan ID |
| `course_code` | string | Yes | Course code to evaluate (1–50 chars) |
| `university_id` | UUID | No | Optional tenant scope; validated against active membership |

#### Response Codes
| Status | Error Code | Description |
| :--- | :--- | :--- |
| **200 OK** | — | Institutional Intelligence evaluated successfully |
| **401 Unauthorized** | `AUTH_REQUIRED` | Missing or invalid authentication token |
| **403 Forbidden** | `INSTITUTIONAL_ACCESS_DENIED` | Subject is not an active institutional analyst for tenant |
| **404 Not Found** | `TARGET_PERIOD_UNAVAILABLE` | Target planning period does not exist in authorized tenant |
| **404 Not Found** | `STUDY_PLAN_UNAVAILABLE` | Study plan does not exist in authorized tenant |
| **404 Not Found** | `COURSE_UNAVAILABLE` | Course is not in study plan or prerequisite topology |
| **422 Unprocessable** | `AGGREGATION_SCOPE_INVALID` | Ambiguous scope (e.g. multiple memberships without university_id) |
| **503 Unavailable** | `PERSISTENCE_UNAVAILABLE` | Database or upstream storage unavailable |

---

## 6. Response Schema & Allowlisting

All responses are validated against strictly allowlisted Pydantic models with `extra="forbid"`.

### Zero Student Identity Guarantee
- The response schema contains **no** student-level fields:
  - No `student_id`, `user_id`, `owner_user_id`
  - No `student_name`, `email`
  - No `gpa`, `grade`, `attempts`, `transcript`
- All signals are aggregate course-level or curricular metrics.

### Locked Registries Exchanged
- **13 Signals**:
  1. `INST_SIG_DECLARED_DEMAND_COUNT`
  2. `INST_SIG_DECLARED_DEMAND_SHARE`
  3. `INST_SIG_TOTAL_DECLARED_CREDIT_LOAD`
  4. `INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT`
  5. `INST_SIG_SUPPLIED_CAPACITY_COUNT`
  6. `INST_SIG_DECLARED_CAPACITY_DEFICIT`
  7. `INST_SIG_CAPACITY_PRESSURE_STATE`
  8. `INST_SIG_DEMAND_TO_CAPACITY_RATIO`
  9. `INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT`
  10. `INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT`
  11. `INST_SIG_STRUCTURAL_MANDATORY_ROLE`
  12. `INST_SIG_STRUCTURAL_BOTTLENECK_STATUS`
  13. `INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT`
- **6 Alerts**:
  1. `INST_ALERT_CAPACITY_DEFICIT_DETECTED`
  2. `INST_ALERT_ZERO_CAPACITY_WITH_DEMAND`
  3. `INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE`
  4. `INST_ALERT_REVIEW_REQUIRED_PRESENT`
  5. `INST_ALERT_CAPACITY_DATA_MISSING`
  6. `INST_ALERT_OFFERING_DATA_MISSING`

