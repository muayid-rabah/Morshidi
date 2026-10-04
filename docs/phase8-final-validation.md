# Phase 8 — Comprehensive Semester Planner Final Validation

**Phase:** 8.4 — Final Semester Planner Audit & Acceptance  
**Status:** `VALIDATED`  
**Date:** 2026-09-17  
**Policy Version:** `1.0`  
**Planning Scope:** `ACADEMIC_STRUCTURE_ONLY`  

---

## 1. Executive Summary & Architecture

Phase 8 integrates and audits the deterministic **Semester Planner Engine** and its authenticated API for Morshidi (مرشدي).

### Core Pipeline:
```
Authenticated User
    ↓
Student Academic State (profile facts + persisted attempts)
    ↓
Progress Catalog (StudyPlan + RequirementGroups + PlanCourses)
    ↓
Eligibility Catalog (Rules + CourseIdentities)
    ↓
Phase 7 Recommendation Engine (Full candidate set without presentation limit)
    ↓
Phase 8 Pure Semester Planner (Top-M candidate window + Whole-plan simulation + Lexicographic ranking)
    ↓
StudentService (Orchestration boundary)
    ↓
POST /api/v1/me/semester-plans (FastAPI transport)
```

The system answers:
> *"Which combinations of eligible courses should the student consider registering together in their next registration period to maximize degree progress?"*

---

## 2. Components Audited

1. **Policy Specification (`docs/semester-planner-policy-spec.md`):** Complete academic consistency with Phase 5, Phase 6, and Phase 7.
2. **Pure Planner Models (`apps/api/app/planner/models.py`):**
   - Immutable frozen dataclasses.
   - `PlannerConstraints`: contains strictly `max_credit_hours`, `max_courses`, and `max_options`.
   - `candidate_window_size` is computation configuration on `plan_semester`, not in `PlannerConstraints`.
   - Strict `Decimal` credit arithmetic; float rejection.
3. **Pure Planner Engine (`apps/api/app/planner/engine.py`):**
   - Candidate window bounding to top $M=15$ Phase 7 recommendations.
   - Depth-First Branch-and-Bound combinatorial search.
   - Exact whole-plan degree progress simulation via Phase 6 (`calculate_academic_progress`).
   - Exact joint prerequisite unlock simulation via Phase 5 (`evaluate_can_take`).
   - 7-component lexicographic priority tuple ranking.
   - Deterministic reason code derivation with mutual exclusivity.
   - Zero I/O, zero timestamps, zero random generation.
4. **Service Orchestration (`apps/api/app/services/student.py`):**
   - `StudentService.get_semester_plans` loads state once, progress catalog once, eligibility catalog once.
   - Slices zero candidates before passing full recommendation universe to the planner engine.
   - Zero ranking or combination math in service.
5. **API & Schemas (`apps/api/app/api/schemas/semester_planner.py`, `apps/api/app/api/routes/student.py`):**
   - `POST /api/v1/me/semester-plans` authenticated via `get_current_user`.
   - Strict `extra="forbid"` preventing injection of `candidate_window_size`, `owner_user_id`, or `study_plan_id`.
   - Exact Decimal serialization contracts.
6. **Data API & Persistence Safety:**
   - 10 total HTTP reads for Zarqa University Plan 12 upfront.
   - Zero HTTP reads inside combination or unlock simulation loops.
   - Zero database writes or cache rows.

---

## 3. Policy & Constraint Invariants

- `SEMESTER_PLANNER_POLICY_VERSION = "1.0"`
- `PLANNING_SCOPE = "ACADEMIC_STRUCTURE_ONLY"`
- **Planning Horizon:** Strictly the single upcoming registration period (Next Registration Set). Existing `IN_PROGRESS` courses earn 0 credits, do not satisfy prerequisites, cannot be registered again, and do not consume the planned semester budget.
- **Candidate Universe:** Sourced exclusively from Phase 7 `RecommendationResult.ranked_recommendations`.
- **Candidate Window ($M=15$):** Bounded search within top 15 candidates ($2^{15} - 1 = 32,767$ theoretical combinations prior to branch-and-bound pruning).
- **Search Limitation:** Explicitly documented that results are exact within the candidate window but not guaranteed globally optimal across unexamined eligible courses outside this window.
- **Credit Safety Ceiling (30.00):** A numerical safety guardrail, not an authorized university registration limit.
- **Decimal Safety:** All credit math uses exact Python `Decimal`.

---

## 4. Academic Simulation & Ranking Invariants

- **Same-Semester Prerequisite Prevention:** Every course selected in a plan must be baseline `ELIGIBLE` in Phase 5. If Course B requires Course A, they can never appear in the same plan.
- **Whole-Plan Joint AND Unlocks:** Unlocks are evaluated by simulating hypothetical completion of all selected courses simultaneously. Joint dependencies (e.g. Course T requiring both A and B) are correctly captured. Individual Phase 7 unlock counts are never summed.
- **Unlock Exclusions:** `newly_eligible_course_codes` excludes baseline eligible courses, completed courses, in-progress courses, selected plan courses, and external referenced-only courses.
- **Degree Progress Delta ($P_3$):** Reuses Phase 6 `calculate_academic_progress`. Respects elective credit caps.
- **7-Component Lexicographic Priority Tuple:**
  $$\text{Priority Tuple} = (P_1, P_2, P_3, P_4, P_5, P_6, P_7)$$
  - $P_1$ `mandatory_course_count` (DESC)
  - $P_2$ `newly_satisfied_requirement_group_count` (DESC)
  - $P_3$ `completed_plan_credit_delta` (DESC)
  - $P_4$ `newly_eligible_count` (DESC)
  - $P_5$ `total_credit_hours` (DESC)
  - $P_6$ `recommendation_rank_sum` (ASC)
  - $P_7$ `canonical_course_codes` (ASC alphabetical tiebreaker)
- **`MAXIMIZES_MODELED_CREDIT_PROGRESS`:** Assigned to any plan achieving the global maximum credit delta among all valid combinations evaluated in the candidate window, including when the maximum is 0. Multiple tied plans receive it.
- **Reason Code Exclusivity:**
  - Prerequisite impact: exactly one of `NO_DIRECT_PREREQUISITE_IMPACT` ($P_4=0$), `UNLOCKS_FUTURE_COURSE` ($P_4=1$), or `UNLOCKS_MULTIPLE_FUTURE_COURSES` ($P_4 \ge 2$).
  - Group completion: `COMPLETES_REQUIREMENT_GROUP` ($P_2=1$) and `COMPLETES_MULTIPLE_REQUIREMENT_GROUPS` ($P_2 \ge 2$) are mutually exclusive.

---

## 5. Real Plan 12 Catalog Facts

- **Total Plan Credits:** 132 credit hours across 6 requirement groups and 68 `study_plan_courses`.
- **Elective Saturation:** University Electives (9 required / 33 listed) and Major Electives (9 required / 39 listed).
- **Zero-Credit Required Courses:** `0200115` (`تنمية المجتمع والعمل التطوعي` / Community Development and Volunteer Work, `UNIVERSITY_REQUIRED`) and `1509999` (`حلقة بحث لطلبة كلية تكنولوجيا المعلومات` / Research Seminar for IT College Students, `FACULTY_REQUIRED`) consume 0 credits, contribute to $P_1$, count toward `max_courses`, and form valid plans when `max_credit_hours = Decimal("0")`.
- **Review-Required Courses:** `1505311` (`تعلم الالة` / Machine Learning, `unresolved`) and `1505320` (`تعلم الآلة المتقدم` / Advanced Machine Learning, `source_conflict`) remain in `review_required_courses` and never enter plans.
- **Referenced-Only Courses:** `0300103` (`الإحصاء والاحتمالات`, `referenced_only`) is external to the study plan, earns 0 plan credits, and affects eligibility only if verified as a prerequisite.
- **Verified Prerequisite Chain:** `0300153 -> 1501110 -> 1501112`.

---

## 6. Security & Infrastructure Audit

- **Authentication:** Bearer token is verified directly via server-side HTTP `GET /auth/v1/user`. Zero trust in local unverified JWT decoding.
- **Credential Hygiene:** Zero literal JWT tokens, secret keys, or service role credentials exist in tracked or untracked project files. All local tests load credentials exclusively via environment variables.
- **No Remote Access:** Only the local Supabase stack (`http://127.0.0.1:54321`) is accessed.
- **Read-Only Invariant:** Zero database writes. Transient attempt simulation occurs in-memory.
- **Data API Requests (Plan 12):**
  - Profile & attempts: 2 requests
  - Progress catalog: 3 requests
  - Eligibility catalog: 5 requests (chunked batching)
  - Total: **10 HTTP requests** upfront; zero in candidate or combination loops.
- **Clean Database Replay:** `supabase db reset --local --no-seed` replayed all 5 project migrations cleanly with 0 errors.

---

## 7. Verification Test Matrix

| Test Suite | Scope | Executed | Passed | Skipped |
|---|---|:---:|:---:|:---:|
| `test_semester_planner_engine.py` | Pure branch-and-bound, simulation, priority tuple, reason codes | 97 | 97 | 0 |
| `test_semester_planner_service.py` | StudentService orchestration, full candidate universe, error mapping | 11 | 11 | 0 |
| `test_semester_planner_api.py` | Authenticated FastAPI endpoint, constraints, Decimal serialization | 35 | 35 | 0 |
| `test_semester_planner_local_supabase.py` | Real local Supabase E2E (Scenarios A–I, User A/B isolation) | 1 | 1 | 0 |
| **All Local Supabase Suites** | Full local integration across catalog, progress, recommendations, planner, student | 10 | 10 | 0 |
| **Full Repository Test Suite** | Full pytest regression across Phase 1 through Phase 8 | 466 | 456 | 10* |

*\* The 10 skipped tests are opt-in local Supabase tests when run without local credentials.*

---

## 8. Final Acceptance Invariants

- [x] Pure planner engine boundary strictly maintained (`app/planner/` has zero framework/DB imports).
- [x] `candidate_window_size = 15` is engine configuration and forbidden in API requests.
- [x] Full Phase 7 candidate universe passed to planner engine without presentation truncation.
- [x] Zero-credit courses count toward course limits and contribute at $P_1$.
- [x] Prerequisite logic delegated entirely to Phase 5 `evaluate_can_take`.
- [x] Academic progress delta delegated entirely to Phase 6 `calculate_academic_progress`.
- [x] `MAXIMIZES_MODELED_CREDIT_PROGRESS` awarded to all plans achieving maximal delta, including 0.
- [x] Reason code mutual exclusivity preserved.
- [x] `POST /api/v1/me/semester-plans` verified in OpenAPI with `additionalProperties: false`.
- [x] Server-side token validation via `/auth/v1/user` verified.
- [x] Exactly 10 Data API HTTP requests for Plan 12 upfront; zero inside planner loops.
- [x] Real Plan 12 scenarios A through I pass against local Supabase.
- [x] Clean database migration replay verified.
- [x] Zero literal credentials in project files.
- [x] Zero database persistence or RLS drift.

