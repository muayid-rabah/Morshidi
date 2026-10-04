# Morshidi Semester Planning Policy & Optimization Specification

## Document status
## Document Status

- **Phase:** 8.1 — Semester Planning Policy & Optimization Specification
- **Status:** SPECIFICATION ONLY — no implementation
- **Policy version:** `1.0`
- **Phase:** 8.1 — Semester Planning Policy & Optimization Specification (Corrected)
- **Status:** SPECIFICATION ONLY — zero implementation
- **Policy Version:** `1.0`
- **Date:** 2026-09-17

---

## 1. Purpose
## 1. Purpose & Product Philosophy

This specification defines the deterministic policy by which Morshidi generates and ranks **COURSE COMBINATIONS (Semester Plans)** for an authenticated student.

In the Morshidi academic architecture:
- **Phase 5 (CAN TAKE):** Answers whether prerequisite rules are satisfied for individual courses.
- **Phase 6 (ACADEMIC PROGRESS):** Quantifies student degree state, completed requirements, and remaining credits.
- **Phase 7 (SHOULD TAKE):** Ranks individual eligible courses by degree-progress utility.
- **Phase 5 (CAN TAKE):** Answers whether prerequisite rules are satisfied for individual courses via `evaluate_can_take()`.
- **Phase 6 (ACADEMIC PROGRESS):** Quantifies student degree state, completed requirements, in-progress credits, and remaining credits via `calculate_academic_progress()`.
- **Phase 7 (SHOULD TAKE):** Ranks individual eligible courses by degree-progress utility via `recommend_courses()`.
- **Phase 8 (SEMESTER PLANNER):** Answers: **"Which combinations of eligible courses should the student consider taking together in their next registration period?"**

The core product philosophy remains immutable:

$$\text{\textbf{AI explains — Rules decide.}}$$

The semester planner builds strictly and deterministically on top of Phase 5, Phase 6, and Phase 7 outputs. It **never** relaxes prerequisite requirements, **never** fabricates institutional scheduling authority, and **never** makes stochastic or heuristic selections.
The semester planner builds strictly and deterministically on top of Phase 5, Phase 6, and Phase 7 outputs. It:
- **Never** relaxes prerequisite requirements.
- **Never** fabricates institutional scheduling authority or registration permissions.
- **Never** makes stochastic, genetic, or heuristic selections.
- **Never** evaluates GPA or performs GPA-based suitability optimization.
- **Never** claims official graduation clearance.

All generated plans represent **modeled academic study plan suggestions** based on verified study plan structure and user planning preferences.

---

## 2. Scope

In scope for Phase 8.1:

1. Formal definition of the semester planning horizon.
2. Hard prerequisite eligibility constraints (zero same-semester prerequisite chaining).
3. Source candidate universe definition derived from Phase 7.
4. User planning constraints model (`max_credit_hours`, `max_courses`).
5. Decimal-safe credit accounting rules and zero-credit required course handling.
6. Plan combination validity rules.
7. Pure hypothetical semester simulation architecture (simultaneous pass of all selected courses).
8. Plan-level interaction effects (joint multi-course unlocks).
9. Combinatorial search strategy, complexity analysis, and deterministic Top-$M$ candidate bounding.
10. Set-level lexicographic priority tuple $(P_1 \dots P_7)$ and sort semantics.
11. Machine-readable plan-level reason codes.
12. Domain result and response models.
13. Future API contract (`POST /api/v1/me/semester-plans`) and error semantics.
14. Comprehensive test matrix (54+ test cases).
15. Concrete Plan 12 examples using verified repository facts.
16. Authoritative documentation of all 20 final architectural decisions.
1. Formal definition of the semester planning horizon (**Next Registration Set**).
2. Clarification of `IN_PROGRESS` course semantics (excluded from candidates, zero consumption of planning preference budget).
3. Hard prerequisite eligibility gate (baseline `ELIGIBLE` only; no same-semester prerequisite chaining).
4. Source candidate universe definition derived from Phase 7 `ranked_recommendations`.
5. User planning constraints model (`max_credit_hours`, `max_courses`, `max_options`).
6. Exact decimal credit accounting rules and zero-credit required course handling.
7. Plan combination validity rules (pure academic constraints).
8. Pure in-memory hypothetical semester simulation architecture (simultaneous pass of all selected courses).
9. Plan-level interaction effects (joint multi-course prerequisite unlocks evaluated via Phase 5 re-evaluation; never summing individual Phase 7 unlocks).
10. Combinatorial search strategy, complexity analysis, and deterministic Top-$M$ candidate bounding.
11. Set-level lexicographic priority tuple $(P_1 \dots P_7)$ and sort semantics.
12. Machine-readable plan-level reason codes matching Phase 7 unlock semantics.
13. Domain result and response models reflecting actual repository nullable conventions.
14. Future API contract (`POST /api/v1/me/semester-plans`) with standard FastAPI validation (422) and integrity error (500) semantics.
15. Comprehensive test matrix (54 test cases) reflecting only supported features.
16. Concrete Plan 12 examples verified strictly against canonical repository data.
17. Authoritative documentation of all 20 final architectural decisions.

---

## 3. Non-Goals
## 3. Explicit Non-Goals & System Limitations

The following are explicitly **out of scope** for Phase 8:

- Official timetable generation or section scheduling.
- Class time conflict solving or exam clash detection.
- Instructor, professor, or grading leniency scoring.
- Student workload, course difficulty, or study-hour estimation.
- GPA-based suitability filtering or GPA optimization.
- Official registration hold, tuition payment, or administrative probation enforcement.
- Real-time seat availability or section capacity tracking.
- Automatic multi-semester pathing or graduation year forecasting.
- Machine learning, genetic algorithms, or non-deterministic heuristics.
- Any database writes, persistence of simulated attempts, or stored plan caches.
- Modification of Phase 5 eligibility, Phase 6 progress, or Phase 7 recommendation logic.
- **Timetable & Section Scheduling:** No section times, room allocations, or schedule clash resolution.
- **Exam Clash Detection:** No midterm or final examination scheduling.
- **Instructor / Professor Ratings:** No grading leniency, difficulty estimation, or professor preferences.
- **Workload / Study-Hour Estimation:** No subjective difficulty or effort scoring.
- **GPA Calculation or Optimization:** No GPA probation, honors thresholds, or GPA forecasting.
- **Institutional Hold Enforcement:** No tuition holds, registration queues, or administrative blocks.
- **Real-Time Seat Availability:** No seat counters, closed section tracking, or waitlists.
- **Multi-Semester Sequencing:** No 4-year pathing or expected graduation term forecasting.
- **Co-Requisites:** The current project does not model co-requisite rules; co-requisite semantics are unsupported.
- **Equivalencies & Substitutions:** The current project models NO course equivalencies, NO course substitutions, and NO transfer-credit evaluations.
- **Database Persistence:** Pure in-memory computation only. Zero database writes, no persisted simulated attempts, and no saved plan cache.
- **Modification of Prior Phases:** Zero changes to Phase 5 rules, Phase 6 progress, or Phase 7 recommendations.

---

## 4. Planning Horizon: Next Registration Set
## 4. Planning Horizon & In-Progress Semantics

### Architectural Decision 1: Planning Horizon Definition
> [!IMPORTANT]
> The planning horizon for Phase 8 is strictly defined as the **"Next Registration Set"** from the student's current academic state.
### 4.1 Planning Horizon: Next Registration Set
The planning horizon for Phase 8 is strictly defined as the **"Next Registration Set"** from the student's current academic state.
- It represents the candidate set of courses the student should consider registering for in their single upcoming term.
- It does not attempt multi-semester lookahead, avoiding speculative branching on unknown future grades, catalog revisions, or offering shifts.

- It represents the set of courses the student will register for in their next upcoming term.
- It is **not** a retrospective audit of the current term.
- Courses currently with status `IN_PROGRESS` represent work already underway in the ongoing term. They are excluded from the candidate universe and **do not** consume the credit ceiling (`max_credit_hours`) requested for the next registration set.
- All credits planned in Phase 8 represent new, unstarted course registrations.
### 4.2 Handling of In-Progress Courses
In Phase 6, `IN_PROGRESS` is a distinct course state (`CourseProgressState.IN_PROGRESS`). Per verified repository progress semantics:
- `IN_PROGRESS` courses are **not COMPLETED**.
- `IN_PROGRESS` courses earn **zero completed credits** toward degree completion (`completed_plan_credits` and `credited_toward_requirement`).
- `IN_PROGRESS` courses **do not satisfy prerequisites** in Phase 5 (`evaluate_can_take()` requires `AttemptOutcome.PASSED`).
- `IN_PROGRESS` courses are tracked separately in Phase 6 under `in_progress_plan_credits` and `in_progress_listed_credits`.

**Authoritative Phase 8 Rules for `IN_PROGRESS`:**
1. **Candidate Exclusion:** Courses currently with state `IN_PROGRESS` are **strictly excluded** from the planner candidate universe. A student cannot register for a course they are currently taking.
2. **Preference Budget Independence:** Existing in-progress courses **do not consume** any portion of the user's `max_credit_hours` planning preference for the upcoming term.
3. **Prerequisite Boundary:** Courses whose prerequisites depend *only* on currently in-progress courses remain `NOT_ELIGIBLE` at the planning baseline and are not eligible for same-semester registration.
4. **Transparency Metadata:** In-progress plan course codes are returned in the response metadata list `excluded_in_progress: tuple[str, ...]` matching Phase 7 behavior.

---

## 5. Relationship to CAN TAKE and SHOULD TAKE
## 5. Prerequisite Gate & Same-Semester Chaining Policy

The Morshidi decision pipeline flows in a strictly layered, feed-forward architecture:
### 5.1 Baseline Phase 5 Eligibility is the Hard Gate
The foundational requirement of the semester planner is:

```mermaid
flowchart TD
    subgraph Phase5 ["Phase 5: CAN TAKE (Rules Engine)"]
        P5[evaluate_can_take] -->|Prerequisites Satisfied| ELIG[ELIGIBLE Courses]
        P5 -->|Prerequisites Missing| NOT_ELIG[NOT_ELIGIBLE]
        P5 -->|Logic Unresolved / Conflict| REV_REQ[REVIEW_REQUIRED]
    end
$$\forall c \in S, \quad \text{Phase 5 Decision}(c, \text{Profile}_{\text{baseline}}) == \text{ELIGIBLE}$$

    subgraph Phase6 ["Phase 6: ACADEMIC PROGRESS"]
        P6[calculate_academic_progress] --> PROG[Completed Credits & Group Status]
    end
Every course included in a proposed semester plan must independently evaluate to `Decision.ELIGIBLE` under Phase 5 rules against the student's *current* persisted attempt history at the planning baseline.

    subgraph Phase7 ["Phase 7: SHOULD TAKE (Individual Ranking)"]
        ELIG & PROG --> P7[recommend_courses]
        P7 --> RANKED[Ranked Recommendations 1..N]
    end
### 5.2 Prohibition of Same-Semester Prerequisite Chaining
Same-semester prerequisite chaining (e.g., taking Course A and Course B together when B requires A) is **strictly prevented by the baseline eligibility gate**.

    subgraph Phase8 ["Phase 8: SEMESTER PLANNER (Set Optimization)"]
        RANKED & PROG & P5 --> P8[plan_semester]
        P8 --> OPTIONS[Ranked Plan Options A, B, C...]
    end
```
**Mechanical Proof:**
1. Suppose Course B requires Course A as a prerequisite.
2. At the planning baseline, the student has not yet passed Course A.
3. Therefore, Phase 5 evaluation of Course B against baseline attempts yields `Decision.NOT_ELIGIBLE` (reason: `MISSING_PREREQUISITE_GROUP`).
4. Because Course B is `NOT_ELIGIBLE`, Course B is excluded from Phase 7 `ranked_recommendations`.
5. Because Course B is not in `ranked_recommendations`, Course B cannot enter the planner candidate window $\mathcal{C}$.
6. Therefore, Course B can never be co-selected in any plan containing Course A.

- **Phase 5** establishes the immutable prerequisite gate.
- **Phase 6** establishes degree progress, requirement satisfaction, and credit accounting.
- **Phase 7** ranks eligible courses individually by degree-progress utility.
- **Phase 8** evaluates combinations of Phase 7 candidates, measuring **set-level synergy**, joint group completions, and multi-course unlocks.
**No Duplicated Prerequisite Logic:**
The planner does not maintain a secondary custom rule checking "course A is not in the prerequisite list of course B". The baseline Phase 5 eligibility gate guarantees this invariant unconditionally. Hypothetical in-memory passes during plan evaluation do not retroactively admit new courses into the active candidate combination.

---

## 6. Candidate Universe & Hard Eligibility Gate
## 6. Source Candidate Universe & Connection to Phase 7

### 6.1 Strict Source Universe
The candidate universe for the semester planner is exclusively the **`ranked_recommendations`** produced by the pure Phase 7 recommendation engine.
### 6.1 Strict Upstream Derivation
The planner candidate universe is derived directly from the pure Phase 7 recommendation engine:

The planner **never** recomputes individual course eligibility independently. The planner universe inherits all Phase 7 filtering guarantees:
- Every candidate is currently `ELIGIBLE` in Phase 5.
```
recommend_courses(progress_catalog, eligibility_catalog, student_attempts, ...)
```

From the resulting `RecommendationResult`, the planner extracts `ranked_recommendations: tuple[RecommendationCandidate, ...]`.

### 6.2 Guaranteed Candidate Invariants
By sourcing candidates strictly from `ranked_recommendations`, the planner inherits all Phase 7 filtering guarantees:
- Every candidate is `ELIGIBLE` in Phase 5.
- No `COMPLETED` course is present.
- No `IN_PROGRESS` course is present.
- No `NOT_ELIGIBLE` course is present.
- No `REVIEW_REQUIRED` course is present.
- No external `referenced_only` course (e.g. `0300103`) is present.
- No `REVIEW_REQUIRED` course is present (e.g., `1505311`, `1505320` reside exclusively in `review_required_courses`).
- No external `referenced_only` course (e.g., `0300103`) is present.
- No course from an already satisfied elective group is present.

### 6.2 Prohibition of Same-Semester Prerequisite Chaining
> [!CAUTION]
> **No Same-Semester Chaining:** A planned course cannot depend on another course planned in the same semester.
### 6.3 Candidate Window Bounding ($M$)
To prevent combinatorial explosion, the active candidate pool $\mathcal{C}$ is bounded to the top $M$ candidates from `ranked_recommendations`:

**Concrete Example (Zarqa University AI Plan 12):**
- Course `1501110` (Computer Programming 1) is currently `ELIGIBLE`.
- Course `1501112` (Computer Programming 2) requires `1501110` as a verified prerequisite.
- `1501112` is currently `NOT_ELIGIBLE` in the baseline state.
- **Rule:** The planner **MUST NOT** include both `1501110` and `1501112` in the same semester plan option.
- `1501112` cannot be registered until `1501110` has been fully completed and passed in a prior term. `1501112` is recognized only as a future post-plan unlock.
$$\mathcal{C} = \text{ranked\_recommendations}[:M]$$

The default MVP candidate window size is **$M = 15$**.

---

## 7. User Planning Preferences vs Institutional Rules

Morshidi does not currently store verified institutional semester credit policies (such as minimum credit load for full-time status, probation credit caps, or honor-roll maximum overloads).
Morshidi models degree study plan requirements (132 credits for Plan 12, group credit targets, and verified prerequisites). It does **not** model administrative university registration caps (e.g., full-time minimums, probation credit limits, or honor-roll overloads).

Therefore, all planner bounds are strictly **User-Supplied Planning Preferences**:
Therefore, planner constraints are strictly **User Planning Preferences**:

| Parameter | Type | Required / Optional | Semantic Meaning |
| Parameter | Type | Optionality | Semantic Meaning |
|---|---|---|---|
| `max_credit_hours` | `Decimal` | **Required** | The maximum modeled credit hours the student desires to take in the next term. |
| `max_courses` | `int` | **Optional** (default `None`) | The maximum number of course enrollments the student desires to take. |
| `max_credit_hours` | `Decimal` | **Required** | The maximum modeled credit hours the student wishes to plan for the next registration period. |
| `max_courses` | `int \| None` | **Optional** (default `None`) | The maximum number of course enrollments the student wishes to register. |
| `max_options` | `int` | **Optional** (default `5`) | The maximum number of ranked plan combinations to return ($1 \le K \le 10$). |

> [!NOTE]
> The resulting plan options represent academically coherent suggestions within the user's preferred limits. They do not convey institutional registration authorization.
> `max_credit_hours` is a user preference parameter, not an authorized university credit ceiling. The resulting plans are academic suggestions within the requested preference, not registration authorizations.

---

## 8. Credit Accounting & Constraints
## 8. Credit Accounting & Validity Constraints

### 8.1 Credit Calculation
For any proposed course combination $C = \{c_1, c_2, \dots, c_k\}$:
### 8.1 Decimal-Safe Credit Calculation
For any candidate combination $S = \{c_1, c_2, \dots, c_k\} \subseteq \mathcal{C}$:

$$\text{Total Plan Credits}(C) = \sum_{c \in C} c.\text{credit\_hours}$$
$$\text{total\_credit\_hours}(S) = \sum_{c \in S} c.\text{credit\_hours}$$

- Uses exact `Decimal` arithmetic.
- Zero-credit courses contribute exactly `Decimal("0.00")`.
- Completed courses, in-progress courses, and unselected courses contribute `0`.
- Arithmetic uses Python `Decimal` with exact fixed-point precision. Floating-point arithmetic (`float`) is strictly prohibited.
- Zero-credit required courses contribute exactly `Decimal("0.00")` to `total_credit_hours`.

### 8.2 Hard Constraint Enforcement
A combination $C$ is valid if and only if:
1. $\text{Total Plan Credits}(C) \le \text{max\_credit\_hours}$
2. If `max_courses` is specified: $|C| \le \text{max\_courses}$
3. $|C| \ge 1$ (no empty plans)
### 8.2 Plan Validity Constraints
A candidate combination $S$ is valid if and only if:
1. **Non-Empty:** $|S| \ge 1$.
2. **Credit Ceiling:** $\text{total\_credit\_hours}(S) \le \text{max\_credit\_hours}$.
3. **Course Ceiling:** If `max_courses` is specified, $|S| \le \text{max\_courses}$.
4. **Independent Baseline Eligibility:** $\forall c \in S$, $c$ is `ELIGIBLE` at the planning baseline.
5. **No Duplicate Courses:** All course codes in $S$ are distinct.

Any combination exceeding `max_credit_hours` or `max_courses` is pruned immediately. There are no soft penalties; constraint violation is an absolute filter.
Any combination violating these constraints is pruned immediately during search.

### 8.3 Zero-Credit Required Courses in Combinations
### 8.3 Zero-Credit Required Course Policy
Plan 12 contains two verified zero-credit mandatory courses:
- `0200115` — Community Service (University Required, 0 cr)
- `1509999` — Practical Training (Faculty Required, 0 cr)
- `0200115` — تنمية المجتمع والعمل التطوعي (Community Development and Volunteer Work, 0 cr, UNIVERSITY_REQUIRED)
- `1509999` — حلقة بحث لطلبة كلية تكنولوجيا المعلومات (IT Research Seminar, 0 cr, FACULTY_REQUIRED)

**Policy for Zero-Credit Courses:**
1. **Credit Budget:** A zero-credit course consumes `0.00` credit hours. It will never cause a combination to exceed `max_credit_hours`.
2. **Course Count:** A zero-credit course counts as $1$ course toward the `max_courses` constraint (if supplied).
3. **`max_credit_hours = 0` Decision:**
   - Setting `max_credit_hours = Decimal("0.00")` is **explicitly valid**.
   - This allows a student to request a plan composed exclusively of zero-credit mandatory requirements (e.g. taking Community Service during a summer or light term).
**Accounting Rules for Zero-Credit Required Courses:**
1. **Credit Budget:** Contributes `Decimal("0.00")`. It never causes a combination to exceed `max_credit_hours`.
2. **Course Count:** Counts as **$1$ course** toward `max_courses` (if specified). A plan with two 3-credit courses and one 0-credit course has $|S| = 3$.
3. **`max_credit_hours = 0` Decision:** Setting `max_credit_hours = Decimal("0.00")` is **explicitly valid**. It allows students to generate plan options composed exclusively of eligible zero-credit mandatory courses.

---

## 9. Hypothetical Semester Simulation Architecture
## 9. Pure In-Memory Simulation Architecture

Unlike Phase 7, which evaluates courses individually, Phase 8 evaluates the **joint impact** of registering and passing the entire combination together.
The planner evaluates the joint impact of a combination $S = \{c_1, \dots, c_k\}$ through pure in-memory simulation, without database writes or profile mutations.

### 9.1 In-Memory Simulation Protocol
For a valid combination $C = \{c_1, \dots, c_k\}$:
1. Create synthetic `PASSED` attempts for all selected courses simultaneously:
   $$\text{attempts}_{\text{plan}} = \text{attempts}_{\text{student}} + \left(\text{StudentCourseAttempt}(c_1.\text{code}, \text{PASSED}), \dots, \text{StudentCourseAttempt}(c_k.\text{code}, \text{PASSED})\right)$$
2. Execute Phase 6 progress engine:
   $$\text{progress}_{\text{after}} = \text{calculate\_academic\_progress}(\text{progress\_catalog}, \text{attempts}_{\text{plan}})$$
3. Execute Phase 5 rules evaluator for all remaining incomplete plan courses:
   $$\forall \text{course } t \notin (\text{completed} \cup C): \quad \text{decision}_{\text{after}}(t) = \text{evaluate\_can\_take}(\text{eligibility\_catalog}, \text{CanTakeRequest}(\text{plan\_id}, t, \text{attempts}_{\text{plan}}))$$
4. Derive plan-level progress deltas and joint unlock sets.
5. All synthetic attempts remain in volatile memory and are discarded immediately after evaluation.
### 9.1 Simulation Protocol
1. **Synthetic Attempt Construction:**
   Create an immutable sequence of in-memory synthetic attempts:
   $$\text{synthetic\_attempts} = \left(\text{StudentCourseAttempt}(c.\text{course\_code}, \text{AttemptOutcome.PASSED}) \text{ for } c \in S\right)$$
   $$\text{combined\_attempts} = \text{student\_attempts} + \text{synthetic\_attempts}$$
2. **Phase 6 Progress Simulation:**
   Re-evaluate academic progress via the real pure Phase 6 engine:
   $$\text{progress}_{\text{after}} = \text{calculate\_academic\_progress}(\text{progress\_catalog}, \text{combined\_attempts})$$
3. **Phase 5 Eligibility Simulation:**
   For all uncompleted plan courses not in $S$, re-evaluate eligibility via the real pure Phase 5 evaluator:
   $$\forall t \in \text{incomplete} \setminus S: \quad \text{decision}_{\text{after}}(t) = \text{evaluate\_can\_take}(\text{eligibility\_catalog}, \text{CanTakeRequest}(\text{study\_plan\_id}, t, \text{combined\_attempts}))$$
4. **Lifecycle & Isolation:**
   All synthetic attempts exist exclusively in volatile call-stack memory and are discarded immediately. No database writes occur.

---

## 10. Joint Unlock Impact & Interaction Effects
## 10. Plan-Level Unlock Impact & Interaction Effects

### Architectural Principle: Do Not Sum Individual Course Unlocks
### 10.1 Do Not Sum Individual Course Unlocks
> [!IMPORTANT]
> The unlock impact of a semester plan is **NOT** the sum of the individual Phase 7 `newly_eligible_count` values of its constituent courses:
> The unlock impact of a semester plan is **NOT** the sum of individual Phase 7 `newly_eligible_count` values:
>
> $$\text{Plan Unlocks}(C) \neq \sum_{c \in C} c.\text{newly\_eligible\_count}$$
> $$\text{Plan Unlocks}(S) \neq \sum_{c \in S} c.\text{newly\_eligible\_count}$$

Summing individual unlocks causes severe errors:
1. **Double-counting shared downstreams:** If course $A$ unlocks $D$ and course $B$ also unlocks $D$, summing would report 2 unlocks instead of 1.
2. **Missing joint AND interactions:** If downstream course $T$ requires **both** $A$ AND $B$:
   - Individual simulation of $A$: target $T$ is NOT unlocked ($0$ unlocks).
   - Individual simulation of $B$: target $T$ is NOT unlocked ($0$ unlocks).
Summing individual unlocks causes two critical errors:
1. **Double-Counting Shared Downstreams:** If Course A unlocks Course D and Course B also unlocks Course D, summing reports 2 unlocks instead of 1.
2. **Missing Joint Multi-Course Unlocks:** If downstream Course T requires **both** Course A AND Course B (e.g. `1501112` and `0300220` jointly unlocking downstream requirements):
   - Individual simulation of A: T is not unlocked ($0$).
   - Individual simulation of B: T is not unlocked ($0$).
   - Sum of individual unlocks: $0 + 0 = 0$.
   - **Joint Plan Simulation $\{A, B\}$:** Target $T$ transitions to `ELIGIBLE`! Joint unlocks $= 1$.
   - **Joint Plan Simulation $\{A, B\}$:** Target T transitions to `ELIGIBLE`! Joint unlocks $= 1$.

### Plan Unlock Metric
$$\text{newly\_eligible\_course\_codes\_after\_plan} = \left\{ t \in \text{incomplete} \setminus C \mid \text{decision}_{\text{base}}(t) \neq \text{ELIGIBLE} \land \text{decision}_{\text{after}}(t) = \text{ELIGIBLE} \right\}$$
### 10.2 Plan Unlock Metric ($P_4$)
$$\text{newly\_eligible\_course\_codes} = \left( t \in \text{incomplete} \setminus S \mid \text{decision}_{\text{base}}(t) \neq \text{ELIGIBLE} \land \text{decision}_{\text{after}}(t) == \text{ELIGIBLE} \right)$$

$$\text{newly\_eligible\_count\_after\_plan} = |\text{newly\_eligible\_course\_codes\_after\_plan}|$$
$$\text{newly\_eligible\_count} = |\text{newly\_eligible\_course\_codes}|$$

Sorted deterministically ascending by `course_code`.
Course codes are sorted deterministically ascending by `course_code`.

---

## 11. Plan Progress Deltas
## 11. Plan Progress Deltas & Elective Caps

Progress metrics are computed by comparing baseline `calculate_academic_progress()` with post-plan `calculate_academic_progress()`:
### 11.1 Completed Plan Credit Delta ($P_3$)
$$\Delta\text{credits} = \text{progress}_{\text{after}}.\text{completed\_plan\_credits} - \text{progress}_{\text{base}}.\text{completed\_plan\_credits}$$

1. **Completed Plan Credit Delta ($P_3$):**
   $$\Delta\text{credits} = \text{progress}_{\text{after}}.\text{completed\_plan\_credits} - \text{progress}_{\text{base}}.\text{completed\_plan\_credits}$$
   - Naturally respects elective group credit capping.
   - Zero-credit courses contribute `0.00` to credit delta.
2. **Newly Satisfied Requirement Groups ($P_2$):**
   $$\text{newly\_satisfied\_groups} = \left\{ g \mid \neg g_{\text{base}}.\text{is\_satisfied} \land g_{\text{after}}.\text{is\_satisfied} \right\}$$
   $$\text{newly\_satisfied\_group\_count} = |\text{newly\_satisfied\_groups}|$$
3. **Mandatory Required Course Count ($P_1$):**
   $$\text{mandatory\_course\_count} = |\{c \in C \mid c.\text{requirement\_type} == \text{REQUIRED}\}|$$
   - Zero-credit mandatory courses (`0200115`, `1509999`) count fully toward $P_1$.
- **Elective Cap Protection:** Because Phase 6 caps credited elective hours at `group.required_credit_hours`, any excess elective credits do not increment `completed_plan_credits`.
  - *Example:* If `UNIVERSITY_ELECTIVE` needs 3 remaining credits, selecting two 3-credit electives produces a credit delta of `Decimal("3.00")`, not `6.00`.
- Zero-credit required courses contribute `Decimal("0.00")` to credit delta.

### 11.2 Newly Satisfied Requirement Groups ($P_2$)
A requirement group $g$ is newly satisfied if:

$$\neg g_{\text{base}}.\text{is\_satisfied} \quad \land \quad g_{\text{after}}.\text{is\_satisfied}$$

$$\text{newly\_satisfied\_groups\_count} = |\{g \mid \neg g_{\text{base}}.\text{is\_satisfied} \land g_{\text{after}}.\text{is\_satisfied}\}|$$

### 11.3 Mandatory Required Course Count ($P_1$)
$$\text{mandatory\_course\_count} = |\{c \in S \mid c.\text{requirement\_type} == \text{"required"}\}|$$

Both positive-credit and zero-credit mandatory courses (`0200115`, `1509999`) increment $P_1$.

---

## 12. Combinatorial Search Strategy & Complexity Analysis
## 12. Combinatorial Search Strategy & Mathematical Bounds

### 12.1 Complexity Analysis of Naive Powerset
In Zarqa University AI Plan 12, a new student with zero attempts has **21 currently eligible courses**.
- A naive powerset search examines:
  $$2^{21} = 2,097,152 \text{ combinations}$$
- Even with credit pruning at 15 credits, evaluating hundreds of thousands of combinations through Phase 5 and Phase 6 engines would cause unacceptable latency (> 10 seconds).
### 12.1 Mathematical Upper Bounds
- For a candidate universe of size $N$, the unconstrained powerset size is $2^N - 1$.
- In Plan 12, a new student has 21 eligible courses, yielding $2^{21} - 1 = 2,097,151$ non-empty subsets.
- By bounding the search to an active window of top $M = 15$ Phase 7 recommendations:
  $$\text{Maximum Subsets Before Pruning} = 2^{15} - 1 = 32,767$$
- Under standard planning constraints ($12 \le \text{max\_credit\_hours} \le 18$), credit-based branch-and-bound prunes the search tree aggressively, evaluating only a fraction of this theoretical bound.

### 12.2 Search Strategy Selection: Deterministic Top-$M$ Candidate Window with Depth-First Pruning
To ensure strict determinism, transparent auditability, and sub-50ms execution:
### 12.2 Search Strategy: Depth-First Branch-and-Bound
The engine enumerates candidate combinations using a deterministic Depth-First Search (DFS) over the $M$ candidates (ordered by Phase 7 recommendation rank):
1. **Branch Cut 1 (Credit Ceiling):** Prune branch if $\text{current\_credits} + c.\text{credit\_hours} > \text{max\_credit\_hours}$.
2. **Branch Cut 2 (Course Ceiling):** Prune branch if $\text{max\_courses}$ is defined and $\text{current\_count} + 1 > \text{max\_courses}$.
3. **Combination Evaluation:** Each valid leaf combination is simulated via Phase 6 and Phase 5, evaluated for its 7-component priority tuple, and inserted into a bounded top-$K$ priority queue.

1. **Top-$M$ Candidate Search Window ($M = 15$):**
   - The planner considers only the top $M$ candidates from Phase 7 `ranked_recommendations`.
   - Default $M = 15$.
   - Why 15? The Phase 7 ranking has already filtered and sorted the courses by academic utility. The optimal combination of 4–5 courses will overwhelmingly be formed from the highest-ranked candidates.
2. **Depth-First Branch-and-Bound Search with Pruning:**
   - Enumerate combinations using a recursive DFS tree over the $M$ candidates.
   - **Pruning Rule 1 (Credit Ceiling):** If $\text{current\_credits} + c_i.\text{credit\_hours} > \text{max\_credit\_hours}$, prune this branch.
   - **Pruning Rule 2 (Course Count):** If $\text{max\_courses}$ is set and $\text{current\_count} + 1 > \text{max\_courses}$, prune this branch.
3. **Number of Combinations Evaluated:**
   - Under $M = 15$ with credit limit of 15 credits (typical course = 3 cr, max 5 courses):
     $$\sum_{k=1}^5 \binom{15}{k} \text{ filtered by credit budget} \approx 80 - 250 \text{ valid combinations}$$
   - Evaluating 200 combinations in memory requires $< 30$ milliseconds.
4. **Transparency Limitation:**
   - The output is formally documented as:
     $$\text{"Optimal plan options within the Top-} M \text{ recommendation candidate window."}$$
### 12.3 Explicit Non-Global-Optimality Limitation
> [!WARNING]
> **Candidate Window Bounding Limitation:**
> $M = 15$ and $K = 5$ are **MVP computation configuration parameters**, not academic rules.
> Because the search evaluates combinations formed exclusively from the top $M$ Phase 7 candidates, the planner is **not guaranteed globally optimal** over hypothetical combinations that include eligible courses ranked outside the top $M$ window.

---

## 13. Set-Level Ranking Policy & Priority Tuple
## 13. Set-Level Ranking Policy & Exact Priority Tuple

Phase 8 ranks **entire course sets**, not individual courses. Consistent with Morshidi's architectural standard, ranking is strictly **lexicographic** using an exact 7-element priority tuple.
Phase 8 ranks **entire course sets** using an exact, deterministic 7-element lexicographic priority tuple:

### 13.1 Exact Plan Priority Tuple

$$\text{Plan Priority Tuple} = \left( P_1, P_2, P_3, P_4, P_5, P_6, P_7 \right)$$

| Position | Dimension | Type | Sort Direction | Semantic Justification |
|:---:|---|---|:---:|---|
| **$P_1$** | `mandatory_required_course_count` | `int` | **Higher first** | Degree completion requires passing all mandatory courses. Prioritizing mandatory courses prevents students from filling schedules exclusively with electives. Zero-credit required courses count fully here. |
| **$P_2$** | `newly_satisfied_requirement_group_count` | `int` | **Higher first** | Completely clearing a requirement group (e.g. University Required or Faculty Required) is a major academic milestone that eliminates entire categories of degree constraints. |
| **$P_3$** | `completed_plan_credit_delta` | `Decimal` | **Higher first** | Net progress toward the 132-credit degree requirement. Evaluated via Phase 6 progress delta, properly respecting elective caps. |
| **$P_4$** | `newly_eligible_count_after_plan` | `int` | **Higher first** | Forward academic momentum. Measures how many downstream courses are unlocked by the joint completion of this plan. |
| **$P_5$** | `total_plan_credits` (Budget Utilization) | `Decimal` | **Higher first** | All academic outcomes being equal, a student requesting up to 15 credits prefers a plan utilizing 15 credits over a plan utilizing 12 credits. |
| **$P_6$** | `individual_recommendation_rank_sum` | `int` | **Lower first** (negated in tuple) | Sum of individual Phase 7 ranks of constituent courses. Breaks ties by favoring combinations of individually stronger recommendations. |
| **$P_7$** | `canonical_course_codes` | `tuple[str, ...]` | **Ascending** (lexicographic) | Final deterministic tie-breaker. Sorted tuple of course codes (e.g. `('0200104', '1501110')`). Guarantees zero set-iteration instability. |
| Position | Dimension | Type | Direction | Academic Meaning |
|:---:|---|:---:|:---:|---|
| **$P_1$** | `mandatory_course_count` | `int` | **Descending** ($\max$) | Count of mandatory study plan courses (including zero-credit required courses). Prioritizes core requirements over electives. |
| **$P_2$** | `newly_satisfied_groups_count` | `int` | **Descending** ($\max$) | Count of requirement groups transitioned from unsatisfied to satisfied by this plan. |
| **$P_3$** | `completed_plan_credit_delta` | `Decimal` | **Descending** ($\max$) | Net modeled degree credit progress toward 132 credits (respecting elective caps). |
| **$P_4$** | `newly_eligible_count` | `int` | **Descending** ($\max$) | Count of downstream courses newly unlocked by the joint completion of this plan. |
| **$P_5$** | `total_plan_credits` (Budget Utilization) | `Decimal` | **Descending** ($\max$) | Total credits in the plan ($\le \text{max\_credit\_hours}$). Prefers fuller utilization of user preference when academic deltas are equal. |
| **$P_6$** | `recommendation_rank_sum` | `int` | **Ascending** ($\min$, negated for sort) | Sum of individual 1-based Phase 7 ranks of constituent courses. Favors combinations of individually higher-ranked recommendations. |
| **$P_7$** | `canonical_course_codes` | `tuple[str, ...]` | **Ascending** ($\min$, lexicographic) | Alphabetically sorted tuple of course code strings. Absolute deterministic tiebreaker. |

### 13.2 Justification of Key Ordering Decisions
1. **$P_1$ (Mandatory Count) before $P_3$ (Credit Delta):**
   - Zero-credit mandatory courses contribute $0$ credits. Placing $P_1$ first guarantees that combinations including `0200115` or `1509999` are recognized for their structural necessity rather than penalized for having 0 credits.
2. **$P_2$ (Group Satisfaction) before $P_3$ (Credit Delta):**
   - Completing a requirement group is a permanent structural milestone. Two plans offering the same credit progress will prefer the one that formally satisfies a group.
3. **$P_3$ (Credit Delta) before $P_4$ (Unlock Count):**
   - Earning modeled degree credits toward the 132-credit requirement is the primary graduation metric; forward unlocking serves as a differentiator among equal-progress plans.
4. **$P_5$ (Budget Utilization) Late in the Tuple:**
   - Budget utilization reflects user preference, not academic quality. Consuming more credits without producing more mandatory courses, group completions, credit progress, or unlocks should never rank higher.
### 13.1 Justification of Ordering Decisions
1. **$P_1$ (Mandatory Count) First:** Mandatory courses are non-substitutable degree requirements. Placing $P_1$ first guarantees that zero-credit mandatory courses (`0200115`, `1509999`) are recognized for their structural necessity rather than penalized for contributing zero credits.
2. **$P_2$ (Group Completion) before $P_3$ (Credit Delta):** Completely satisfying a requirement group clears an entire category of degree requirements, providing higher structural milestone value than equal credit accumulation across uncompleted groups.
3. **$P_3$ (Credit Delta) before $P_4$ (Unlock Count):** Earning modeled degree credits directly advances the 132-credit degree requirement; forward unlocking serves as a differentiator among equal-credit plans.
4. **$P_5$ (Budget Utilization) Late:** User credit preference is an upper ceiling, not an academic priority. Consuming more credits without producing more mandatory courses, group completions, or credit progress should never outrank a more efficient plan.
5. **$P_6$ (Rank Sum) before $P_7$ (Tiebreak):** Phase 7 ranks reflect individual degree-utility factors ($P_1$: mandatory priority, $P_2$: group need, $P_3$: credit contribution, $P_4$: group completion, $P_5$: direct unlocks, $P_6$: display order, $P_7$: course code). Summing these ranks breaks ties in favor of courses with higher individual priority.
6. **$P_7$ (Canonical Course Codes):** Because course codes are unique, $P_7$ provides a 100% deterministic tiebreaker.

---

## 14. Top-$K$ Plan Options & Presentation
## 14. Top-$K$ Options & Presentation

- The engine evaluates all valid combinations within the candidate window, sorts them by the priority tuple, and returns the **Top-$K$ Plan Options**.
- **Default $K$:** $K = 5$ plan options.
- **Presentation Slicing:**
  $$\text{plan\_options} = \text{sorted\_combinations}[:K]$$
- Slicing affects presentation only; the top $K$ plans maintain their true global ranks ($1, 2, \dots, K$).
- **Plan Diversity:** Phase 8 MVP does not introduce artificial diversity heuristics. If the top 3 plans differ by only one elective, they are presented in their true deterministic mathematical rank order.
- The engine retains the top $K$ plan options ($K = 5$ by default, configurable up to 10).
- Presentation slicing: $\text{plan\_options} = \text{sorted\_combinations}[:K]$.
- Within each `SemesterPlanOption`, courses in the `courses` tuple are ordered deterministically by:
  1. `display_order` ascending (from the study plan catalog).
  2. `course_code` ascending (alphabetical tiebreaker).

---

## 15. Plan-Level Reason Codes

Each generated `SemesterPlanOption` carries mechanically derived, deterministic reason codes:
Each generated `SemesterPlanOption` carries mechanically derived, deterministic reason codes aligned with Phase 7 semantics:

| Reason Code | Trigger Condition |
|---|---|
| `CONTAINS_MANDATORY_COURSES` | $P_1 > 0$ (contains at least one course in a REQUIRED group) |
| `INCLUDES_ZERO_CREDIT_REQUIRED` | Contains at least one course with `credit_hours == 0` and `requirement_type == REQUIRED` |
| `COMPLETES_REQUIREMENT_GROUP` | $P_2 == 1$ (transitions exactly 1 requirement group to satisfied) |
| `COMPLETES_MULTIPLE_REQUIREMENT_GROUPS` | $P_2 \ge 2$ (transitions 2 or more groups to satisfied) |
| `MAXIMIZES_MODELED_CREDIT_PROGRESS` | $P_3 > 0$ and equals the highest credit delta found among candidate combinations |
| `UNLOCKS_FUTURE_COURSES` | $P_4 == 1$ (jointly unlocks exactly 1 downstream plan course) |
| `UNLOCKS_MULTIPLE_FUTURE_COURSES` | $P_4 \ge 2$ (jointly unlocks 2 or more downstream plan courses) |
| `NO_DIRECT_PREREQUISITE_IMPACT` | $P_4 == 0$ (unlocks zero downstream plan courses) |
| `USES_FULL_CREDIT_PREFERENCE` | $\text{total\_credit\_hours} == \text{max\_credit\_hours}$ |
| `INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE` | Contains at least one course where student had a prior non-passing attempt |
| `CONTAINS_MANDATORY_COURSES` | $P_1 > 0$ (contains at least one course in a `required` group). |
| `INCLUDES_ZERO_CREDIT_REQUIRED` | Contains at least one course with `credit_hours == Decimal("0.00")` and `requirement_type == "required"`. |
| `COMPLETES_REQUIREMENT_GROUP` | $P_2 == 1$ (transitions exactly 1 requirement group to satisfied). |
| `COMPLETES_MULTIPLE_REQUIREMENT_GROUPS` | $P_2 \ge 2$ (transitions 2 or more requirement groups to satisfied). |
| `MAXIMIZES_MODELED_CREDIT_PROGRESS` | $P_3 > 0$ and equals the highest credit delta found among evaluated candidate plans. |
| `UNLOCKS_FUTURE_COURSE` | $P_4 == 1$ (jointly unlocks exactly 1 downstream plan course). |
| `UNLOCKS_MULTIPLE_FUTURE_COURSES` | $P_4 \ge 2$ (jointly unlocks 2 or more downstream plan courses). |
| `NO_DIRECT_PREREQUISITE_IMPACT` | $P_4 == 0$ (unlocks zero downstream plan courses). |
| `USES_FULL_CREDIT_PREFERENCE` | $\text{total\_credit\_hours} == \text{max\_credit\_hours}$. |
| `INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE` | Contains at least one course where the student has a prior non-passing attempt. |

*Note on Unlock Reason Codes:* Exactly one of `NO_DIRECT_PREREQUISITE_IMPACT` ($P_4=0$), `UNLOCKS_FUTURE_COURSE` ($P_4=1$), or `UNLOCKS_MULTIPLE_FUTURE_COURSES` ($P_4 \ge 2$) is emitted per plan option, matching Phase 7 unlock reason semantics.

---

## 16. Data Models & Result Contracts
## 16. Domain Models & Result Contracts

### 16.1 Internal Domain Models
All domain models use nullable Arabic/English names matching existing repository contracts:

```python
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Sequence

SEMESTER_PLANNER_POLICY_VERSION = "1.0"


class PlanReasonCode(str, Enum):
    CONTAINS_MANDATORY_COURSES = "CONTAINS_MANDATORY_COURSES"
    INCLUDES_ZERO_CREDIT_REQUIRED = "INCLUDES_ZERO_CREDIT_REQUIRED"
    COMPLETES_REQUIREMENT_GROUP = "COMPLETES_REQUIREMENT_GROUP"
    COMPLETES_MULTIPLE_REQUIREMENT_GROUPS = "COMPLETES_MULTIPLE_REQUIREMENT_GROUPS"
    MAXIMIZES_MODELED_CREDIT_PROGRESS = "MAXIMIZES_MODELED_CREDIT_PROGRESS"
    UNLOCKS_FUTURE_COURSES = "UNLOCKS_FUTURE_COURSES"
    UNLOCKS_FUTURE_COURSE = "UNLOCKS_FUTURE_COURSE"
    UNLOCKS_MULTIPLE_FUTURE_COURSES = "UNLOCKS_MULTIPLE_FUTURE_COURSES"
    NO_DIRECT_PREREQUISITE_IMPACT = "NO_DIRECT_PREREQUISITE_IMPACT"
    USES_FULL_CREDIT_PREFERENCE = "USES_FULL_CREDIT_PREFERENCE"
    INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE = "INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE"


@dataclass(frozen=True)
class PlannedCourseEntry:
    """A selected course entry within a proposed semester plan option."""
    course_code: str
    course_name_ar: str | None
    course_name_en: str | None
    credit_hours: Decimal
    requirement_group_code: str
    requirement_type: str                  # "required" | "elective"
    recommendation_rank: int               # Phase 7 individual rank
    previously_attempted: bool


@dataclass(frozen=True)
class SemesterPlanOption:
    """A single ranked course combination option for the semester."""
    rank: int                              # 1-based rank
    rank: int                              # 1-based rank (1 = best)
    courses: tuple[PlannedCourseEntry, ...] # Ordered by display_order, course_code
    total_credit_hours: Decimal
    required_course_count: int
    elective_course_count: int
    zero_credit_required_count: int
    completed_plan_credit_delta: Decimal
    newly_satisfied_requirement_group_codes: tuple[str, ...]
    newly_eligible_course_codes: tuple[str, ...]
    newly_eligible_count: int
    priority_tuple: tuple[int, int, Decimal, int, Decimal, int, tuple[str, ...]]
    reason_codes: tuple[PlanReasonCode, ...]


@dataclass(frozen=True)
class PlannerConstraints:
    """Planning constraints provided as input."""
    max_credit_hours: Decimal
    max_courses: int | None = None
    max_options: int = 5
    candidate_window_size: int = 15


@dataclass(frozen=True)
class SemesterPlannerResult:
    """Complete result returned by the semester planning engine."""
    """Complete result returned by the pure semester planning engine."""
    study_plan_id: str
    planner_policy_version: str
    planning_scope: str                    # "ACADEMIC_STRUCTURE_ONLY"
    constraints: PlannerConstraints
    plan_options: tuple[SemesterPlanOption, ...]
    review_required_courses: tuple[ReviewRequiredCourse, ...]
    excluded_in_progress: tuple[str, ...]
    review_required_courses: tuple[str, ...]  # Course codes with REVIEW_REQUIRED
    excluded_in_progress: tuple[str, ...]     # Course codes currently IN_PROGRESS
    candidate_window_size_applied: int
    methodology_note: str
    limitations: tuple[str, ...]
```

### 16.2 Determinism Guarantees
- No timestamps (`created_at`, `evaluated_at`) or runtime execution timers exist in `SemesterPlannerResult` or `SemesterPlanOption`.
- Given identical catalogs, attempts, and constraints, the planner produces identical, byte-reproducible outputs.

---

## 17. Future API Specification

### 17.1 Endpoint Route & Method
`POST /api/v1/me/semester-plans`

- **HTTP Method:** `POST`
  - *Rationale:* Planner constraints represent a structured request payload (`max_credit_hours`, `max_courses`, `max_options`). POST is standard for complex computation requests with request bodies.
  - *Statelessness:* The endpoint performs zero database mutations. No plan rows or simulation attempts are written to Supabase.
- **Authentication:** Bearer token (`HTTPBearer`). Identity derived strictly from `get_current_user`.
- **Security:** No `owner_user_id`, `study_plan_id`, or student history is accepted from the client.
- **HTTP Method:** `POST` (computational request carrying structured JSON payload).
- **Stateless Computation:** Performs zero database writes. No plans or synthetic attempts are persisted.
- **Authentication:** Bearer token (`HTTPBearer`). User identity derived strictly from auth token via `get_current_user`.
- **Security:** The request accepts zero user IDs or attempt histories from the client.

### 17.2 Request Schema
```json
{
  "max_credit_hours": 15,
  "max_courses": 5,
  "max_options": 5
}
```python
from decimal import Decimal
from pydantic import BaseModel, Field

class SemesterPlanRequest(BaseModel):
    max_credit_hours: Decimal = Field(
        ...,
        ge=Decimal("0.0"),
        le=Decimal("30.0"),
        description="Maximum planned credit hours preference (safety upper bound: 30.0)"
    )
    max_courses: int | None = Field(
        None,
        ge=1,
        le=10,
        description="Optional maximum number of course enrollments"
    )
    max_options: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of ranked plan options to return"
    )
```

- `max_credit_hours`: Decimal, required, $\ge 0.00$, $\le 30.00$.
- `max_courses`: Integer, optional, $\ge 1$, $\le 10$, nullable.
- `max_options`: Integer, optional, $\ge 1$, $\le 10$, default 5.
> [!NOTE]
> `max_credit_hours <= 30.0` is an API computational sanity bound, not an official university policy limit.

### 17.3 Response Status Codes
- `200 OK`: Successful computation, including valid empty options (`plan_options: []`).
- `401 Unauthorized`: Missing or invalid Bearer token.
- `404 Not Found`: Student profile not found.
- `422 Unprocessable Entity`: Input validation failure (`max_credit_hours < 0`, invalid types).
- `500 Internal Server Error`: Catalog or student profile integrity failure.
- `503 Service Unavailable`: Transport failure connecting to database.
### 17.3 Response Status Codes & Error Mapping
Aligning strictly with Morshidi FastAPI architectural conventions:
- **`200 OK`**: Successful computation, including valid empty options (`plan_options: []`).
- **`401 Unauthorized`**: Missing or invalid Bearer authentication token.
- **`404 Not Found`**: Student academic profile not found for authenticated user.
- **`422 Unprocessable Entity`**: Pydantic schema validation failure (e.g., negative `max_credit_hours`, `max_courses < 1` or `> 10`, non-numeric credits).
- **`500 Internal Server Error`**: Study plan catalog integrity failure (`ProgressIntegrityError`, inconsistent requirement groups).
- **`503 Service Unavailable`**: Server configuration or database transport failure (`StudentConfigurationError`).

---

## 18. Concrete Plan 12 Examples
## 18. Verified Real Plan 12 Examples

### Example 1: New Student (Zero Attempts)
**Context:** Zarqa University AI Plan 12 (132 credits). Student has 0 completed credits and 0 attempts.
- **Eligible Courses:** 21 courses currently eligible (e.g. `0200104`, `0200110`, `0200111`, `0200115`, `0300153`, `1505490`...).
- **User Constraints:** `max_credit_hours = 15`, `max_courses = 5`.
- **Generated Plan Option 1:**
  - Courses:
    1. `0300153` (Life Skills, 1 cr, Univ Req) — Unlocks `1501110` (Computer Programming 1)!
    2. `0200104` (National Education, 3 cr, Univ Req)
    3. `0200110` (Military Sciences, 3 cr, Univ Req)
    4. `0200111` (Islamic Culture, 3 cr, Univ Req)
    5. `1505467` (Linear Algebra, 3 cr, Faculty Req) — Unlocks `1505201`!
  - Total Credits: $1 + 3 + 3 + 3 + 3 = 13\text{ credits}$.
  - $P_1 = 5$ mandatory courses.
  - $P_2 = 0$ groups completed (Univ Req requires 18 cr, this adds 10 cr).
  - $P_3 = 13.00$ credit delta.
  - $P_4 = 4$ newly eligible downstream courses (`1501110`, `0300220`, `1503270`, `1505201`).
  - Reason Codes: `CONTAINS_MANDATORY_COURSES`, `MAXIMIZES_MODELED_CREDIT_PROGRESS`, `UNLOCKS_MULTIPLE_FUTURE_COURSES`.
All courses and requirement groups below are verified against canonical repository seed migrations (`20260916224842_seed_ai_plan12_foundation.sql`, `20260916230222_seed_ai_plan12_courses.sql`, and `20260916231030_model_ai_plan12_prerequisites.sql`).

### Study Plan 12 Structure:
- **Total Degree Credits:** 132 credits.
- **Groups:**
  1. `UNIVERSITY_REQUIRED` (18 credits required)
  2. `UNIVERSITY_ELECTIVE` (9 credits required from 33 listed)
  3. `FACULTY_REQUIRED` (21 credits required)
  4. `SUPPORTING_REQUIRED` (12 credits required)
  5. `MAJOR_REQUIRED` (63 credits required)
  6. `MAJOR_ELECTIVE` (9 credits required from 39 listed)

---

### Example 1: New Student (Zero Completed Credits, Zero Attempts)
**Context:** Student has 0 completed credits.
- **Baseline Eligible Courses:** 21 courses are baseline `ELIGIBLE`, including:
  - `0200104` (التربية الوطنية, 3 cr, Univ Req)
  - `0200110` (العلوم العسكرية, 3 cr, Univ Req)
  - `0200111` (الثقافة الاسلامية وقضايا العصر, 3 cr, Univ Req)
  - `0200115` (تنمية المجتمع والعمل التطوعي, 0 cr, Univ Req)
  - `0200153` (المهارات الحياتية, 1 cr, Univ Req)
  - `0200154` (القيادة والمسؤولية المجتمعية, 1 cr, Univ Req)
  - `0400202` (الريادة والابتكار, 1 cr, Univ Req)
  - `0300153` (اساسيات تكنولوجيا المعلومات, 3 cr, Faculty Req)
  - `0300154` (اساسيات الامن السيبراني, 3 cr, Faculty Req)
  - `0300155` (تصميم المنطق الرقمي, 3 cr, Faculty Req)
  - `0300101` (التفاضل والتكامل 1, 3 cr, Supporting Req)
  - `0300104` (الاحصاء والاحتمالات لتكنولوجيا المعلومات, 3 cr, Supporting Req)
  - `0301245` (الجبر الخطي لتكنولوجيا المعلومات, 3 cr, Supporting Req)
  - `1509999` (حلقة بحث لطلبة كلية تكنولوجيا المعلومات, 0 cr, Faculty Req)
- **User Preference:** `max_credit_hours = 15.00`, `max_courses = 5`.
- **Top Plan Option Evaluation:**
  - Includes `0300153` (IT Fundamentals, 3 cr, Faculty Req).
  - Passing `0300153` unlocks 5 downstream plan courses: `0300220`, `1501110`, `1501111`, `1503270`, `1505201`.
  - Together with 4 other 3-credit mandatory courses (e.g., `0200104`, `0200110`, `0200111`, `0300101`):
    - Total Credits: 15.00.
    - $P_1 = 5$ mandatory courses.
    - $P_2 = 0$ groups completed (Univ Req needs 18 cr, Faculty Req needs 21 cr).
    - $P_3 = 15.00$ credit delta.
    - $P_4 = 5$ unlocked courses.
    - Reason Codes: `CONTAINS_MANDATORY_COURSES`, `MAXIMIZES_MODELED_CREDIT_PROGRESS`, `UNLOCKS_MULTIPLE_FUTURE_COURSES`, `USES_FULL_CREDIT_PREFERENCE`.

---

### Example 2: Same-Semester Prerequisite Chain Prevention
- In the same baseline state, `1501112` (Programming 2) requires `1501110` (Programming 1).
- Even though `0300153` unlocks `1501110`, neither `1501110` nor `1501112` can appear together in Plan Option 1.
- `1501110` is unlocked only as a **future** downstream course in `newly_eligible_course_codes`.
**Context:** Student has passed `0300153` in a prior semester.
- `1501110` (برمجة الحاسوب 1, 3 cr) has verified prerequisite `0300153`. Because `0300153` is passed, `1501110` is baseline **`ELIGIBLE`**.
- `1501112` (برمجة الحاسوب 2, 3 cr) has verified prerequisite `1501110`. Because `1501110` is NOT yet passed, `1501112` is baseline **`NOT_ELIGIBLE`**.
- **Result:** `1501112` is excluded from Phase 7 `ranked_recommendations`. It cannot be selected into any proposed plan.
- A plan selecting `1501110` will report `1501112` in `newly_eligible_course_codes` as a future post-plan unlock, but `1501110` and `1501112` **never appear together in the same semester plan**.

### Example 3: Zero-Credit Inclusion
- If user requests `max_credit_hours = 12`, `max_courses = 5`:
- A combination containing 4 positive-credit required courses (12 cr) + `0200115` (0 cr) has 12 credits and 5 courses.
- Total Credits: 12.00.
- Mandatory Course Count ($P_1$): 5 courses.
- This plan ranks above a 4-course 12-credit plan ($P_1 = 4$) solely because it includes the zero-credit mandatory requirement.
---

### Example 3: Zero-Credit Required Milestone Planning
**Context:** Student has 12 credits remaining in a term and sets `max_credit_hours = 12.00`, `max_courses = 5`.
- Plan Option A: Four 3-credit mandatory courses (12 cr, $|S| = 4$). $P_1 = 4$, Total Credits = 12.00.
- Plan Option B: Four 3-credit mandatory courses + `0200115` (0 cr, $|S| = 5$). $P_1 = 5$, Total Credits = 12.00.
- **Result:** Plan Option B strictly outranks Plan Option A at $P_1$ ($5 > 4$). The zero-credit mandatory course is successfully incorporated without exceeding `max_credit_hours` or `max_courses`.

---

### Example 4: Elective Capping & Credit Delta Progress
**Context:** Student has already completed 6 credits in `UNIVERSITY_ELECTIVE` (which requires 9 credits).
- The student's candidate pool includes eligible university electives: `0200113` (3 cr) and `0200114` (3 cr).
- If a proposed plan selects both `0200113` and `0200114` (6 attempted credits):
  - Phase 6 progress calculation caps credited elective hours at 9 credits.
  - Baseline credited hours = 6.00. Post-plan credited hours = 9.00.
  - Modeled credit delta $P_3 = 3.00$ credits (not 6.00 credits).
  - Group completion: `UNIVERSITY_ELECTIVE` transitions from unsatisfied to satisfied ($P_2 = 1$).
  - Reason Codes include `COMPLETES_REQUIREMENT_GROUP`.

---

## 19. Comprehensive Test Matrix (54 Test Cases)

```
================================================================================
PART 1: CONSTRAINTS & INPUT VALIDATION (Tests 01–10)
================================================================================
01. combination_over_credit_max_pruned
    - Given a candidate combination whose sum of credit_hours > max_credit_hours,
      assert it is pruned during search and never appears in plan_options.
02. combination_exactly_at_credit_max_valid
    - Given a candidate combination whose sum == max_credit_hours, assert it is
      valid and can be ranked.
03. zero_credit_course_does_not_consume_credit_budget
    - Adding 0200115 (0 cr) to a 12-credit plan yields total_credit_hours == 12.00.
04. max_courses_constraint_enforced
    - If max_courses = 4, a 5-course combination is pruned even if within credit limit.
05. zero_credit_course_counts_toward_max_courses
    - 4 positive-credit courses + 1 zero-credit course = 5 courses; violates max_courses = 4.
06. empty_combination_excluded
    - The empty combination () is never returned as a plan option.
07. duplicate_courses_impossible
    - A course code can appear at most once in any proposed plan option.
08. decimal_credit_safety
    - Combinations with fractional credits (e.g. 1.00 + 3.00 = 4.00) use exact Decimal arithmetic.
09. max_credit_hours_zero_valid
    - Request with max_credit_hours = 0 returns plans containing only zero-credit courses.
10. negative_max_credit_hours_rejected
    - Input validation rejects max_credit_hours < 0 with HTTP 422.
10. pydantic_schema_validation_rejects_negative_credits_with_422
    - Input validation rejects max_credit_hours < 0 with HTTP 422 Unprocessable Entity.

================================================================================
PART 2: ELIGIBILITY & CANDIDATE FILTERING (Tests 11–18)
================================================================================
11. completed_courses_excluded_from_plans
    - Courses marked COMPLETED in Phase 6 never appear in any plan option.
12. in_progress_courses_excluded_from_plans
    - Courses with state IN_PROGRESS never appear in any plan option.
13. not_eligible_courses_excluded_from_plans
    - Courses with Phase 5 decision NOT_ELIGIBLE never appear in any plan option.
14. review_required_courses_excluded_from_plans
    - Courses with Phase 5 decision REVIEW_REQUIRED (1505311, 1505320) never appear in plans.
15. referenced_only_courses_excluded_from_plans
    - External courses (0300103) never appear in any plan option.
16. satisfied_elective_options_excluded_from_plans
    - If an elective group is satisfied, remaining uncompleted electives in that group are excluded.
17. previously_failed_eligible_candidate_can_appear
    - A course with FAILED-only history that is currently ELIGIBLE can be included in plans.
18. previously_attempted_flag_set_on_entry
    - When a previously failed course is planned, PlannedCourseEntry.previously_attempted is True.

================================================================================
PART 3: SAME-SEMESTER PREREQUISITE CHAIN PREVENTION (Tests 19–21)
================================================================================
19. dependent_course_not_eligible_at_baseline_excluded
    - If A is eligible and B requires A, B cannot appear in any plan containing A.
20. hypothetical_pass_of_A_does_not_admit_B_to_same_plan
    - Passing A in simulation does not dynamically admit B into the current semester plan.
21. B_appears_in_newly_eligible_after_plan
    - B correctly appears in newly_eligible_course_codes of the plan containing A.

================================================================================
PART 4: PROGRESS DELTA & GROUP SATISFACTION (Tests 22–27)
================================================================================
22. selected_required_course_increases_credit_delta
    - Adding a 3-credit required course increases completed_plan_credit_delta by 3.00.
23. selected_zero_credit_required_course_yields_zero_credit_delta
    - Adding 0200115 (0 cr) contributes 0.00 to completed_plan_credit_delta.
24. elective_credits_capped_at_requirement_need
    - In elective group needing 3 credits, selecting two 3-credit electives yields delta = 3.00.
25. single_group_satisfaction_detected
    - When plan courses satisfy a group, newly_satisfied_requirement_group_codes contains group.
26. multiple_groups_satisfied_detected
    - Plan completing both Faculty Req and a minor group reflects count = 2 in P2.
27. group_completion_increases_P2
    - Priority tuple P2 exactly equals len(newly_satisfied_requirement_group_codes).

================================================================================
PART 5: PLAN-LEVEL UNLOCK SIMULATION (Tests 28–34)
================================================================================
28. plan_level_unlock_not_sum_of_individual_unlocks
    - Assert plan unlock count != sum of individual counts when shared downstreams exist.
29. joint_and_interaction_unlock_detected
    - Course requiring X AND Y is unlocked only by plan containing both X and Y.
30. single_course_unlock_triggers_UNLOCKS_FUTURE_COURSES
    - When newly_eligible_count == 1, exactly UNLOCKS_FUTURE_COURSES is emitted.
30. single_course_unlock_triggers_UNLOCKS_FUTURE_COURSE
    - When newly_eligible_count == 1, exactly UNLOCKS_FUTURE_COURSE is emitted.
31. multiple_course_unlock_triggers_UNLOCKS_MULTIPLE_FUTURE_COURSES
    - When newly_eligible_count >= 2, exactly UNLOCKS_MULTIPLE_FUTURE_COURSES is emitted.
32. zero_unlocks_triggers_NO_DIRECT_PREREQUISITE_IMPACT
    - When newly_eligible_count == 0, exactly NO_DIRECT_PREREQUISITE_IMPACT is emitted.
33. unlock_codes_mutually_exclusive
    - Exactly one of the three unlock reason codes is emitted per plan option.
34. already_eligible_course_not_counted_as_unlocked
    - Downstream course that was already ELIGIBLE at baseline is not in newly_eligible list.

================================================================================
PART 6: PLAN RANKING & PRIORITY TUPLE (Tests 35–42)
================================================================================
35. higher_mandatory_count_wins_at_P1
    - Plan with 5 mandatory courses outranks plan with 4 mandatory courses at equal credits.
36. zero_credit_mandatory_course_wins_P1_tie
    - 4 positive + 1 zero-credit required (P1=5) outranks 4 positive required (P1=4).
37. group_completion_wins_at_P2
    - Plan completing a group outranks plan completing no groups at equal P1 and P3.
38. higher_credit_delta_wins_at_P3
    - Plan contributing 15 credits outranks plan contributing 12 credits at equal P1 and P2.
39. higher_unlock_count_wins_at_P4
    - Plan unlocking 4 courses outranks plan unlocking 2 courses at equal P1, P2, P3.
40. higher_budget_utilization_wins_at_P5
    - Plan utilizing 15 credits outranks plan utilizing 12 credits at equal academic factors.
41. lower_individual_rank_sum_wins_at_P6
    - Plan composed of Phase 7 rank #1 and #2 outranks plan composed of #3 and #4.
42. canonical_course_codes_tiebreak_at_P7
    - Two identical plans break tie by ascending alphabetical order of course codes.

================================================================================
PART 7: SEARCH & BOUNDING (Tests 43–47)
================================================================================
43. candidate_window_enforced
    - Candidates beyond top M (e.g. rank > 15) are not evaluated in plan generation.
44. max_options_parameter_limits_output_size
    - If max_options = 3, len(plan_options) <= 3.
45. ranking_metadata_preserved_after_slicing
    - Ranks 1..3 in sliced output maintain exact priority tuples and candidate contents.
46. deterministic_search_order_independent_of_input_shuffling
    - Permuting the input catalog order produces identical plan options.
47. performance_bound_guaranteed
    - Benchmark asserts 15-candidate search executes within < 50 milliseconds.
47. candidate_window_limitation_documented
    - Result limitations include explicit statement that options are bounded to top M candidates.

================================================================================
PART 8: SPECIAL & EDGE CASES (Tests 48–54)
================================================================================
48. no_valid_combination_returns_empty_plan_options
    - When all candidates exceed max_credit_hours, returns 200 OK with plan_options == [].
49. all_plan_courses_completed_returns_empty_plan_options
    - Student who completed all 132 credits receives plan_options == [].
50. single_eligible_course_produces_single_course_plan
    - When only 1 course is eligible, a 1-course plan option is returned.
51. max_courses_one_produces_single_course_plans
    - When max_courses = 1, all generated plan options contain exactly 1 course.
52. only_review_required_candidates_returns_empty_plans
    - When remaining incomplete courses are all REVIEW_REQUIRED, plan_options == [].
53. cross_user_isolation_preserved
    - Planning for User B never reads User A profile, attempts, or exclusions.
53. database_integrity_error_maps_to_500
    - Corrupt study plan data raises ProgressIntegrityError mapping to HTTP 500.
54. determinism_repeated_executions_identical
    - Executing planner 5 times on identical inputs yields byte-identical results.
```

---

## 20. Summary of Authoritative Decisions
## 20. Summary of Authoritative Architectural Decisions

| # | Topic | Final Authoritative Decision |
|:---:|---|---|
| **1** | **Planning Horizon** | Strictly defined as **Next Registration Set**. Current `IN_PROGRESS` courses are excluded and do not consume planned credit ceiling. |
| **2** | **`max_credit_hours` Requiredness** | **Required** in pure engine and future API. Prevents unbounded search space. |
| **2** | **`max_credit_hours` Requiredness** | **Required** parameter in pure engine and future API. Prevents unconstrained search. |
| **3** | **`max_credit_hours = 0` Decision** | **Valid**. Enables students to intentionally plan zero-credit mandatory courses alone. |
| **4** | **`max_courses` Existence** | **Exists** as an explicit constraint parameter. |
| **5** | **`max_courses` Optionality** | **Optional** (`int | None`, default `None`). |
| **6** | **Search Strategy** | **Deterministic Bounded Search** using Depth-First Branch-and-Bound with credit and course pruning. |
| **7** | **Candidate Search Window ($M$)** | Fixed default **$M = 15$** from Phase 7 `ranked_recommendations`. Safe and sub-50ms. |
| **5** | **`max_courses` Optionality** | **Optional** (`int \| None`, default `None`). |
| **6** | **Search Strategy** | **Deterministic Depth-First Branch-and-Bound** with credit and course count pruning. |
| **7** | **Candidate Search Window ($M$)** | Fixed default **$M = 15$** from Phase 7 `ranked_recommendations` (MVP computation configuration). |
| **8** | **`max_options` ($K$)** | Engine default **$K = 5$** (API allowable $1 \le K \le 10$). |
| **9** | **Priority Tuple** | Exact 7-tuple: $(P_1 \text{ mandatory count}, P_2 \text{ group completion}, P_3 \text{ credit delta}, P_4 \text{ unlock count}, P_5 \text{ budget utilization}, P_6 \text{ rank sum}, P_7 \text{ course tuple})$. |
| **10** | **Budget Utilization Position** | Placed late at **$P_5$**. User preference must never override academic progress milestones. |
| **11** | **Phase 7 Rank Aggregation** | Placed at **$P_6$** as sum of individual 1-based ranks (lower is better). |
| **11** | **Phase 7 Rank Aggregation** | Placed at **$P_6$** as sum of individual 1-based ranks (lower sum is better). |
| **12** | **Group Completion vs Credit Delta** | **$P_2$ before $P_3$**. Completely satisfying a requirement group outranks raw credit accumulation. |
| **13** | **Unlock Impact vs Credit Delta** | **$P_3$ before $P_4$**. Degree progress toward 132 credits outranks forward unlocking. |
| **14** | **Course Ordering Inside Plan** | Ordered by `display_order` ascending, then `course_code` ascending. |
| **15** | **Reason Code Set** | Exactly 10 stable, machine-readable reason codes (Section 15). |
| **15** | **Reason Code Set** | Exactly 10 stable, machine-readable reason codes aligned with Phase 7 unlock semantics (Section 15). |
| **16** | **API Route & Method** | `POST /api/v1/me/semester-plans` (stateless computation, zero persistence). |
| **17** | **Review-Required Context** | Included as top-level `review_required_courses` list (never in plan options). |
| **18** | **In-Progress Context** | Included as top-level `excluded_in_progress` list (never in plan options). |
| **19** | **Planner Policy Version** | `SEMESTER_PLANNER_POLICY_VERSION = "1.0"`. |
| **20** | **Planning Scope Marker** | Top-level structured field `planning_scope = "ACADEMIC_STRUCTURE_ONLY"`. |

