# Phase 9.2 — Pure Degree Path Engine Validation (Correction Pass)

**Status**: VALIDATED  
**Date**: 2026-09-17  
**Policy Version**: `1.0`  
**Planning Scope**: `MODELED_DEGREE_PATH_ONLY`  

---

## 1. Executive Summary

Phase 9.2 delivers the **Pure Multi-Semester Degree Path Planning Engine** (`plan_degree_paths`) for Morshidi (مرشدي). The engine explores possible academic trajectories across future semesters using deterministic beam search over Phase 8 (`plan_semester`), Phase 7 (`recommend_courses`), Phase 6 (`calculate_academic_progress`), and Phase 5 (`CanTakeCatalog`).

This document records the results of the **Phase 9.2 Correction Pass**, confirming 100% compliance with the accepted Phase 9.1 specification (`docs/degree-path-planner-policy-spec.md`):
- **Exact Reason Codes**: 100% alignment with Phase 9.1 §26 vocabulary.
- **Exact Academic State Key**: $\text{AcademicStateKey} = (\text{frozenset}(C_{\text{completed\_and\_hypothetical}}), \text{frozenset}(C_{\text{persisted\_in\_progress}}))$.
- **Verified Plan 12 Course Facts**: All canonical names (`0300103 = الإحصاء والاحتمالات`, `1505311 = تعلم الالة`, `1505320 = تعلم الآلة المتقدم`) strictly verified against the academic catalog.
- **Engine-Only Search Configuration**: `beam_width` and `semester_branch_width` are strictly internal engine parameters, NOT user-facing constraints.
- **Exact Ranking Tuples**: Both `FinalPriorityTuple` and `PartialPriorityTuple` match Phase 9.1 §23 and §24 mathematical definitions.
- **Relative Reason Timing**: Assigned over ALL finalized paths before `max_paths` presentation slicing.
- **113 Focused Tests**: All passing in 0.55s. Zero regressions across the full 569 test suite.

---

## 2. Test Execution & Evidence

### 2.1 Degree Path Engine Test Suite
- **Command**: `.venv\Scripts\pytest tests/test_degree_path_engine.py -v` (from `apps/api`)
- **Result**: `113 passed in 0.55s`
- **Exit Code**: `0`

```text
tests/test_degree_path_engine.py::TestConstraints::test_01_valid_default_constraints PASSED
...
tests/test_degree_path_engine.py::TestPolicySpecificationContracts::test_109_path_reason_code_exact_members PASSED
tests/test_degree_path_engine.py::TestPolicySpecificationContracts::test_110_academic_state_key_exact_policy PASSED
tests/test_degree_path_engine.py::TestPolicySpecificationContracts::test_111_dedup_independent_progress_construction PASSED
tests/test_degree_path_engine.py::TestPolicySpecificationContracts::test_112_final_priority_tuple_exact_structure PASSED
tests/test_degree_path_engine.py::TestPolicySpecificationContracts::test_113_partial_priority_tuple_exact_structure PASSED
============================= 113 passed in 0.55s =============================
```

### 2.2 Full Repository Regression Suite
- **Command**: `apps\api\.venv\Scripts\pytest -v` (from repository root)
- **Result**: `569 passed, 10 skipped, 2 warnings in 25.12s`
- **Exit Code**: `0`

Zero regressions across all earlier phases (Phase 1–4 catalogs and database, Phase 5 rules evaluator, Phase 6 academic progress, Phase 7 recommendations, Phase 8 semester planner).

---

## 3. Module Structure & Exports

Encapsulated within `apps/api/app/degree_path/`:

```text
apps/api/app/degree_path/
├── __init__.py       # Public package exports
├── models.py         # Immutable domain models, constraints, enums, exceptions
└── engine.py         # Pure deterministic beam-search degree path planning engine
```

### 3.1 Public API (`__init__.py`)
```python
from app.degree_path.engine import plan_degree_paths
from app.degree_path.models import (
    DEGREE_PATH_POLICY_VERSION,
    PLANNING_SCOPE,
    DEFAULT_BEAM_WIDTH,
    DEFAULT_SEMESTER_BRANCH_WIDTH,
    DEFAULT_CANDIDATE_WINDOW_SIZE,
    MAX_CREDIT_HOURS_PER_SEMESTER_CEILING,
    DegreePathConstraintError,
    DegreePathIntegrityError,
    PathStatus,
    BlockerType,
    PathReasonCode,
    DegreePathConstraints,
    ModeledSemesterEntry,
    DegreePathOption,
    DegreePathResult,
)
```

---

## 4. Exact PathReasonCode Vocabulary (Phase 9.1 §26)

The engine emits strictly and exclusively the 10 machine-readable reason codes defined in Phase 9.1:

```python
class PathReasonCode(str, Enum):
    REACHES_MODELED_PLAN_COMPLETION = "REACHES_MODELED_PLAN_COMPLETION"
    """Path successfully satisfies all modeled study plan requirements under simulation."""

    FEWER_MODELED_SEMESTERS = "FEWER_MODELED_SEMESTERS"
    """Path achieves completion in fewer modeled semesters than competing valid paths."""

    MAXIMIZES_PROGRESS_WITHIN_HORIZON = "MAXIMIZES_PROGRESS_WITHIN_HORIZON"
    """Path achieves the maximal credit and requirement progress within the planning horizon."""

    CONTAINS_MANDATORY_COURSES = "CONTAINS_MANDATORY_COURSES"
    """Path incorporates mandatory study plan courses in its planned semesters."""

    INCLUDES_ZERO_CREDIT_REQUIRED = "INCLUDES_ZERO_CREDIT_REQUIRED"
    """Path schedules required zero-credit courses (e.g. 0200115, 1509999)."""

    COMPLETES_ALL_REQUIREMENT_GROUPS = "COMPLETES_ALL_REQUIREMENT_GROUPS"
    """Path satisfies 100% of the study plan requirement groups."""

    INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE = "INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE"
    """Path includes at least one course previously attempted but not passed."""

    BLOCKED_BY_REVIEW_REQUIRED = "BLOCKED_BY_REVIEW_REQUIRED"
    """Further path progression halted due to courses requiring academic review."""

    BLOCKED_BY_CURRENT_IN_PROGRESS = "BLOCKED_BY_CURRENT_IN_PROGRESS"
    """Path progression halted because remaining courses depend on an active in-progress attempt."""

    NO_VALID_NEXT_SEMESTER = "NO_VALID_NEXT_SEMESTER"
    """Path halted because no valid course combination could be formed under constraints."""
```

Regression test `test_109_path_reason_code_exact_members` asserts this exact set of 10 members.

---

## 5. Academic State Key & Deduplication Policy (Phase 9.1 §20)

### 5.1 Exact State Key
The deduplication key used by the engine is:
$$\text{AcademicStateKey} = \left(\text{frozenset}(C_{\text{completed\_and\_hypothetical}}),\; \text{frozenset}(C_{\text{persisted\_in\_progress}})\right)$$

Derived progress metrics (`remaining_required`, `satisfied_groups`) are deterministic functions of the student's study plan and academic state. They are **NOT** included in the deduplication key, ensuring states with identical completed and in-progress course sets correctly merge into a single canonical representative.

### 5.2 Exact Collision Policy
When two paths produce the same `AcademicStateKey`:
1. **Shallower Depth Wins**: Path reaching the academic state in strictly fewer semesters is retained.
2. **Equal Depth Tiebreaker**: If both paths reach the state at the identical `depth`, the path with the superior `PartialPriorityTuple` wins.
3. **Single Representative Retained**: The winning path remains in the beam; duplicate paths are discarded immediately.
4. **Deduplication Timing**: Deduplication occurs **prior to beam pruning** at each depth.

---

## 6. Real Plan 12 Academic Catalog Facts

All Plan 12 courses used in unit tests and documentation are verified against the authoritative database seeds:

| Course Code | Canonical Arabic Name | Academic Nature / Status |
| :--- | :--- | :--- |
| `0300103` | `الإحصاء والاحتمالات` | **Referenced-only**. External prerequisite for `1505320`. Not selectable; not in plan courses. |
| `0300153` | `اساسيات تكنولوجيا المعلومات` | Faculty Required (3 cr). Prerequisite for `1501110` and `0300220`. |
| `1501110` | `برمجة الحاسوب (1)` | Faculty Required (3 cr). Prerequisite: `0300153`. |
| `1501112` | `برمجة الحاسوب (2)` | Faculty Required (3 cr). Prerequisite: `1501110`. |
| `1501221` | `تراكيب البيانات` | Faculty Required (3 cr). Prerequisite: `1501112`. |
| `0200115` | `تنمية المجتمع والعمل التطوعي` | University Required (**0 cr**). Consumes 0 credit budget; required for degree completion. |
| `1509999` | `حلقة بحث لطلبة كلية تكنولوجيا المعلومات` | Faculty Required (**0 cr**). Consumes 0 credit budget; required for degree completion. |
| `0200110` | `العلوم العسكرية` | University Required (3 cr). |
| `1505311` | `تعلم الالة` | Major Required (3 cr). Prerequisite logic status `unresolved` $\to$ `REVIEW_REQUIRED`. Never silently planned. |
| `1505320` | `تعلم الآلة المتقدم` | Major Required (3 cr). Prerequisite logic status `source_conflict`; raw prerequisites: `0300103, 1505311` $\to$ `REVIEW_REQUIRED`. Never silently planned. |

---

## 7. Engine Configuration vs User Constraints

### 7.1 Separation of Concerns
- **User Planning Constraints (`DegreePathConstraints`)**:
  - `max_credit_hours_per_semester: Decimal`
  - `max_courses_per_semester: int | None = None`
  - `max_semesters_ahead: int = 8`
  - `max_paths: int = 3`
  - **User-facing**: YES (these represent student preferences and are exposed via API in Phase 9.3).

- **Engine Search Configuration (`beam_width`, `semester_branch_width`)**:
  - `DEFAULT_BEAM_WIDTH = 3`
  - `DEFAULT_SEMESTER_BRANCH_WIDTH = 3`
  - **User-facing**: **NO**.
  - These are internal engine parameters controlling the search frontier size and branch branching factor. They are NOT part of `DegreePathConstraints`, NOT exposed in user requests, and remain fixed to default values (3 and 3) in production.

---

## 8. Exact Ranking Tuples

### 8.1 Final Path Ranking Priority Tuple (Phase 9.1 §23)
Final paths are sorted in ascending order of:
$$\text{FinalPriorityTuple} = \left(-\text{completion\_rank},\; \text{semester\_count},\; -\text{completed\_credits\_delta},\; -\text{newly\_satisfied\_groups},\; \text{unresolved\_blocker\_count},\; \text{aggregate\_rank\_sum},\; \text{canonical\_path\_codes}\right)$$

```python
final_priority_tuple = (
    -completion_rank,          # -1 if MODELED_COMPLETE, 0 otherwise
    semester_count,            # Fewer modeled semesters rank higher
    -completed_credits_delta,  # Net degree credits earned across path
    -newly_satisfied_groups,   # Count of newly satisfied requirement groups
    unresolved_blocker_count,  # Fewer blocking conditions rank higher
    aggregate_rank_sum,        # Sum of Phase 8 option ranks across semesters
    canonical_path_codes,      # Alphabetical tuple of course codes across semesters
)
```

### 8.2 Intermediate Partial-Path Ranking Priority Tuple (Phase 9.1 §24)
Partial paths are ranked for beam retention at each depth using:
$$\text{PartialPriorityTuple} = \left(-\text{is\_complete},\; \text{depth},\; -\text{modeled\_credits\_delta},\; -\text{satisfied\_groups\_count},\; \text{blocker\_count},\; \text{aggregate\_rank\_sum},\; \text{canonical\_path\_codes}\right)$$

---

## 9. Relative-Reason Calculation & max_paths Timing

1. **Generation**: The beam search runs until all active paths terminate (reach `MODELED_COMPLETE`, `HORIZON_REACHED`, or a blocker status).
2. **Sort**: All finalized paths known to the bounded search are sorted by `FinalPriorityTuple`.
3. **Relative-Reason Assignment**:
   - `FEWER_MODELED_SEMESTERS` is assigned to complete paths matching `min(semester_count)`. If multiple paths tie, **all** receive the reason code.
   - `MAXIMIZES_PROGRESS_WITHIN_HORIZON` is assigned to incomplete paths matching `max(completed_plan_credit_delta) > 0`. If multiple paths tie, **all** receive the reason code.
   - **Crucial**: This is computed across **ALL** finalized paths in the candidate pool, never restricted to top-K.
4. **Presentation Slicing**:
   - `final_paths = tuple(ranked_options[:constraints.max_paths])` is applied as the final presentation step.
   - Prefix equivalence is preserved: requesting `max_paths=1` returns the exact first element of `max_paths=3`.

---

## 10. Conclusion

Phase 9.2 has undergone an exhaustive correction pass. All enum names, state keys, Plan 12 course labels, ranking tuples, and engine configuration semantics are in exact mathematical alignment with the Phase 9.1 specification.
