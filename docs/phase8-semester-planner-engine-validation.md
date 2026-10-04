# Phase 8.2 — Pure Semester Planner Engine Validation

**Phase:** 8.2 — Pure Semester Planner Engine  
**Status:** `VALIDATED`  
**Date:** 2026-09-17  
**Policy Version:** `1.0`  
**Planning Scope:** `ACADEMIC_STRUCTURE_ONLY`  

---

## 1. Executive Summary

Phase 8.2 implements the deterministic **Semester Planner Engine** for Morshidi (مرشدي) as pure Python without I/O, database, API, framework, or AI dependencies.

Building upon:
- **Phase 5:** Deterministic Prerequisite Evaluator (`evaluate_can_take`)
- **Phase 6:** Degree Progress Engine (`calculate_academic_progress`)
- **Phase 7:** Pure Recommendation Engine (`recommend_courses`)
- **Phase 8.1:** Semester Planning Policy & Optimization Specification (`docs/semester-planner-policy-spec.md`)

The engine deterministically answers:
> *"Which combinations of eligible courses should the student consider taking together in their next registration period?"*

---

## 2. Architecture & Pure Engineering Principles

The planner package is located at `apps/api/app/planner/`:
- `__init__.py`: Package export interface.
- `models.py`: Immutable frozen dataclasses, constraints, reason codes, and exceptions.
- `engine.py`: Pure deterministic branch-and-bound search, whole-plan simulation, and lexicographic ranking.

### Purity Guarantees:
- **Zero I/O / Network:** No database reads or writes, no HTTP calls, no filesystem access.
- **Zero Framework Coupling:** No FastAPI, Starlette, Supabase, or Pydantic imports inside the engine.
- **Strict Immutability:** Input catalogs, attempt tuples, and constraints are never mutated.
- **Zero Nondeterminism:** No timestamps, random generators, or execution time telemetry in result models.
- **Floating-Point Prohibition:** All credit calculations use exact Python `Decimal` arithmetic.

---

## 3. Authoritative Policy & Contracts

### 3.1 Policy Version & Planning Scope
- `SEMESTER_PLANNER_POLICY_VERSION = "1.0"`
- `PLANNING_SCOPE = "ACADEMIC_STRUCTURE_ONLY"`
  - Signals to client applications that plans represent academic eligibility and degree progression only, without timetable, schedule conflict, or seat availability guarantees.

### 3.2 Planning Horizon & In-Progress Semantics
- Strictly defined as the **Next Registration Set** (the single upcoming semester).
- Existing `IN_PROGRESS` courses:
  - Excluded from planner candidates.
  - Earn 0 completed credits in Phase 6.
  - Do not satisfy prerequisites in Phase 5.
  - Do NOT consume the upcoming `max_credit_hours` planning preference budget.
  - Reported transparently in `excluded_in_progress: tuple[str, ...]`.

### 3.3 Constraints Model (`PlannerConstraints`)
```python
@dataclass(frozen=True)
class PlannerConstraints:
    max_credit_hours: Decimal  # >= 0, <= 30.00 safety ceiling (0.00 is explicitly valid)
    max_courses: int | None = None  # Optional: 1..10 or None
    max_options: int = 5  # 1..10, default 5
    candidate_window_size: int = 15  # Default 15
```
- Validates constraints upon construction. Passing `float` raises `PlannerConstraintError`.
- Validates user planning constraints upon construction. Passing `float` raises `PlannerConstraintError`.
- Engine configuration (`candidate_window_size: int = DEFAULT_CANDIDATE_WINDOW_SIZE`) is accepted as an explicit parameter on `plan_semester(...)`, not inside `PlannerConstraints`.

---

## 4. Combinatorial Search & Whole-Plan Simulation

### 4.1 Candidate Universe & Window Bounding
- Candidates are sourced strictly from `recommendation_result.ranked_recommendations`.
- The active search window is bounded to the top $M = 15$ candidates.
- **Search Limitation:** The output is optimal within the top $M$ candidate window. The engine explicitly notes in `limitations` that results are not guaranteed globally optimal over unexamined eligible courses outside this window.

### 4.2 Exact Mathematical Search Bound
- For $M = 15$, the maximum non-empty combinations before pruning is:
  $$2^{15} - 1 = 32,767 \text{ combinations}$$
- The Depth-First Branch-and-Bound algorithm prunes branches immediately when:
  $$\text{running\_credits} + c.\text{credit\_hours} > \text{max\_credit\_hours}$$
  $$\text{running\_count} + 1 > \text{max\_courses} \quad (\text{if specified})$$
- Zero-credit mandatory courses contribute `Decimal("0")` to credits, allowing them to be evaluated even when `max_credit_hours = Decimal("0")`.

### 4.3 Whole-Plan Progress Simulation (Phase 6 Reuse)
For each valid combination $S$:
1. Create in-memory synthetic attempts:
   $$\text{synthetic\_attempts} = \left(\text{StudentCourseAttempt}(c.\text{code}, \text{PASSED}) \text{ for } c \in S\right)$$
2. Compute hypothetical academic progress via `calculate_academic_progress`:
   $$\text{modeled\_credit\_delta} = \text{progress}_{\text{after}}.\text{completed\_plan\_credits} - \text{progress}_{\text{base}}.\text{completed\_plan\_credits}$$
   - Properly respects elective group credit caps.
3. Determine newly satisfied requirement groups:
   $$\text{newly\_satisfied\_groups} = \left( g.\text{code} \mid \neg g_{\text{base}}.\text{satisfied} \land g_{\text{after}}.\text{satisfied} \right)$$

### 4.4 Whole-Plan Unlock Simulation (Phase 5 Reuse)
- The planner **never sums** individual Phase 7 unlock counts.
- For all uncompleted plan courses not in $S$ and not already baseline `ELIGIBLE`, the engine calls `evaluate_can_take()` with `combined_attempts`.
- Successfully captures joint multi-course AND dependencies (e.g. Course T requiring both A and B).
- Newly unlocked course codes are sorted ascending: `newly_eligible_course_codes`.

---

## 5. Lexicographic Priority Tuple & Sort Order

Each evaluated combination is scored by the exact 7-element priority tuple:

$$\text{Priority Tuple} = (P_1, P_2, P_3, P_4, P_5, P_6, P_7)$$

| Component | Metric | Direction | Description |
|:---:|---|:---:|---|
| **$P_1$** | `mandatory_course_count` | Higher first | Count of courses from required groups (including zero-credit required). |
| **$P_2$** | `newly_satisfied_groups_count` | Higher first | Count of requirement groups transitioned to satisfied. |
| **$P_3$** | `modeled_credit_delta` | Higher first | Net completed degree credit gain (Phase 6). |
| **$P_4$** | `newly_eligible_count` | Higher first | Downstream courses newly unlocked by joint plan completion. |
| **$P_5$** | `budget_utilization` | Higher first | Total plan credits ($\le \text{max\_credit\_hours}$). |
| **$P_6$** | `recommendation_rank_sum` | Lower first | Sum of 1-based Phase 7 ranks of constituent courses. |
| **$P_7$** | `canonical_course_codes` | Ascending | Alphabetical tuple of course codes (deterministic tiebreaker). |

### Deterministic Sort Key:
```python
(-P1, -P2, -P3, -P4, -P5, P6, P7)
```
Top $K = \text{max\_options}$ combinations are sliced from the fully sorted list and assigned ranks $1 \dots K$.

---

## 6. Reason Codes & Global Search Knowledge

The engine assigns mechanically derived reason codes matching Phase 7 semantics:

| Reason Code | Condition |
|---|---|
| `CONTAINS_MANDATORY_COURSES` | $P_1 > 0$ |
| `INCLUDES_ZERO_CREDIT_REQUIRED` | Contains a required course with `credit_hours == 0` |
| `COMPLETES_REQUIREMENT_GROUP` | $P_2 == 1$ |
| `COMPLETES_MULTIPLE_REQUIREMENT_GROUPS` | $P_2 \ge 2$ |
| `MAXIMIZES_MODELED_CREDIT_PROGRESS` | $P_3 > 0$ and $P_3 == \max(P_3)$ across ALL valid combinations evaluated in candidate window |
| `MAXIMIZES_MODELED_CREDIT_PROGRESS` | $P_3 == \max(P_3)$ across ALL valid combinations evaluated in candidate window (including when $\max(P_3) = 0$; multiple tied plans all receive it) |
| `UNLOCKS_FUTURE_COURSE` | $P_4 == 1$ |
| `UNLOCKS_MULTIPLE_FUTURE_COURSES` | $P_4 \ge 2$ |
| `NO_DIRECT_PREREQUISITE_IMPACT` | $P_4 == 0$ |
| `USES_FULL_CREDIT_PREFERENCE` | Total credits $== \text{max\_credit\_hours}$ (exact Decimal equality) |
| `INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE` | Any selected course has `previously_attempted == True` |

### Exclusivity Rules:
- Exactly one of `NO_DIRECT_PREREQUISITE_IMPACT`, `UNLOCKS_FUTURE_COURSE`, or `UNLOCKS_MULTIPLE_FUTURE_COURSES` is emitted.
- If $P_2 == 1$, only `COMPLETES_REQUIREMENT_GROUP` is emitted; if $P_2 \ge 2$, only `COMPLETES_MULTIPLE_REQUIREMENT_GROUPS` is emitted.
- `MAXIMIZES_MODELED_CREDIT_PROGRESS` is computed against global knowledge of all valid evaluated combinations, never prematurely sliced.

---

## 7. Test Matrix & Validation Results

The pure test suite is implemented in `apps/api/tests/test_semester_planner_engine.py`.

### Test Summary:
- **Suite 1 (Tests 1–12):** Constraints & validation (boundaries, float rejection, type safety).
- **Suite 2 (Tests 13–18):** Candidate window & Phase 7 derivation.
- **Suite 3 (Tests 19–25):** Combination validity & zero-credit counting.
- **Suite 4 (Tests 26–28):** Same-semester prerequisite chain prevention.
- **Suite 5 (Tests 29–35):** Progress simulation & elective capping.
- **Suite 6 (Tests 36–46):** Unlock simulation, joint AND interaction, unlock exclusions.
- **Suite 7 (Tests 47–54):** Priority tuple dimensions & sort directions.
- **Suite 8 (Tests 55–58):** Zero-credit required courses (`max_credit_hours = 0`).
- **Suite 9 (Tests 59–69):** Reason code generation & mutual exclusivity.
- **Suite 10 (Tests 70–73):** Top-$K$ retention & ranking.
- **Suite 11 (Tests 74–79):** Byte determinism & field stability.
- **Suite 12 (Tests 80–88):** Real Plan 12 facts (`0200115`, `1509999`, `1501110`, `1501112`, `1505311`, `1505320`, `0300103`).
- **Suite 13 (Tests 89–92):** Candidate window bounding & search visibility.
- **Suite 14 (Tests 93–95):** Structural integrity checks (`PlannerIntegrityError`).

### Test Execution Results:
```
apps/api/tests/test_semester_planner_engine.py: 95 passed in 0.77s
Full repository test suite: 408 passed, 9 skipped in 17.16s
apps/api/tests/test_semester_planner_engine.py: 97 passed in 0.67s
Full repository test suite: 410 passed, 9 skipped in 16.50s
```
Zero regressions across Phase 5, Phase 6, Phase 7, or earlier test suites.

---

## 8. Verification Invariants Achieved

- [x] Pure planner package created at `apps/api/app/planner/`.
- [x] Zero FastAPI, Starlette, Supabase, or I/O dependencies in engine.
- [x] Policy version `1.0` and scope marker `ACADEMIC_STRUCTURE_ONLY` verified.
- [x] Exact Decimal-safe credit arithmetic without floating-point coercion.
- [x] Top $M = 15$ candidate window bounding verified.
- [x] Explicit non-global-optimality limitation documented.
- [x] Same-semester prerequisite chaining strictly prevented by baseline eligibility.
- [x] Zero-credit required courses count toward `max_courses` and contribute at $P_1$.
- [x] Whole-plan progress simulation reuses pure Phase 6 without logic duplication.
- [x] Whole-plan unlock simulation reuses pure Phase 5 without summing individual unlocks.
- [x] Exact 7-component lexicographic priority tuple implemented and verified.
- [x] `MAXIMIZES_MODELED_CREDIT_PROGRESS` computed across all valid candidate combinations.
- [x] `MAXIMIZES_MODELED_CREDIT_PROGRESS` computed across all valid candidate combinations (including 0-delta max).
- [x] Complete determinism guaranteed (no timestamps or execution timers).
- [x] Real Plan 12 facts and exclusions verified.
- [x] All 95 planner tests and 408 total tests pass cleanly.
- [x] All 97 planner tests and 410 total tests pass cleanly.
- [x] `git diff --check` clean.

