# Phase 7 — Recommendation System: Final Acceptance & Audit Validation

**Status:** `VALIDATED`
**Date:** 2026-09-17
**Policy version:** `1.0`

---

## 1. Scope

Phase 7 defines and validates the deterministic **SHOULD TAKE** degree-recommendation subsystem for Morshidi (مرشدي). It builds strictly on top of:
- Phase 5: Deterministic Prerequisite & Academic Rules Engine ([`evaluate_can_take`](file:///d:/imporant/Morshidi/apps/api/app/rules/evaluator.py))
- Phase 6: Degree Progress Engine ([`calculate_academic_progress`](file:///d:/imporant/Morshidi/apps/api/app/progress/engine.py)) and Student Academic State

Phase 7 consists of:
- **Phase 7.1:** Recommendation Policy & Scoring Specification ([`docs/recommendation-policy-spec.md`](file:///d:/imporant/Morshidi/docs/recommendation-policy-spec.md))
- **Phase 7.2:** Pure Deterministic Recommendation Engine ([`apps/api/app/recommendations/`](file:///d:/imporant/Morshidi/apps/api/app/recommendations/))
- **Phase 7.3:** Repository Integration, StudentService Orchestration & API ([`docs/phase7-recommendation-api-validation.md`](file:///d:/imporant/Morshidi/docs/phase7-recommendation-api-validation.md))
- **Phase 7.4:** Final Acceptance, Security, Replay, and Invariant Audit (this document)

---

## 2. Components Audited

| Component | Path | Responsibility |
|---|---|---|
| Pure Domain Models | `apps/api/app/recommendations/models.py` | Policy version, 10 reason codes, `RecommendationCandidate`, `ReviewRequiredCourse`, `RecommendationResult` |
| Pure Recommendation Engine | `apps/api/app/recommendations/engine.py` | Full ranking, hypothetical progress/eligibility simulations, zero I/O |
| Catalog Repository Adapter | `apps/api/app/catalog/supabase_repository.py` | `load_plan_eligibility_catalog`, batch chunking (size 50), explicit column selections |
| Catalog Repository Protocol | `apps/api/app/catalog/repository.py` | Read contract definition |
| StudentService Orchestration | `apps/api/app/services/student.py` | `get_course_recommendations`, single-pass state and catalog loading, presentation slicing |
| API Schemas | `apps/api/app/api/schemas/recommendations.py` | `RecommendationResponse`, `RecommendationCandidateResponse`, `ReviewRequiredCourseResponse` |
| API Routes | `apps/api/app/api/routes/student.py` | `GET /api/v1/me/course-recommendations` with HTTPBearer auth and bounded `limit` query param |
| Test Suites | `apps/api/tests/` | 84 engine tests, 15 service tests, 23 API tests, 7 audit invariant tests, 9 local Supabase integration tests |

---

## 3. Policy / Specification Consistency

The implemented engine strictly matches the accepted Phase 7.1 specification:
- **Phase 5 Gate:** Only courses where Phase 5 returns `Decision.ELIGIBLE` can enter `ranked_recommendations`.
- **Course States:**
  - `COMPLETED`: Excluded silently.
  - `IN_PROGRESS`: Excluded from ranking and recorded in `excluded_in_progress` sorted ascending.
  - `ATTEMPTED_NOT_COMPLETED`: Ranked normally without penalty if eligible, with `previously_attempted = True` and reason code `PREVIOUSLY_ATTEMPTED`.
  - `NOT_ATTEMPTED`: Ranked normally.
- **Decision Outcomes:**
  - `NOT_ELIGIBLE`: Excluded silently.
  - `REVIEW_REQUIRED`: Placed exclusively in `review_required_courses`, carrying the Phase 5 review reason.
- **Referenced-Only Courses:** Courses external to the study plan (e.g. `0300103`) recorded in attempt history contribute no plan credits and are never recommendation candidates.
- **Elective Saturation:** When an elective group reaches `remaining_required_credits == 0`, all remaining uncompleted options in that group are excluded from `ranked_recommendations`.
- **Zero-Credit Required Courses:** Handled as mandatory degree milestones (`P1 = 1`), outranking elective courses while contributing 0 credits.
- **Zero Academic AI / ML:** No machine learning, course difficulty rankings, professor ratings, or GPA-based suitability scoring exist.

---

## 4. Candidate Filtering & Classification Invariant

Every course in the study plan is partitioned into **exactly one** mutually disjoint classification:
1. `ranked_recommendations`: Eligible, incomplete, degree-useful candidates.
2. `review_required_courses`: Incomplete plan courses with `Decision.REVIEW_REQUIRED`.
3. `excluded_in_progress`: Incomplete plan courses with state `IN_PROGRESS`.
4. `completed`: Plan courses with state `COMPLETED` in Phase 6.
5. `not_eligible`: Plan courses with `Decision.NOT_ELIGIBLE`.
6. `satisfied_elective`: Eligible elective courses whose group requirement is already met.

Tested and verified by [`test_audit_candidate_partition_invariant_every_plan_course_accounted_for`](file:///d:/imporant/Morshidi/apps/api/tests/test_recommendation_audit.py).

---

## 5. Priority Tuple

Exact 7-element lexicographic priority tuple:

$$\text{Priority Tuple} = (P_1, P_2, P_3, P_4, P_5, P_6, P_7)$$

| Position | Dimension | Definition | Direction |
|---|---|---|---|
| $P_1$ | `required_mandatory_priority` | $2$ (positive-credit required), $1$ (zero-credit required), $0$ (elective) | Higher first |
| $P_2$ | `group_has_remaining_need` | $1$ (group remaining need $> 0$), $0$ (group satisfied) | Higher first |
| $P_3$ | `effective_credit_contribution` | Credits contributed to unsatisfied group need (Decimal) | Higher first |
| $P_4$ | `completes_requirement_group` | $1$ (transition from unsatisfied to satisfied), $0$ (otherwise) | Higher first |
| $P_5$ | `newly_eligible_count` | Count of downstream plan courses unlocked (int) | Higher first |
| $P_6$ | `-display_order` | Stored as `-display_order` | Lower display order first |
| $P_7$ | `course_code` | Catalog alphanumeric course code string | Ascending (alphabetical) |

---

## 6. Sort Direction & Tiebreak Audit

In Python sort keys:
$$\text{sort\_key}(c) = (-P_1, -P_2, -P_3, -P_4, -P_5, -P_6, P_7)$$
- Because $P_6 = -\text{display\_order}$, negating it yields $-P_6 = +\text{display\_order}$.
- Standard ascending sort places smaller positive display orders first, preserving canonical study-plan display sequence when $P_1 \dots P_5$ are tied.
- $P_7$ (`course_code`) is sorted ascending as the final deterministic tie-break.
- Verified by [`test_audit_display_order_tiebreak_direction`](file:///d:/imporant/Morshidi/apps/api/tests/test_recommendation_audit.py).

---

## 7. Required vs Elective Behavior

- Positive-credit required courses receive $P_1 = 2$.
- Zero-credit required courses receive $P_1 = 1$.
- Elective courses receive $P_1 = 0$.
- Any unsatisfied required course strictly outranks any elective course at $P_1$ regardless of credit hours or unlocks.

---

## 8. Zero-Credit Required Course Behavior

- Real Plan 12 courses: `0200115` (Community Service) and `1509999` (Practical Training).
- Credit hours: `0.00`.
- Effective credit contribution: `0.00` (derived directly from Phase 6 progress delta).
- $P_1 = 1$, ensuring they rank above all electives ($P_1 = 0$).
- Assigned reason codes: `REQUIRED_PLAN_COURSE` and `MANDATORY_ZERO_CREDIT_COURSE`.
- Verified in unit tests and against real local Supabase catalog data.

---

## 9. Hypothetical Progress Simulation

- Pure delegation to [`calculate_academic_progress`](file:///d:/imporant/Morshidi/apps/api/app/progress/engine.py).
- For each eligible candidate $c$, a synthetic attempt is appended immutably:
  $$\text{attempts}_{\text{hyp}} = \text{attempts} + (\text{StudentCourseAttempt}(c.\text{code}, \text{PASSED}),)$$
- Original student attempts tuple is **never mutated**.
- $\Delta\text{credit} = \text{hyp}.\text{credited\_toward\_requirement} - \text{cur}.\text{credited\_toward\_requirement}$.
- $\text{completes\_group} = (\neg \text{cur}.\text{is\_satisfied}) \land \text{hyp}.\text{is\_satisfied}$.
- Zero duplicate progress math in the recommendation module.

---

## 10. Hypothetical Eligibility Simulation

- Pure delegation to [`evaluate_can_take`](file:///d:/imporant/Morshidi/apps/api/app/rules/evaluator.py).
- Baseline eligibility is evaluated for all incomplete plan courses.
- In the simulation, each non-eligible, non-candidate course is re-evaluated with $\text{attempts}_{\text{hyp}}$.
- Any transition from non-eligible to `Decision.ELIGIBLE` is recorded.
- Unresolved (`1505311`) and source conflict (`1505320`) courses stay `REVIEW_REQUIRED` and are never erroneously unlocked.
- Zero raw prerequisite text parsing or custom rule evaluation.

---

## 11. Newly Eligible Semantics

- Count includes only courses where $\text{decision}_{\text{base}} \neq \text{ELIGIBLE}$ and $\text{decision}_{\text{hyp}} = \text{ELIGIBLE}$.
- Specifically excludes:
  - The candidate course itself.
  - Already completed courses.
  - Currently in-progress courses.
  - Already eligible courses.
  - External referenced-only courses.
- `newly_eligible_course_codes` is deterministically sorted ascending.
- `newly_eligible_count == len(newly_eligible_course_codes)`.

---

## 12. Review-Required Separation

- Plan 12 courses with unresolved prerequisites (`1505311`, `0200105`, `0200106`, `1505461`) or source conflicts (`1505320`, `1505366`) are placed into `review_required_courses`.
- They are excluded from `ranked_recommendations`, receive no priority tuple, and do not distort sequential rank numbering.

---

## 13. Previous Attempt Context

- `FAILED` or `WITHDRAWN` attempts in student history do not penalize course ranking.
- If a course is eligible, it is ranked on equal structural footing.
- Contextual flag: `previously_attempted = True`.
- Contextual reason: `PREVIOUSLY_ATTEMPTED`.
- If a course was `FAILED` then `PASSED`, Phase 6 recognizes it as `COMPLETED` and it is excluded.

---

## 14. Reason Code Audit (10-Code Vocabulary)

Verified stable vocabulary:
1. `REQUIRED_PLAN_COURSE`
2. `MANDATORY_ZERO_CREDIT_COURSE`
3. `ADVANCES_REQUIRED_GROUP`
4. `ADVANCES_ELECTIVE_REQUIREMENT`
5. `COMPLETES_REQUIREMENT_GROUP`
6. `UNLOCKS_FUTURE_COURSE`
7. `UNLOCKS_MULTIPLE_FUTURE_COURSES`
8. `NO_REMAINING_GROUP_NEED`
9. `PREVIOUSLY_ATTEMPTED`
10. `NO_DIRECT_PREREQUISITE_IMPACT`

**Mutual Exclusivity:**
Exactly one unlock reason code is emitted per candidate:
- `NO_DIRECT_PREREQUISITE_IMPACT` if $\text{newly\_eligible\_count} = 0$.
- `UNLOCKS_FUTURE_COURSE` if $\text{newly\_eligible\_count} = 1$.
- `UNLOCKS_MULTIPLE_FUTURE_COURSES` if $\text{newly\_eligible\_count} \ge 2$.
Verified by [`test_audit_unlock_reason_codes_mutually_exclusive`](file:///d:/imporant/Morshidi/apps/api/tests/test_recommendation_audit.py).

---

## 15. Service and Repository Boundaries

- `StudentService.get_course_recommendations`:
  - Fetches student academic state once.
  - Fetches progress catalog once.
  - Fetches plan eligibility catalog once.
  - Delegates execution to pure `recommend_courses(...)`.
  - Performs presentation-only slicing when `limit` is provided.
  - Performs zero ranking calculations or priority tuple construction.
- `SupabaseAcademicCatalogRepository`:
  - Strictly reads database rows and maps them to pure catalog models.
  - Contains no ranking logic, recommendation scoring, or simulation.

---

## 16. N+1 Audit & PostgREST Request Count

- Verified fixed bounded request count per endpoint call:
  - 1 request to `profiles` / `student_course_attempts`
  - 3 requests for progress catalog (`study_plans`, `requirement_groups`, `study_plan_courses`)
  - 4 requests for plan eligibility catalog (`study_plans`, `study_plan_courses`, `course_dependency_groups`, `course_dependency_options`)
  - Total: **8 HTTP requests to Supabase**, independent of candidate count.
- Simulation & ranking: **0 queries**.

---

## 17. Limit Audit

- `GET /api/v1/me/course-recommendations?limit=N`
- Enforces strict validation: $1 \le N \le 100$.
- $N = 0$, $N = -1$, $N > 100$, and non-integers return HTTP `422 Unprocessable Entity`.
- Slices `ranked_recommendations` presentation after full ranking is complete.
- `review_required_courses`, `excluded_in_progress`, notes, and candidate metadata are identical to the unconstrained response.

---

## 18. Real Plan 12 Integration Scenarios

Executed and validated against local Supabase:
- **Scenario A (Empty History):** Valid HTTP 200, only eligible plan courses ranked, zero-credit courses (`0200115`, `1509999`) ranked with $P_1 = 1$, `1505311` and `1505320` placed in `review_required_courses`.
- **Scenario B (Prerequisite Chain):** Passing `0300153` and `1501110` removes `1501110` and exposes `1501112` as eligible and ranked.
- **Scenario C (In-Progress Exclusion):** Marking `1501112` as `IN_PROGRESS` excludes it from recommendations and places it in `excluded_in_progress`.
- **Scenario D (Previous Failure):** Failing `0200104` keeps it eligible, sets `previously_attempted = True`, adds reason `PREVIOUSLY_ATTEMPTED`, and imposes no ranking penalty.
- **Scenario E (Referenced-Only History):** Passing `0300103` (external calculus course) records attempt without adding degree progress or generating recommendation candidates.
- **Scenario F (Review Required):** Non-executable targets remain separated.
- **Scenario G (Limit):** `?limit=3` returns exactly the first 3 items of the full ranking.

---

## 19. Cross-User Isolation

- User A and User B operate with distinct JWT tokens.
- User B with no profile receives `404 Not Found`.
- User B cannot see User A’s recommendations or in-progress courses.
- No client-controlled owner or profile parameter exists.

---

## 20. Determinism

- Byte-identical JSON responses returned on sequential calls with identical persisted data.
- Ranks, newly-eligible codes, excluded in-progress codes, and review-required lists are strictly sorted.
- Zero randomized, clock-dependent, or set-iteration instability.

---

## 21. API Contract & OpenAPI

- Path: `GET /api/v1/me/course-recommendations`
- Authentication: Bearer token (`HTTPBearer`).
- Query: optional `limit` (`minimum: 1`, `maximum: 100`).
- Registered schemas: `RecommendationResponse`, `RecommendationCandidateResponse`, `ReviewRequiredCourseResponse`, and `RecommendationReason`.

---

## 22. Security Audit

- Clean scan across all tracked source files:
  - Zero hardcoded API keys, secrets, or real JWT tokens.
  - Authorization headers and tokens are never printed or logged.
  - Server-side secret key is never returned in client errors.
  - Zero database writes during recommendation generation.
  - Local Supabase endpoint only (`http://127.0.0.1:54321`). Zero remote calls.

---

## 23. Clean Database Replay

- Replay executed: `supabase db reset --local --no-seed` (exit code 0).
- All migrations applied cleanly:
  - `0001_academic_catalog.sql`
  - `20260916224842_seed_ai_plan12_foundation.sql`
  - `20260916230222_seed_ai_plan12_courses.sql`
  - `20260916231030_model_ai_plan12_prerequisites.sql`
  - `20260917085254_create_student_academic_profile.sql`
- Zero schema or RLS drift. All 9 local Supabase integration tests passed against freshly replayed catalog.

---

## 24. Full Test Results

### Normal pytest Suite (Mocked & Pure Unit Tests)
```
apps/api/tests/test_catalog_repository.py         31 passed
apps/api/tests/test_eligibility_api.py            26 passed
apps/api/tests/test_eligibility_service.py         3 passed
apps/api/tests/test_health.py                      2 passed
apps/api/tests/test_progress_engine.py            21 passed
apps/api/tests/test_progress_repository.py         5 passed
apps/api/tests/test_progress_service.py            1 passed
apps/api/tests/test_recommendation_api.py         23 passed
apps/api/tests/test_recommendation_audit.py        7 passed (NEW)
apps/api/tests/test_recommendation_engine.py      84 passed
apps/api/tests/test_recommendation_service.py     15 passed
apps/api/tests/test_rules_evaluator.py            43 passed
apps/api/tests/test_student_api.py                22 passed
apps/api/tests/test_student_repository.py         10 passed
apps/api/tests/test_student_repository_rules_integration.py  3 passed
apps/api/tests/test_student_repository_writes.py  14 passed

TOTAL: 308 passed, 0 failed in 14.59s
```

### Opt-in Local Supabase Integration Suite
```
apps/api/tests/test_catalog_repository_local_supabase.py    3 passed
apps/api/tests/test_eligibility_api_local_supabase.py       1 passed
apps/api/tests/test_progress_local_supabase.py              2 passed
apps/api/tests/test_student_api_local_supabase.py           1 passed
apps/api/tests/test_student_repository_local_supabase.py    1 passed
apps/api/tests/test_recommendation_local_supabase.py        1 passed

TOTAL: 9 passed, 0 failed in 8.79s
```

---

## 25. Bugs Discovered & Resolved During Phase 7 Audit

1. **OpenAPI limit schema nullable anyOf inspection:**
   - *Discovery:* When validating OpenAPI schema for `limit: int | None`, Pydantic v2 / FastAPI wrapped schema in an `anyOf: [{'type': 'integer', ...}, {'type': 'null'}]`.
   - *Resolution:* Audit assertion updated to inspect the integer schema within `anyOf`.
2. **Real Plan 12 prerequisite dependency in local integration:**
   - *Discovery:* User B test assertion assumed `1501110` was eligible with no prerequisites, but real Plan 12 requires `0300153`.
   - *Resolution:* Verified canonical prerequisite catalog: `0300153` is eligible for User B with 0 attempts, and `1501110` becomes eligible once `0300153` is passed.

---

## 26. Known Limitations (Retained)

- Course offering, section schedule, and classroom capacity are unknown.
- Timetable clash detection is out of scope.
- No course workload, difficulty rating, or instructor rating model.
- Recommendations represent academic decision support based on modeled study-plan structure, not official university graduation clearance.
- Courses with unresolved prerequisites or source conflicts remain in `review_required_courses`.

---

## 27. Acceptance Checklist

- [x] Phase 7.1 policy matches implementation exactly
- [x] Policy version is `"1.0"` across all models
- [x] Candidate partitioning is exhaustive and disjoint
- [x] Priority tuple is exact 7-tuple
- [x] Sort direction preserves lower display order via $-P_6$
- [x] Zero-credit required courses rank with $P_1 = 1$
- [x] Elective saturation correctly excludes satisfied groups
- [x] Progress simulation immutably reuses Phase 6 engine
- [x] Eligibility simulation immutably reuses Phase 5 engine
- [x] Unlock count and newly eligible codes are strictly sorted
- [x] Review-required courses are strictly separated
- [x] Previous failures/withdrawals carry no ranking penalty
- [x] 10 reason codes match specification vocabulary
- [x] Service orchestration is clean with single-pass loading
- [x] Repository only loads facts (no ranking logic)
- [x] N+1 query audit confirms bounded request count (8 HTTP requests)
- [x] Limit parameter is presentation-only ($1 \le N \le 100$)
- [x] Empty states return HTTP 200
- [x] Real Plan 12 scenarios validated against local database
- [x] Cross-user isolation verified (User B cannot see User A)
- [x] Deterministic byte-equivalent outputs
- [x] OpenAPI schema matches specification
- [x] Zero hardcoded secrets, JWTs, or remote endpoints
- [x] Database replay verified from scratch with zero migrations added
- [x] 308/308 normal unit tests pass, 9/9 local integration tests pass
- [x] Python compilation succeeds on all files
- [x] git diff --check clean

