# Phase 7.2 — Pure Recommendation Engine: Validation

**Status:** `VALIDATED`
**Date:** 2026-09-17
**Policy version:** `1.0`

---

## 1. Engine Architecture

The recommendation engine is a **pure deterministic Python function** with no I/O,
no FastAPI dependency, and no Supabase client dependency.

```
apps/api/app/recommendations/
    __init__.py       — package marker
    models.py         — RECOMMENDATION_POLICY_VERSION, RecommendationReason enum,
                        RecommendationCandidate, ReviewRequiredCourse, RecommendationResult
    engine.py         — recommend_courses() pure function

apps/api/tests/
    test_recommendation_engine.py — 84 pure tests
```

All computation is orchestrated from existing Phase 5 and Phase 6 pure functions.
**No prerequisite logic, AND/OR semantics, course-state collapsing, or credit accounting
was reimplemented.** Every such decision delegates to the validated upstream engines.

---

## 2. Policy Version

```python
RECOMMENDATION_POLICY_VERSION = "1.0"
```

Defined as a module-level constant in `models.py`. Returned verbatim in every
`RecommendationResult.recommendation_policy_version` field. No DB persistence required.

---

## 3. Engine Function Signature

```python
def recommend_courses(
    progress_catalog: AcademicProgressCatalog,
    eligibility_catalog: CanTakeCatalog,
    student_attempts: tuple[StudentCourseAttempt, ...],
    *,
    reported_cumulative_gpa: Decimal | None = None,
    reported_gpa_scale: Decimal | None = None,
    reported_earned_credit_hours: Decimal | None = None,
) -> RecommendationResult:
```

- Accepts all facts in memory. No remote calls inside the function.
- `reported_*` fields are passed through to Phase 6 unchanged (not used for ranking).
- `student_attempts` is **never mutated**. Synthetic PASSED attempts are created via append
  (`original + (synthetic,)`) which always creates a new tuple.

---

## 4. Input Models

| Model | Source | Used For |
|---|---|---|
| `AcademicProgressCatalog` | Phase 6 `progress/models.py` | Progress calculation, group structure |
| `CanTakeCatalog` | Phase 5 `rules/models.py` | Baseline and simulation eligibility |
| `tuple[StudentCourseAttempt, ...]` | Phase 5 `rules/models.py` | All student attempt history |

No new input models were created. The engine works directly with the existing domain
contracts from Phases 5 and 6.

---

## 5. Result Models

### `RecommendationReason` (10 stable codes)

| Code | Meaning |
|---|---|
| `REQUIRED_PLAN_COURSE` | Candidate belongs to a required group |
| `MANDATORY_ZERO_CREDIT_COURSE` | Required + credit_hours == 0 |
| `ADVANCES_REQUIRED_GROUP` | Contributes to unsatisfied required group |
| `ADVANCES_ELECTIVE_REQUIREMENT` | Contributes to unsatisfied elective group |
| `COMPLETES_REQUIREMENT_GROUP` | Group transitions from unsatisfied to satisfied |
| `UNLOCKS_FUTURE_COURSE` | Hypothetical pass enables exactly 1 downstream course |
| `UNLOCKS_MULTIPLE_FUTURE_COURSES` | Hypothetical pass enables ≥ 2 downstream courses |
| `NO_REMAINING_GROUP_NEED` | Group already satisfied (informational) |
| `PREVIOUSLY_ATTEMPTED` | At least one prior non-passing attempt |
| `NO_DIRECT_PREREQUISITE_IMPACT` | No downstream course becomes newly eligible |

### `RecommendationCandidate` (17 fields)

Includes: `course_code`, `course_name_ar`, `credit_hours`, `requirement_group_code`,
`requirement_type`, `course_state`, `eligibility_decision`,
`effective_credit_contribution`, `group_remaining_credits_before`,
`group_remaining_credits_after`, `completes_requirement_group`,
`newly_eligible_count`, `newly_eligible_course_codes`, `priority_tuple`, `rank`,
`reason_codes`, `previously_attempted`.

### `ReviewRequiredCourse` (7 fields)

Includes: `course_code`, `course_name_ar`, `credit_hours`, `requirement_group_code`,
`requirement_type`, `review_reason`, `previously_attempted`.

### `RecommendationResult` (7 fields)

`study_plan_id`, `recommendation_policy_version`, `ranked_recommendations`,
`review_required_courses`, `excluded_in_progress`, `methodology_note`, `limitations`.

---

## 6. Candidate Filtering

The engine partitions all plan courses into exactly one class:

| Class | Criteria | Output |
|---|---|---|
| **COMPLETED** | Phase 6 state is `COMPLETED` | Excluded silently |
| **IN_PROGRESS** | Phase 6 state is `IN_PROGRESS` | Excluded; code listed in `excluded_in_progress` |
| **NOT_ELIGIBLE** | Phase 5 decision is `NOT_ELIGIBLE` | Excluded silently |
| **REVIEW_REQUIRED** | Phase 5 decision is `REVIEW_REQUIRED` | Placed in `review_required_courses` |
| **ELIGIBLE** | Phase 5 decision is `ELIGIBLE` | Candidate for ranking |

Eligible candidates are then further filtered by the satisfied-elective-group policy
before ranking.

---

## 7. Satisfied-Elective-Group Policy

An eligible candidate is excluded from `ranked_recommendations` if:

- Its `requirement_type` is `ELECTIVE`, AND
- Its group's `remaining_required_credits == 0` (already satisfied)

This applies to both University Elective (9/33 credits needed) and Major Elective
(9/39 credits needed) in Plan 12. The progress engine's `credited_toward_requirement`
capping naturally produces `remaining_required_credits == 0` when the credit target
has been met.

---

## 8. Zero-Credit Required Course Behavior

Courses like `0200115` (University Required, 0 credits) and `1509999` (Faculty Required,
0 credits) receive:

- `P1 = 1` (zero-credit required), ranking above all electives (`P1 = 0`)
- `effective_credit_contribution = 0` (verified by Phase 6 delta calculation)
- `REQUIRED_PLAN_COURSE` + `MANDATORY_ZERO_CREDIT_COURSE` reason codes
- Reason code `ADVANCES_REQUIRED_GROUP` is **not** generated because `P3 = 0`

Phase 6 guarantees that required groups are not satisfied until ALL courses in the group
are COMPLETED (the `mandatory_condition`). Zero-credit courses participate in group
satisfaction as mandatory completion targets even though they contribute 0 credits.

---

## 9. Hypothetical Pass Simulation — Progress

For each eligible candidate `c`:

1. **Current progress** is already available from the single pre-simulation call to
   `calculate_academic_progress(progress_catalog, student_attempts)`.
2. A **synthetic attempt** is created:
   ```python
   StudentCourseAttempt(course_code=c.course_code, outcome=AttemptOutcome.PASSED)
   ```
3. **Hypothetical attempts** are constructed immutably:
   ```python
   hypothetical_attempts = student_attempts + (synthetic_attempt,)
   ```
4. **Hypothetical progress** is computed:
   ```python
   hyp_progress = calculate_academic_progress(progress_catalog, hypothetical_attempts)
   ```
5. **Delta fields** are derived:
   - `effective_credit_contribution = hyp_group.credited_toward_requirement − cur_group.credited_toward_requirement`
   - `completes_requirement_group = (not cur_group.is_satisfied) and hyp_group.is_satisfied`
   - `group_remaining_credits_after = hyp_group.remaining_required_credits`

No Phase 6 logic is duplicated. The simulation is a transparent delegation.

---

## 10. Hypothetical Pass Simulation — Eligibility (Unlock)

For each eligible candidate `c`, and each incomplete plan course `other` where
`other ≠ c`:

- If baseline `other` is `ELIGIBLE` → **skip** (not a new eligibility transition)
- If baseline `other` is `REVIEW_REQUIRED` or `NOT_ELIGIBLE`:
  - Run `evaluate_can_take(eligibility_catalog, CanTakeRequest(..., student_attempts=hypothetical_attempts))`
  - If the result is `Decision.ELIGIBLE` → count `other` as **newly eligible**

This is the complete Phase 5 evaluation, not an ad-hoc graph inspection.
REVIEW_REQUIRED courses stay REVIEW_REQUIRED unless the Phase 5 evaluator genuinely
changes its decision (which it does not for `unresolved` or `source_conflict` status).

---

## 11. Newly-Eligible Logic

```python
newly_eligible_count = len(newly_eligible_codes)
newly_eligible_course_codes = tuple(sorted(newly_eligible_codes))
```

The following are never counted:

- The candidate itself
- COMPLETED courses (already excluded from `incomplete_codes`)
- IN_PROGRESS courses (already excluded from `incomplete_codes`)
- Courses already ELIGIBLE in the baseline

---

## 12. AND/OR Prerequisite Semantics

**Zero re-implementation.** AND (multi-group) and OR (multi-option within one group)
semantics are handled entirely by `evaluate_can_take()`:

- AND across groups: all groups must have at least one satisfied option
- OR within a group: any option in the group is sufficient

Test 34 verifies AND: partial group satisfaction does not unlock a two-group course.
Test 35 verifies OR: either option in a single group unlocks the target.

---

## 13. Priority Tuple

The 7-element lexicographic priority tuple:

| Position | Name | Value | Direction |
|---|---|---|---|
| P1 | `required_mandatory_priority` | 2 (pos-credit required) / 1 (zero-credit required) / 0 (elective) | Higher first |
| P2 | `group_has_remaining_need` | 1 (remaining > 0) / 0 (satisfied) | Higher first |
| P3 | `effective_credit_contribution` | `Decimal` | Higher first |
| P4 | `completes_requirement_group` | 1 (True) / 0 (False) | Higher first |
| P5 | `newly_eligible_count` | `int` | Higher first |
| P6 | `-display_order` | negated int | Lower display_order wins |
| P7 | `course_code` | `str` | Ascending |

---

## 14. Sort-Key Implementation

Python's `list.sort()` is ascending. To achieve "higher first" for P1–P5, all are
negated in the sort key:

```python
def _sort_key(c: RecommendationCandidate) -> tuple:
    p1, p2, p3, p4, p5, p6, p7 = c.priority_tuple
    return (
        -p1,   # higher P1 first → negate
        -p2,   # higher P2 first → negate
        -p3,   # higher P3 first → negate (Decimal supports negation)
        -p4,   # group-completing first → negate
        -p5,   # more unlocks first → negate
        -p6,   # p6 = -display_order; negate gives +display_order → lower wins ✓
        p7,    # course_code ascending (no negation)
    )
```

`P6` in the tuple is already stored as `-display_order`, so `-p6 = +display_order` which
when sorted ascending gives lower display_order first. This double-negation is deliberate
and is verified by test 41.

---

## 15. Reason-Code Generation

Reason codes are generated mechanically by `_compute_reason_codes()`:

| Condition | Code(s) generated |
|---|---|
| `requirement_type == REQUIRED` | `REQUIRED_PLAN_COURSE` |
| `requirement_type == REQUIRED and credit_hours == 0` | + `MANDATORY_ZERO_CREDIT_COURSE` |
| `remaining_required_credits > 0 and REQUIRED` | `ADVANCES_REQUIRED_GROUP` |
| `remaining_required_credits > 0 and ELECTIVE` | `ADVANCES_ELECTIVE_REQUIREMENT` |
| `completes_group == True` | `COMPLETES_REQUIREMENT_GROUP` |
| `newly_eligible_count == 0` | `NO_DIRECT_PREREQUISITE_IMPACT` |
| `newly_eligible_count == 1` | `UNLOCKS_FUTURE_COURSE` |
| `newly_eligible_count >= 2` | `UNLOCKS_MULTIPLE_FUTURE_COURSES` |
| `course_state == ATTEMPTED_NOT_COMPLETED` | `PREVIOUSLY_ATTEMPTED` |

Exactly one unlock-impact code is always generated. Reason codes are always a frozen tuple.

---

## 16. Determinism

Same inputs → byte-equivalent `RecommendationResult`:

- No `time`, `random`, or `uuid` calls
- No unordered set serialization in output collections
- `newly_eligible_course_codes` → sorted ascending
- `excluded_in_progress` → sorted ascending
- `review_required_courses` → sorted by `course_code` ascending
- `ranked_recommendations` → deterministic sort key
- `student_attempts` is a `tuple` (ordered, immutable)

Verified by test 43.

---

## 17. Edge Cases Handled

| Case | Behavior |
|---|---|
| All courses completed | `ranked_recommendations == ()` — no fabricated recommendations |
| Only REVIEW_REQUIRED courses | Valid result with empty ranking and non-empty review list |
| No eligible incomplete courses | Valid empty result — not an error |
| Satisfied elective group | Remaining options excluded from ranking |
| Zero-credit required course | P1=1, effective contribution=0, structural reasons preserved |
| Referenced-only course in history | Contributes no plan progress; never becomes candidate |
| Duplicate real attempts | Phase 6 deduplicates to one COMPLETED state; no credit inflation |
| FAILED then PASSED | COMPLETED → excluded (Phase 6 priority: any PASSED → COMPLETED) |
| Multiple in-progress courses | All listed in `excluded_in_progress` sorted ascending |

---

## 18. Performance

Plan 12 has 68 plan courses.

- Phase 6 progress: called **once** for baseline, then **once per eligible candidate** for
  hypothetical progress delta. At most 68 calls total.
- Phase 5 eligibility: called **once per incomplete course** for baseline, then
  **once per (candidate × remaining incomplete course)** for unlock simulation.
  Worst case: O(N²) = 68 × 68 = 4,624 evaluations.

O(N²) is acceptable for N=68. The test suite runs all 84 tests in under 1 second.

---

## 19. Pure Test Results

**84 tests — 84 PASSED — 0 FAILED**

Test categories and counts:

| Category | Tests |
|---|---|
| Candidate filtering | 7 (tests 1–7) |
| Required / elective | 7 (tests 8–14) |
| Zero credit | 4 (tests 15–18) |
| Progress delta | 6 (tests 19–24) |
| Unlock simulation / AND/OR | 11 (tests 25–35) |
| Ranking | 8 (tests 36–43) |
| History | 5 (tests 44–48) |
| Special cases | 4 (tests 49–52) |
| Reason codes | 7 (tests 53–59) |
| Policy version | 1 (test 60) |
| Real Plan 12 facts | 12 (tests 61–68 + subtests) |
| Additional invariants | 12 (rank sequence, sort stability, import guards, etc.) |

**Total: 84 pure tests, all passing**

---

## 20. Real Plan 12 Test Results

All 12 real Plan 12 tests pass using actual course codes, credit hours, prerequisite
relationships, and group definitions from the verified migration data:

| Test | Code | Result |
|---|---|---|
| 61 | `1501112` eligible after `1501110` PASSED | ✅ PASS |
| 61b | `1501110` simulation unlocks `1501112`, `1505101`, `1506180` | ✅ PASS |
| 62 | `1505311` (unresolved) always in `review_required_courses` | ✅ PASS |
| 62b | `1505311` stays REVIEW_REQUIRED with full history | ✅ PASS |
| 63 | `1505320` (source_conflict) in `review_required_courses` | ✅ PASS |
| 63b | `1505320` review_reason contains SOURCE_CONFLICT | ✅ PASS |
| 64 | `0200115` zero-credit UNIVERSITY_REQUIRED behavior | ✅ PASS |
| 65 | `1509999` zero-credit FACULTY_REQUIRED behavior | ✅ PASS |
| 65b | Both zero-credit required courses outrank Major Elective courses | ✅ PASS |
| 66 | University Elective 9-credit satisfaction excludes remaining options | ✅ PASS |
| 67 | Major Elective 9-credit satisfaction excludes remaining options | ✅ PASS |
| 68 | `0300103` referenced-only history is never a candidate | ✅ PASS |

---

## 21. Full pytest Results

```
apps/api/tests/test_catalog_repository.py         27 passed
apps/api/tests/test_eligibility_api.py            26 passed
apps/api/tests/test_eligibility_service.py         3 passed
apps/api/tests/test_health.py                      2 passed
apps/api/tests/test_progress_engine.py            21 passed
apps/api/tests/test_progress_repository.py         5 passed
apps/api/tests/test_progress_service.py            1 passed
apps/api/tests/test_recommendation_engine.py      84 passed   ← NEW
apps/api/tests/test_rules_evaluator.py            43 passed
apps/api/tests/test_student_api.py                22 passed
apps/api/tests/test_student_repository.py         10 passed
apps/api/tests/test_student_repository_rules_integration.py  3 passed
apps/api/tests/test_student_repository_writes.py  14 passed

TOTAL: 259 passed, 0 failed
```

(Local-Supabase integration tests excluded, as they require a running Supabase instance.)

---

## 22. Python Compilation

All Phase 7.2 source files compile without error:

```
py_compile apps/api/app/recommendations/__init__.py  → OK
py_compile apps/api/app/recommendations/models.py    → OK
py_compile apps/api/app/recommendations/engine.py    → OK
py_compile apps/api/tests/test_recommendation_engine.py → OK
```

---

## 23. Dependency Confirmation

| Dependency | Status |
|---|---|
| FastAPI | ❌ Not imported in `engine.py` or `models.py` |
| Supabase client | ❌ Not imported in any Phase 7.2 file |
| httpx | ❌ Not imported in any Phase 7.2 file |
| Database migration | ❌ None created |
| Remote Supabase access | ❌ None — all computation is in-memory |
| Commit / push | ❌ Not performed |

---

## 24. Known Limitations

1. Recommendation quality is bounded by modeled academic structure.
2. Course offering and section availability are unknown.
3. Some prerequisite data remains unresolved or has source conflicts; affected courses appear only in `review_required_courses`.
4. No transfer-credit, course equivalency, or substitution model exists.
5. No course difficulty, workload, or student preference model exists.
6. Individual course ranking is not a complete semester plan.
7. No institutional administrative rules (GPA probation, holds, etc.) are modeled.
8. No official GPA calculation engine exists.
9. Derived plan progress does not constitute official graduation clearance.
10. Referenced-only courses in student history contribute no plan credit.

---

## 25. Files Created

| File | Purpose |
|---|---|
| `apps/api/app/recommendations/__init__.py` | Package marker |
| `apps/api/app/recommendations/models.py` | Policy version, reason codes, result models |
| `apps/api/app/recommendations/engine.py` | `recommend_courses()` pure engine |
| `apps/api/tests/test_recommendation_engine.py` | 84 pure tests |
| `docs/phase7-recommendation-engine-validation.md` | This document |
| `docs/recommendation-policy-spec.md` | Phase 7.1 specification (prior session) |

---

## 26. git diff --check

Exit code 0 — passed. No whitespace errors.

## 27. git status

```
On branch main
Your branch is up to date with 'origin/main'.

Untracked files:
  (use "git add <file>..." to include in what will be committed)
    apps/api/app/recommendations/
    apps/api/tests/test_recommendation_engine.py
    docs/phase7-recommendation-engine-validation.md   ← this file
    docs/recommendation-policy-spec.md                ← Phase 7.1

nothing added to commit but untracked files present
```

Only intentional Phase 7.2 files are untracked. No existing Phase 5/6 files were
modified. No commits or pushes were made.

