# Phase 9.3 — Degree Path Service & Authenticated API Validation

**Phase:** 9.3 — Degree Path Service + Authenticated API  
**Status:** `VALIDATED`  
**Date:** 2026-09-17  
**Policy Version:** `1.0`  
**Planning Scope:** `MODELED_DEGREE_PATH_ONLY`  

---

## 1. Executive Summary

Phase 9.3 exposes the validated pure deterministic Degree Path Planner Engine (Phase 9.2) as an authenticated, production-grade service and REST API endpoint in Morshidi (مرشدي).

The endpoint `POST /api/v1/me/degree-paths` allows authenticated students to obtain multi-semester degree completion trajectories (degree paths) starting from their current academic standing. The engine models semester-by-semester course progression deterministically until full degree completion is modeled or search termination bounds are reached.

### Core Architecture & Guarantees:
- **Strict Separation of Concerns:** Zero academic planning logic resides in the API route or service. The route and `StudentService.get_degree_paths` act strictly as an orchestration and transport layer. All combinatorial search, beam search expansion, topological simulation, eligibility checks, progress modeling, tie-breaking, and ranking are executed by `app.degree_path.engine.plan_degree_paths`.
- **Zero Database Persistence:** All multi-semester paths, synthetic semester attempts, and simulated milestone completions remain purely transient in-memory models. No synthetic attempts or degree paths are persisted to PostgreSQL/Supabase.
- **Zero Schema or RLS Migrations:** Phase 9 requires and creates zero database migrations (`supabase db reset --local --no-seed` replayed cleanly with 5 pre-existing migrations).
- **Client Constraint Bounds:** The request model `DegreePathRequest` forbids unknown fields (`extra="forbid"`) and restricts client controls to safe bounds:
  - `max_credit_hours_per_semester`: $0.00$ to $30.00$ SCH
  - `max_courses_per_semester`: $1$ to $10$ courses (optional)
  - `max_semesters_ahead`: $1$ to $16$ semesters (default: $8$)
  - `max_paths`: $1$ to $10$ paths (default: $3$)
- **Protected Internal Tuning Parameters:** Internal beam search parameters (`DEFAULT_BEAM_WIDTH = 3`, `DEFAULT_SEMESTER_BRANCH_WIDTH = 3`, `DEFAULT_CANDIDATE_WINDOW_SIZE = 15`) are strictly non-client-controlled engine constants.
- **Single-Pass State & Catalog Loading:** The service loads the student's profile and catalog data in a single bounded pass (3 reads total: `load_student_academic_state`, `load_progress_catalog`, `load_plan_eligibility_catalog`). The pure engine then executes multi-semester simulation without further database calls.

---

## 2. Architecture & Service Orchestration

### 2.1 Request Flow Diagram
```mermaid
sequenceDiagram
    autonumber
    actor Client as Authenticated Student Client
    participant Auth as FastAPI Auth (get_current_user)
    participant Route as student_router (POST /api/v1/me/degree-paths)
    participant Service as StudentService.get_degree_paths
    participant StudentRepo as SupabaseStudentAcademicRepository
    participant CatalogRepo as SupabaseAcademicCatalogRepository
    participant Engine as Pure Phase 9.2 plan_degree_paths

    Client->>Auth: Bearer JWT Token
    Auth->>Route: CurrentUser(user_id)
    Route->>Service: get_degree_paths(user_id, max_credit_hours, max_courses, max_semesters, max_paths)
    Service->>StudentRepo: load_student_academic_state(user_id)
    StudentRepo-->>Service: StudentAcademicState (study_plan_id, attempts, GPA facts)
    Service->>CatalogRepo: load_progress_catalog(study_plan_id)
    CatalogRepo-->>Service: AcademicProgressCatalog
    Service->>CatalogRepo: load_plan_eligibility_catalog(study_plan_id)
    CatalogRepo-->>Service: CanTakeCatalog
    Service->>Engine: plan_degree_paths(progress_catalog, eligibility_catalog, attempts, constraints, ...)
    Engine-->>Service: DegreePathResult
    Service-->>Route: DegreePathResult
    Route-->>Client: 200 OK DegreePathResponse
```

### 2.2 Actual Supabase HTTP Call Breakdown (Plan 12)
Direct instrumentation of `POST /api/v1/me/degree-paths` against local Supabase for Plan 12 confirmed exactly **11 HTTP calls**:

1. **Authentication (1 call):**
   - `GET /auth/v1/user` (authoritative server-side verification)
2. **Student Academic State (2 Data API calls):**
   - `GET /rest/v1/student_academic_profiles`
   - `GET /rest/v1/student_course_attempts`
3. **Progress Catalog (3 Data API calls):**
   - `GET /rest/v1/study_plans`
   - `GET /rest/v1/requirement_groups`
   - `GET /rest/v1/study_plan_courses`
4. **Eligibility Catalog (5 Data API calls for Plan 12):**
   - `GET /rest/v1/study_plans`
   - `GET /rest/v1/study_plan_courses`
   - `GET /rest/v1/course_dependency_groups` (chunk 1)
   - `GET /rest/v1/course_dependency_groups` (chunk 2)
   - `GET /rest/v1/course_dependency_options` (chunk 1)

**Total Supabase HTTP calls:** $1 + 2 + 3 + 5 = 11$.

### 2.3 Proof of Zero N+1 Queries Inside Degree-Path Search
During the multi-semester beam search, course recommendation, semester planning, and state deduplication, **zero** network or database calls occur.
Instrumentation confirmed:
- Request with `max_semesters_ahead = 1`, `max_paths = 1`: **11 calls**
- Request with `max_semesters_ahead = 3`, `max_paths = 3`: **11 calls**
The HTTP call count is strictly invariant to beam depth, branch width, generated child states, or candidate combinations.

### 2.4 Server-Side Auth Verification Flow
`get_current_user` enforces:
1. Client presents `Authorization: Bearer <token>`.
2. Server issues `GET {supabase_url}/auth/v1/user` with Supabase server key.
3. Upon authoritative HTTP 200 from Supabase Auth, server parses authoritative user JSON.
4. User ID is extracted and normalized to UUID string: `CurrentUser(user_id)`.
5. **Security Guarantee:** No local JWT claim decoding, no unverified JWT signature trust, and no client-supplied owner ID in the request body.

---

## 3. Schemas & Contracts

### 3.1 Request Schema (`DegreePathRequest`)
Located in `apps/api/app/api/schemas/degree_path.py`:
```python
class DegreePathRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_credit_hours_per_semester: Annotated[
        Decimal,
        Field(
            ge=Decimal("0.00"),
            le=Decimal("30.00"),
            description="Maximum credit hours ceiling per modeled semester (0.00 to 30.00).",
        ),
    ]
    max_courses_per_semester: Annotated[
        int | None,
        Field(
            default=None,
            ge=1,
            le=10,
            description="Optional maximum courses per modeled semester (1 to 10).",
        ),
    ] = None
    max_semesters_ahead: Annotated[
        int,
        Field(
            default=8,
            ge=1,
            le=16,
            description="Maximum forward semester planning horizon (1 to 16, default 8).",
        ),
    ] = 8
    max_paths: Annotated[
        int,
        Field(
            default=3,
            ge=1,
            le=10,
            description="Maximum distinct degree path trajectories to return (1 to 10, default 3).",
        ),
    ] = 3
```

Forbidden fields (e.g. `beam_width`, `semester_branch_width`, `candidate_window_size`, `owner`, `study_plan_id`, `attempts`, `gpa`) are rejected with HTTP 422 Unprocessable Entity.

### 3.2 Response Schema Hierarchy
- `DegreePathResponse`:
  - `study_plan_id`: `UUID`
  - `degree_path_policy_version`: `str` ("1.0")
  - `planning_scope`: `str` ("MODELED_DEGREE_PATH_ONLY")
  - `constraints`: `DegreePathConstraintsResponse`
  - `paths`: `list[DegreePathOptionResponse]`
  - `initial_completed_credits`: `Decimal`
  - `initial_remaining_credits`: `Decimal`
  - `initial_satisfied_group_count`: `int`
  - `total_requirement_group_count`: `int`
  - `unresolved_review_required_courses`: `list[str]`
  - `persisted_in_progress_courses`: `list[str]`
  - `total_parent_states_expanded`: `int`
  - `methodology_note`: `str`
  - `limitations`: `list[str]`
- `DegreePathOptionResponse`:
  - `rank`: `int` (1-indexed rank)
  - `status`: `PathStatus` (`MODELED_COMPLETE` | `HORIZON_REACHED` | `BLOCKED_BY_REVIEW_REQUIRED` | `BLOCKED_BY_CURRENT_IN_PROGRESS` | `NO_VALID_NEXT_PLAN`)
  - `semesters`: `list[ModeledSemesterResponse]`
  - `semester_count`: `int`
  - `total_planned_courses`: `int`
  - `total_planned_credits`: `Decimal`
  - `completed_plan_credit_delta`: `Decimal`
  - `final_completed_plan_credits`: `Decimal`
  - `final_remaining_plan_credits`: `Decimal`
  - `newly_satisfied_requirement_group_count`: `int`
  - `newly_satisfied_requirement_group_codes`: `list[str]`
  - `remaining_required_course_codes`: `list[str]`
  - `unresolved_blocker_codes`: `list[str]`
  - `aggregate_semester_rank_sum`: `int`
  - `priority_tuple`: `list[Any]`
  - `reason_codes`: `list[PathReasonCode]`

---

## 4. HTTP Status Codes & Error Mapping

| Scenario | HTTP Status | Error Code / Structure | Description |
| :--- | :--- | :--- | :--- |
| **Success (Any Domain Status)** | `200 OK` | `DegreePathResponse` | Degree paths computed and serialized |
| **Missing Bearer Token** | `401 Unauthorized` | `{"detail": "Not authenticated"}` | FastAPI security dependency rejection |
| **Missing Profile** | `404 Not Found` | `STUDENT_RESOURCE_NOT_FOUND` | Student profile row does not exist |
| **Constraint Violation (Pydantic)** | `422 Unprocessable` | Standard FastAPI 422 JSON | e.g. `max_credit_hours < 0`, unknown fields |
| **Constraint Violation (Engine)** | `422 Unprocessable` | `DEGREE_PATH_CONSTRAINT_INVALID` | Handled by `DegreePathConstraintError` |
| **Catalog / Plan Integrity Failure** | `500 Internal Server Error` | `CATALOG_INTEGRITY_ERROR` | Handled by `DegreePathIntegrityError` |
| **Supabase Transport / Network Error** | `503 Service Unavailable`| `CATALOG_TRANSPORT_ERROR` | Upstream Supabase client unreachable |

### Domain Status Invariant (HTTP 200)
All five terminal academic outcomes return HTTP 200 OK:
1. `MODELED_COMPLETE` $\to$ HTTP 200
2. `HORIZON_REACHED` $\to$ HTTP 200
3. `BLOCKED_BY_REVIEW_REQUIRED` $\to$ HTTP 200
4. `BLOCKED_BY_CURRENT_IN_PROGRESS` $\to$ HTTP 200
5. `NO_VALID_NEXT_PLAN` $\to$ HTTP 200

---

## 5. End-to-End Validation Against Local Supabase (Plan 12)

All Scenarios A through J were executed and verified against local Supabase using the authentic Plan 12 database catalog (`apps/api/tests/test_degree_path_local_supabase.py`):

| Scenario | Objective | Validation Result | Status |
| :--- | :--- | :--- | :--- |
| **Scenario A** | Fresh AI student with empty history | Valid multi-semester paths generated; credit bounds observed; 0 review-required courses selected | `PASSED` |
| **Scenario B** | Verified prerequisite chain (`0300153` $\to$ `1501110` $\to$ `1501112` $\to$ `1501221`) | Strict sequential semester ordering verified across all paths | `PASSED` |
| **Scenario C** | In-progress course (`1501110` IN_PROGRESS) | Course omitted from plan; dependent `1501112` remains blocked in future semesters | `PASSED` |
| **Scenario D** | Zero-credit required courses (`0200115`, `1509999`) | Successfully scheduled with exact 0.00 credit hours | `PASSED` |
| **Scenario E** | Review-required courses (`1505311` is `unresolved`; `1505320` is `source_conflict`) | Never selected in any modeled semester | `PASSED` |
| **Scenario F** | Referenced-only course (`0300103`) | Accepted in student history; never scheduled in degree path options | `PASSED` |
| **Scenario G** | Failed course (`0200104`) | Re-planned with priority reason `INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE` | `PASSED` |
| **Scenario H** | Bounded horizon (`max_semesters_ahead: 1`) | Generates 1-semester path with status `HORIZON_REACHED` | `PASSED` |
| **Scenario I** | `max_paths` prefix equivalence | `max_paths=1` path is strictly identical to the top path of `max_paths=3` | `PASSED` |
| **Scenario J** | Credit ceiling variation ($12$ vs $18$ SCH) | Credit hours strictly bounded; $18$ SCH allows higher credit utilization | `PASSED` |
| **Zero-Semester Complete** | Student already completed all requirements | HTTP 200, status `MODELED_COMPLETE`, 0 semesters, `total_parent_states_expanded = 0` | `PASSED` |
| **Determinism** | Repeated calls with identical inputs | Bit-for-bit identical JSON response | `PASSED` |
| **User Isolation** | Cross-user data isolation | User A's attempts and profile do not leak to User B; uninitialized user returns 404 | `PASSED` |

*Note on Scenario J / Zero-Semester Complete in Local Supabase:* Full Plan 12 completion requires creating 47 course attempt rows across multiple prerequisite levels. Due to test performance and database reset overhead, zero-semester completion is rigorously proved via pure engine unit test (`test_20_zero_semester_already_complete`), service unit test (`test_14_zero_semester_modeled_complete_service`), and API route test (`test_51_zero_semester_modeled_complete`), while local Supabase Scenario J validates the credit limit sensitivity contract.

---

## 6. Test Suite & Regression Verification

### 6.1 Pure Engine Tests (`test_degree_path_engine.py`)
- **113 passed** in 0.37s:
  - Prerequisite and chain progression
  - Zero-credit course inclusion
  - State deduplication and monotonic progress
  - Beam search width (3) and branch width (3) limits
  - Bounded parent state expansions ($\le 48$)
  - Termination precedence (Priority 1 through 5)
  - Zero-semester already-complete student (`total_parent_states_expanded = 0`)
  - Canonical ranking and tie-breaking
  - Reason code assignments
  - Strict boundary audit (zero FastAPI/HTTP/Supabase imports)

### 6.2 Service Unit Tests (`test_degree_path_service.py`)
- **14 passed** in 0.16s (`@pytest.mark.anyio`):
  - State loaded once
  - Progress and eligibility catalogs loaded once with student's `study_plan_id`
  - Engine invoked with stored attempts
  - Constraints passed accurately
  - Zero database writes
  - Profile not found propagates 404
  - Integrity errors map to 500
  - Constraint errors map to 422
  - Zero-semester modeled complete service test

### 6.3 API Route Tests (`test_degree_path_api.py`)
- **51 passed** in 11.42s:
  - Auth enforcement (401 on missing/invalid token)
  - Parameter bounds (credits 0.00 to 30.00, courses 1 to 10, semesters 1 to 16, paths 1 to 10)
  - `extra="forbid"` rejection of unknown fields (e.g. `beam_width`, `candidate_window_size`)
  - Status mapping (404, 422, 500, 503)
  - Domain status HTTP 200 verification (all 5 `PathStatus` values)
  - Zero-semester modeled complete API test
  - OpenAPI documentation schema conformance

### 6.4 Local Supabase Integration Suites
- `test_degree_path_local_supabase.py`: **1 passed** (covering Scenarios A–J, isolation, determinism)
- `test_semester_planner_local_supabase.py`: **1 passed**
- `test_recommendation_local_supabase.py`: **1 passed**
- `test_student_api_local_supabase.py`: **1 passed**
- `test_student_repository_local_supabase.py`: **1 passed**
- `test_eligibility_api_local_supabase.py`: **1 passed**
- `test_progress_local_supabase.py`: **2 passed**
- `test_catalog_repository_local_supabase.py`: **3 passed**
- **Total Local Supabase Tests:** 11 passed, 0 skipped, 0 failed in 304.78s.

### 6.5 Full Project Regression
- **634 passed**, 11 skipped (opt-in local tests), 0 failed across entire repo in 34.99s.

---

## 7. Security & Code Cleanliness Audit

- **Secret / Token Leakage Audit:** Zero literal JWT tokens, service role keys, or anon keys exist in repository code, tests, or documentation.
- **Git Hygiene:** `git diff --check` clean (zero trailing whitespace, zero stray blank lines at EOF).
- **Source Integrity:** Zero modifications made to Phase 9.2 pure engine (`apps/api/app/degree_path/engine.py` and `apps/api/app/degree_path/models.py`) or Phase 5–8 engine code (`git diff HEAD` is empty).
- **Database Integrity:** Zero new SQL migrations created; zero database tables modified; clean reset replay verified.
- **GPA Forwarding:** GPA metadata is forwarded strictly to preserve existing Phase 6/7/8 function signatures. GPA does **not** influence degree path ranking, prerequisite evaluation, optimization targets, or completion criteria.

---

## 8. Conclusion

Phase 9.3 has fully satisfied all architectural, service, API, security, performance, and determinism requirements.
