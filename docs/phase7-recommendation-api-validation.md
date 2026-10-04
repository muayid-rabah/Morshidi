# Phase 7.3 — Recommendation Repository Integration, StudentService & API: Validation

**Status:** `VALIDATED`
**Date:** 2026-09-17
**Policy version:** `1.0`

---

## 1. Scope

Phase 7.3 connects the deterministic pure recommendation engine (`apps/api/app/recommendations/`) with the authenticated backend:
- Plan-wide eligibility catalog loading in `AcademicCatalogRepository` and `SupabaseAcademicCatalogRepository`.
- `StudentService.get_course_recommendations` orchestration.
- Authenticated endpoint `GET /api/v1/me/course-recommendations`.
- Optional presentation-only `?limit=N` parameter with validation (`1 <= limit <= 100`).
- Transport schemas in `apps/api/app/api/schemas/recommendations.py`.
- Service unit tests, mocked API tests, and real Plan 12 local Supabase integration tests.

---

## 2. Repository Integration

`AcademicCatalogRepository` protocol and `SupabaseAcademicCatalogRepository` were extended with:

```python
async def load_plan_eligibility_catalog(
    self,
    study_plan_id: UUID | str,
) -> CanTakeCatalog:
```

### Fields Selected Explicitly (No `SELECT *`)
1. `study_plans`: `id,majors(faculties(university_id))`
2. `study_plan_courses`: `id,prerequisite_logic_status,raw_prerequisite_text,display_order,courses(id,course_code,name_ar,catalog_status,university_id)`
3. `course_dependency_groups`: `id,study_plan_course_id,dependency_type,group_number`
4. `course_dependency_options`: `dependency_group_id,courses(course_code,catalog_status,university_id)`

### Integrity Enforcement
- Verified course with no groups raises `CatalogIntegrityError`.
- `not_applicable` or non-executable (`unresolved`, `source_conflict`) course with groups raises `CatalogIntegrityError`.
- Duplicate group numbers for the same course raise `CatalogIntegrityError`.
- Empty dependency group raises `CatalogIntegrityError`.
- Duplicate options within a group raise `CatalogIntegrityError`.
- Prerequisite option belonging to another university raises `CatalogIntegrityError`.

---

## 3. Data-Load Strategy (No N+1 Queries)

The recommendation service executes a strictly bounded, constant set of read requests:

1. `StudentAcademicState` — loaded **once** (`load_student_academic_state`)
2. `AcademicProgressCatalog` — loaded **once** (`load_progress_catalog`)
3. Plan-wide `CanTakeCatalog` — loaded **once** (`load_plan_eligibility_catalog`):
   - 1 query to `study_plans`
   - 1 query to `study_plan_courses`
   - 1–2 chunked queries to `course_dependency_groups` (batch size = 50)
   - 1 chunked query to `course_dependency_options` (batch size = 50)

**Total HTTP requests to Supabase:** 4–5 requests total for the entire recommendation operation.
**Candidate ranking and simulation loop queries:** **0 queries**. All simulations (hypothetical pass, progress delta, newly-eligible evaluation) run purely in memory using the pre-loaded catalogs.

---

## 4. StudentService Orchestration

```python
async def get_course_recommendations(
    self,
    owner: str,
    *,
    limit: int | None = None,
) -> RecommendationResult:
```

### Flow:
1. `state = await self.get_profile(owner)` (authenticates profile existence; raises `StudentProfileNotFound` if missing).
2. `progress_catalog = await self._catalog_repository.load_progress_catalog(state.study_plan_id)`.
3. `eligibility_catalog = await self._catalog_repository.load_plan_eligibility_catalog(state.study_plan_id)`.
4. `recommend_courses(progress_catalog, eligibility_catalog, state.attempts, ...)` executed in memory.
5. If `limit is not None`: trims `ranked_recommendations` to `limit`. `review_required_courses`, `excluded_in_progress`, `methodology_note`, `limitations`, priority tuples, and reason codes are unchanged.
6. Returns `RecommendationResult`.

No recommendation ranking or prerequisite logic is computed in the service layer.

---

## 5. API Endpoint

`GET /api/v1/me/course-recommendations`

- **Authentication:** Bearer token via `get_current_user`.
- **Path / Query parameters:**
  - `limit` (optional integer, `ge=1`, `le=100`): presentation-only slice of `ranked_recommendations`.
  - No `owner_user_id` query/body parameter accepted.
  - No `study_plan_id` query/body parameter accepted.
  - No client-supplied attempt history accepted.

---

## 6. Limit Semantics & Validation

- `limit` applies **only** to `ranked_recommendations`.
- `review_required_courses` is **never** trimmed by `limit`.
- Ranking metadata, priority tuples, reason codes, and sequential ranks (`1..N`) are preserved exactly.
- Validation bounds:
  - `limit < 1` (e.g. 0, -1) -> HTTP `422 Unprocessable Entity`
  - `limit > 100` -> HTTP `422 Unprocessable Entity`
  - Non-integer string -> HTTP `422 Unprocessable Entity`

---

## 7. Response Contract

Exposed via `RecommendationResponse` Pydantic model (`apps/api/app/api/schemas/recommendations.py`):

```json
{
  "study_plan_id": "10000000-0000-0000-0000-000000000005",
  "recommendation_policy_version": "1.0",
  "ranked_recommendations": [
    {
      "course_code": "0300153",
      "course_name_ar": "المهارات الحياتية",
      "credit_hours": "1.00",
      "requirement_group_code": "UNIVERSITY_REQUIRED",
      "requirement_type": "required",
      "course_state": "NOT_ATTEMPTED",
      "eligibility_decision": "ELIGIBLE",
      "effective_credit_contribution": "1.00",
      "group_remaining_credits_before": "18.00",
      "group_remaining_credits_after": "17.00",
      "completes_requirement_group": false,
      "newly_eligible_count": 4,
      "newly_eligible_course_codes": ["0300220", "1501110", "1503270", "1505201"],
      "priority_tuple": [2, 1, "1.00", 0, 4, -7, "0300153"],
      "rank": 1,
      "reason_codes": [
        "REQUIRED_PLAN_COURSE",
        "ADVANCES_REQUIRED_GROUP",
        "UNLOCKS_MULTIPLE_FUTURE_COURSES"
      ],
      "previously_attempted": false
    }
  ],
  "review_required_courses": [
    {
      "course_code": "1505311",
      "course_name_ar": "ذكاء اصطناعي متقدم",
      "credit_hours": "3.00",
      "requirement_group_code": "MAJOR_REQUIRED",
      "requirement_type": "required",
      "review_reason": "PREREQUISITE_LOGIC_UNRESOLVED",
      "previously_attempted": false
    }
  ],
  "excluded_in_progress": [],
  "methodology_note": "These recommendations are based on your modeled academic study plan...",
  "limitations": [
    "Recommendation quality is bounded by modeled academic structure.",
    "Course offering and section availability are unknown.",
    "Some prerequisite data remains unresolved or has source conflicts...",
    "..."
  ]
}
```

---

## 8. Error Mappings

| Condition | HTTP Status | Error Code | Detail |
|---|---|---|---|
| Missing or invalid Authorization header | 401 | N/A | Handled by FastAPI auth dependency |
| Student profile not found for user | 404 | `STUDENT_RESOURCE_NOT_FOUND` | Student profile was not found |
| Validation failure (e.g. `limit=0`, `limit=101`) | 422 | N/A | FastAPI request validation error |
| Student profile integrity error | 500 | `STUDENT_INTEGRITY_ERROR` | Student data integrity error |
| Catalog integrity error | 500 | `CATALOG_INTEGRITY_ERROR` | Catalog integrity error |
| Supabase transport or network timeout | 503 | `CATALOG_TRANSPORT_ERROR` | Catalog service unavailable |
| Student service configuration missing | 503 | `STUDENT_SERVICE_UNAVAILABLE` | Student service unavailable |
| Valid empty recommendation list | 200 | N/A | `{"ranked_recommendations": []}` |

---

## 9. Real Plan 12 Local Supabase Integration

All integration scenarios verified against real local Supabase with AI Plan 12:

- **Scenario A (Empty History):** User with Plan 12 and no attempts receives HTTP 200 with policy version `"1.0"`, only eligible incomplete courses ranked, zero-credit courses (`0200115`, `1509999`) ranked with `P1=1`, `REVIEW_REQUIRED` courses (`1505311`, `1505320`) separated, and no referenced-only courses in ranking.
- **Scenario B (Passed Prerequisite):** Passing `0300153` and `1501110` removes `1501110` from recommendations and makes `1501112` newly eligible and ranked.
- **Scenario C (In-Progress Exclusion):** Marking `1501112` as `IN_PROGRESS` removes it from `ranked_recommendations` and places it into `excluded_in_progress`.
- **Scenario D (Previous Failure):** A failed attempt for `0200104` keeps it eligible, sets `previously_attempted = true`, adds reason code `PREVIOUSLY_ATTEMPTED`, and imposes zero ranking penalty.
- **Scenario E (Referenced-Only History):** A passed attempt for `0300103` (referenced-only non-plan course) is accepted in student history, contributes no plan credit, and never appears in recommendations.
- **Scenario F (Review Required):** Courses with unresolved prerequisites (`1505311`) or source conflicts (`1505320`) appear in `review_required_courses`, never in `ranked_recommendations`.
- **Scenario G (Limit):** `?limit=3` returns exactly the first 3 items of the full list with identical fields and preserves the full `review_required_courses`.

---

## 10. Cross-User Isolation

- User A and User B operate with distinct tokens.
- User B with no profile receives `404 Not Found`.
- User B's profile and attempt history never leak into User A's recommendations and vice versa.
- User B does not inherit User A's `excluded_in_progress`.
- No client-controlled `owner_user_id` parameter exists.

---

## 11. Determinism

Calling the recommendation endpoint twice with identical persisted state yields byte-equivalent JSON responses. Ranks, reason codes, priority tuples, and collections are strictly sorted.

---

## 12. Performance / N+1 Audit

- Repository calls were instrumented and verified:
  - `load_student_academic_state`: 1 call
  - `load_progress_catalog`: 1 call
  - `load_plan_eligibility_catalog`: 1 call (with internal batching of dependency queries)
  - Zero database queries per recommendation candidate
  - Worst-case database read count: exactly 5 HTTP requests to Supabase per endpoint invocation.

---

## 13. OpenAPI Specification

Verified via `GET /openapi.json`:
- `GET /api/v1/me/course-recommendations` is present.
- Security requirement defined (`HTTPBearer`).
- Query parameter `limit` documented with `minimum: 1`, `maximum: 100`.
- No `owner_user_id`, `study_plan_id`, or `attempts` parameters exist.
- Response schema `RecommendationResponse` and enum `RecommendationReason` registered.

---

## 14. Security Review

1. Authenticated endpoint requiring valid Bearer JWT.
2. User identity strictly derived from `get_current_user` (`user.user_id`).
3. No client-supplied owner identity or study plan ID.
4. No client-supplied attempt history.
5. Recommendation generation is strictly read-only — zero database writes or cache rows.
6. Server secret key is never exposed in error messages or logs.
7. No raw prerequisite text parsing.
8. No GPA ranking or grade interpretation.

---

## 15. Full Regression Results

```
apps/api/tests/test_catalog_repository.py         31 passed (+4 new)
apps/api/tests/test_eligibility_api.py            26 passed
apps/api/tests/test_eligibility_service.py         3 passed
apps/api/tests/test_health.py                      2 passed
apps/api/tests/test_progress_engine.py            21 passed
apps/api/tests/test_progress_repository.py         5 passed
apps/api/tests/test_progress_service.py            1 passed
apps/api/tests/test_recommendation_api.py         23 passed (NEW)
apps/api/tests/test_recommendation_engine.py      84 passed
apps/api/tests/test_recommendation_service.py     15 passed (NEW)
apps/api/tests/test_rules_evaluator.py            43 passed
apps/api/tests/test_student_api.py                22 passed
apps/api/tests/test_student_repository.py         10 passed
apps/api/tests/test_student_repository_rules_integration.py  3 passed
apps/api/tests/test_student_repository_writes.py  14 passed

TOTAL: 301 passed, 0 failed
Opt-in local Supabase integration: 1 passed, 0 failed
```

---

## 16. Known Limitations

- Course offering and section schedule availability are unknown.
- No timetable clash detection.
- No student workload, difficulty preference, or instructor rating model.
- Recommendations support degree progress but do not constitute official university registration approval.
- Courses with unresolved prerequisites or source conflicts remain in `review_required_courses`.

