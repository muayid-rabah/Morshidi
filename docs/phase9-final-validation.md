# Phase 9 — Comprehensive Degree Path Planner Final Validation

**Phase:** 9.4 — Final Degree Path Planner Audit & Closure  
**Status:** `VALIDATED`  
**Date:** 2026-09-17  
**Policy Version:** `1.0`  
**Planning Scope:** `MODELED_DEGREE_PATH_ONLY`  

---

## 1. Executive Summary & Architecture

Phase 9 designs, implements, validates, and audits the deterministic **Multi-Semester Degree Path Planner Engine** and its authenticated API for Morshidi (مرشدي).

### Core Pipeline & Layered Reuse:
```
Authenticated User (Bearer JWT verified via Supabase server-side /auth/v1/user)
    ↓
StudentService (Orchestration boundary — zero computation/simulation)
    ├── load_student_academic_state (profile facts + persisted attempts) [2 Data API reads]
    ├── load_progress_catalog (study_plans, requirement_groups, study_plan_courses) [3 Data API reads]
    └── load_plan_eligibility_catalog (study_plan_courses, dependency groups/options) [5 Data API reads]
    ↓
Pure Degree Path Planning Engine (plan_degree_paths) [Pure in-memory beam search]
    ├── Baseline: Phase 6 calculate_academic_progress (Zero-semester complete check)
    └── Beam Search Loop (Depth d = 0 .. max_semesters_ahead):
         ├── State Recomputation: Phase 7 recommend_courses (Fresh ranking for state attempts)
         ├── Step Combination: Phase 8 plan_semester (Branching width W=3, candidate window M=15)
         ├── Transition: Synthesize in-memory PASSED attempts for selected courses
         ├── Progress Advancement: Phase 6 calculate_academic_progress (Verify strict monotonicity)
         ├── Academic State Key Collision & Deduplication (Shallower depth / partial priority tiebreak)
         └── Beam Pruning (Keep top B=3 partial paths by PartialPriorityTuple)
    ↓
Post-Processing & Lexicographic Ranking:
    ├── Blocker Diagnostic Classification (Strictly evidence-based from Phases 5–8)
    ├── Lexicographic Sorting across all finalized paths by FinalPriorityTuple
    ├── Relative Reason Code Derivation (FEWER_MODELED_SEMESTERS, MAXIMIZES_PROGRESS_WITHIN_HORIZON)
    └── Presentation Truncation (Slice top max_paths options)
    ↓
POST /api/v1/me/degree-paths (FastAPI transport, strict schema validation, extra="forbid")
```

The system deterministically answers:
> *"What sequence of semester course selections over a multi-semester horizon can the student take to advance toward and achieve modeled degree completion under active semester constraints?"*

---

## 2. Phase 9 Milestone Summaries

1. **Phase 9.1 — Degree Path Planning Policy & Search Specification (`docs/degree-path-planner-policy-spec.md`):**  
   Established the multi-semester planning policy, domain models, termination precedence, 7-component priority tuples, deduplication rules, evidence-based blocker diagnostics, and structural search bounds ($B=3$, $W=3$, $H \le 16$).
2. **Phase 9.2 — Pure Degree Path Engine (`apps/api/app/degree_path/engine.py`):**  
   Implemented `plan_degree_paths` as a pure, zero-I/O function re-using Phase 5, Phase 6, Phase 7, and Phase 8. Enforced strict monotonicity, in-memory synthetic attempt accumulation, zero-semester completion shortcut, and exact reason code vocabularies.
3. **Phase 9.3 — Degree Path Service + Authenticated API (`apps/api/app/services/student.py`, `apps/api/app/api/routes/student.py`):**  
   Exposed `POST /api/v1/me/degree-paths` with strict schema validation (`extra="forbid"`), verified server-side authentication, zero-persistence guarantee, and constant-time network architecture (11 Supabase HTTP calls for Zarqa University Plan 12).
4. **Phase 9.4 — Final Degree Path Planner Audit (`docs/phase9-final-validation.md`):**  
   Exhaustive 50-point audit verifying evidence-based diagnostics, regression proofs, canonical Plan 12 facts, test suites (184 focused degree path tests, 640 full suite tests, 11 local Supabase tests), clean database replay, and secret hygiene.

---

## 3. Core Policy, Enums, & Contract Invariants

### 3.1 Policy Metadata
- `DEGREE_PATH_POLICY_VERSION = "1.0"`
- `PLANNING_SCOPE = "MODELED_DEGREE_PATH_ONLY"`

### 3.2 DegreePathConstraints
Client-controlled planning preferences are strictly bounded:
- `max_credit_hours_per_semester`: `Decimal` between `0.00` and `30.00` (float rejected).
- `max_courses_per_semester`: optional `int` between `1` and `10` (or `None`).
- `max_semesters_ahead`: `int` between `1` and `16` (default `8`).
- `max_paths`: `int` between `1` and `10` (default `3`).

Internal search parameters (`beam_width = 3`, `semester_branch_width = 3`, `candidate_window_size = 15`) are engine constants and strictly prohibited from client manipulation.

### 3.3 PathStatus Members & Termination Precedence
When expanding path states, termination precedence is strictly enforced:
1. `MODELED_COMPLETE`: All modeled study plan requirements satisfied (`all_modeled_plan_requirements_satisfied == True`).
2. `HORIZON_REACHED`: Depth reached `max_semesters_ahead` without full plan completion.
3. `BLOCKED_BY_REVIEW_REQUIRED`: When depth < horizon, no valid next plan exists, and remaining unsatisfied requirements include courses requiring academic review.
4. `BLOCKED_BY_CURRENT_IN_PROGRESS`: When depth < horizon, no valid next plan exists, and remaining unsatisfied requirements depend on active persisted in-progress attempts.
5. `NO_VALID_NEXT_PLAN`: When depth < horizon, no course combinations fit constraints and no specific review/in-progress blocker accounts for the stoppage.

### 3.4 BlockerType Diagnostic Vocabulary
Diagnostic codes emitted in `unresolved_blocker_codes`:
- `REVIEW_REQUIRED_BLOCKER`
- `CURRENT_IN_PROGRESS_BLOCKER`
- `PREREQUISITES_LOCKED`
- `PLAN_CONSTRAINTS_TOO_RESTRICTIVE`
- `CANDIDATE_WINDOW_EXCLUSION`

### 3.5 PathReasonCode Members
Machine-readable reason codes assigned to paths:
- `REACHES_MODELED_PLAN_COMPLETION`
- `FEWER_MODELED_SEMESTERS`
- `MAXIMIZES_PROGRESS_WITHIN_HORIZON`
- `CONTAINS_MANDATORY_COURSES`
- `INCLUDES_ZERO_CREDIT_REQUIRED`
- `COMPLETES_ALL_REQUIREMENT_GROUPS`
- `INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE`
- `BLOCKED_BY_REVIEW_REQUIRED`
- `BLOCKED_BY_CURRENT_IN_PROGRESS`
- `NO_VALID_NEXT_SEMESTER`

---

## 4. Search Algorithm, State Representation, & Ranking

### 4.1 Academic State Key & Monotonicity
The state of each path node is indexed by:
$$\text{AcademicStateKey} = \left(\text{frozenset}(\text{passed\_and\_hypothetical\_codes}),\; \text{frozenset}(\text{persisted\_in\_progress\_codes})\right)$$
- **Strict Monotonicity:** Every valid child transition must satisfy $\text{child\_passed\_set} \supset \text{parent\_passed\_set}$. Transitions that do not strictly add new completed courses trigger a `DegreePathIntegrityError`.
- **Zero-Credit Progression:** Zero-credit required courses (`0200115`, `1509999`) consume 0 credit budget but advance course completion and requirement group satisfaction without violating monotonicity.

### 4.2 Deduplication Collision Policy
Before beam pruning at depth $d$, child states are grouped by `AcademicStateKey`:
1. **Shallower Depth Wins:** If an identical state key was reached at a strictly shallower depth $d' < d$, the deeper child is pruned.
2. **Priority Tiebreak:** If identical state keys occur at the same depth, the child with the lexicographically superior `PartialPriorityTuple` is retained.
3. Exactly one canonical state survives per unique state key.

### 4.3 Priority Tuples
**Partial Priority Tuple (Intermediate Beam Selection — Ascending):**
$$\text{PartialPriorityTuple} = (-\text{is\_complete},\; \text{depth},\; -\Delta\text{credits},\; -\Delta\text{groups},\; \text{blocker\_count},\; \text{rank\_sum},\; \text{path\_codes})$$

**Final Priority Tuple (Finalized Option Ranking — Ascending):**
$$\text{FinalPriorityTuple} = (-\text{completion\_rank},\; \text{semester\_count},\; -\Delta\text{credits},\; -\text{newly\_satisfied\_groups},\; \text{blocker\_count},\; \text{rank\_sum},\; \text{path\_codes})$$

### 4.4 Structural Search Bounds
For beam width $B=3$, semester branch width $W=3$, and horizon $H \le 16$:
- **Maximum Parent Expansions:** $\le B \times H = 3 \times 16 = 48$.
- **Maximum Child States Generated:** $\le B \times H \times W = 3 \times 16 \times 3 = 144$.
- Pruning and deduplication ensure search time and memory usage remain tightly bounded and deterministic.

### 4.5 Zero-Semester Modeled Complete
When a student has already completed all modeled requirements upon initial entry:
- Returns immediately without search expansion (`total_parent_states_expanded = 0`).
- Generates exactly one option: `status = MODELED_COMPLETE`, `semester_count = 0`, `semesters = ()`, `reason_codes = (REACHES_MODELED_PLAN_COMPLETION,)`.

---

## 5. Evidence-Based Blocker Diagnostics

Blocker diagnostics are strictly derived from positive mechanical evidence from Phases 5–8; speculative inference and guessing are prohibited:

1. **`REVIEW_REQUIRED_BLOCKER`:** Requires a course in Phase 7 `review_required_courses` that directly belongs to an unsatisfied modeled requirement group.
2. **`CURRENT_IN_PROGRESS_BLOCKER`:** Requires a course in Phase 7 `excluded_in_progress` that belongs to an unsatisfied modeled requirement group.
3. **`PREREQUISITES_LOCKED`:** Requires direct Phase 5 evidence (`Decision.NOT_ELIGIBLE` and `DecisionReason.MISSING_PREREQUISITE_GROUP`) for a course in an unsatisfied modeled requirement group. Never inferred from empty recommendation lists.
4. **`PLAN_CONSTRAINTS_TOO_RESTRICTIVE`:** Requires that ranked recommendations exist, but none individually fit the user's active credit or course limits (`credit_hours > max_credit_hours` or `max_courses < 1`).
5. **`CANDIDATE_WINDOW_EXCLUSION`:** Requires that top-$M$ ($M=15$) recommendations produce no valid plan, but at least one recommendation outside window ($>M$) independently fits constraints.
6. **Omission Policy:** When a blocker condition cannot be proven mechanically, it is omitted. Unresolved blocker codes remain empty rather than speculative.

---

## 6. Canonical Plan 12 Facts Audit

All canonical facts verified against migrations `0001_academic_catalog.sql` through `20260917085254_create_student_academic_profile.sql`:

| Course Code | Canonical Arabic Name | Credits | Classification | Prerequisites / Logic Status | Behavior in Degree Paths |
|---|---|---|---|---|---|
| `0200115` | تنمية المجتمع والعمل التطوعي | 0 | `UNIVERSITY_REQUIRED` | `not_applicable` | 0 credit budget, mandatory, advances progress |
| `1509999` | حلقة بحث لطلبة كلية تكنولوجيا المعلومات | 0 | `FACULTY_REQUIRED` | `not_applicable` | 0 credit budget, mandatory, advances progress |
| `0300103` | الإحصاء والاحتمالات | 3 | `referenced_only` | External course | Accepted in history; never planned in Plan 12 |
| `1505311` | تعلم الالة | 3 | `MAJOR_REQUIRED` | `unresolved` | Review-required; never planned silently |
| `1505320` | تعلم الآلة المتقدم | 3 | `MAJOR_REQUIRED` | `source_conflict` | Review-required; never planned silently |
| `1501321` | تصميم وتحليل الخوارزميات | 3 | `MAJOR_REQUIRED` | `1501221` | Planned after prerequisite chain passes |

**Verified Prerequisite Progression Chain:**
$$\text{0300153 (استدراك حاسوب)} \longrightarrow \text{1501110 (برمجة 1)} \longrightarrow \text{1501112 (برمجة 2)} \longrightarrow \text{1501221 (تراكيب بيانات)} \longrightarrow \text{1501321 (خوارزميات)}$$

---

## 7. Service & API Contract Validation

### 7.1 Service Layer (`StudentService.get_degree_paths`)
- Pure orchestration: loads student profile, loads catalogs, constructs `DegreePathConstraints`, executes `plan_degree_paths`.
- Zero database writes or cache rows.
- Zero ranking or degree path generation duplicated in service.

### 7.2 API Schema (`DegreePathRequest`)
- Strict `extra="forbid"`: rejects unapproved keys (`owner_user_id`, `study_plan_id`, `attempts`, `beam_width`, `semester_branch_width`, `candidate_window_size`).
- Only 4 client-facing parameters accepted:
  1. `max_credit_hours_per_semester`
  2. `max_courses_per_semester`
  3. `max_semesters_ahead`
  4. `max_paths`

### 7.3 OpenAPI & HTTP Statuses
- `POST /api/v1/me/degree-paths` documented in OpenAPI schema.
- All valid modeled search outcomes return `HTTP 200 OK` with detailed status.
- Standard typed exceptions: `401 Unauthorized`, `404 Not Found`, `422 Unprocessable Entity`, `500 Internal Server Error`, `503 Service Unavailable`.

### 7.4 Fresh Static Network Count Verification
For an authenticated Plan 12 request:
1. **Auth:** 1 call (`GET /auth/v1/user` via server-side bearer verification).
2. **Student Academic State:** 2 Data API reads (`student_academic_profiles`, `student_course_attempts`).
3. **Progress Catalog:** 3 Data API reads (`study_plans`, `requirement_groups`, `study_plan_courses`).
4. **Eligibility Catalog:** 5 Data API reads (`study_plan_courses`, `course_dependency_groups` $\times 2$ chunks, `course_dependency_options` $\times 2$ chunks).
- **Total:** Exactly **11 Supabase HTTP calls** (1 Auth + 10 Data API).
- **$O(1)$ Network Invariance:** Network requests are strictly constant with respect to horizon length, beam states, branching width, and candidate counts.

---

## 8. Verification & Test Suite Execution

### 8.1 Focused Degree Path Test Suites
```powershell
apps\api\.venv\Scripts\pytest.exe apps/api/tests/test_degree_path_engine.py apps/api/tests/test_degree_path_service.py apps/api/tests/test_degree_path_api.py -v
```
**Results:**
- `test_degree_path_engine.py`: **119 passed**
- `test_degree_path_service.py`: **14 passed**
- `test_degree_path_api.py`: **51 passed**
- **Total Focused:** **184 passed, 0 failed**. Warning totals and durations are environment- and run-specific and are not product invariants.

### 8.2 Full Test Suite Execution
```powershell
apps\api\.venv\Scripts\pytest.exe apps/api/tests/ -v
```
**Results:**
- **640 passed, 11 skipped**. Warning totals and durations are environment- and run-specific and are not product invariants.
- **Skipped Test Explanation:** Exactly 11 tests across 8 `*_local_supabase.py` files skipped when local Supabase integration environment variables are not supplied.

### 8.3 Local Supabase Integration Execution
With `MORSHIDI_LOCAL_SUPABASE_*` and `SUPABASE_*` variables configured:
```powershell
apps\api\.venv\Scripts\pytest.exe apps/api/tests/ -k "local_supabase" -v
```
**Results:**
- **11 passed, 0 failed, 0 skipped, 640 deselected in 303.96s (0:05:03)**
- Real Plan 12 degree path E2E (`test_degree_path_local_supabase.py`): **1 passed, 0 skipped** (16 scenarios verified end-to-end against live Postgres).

### 8.4 Clean Database Replay
```powershell
supabase db reset --local --no-seed
```
- Recreated database and schema from scratch.
- Applied all 5 migrations in order (`0001_academic_catalog.sql` through `20260917085254_create_student_academic_profile.sql`).
- Clean exit code 0; zero database drift.

### 8.5 Python Compilation & Secret Scan
- `py_compile` succeeded across all 11 degree-path source and test files (`PY_COMPILE_EXIT=0`).
- Secret scan (`git grep "eyJhbGci"`) confirmed zero literal JWT tokens or credentials committed to repository.

---

## 9. Known Limitations & Non-Goals

1. **Exploratory Simulation Assumption:** Selected courses in future semesters are assumed to pass with `AttemptOutcome.PASSED` at semester conclusion. This is an exploratory simulation assumption, not an outcome prediction.
2. **Current In-Progress Conservative Non-Resolution:** Persisted `IN_PROGRESS` courses are treated as unresolved and never satisfy downstream prerequisites during degree path simulation.
3. **Bounded Search Pruning:** Beam search ($B=3$) prunes partial paths; results are deterministic and bounded, not guaranteed globally optimal across unexamined branches.
4. **Candidate Window Bounding:** Single-semester steps inherit Phase 8 top-$M=15$ candidate window bounding.
5. **No Timetable or Offering Model:** Course availability, seasonal offering patterns, section capacities, instructor preferences, workload or difficulty estimates, and weekly timetable conflicts are not modeled.
6. **No GPA or Grade Prediction:** Cumulative GPA, academic standing, and future grades are not forecast or predicted.
7. **No Official Graduation Clearance or Registration Guarantee:** Degree path options do not predict or guarantee an official graduation date, institutional graduation clearance, or registration approval.
8. **Prerequisite Review Requirement:** Courses with unresolved or conflicting prerequisite sources require institutional academic review before registration.

---

## 10. Final Acceptance & Sign-off

Phase 9 satisfies all architectural, policy, mathematical, and implementation requirements established in Phase 9.1 through Phase 9.4. The degree path planner is deterministic, monotonic, non-persistent, securely authenticated, and fully verified against real Plan 12 academic data.

**Phase 9 Degree Path Planner: FULLY VALIDATED AND ACCEPTED.**
