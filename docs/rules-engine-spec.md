# Morshidi Rules Engine Specification

## 1. Purpose

This specification defines the first deterministic Morshidi academic decision:
**CAN TAKE**, limited to prerequisite eligibility for a target course in a
specific study plan.

The governing principle is **AI explains; rules decide**. An LLM must never
determine, amend, or infer academic eligibility.

The initial accepted catalog is Zarqa University, Faculty of Information
Technology, Artificial Intelligence, Study Plan 12. It has 68 plan-course
rows: 30 `not_applicable`, 32 `verified`, 4 `unresolved`, and 2
`source_conflict` prerequisite statuses.

## 2. Scope and non-goals

CAN TAKE answers only whether verified **prerequisites** are satisfied. It does
not decide whether a student may register for a section or course attempt.

Out of scope until verified data and a later phase explicitly add them:

- course or semester availability, sections, capacity, and timetable conflicts;
- maximum load, GPA, probation, adviser approval, financial, or registration
  holds;
- repeat-attempt, duplicate-registration, and withdrawal regulations;
- corequisite enforcement, graduation, recommendations, and future planning;
- student persistence, authentication, API implementation, and UI work.

`ELIGIBLE` therefore means *prerequisites satisfied*, not *registration
permitted*.

## 3. Academic safety principles

- The evaluator consumes only a canonical catalog snapshot and student attempt
  input. It performs no database query, web request, model call, or fuzzy/name
  comparison.
- `raw_prerequisite_text` is official provenance and explanation data. It is
  never parsed at runtime to create rules.
- Only `course_dependency_groups` and `course_dependency_options` with a
  verified plan-course prerequisite status are executable rules.
- A missing or incomplete purportedly verified dependency model is not treated
  as satisfied or failed; it produces `REVIEW_REQUIRED`.
- No equivalency, replacement, legacy code, code similarity, or Arabic/English
  name matching is assumed. Future equivalency support may use only explicit,
  verified `course_equivalencies` rows and an explicitly approved mapping rule.
- The same canonical catalog, request, and history must produce the same
  result, independent of time, order of duplicate attempts, randomness, or AI.

## 4. Decision and error model

For a valid selectable target in the requested study plan, `decision` is
exactly one of:

| Decision | Meaning |
| --- | --- |
| `ELIGIBLE` | All applicable, verified prerequisite dependency groups are satisfied. |
| `NOT_ELIGIBLE` | At least one applicable, verified dependency group is unsatisfied. |
| `REVIEW_REQUIRED` | The catalog does not establish enough verified prerequisite logic to decide safely. |

Malformed or unsupported target requests are not academic decisions. They use
a separate `kind: "error"` response so `REVIEW_REQUIRED` is never overloaded
to mean invalid input.

## 5. Canonical input contract

The pure engine receives already-resolved canonical data, not Supabase client
objects or authenticated user data.

```text
CanTakeRequest
  study_plan_id: string
  target_course_code: string
  student_attempts: StudentCourseAttempt[]

StudentCourseAttempt
  course_code: string
  outcome: PASSED | FAILED | IN_PROGRESS | WITHDRAWN

CanTakeCatalog
  study_plan_id: string
  plan_courses: PlanCourseRule[]
  courses_by_code: CourseIdentity[]
```

`course_code` remains text, preserving leading zeroes. `study_plan_id` is the
initial external plan selector because no stable public university/major code
exists in the current catalog. The target is addressed by its stable academic
course code. A future API may add a verified public plan key without changing
the pure evaluator.

`StudentCourseAttempt` intentionally has no student ID, grade, term, date, or
database ID. Those facts are not needed for completion-based prerequisite
evaluation. The four outcomes distinguish the minimum facts needed today:

- `PASSED` is a positively completed qualifying attempt.
- `FAILED`, `IN_PROGRESS`, and `WITHDRAWN` are non-qualifying attempts.

Input validation rejects empty/non-text course codes and outcomes outside this
closed contract. Duplicate attempt records are allowed and do not alter the
answer: a prerequisite is satisfied if **at least one** exact-code attempt is
`PASSED`.

## 6. Target-course validation

The repository/catalog adapter must resolve the requested study plan first,
then resolve the target course code within its `study_plan_courses` membership.

| Condition | Response |
| --- | --- |
| Study plan missing or unsupported | error `STUDY_PLAN_NOT_FOUND` |
| Course code does not exist at the university | error `TARGET_NOT_FOUND` |
| Course exists but is not a member of the selected plan, including a `referenced_only` course | error `TARGET_NOT_IN_STUDY_PLAN` |
| Course exists in a different plan but not the selected plan | error `TARGET_NOT_IN_STUDY_PLAN` |
| Course is a selected plan member | evaluate prerequisite eligibility |

Referenced-only courses can be dependencies, but are never valid CAN TAKE
targets unless a future verified plan membership is added.

## 7. Student-history and target-attempt semantics

The evaluator creates two independent target facts from the supplied history:

```text
target_attempt_state
  has_passed_target: boolean
  has_in_progress_target: boolean
```

These facts are returned even for `not_applicable` targets. They do **not**
change a prerequisite decision and do not authorize or deny a duplicate
registration. Repeat and concurrent-registration policy is not yet verified.

For dependency satisfaction, only `PASSED` counts. `FAILED`, `IN_PROGRESS`,
and `WITHDRAWN` never satisfy a completion-based prerequisite. A later passed
attempt satisfies the prerequisite even if earlier attempts failed or were
withdrawn.

## 8. `prerequisite_logic_status` behavior

| Status | Engine behavior |
| --- | --- |
| `not_applicable` | Return `ELIGIBLE` with `NO_PREREQUISITES`; still return target-attempt facts. |
| `verified` | Evaluate only persisted prerequisite dependency groups/options. |
| `unresolved` | Return `REVIEW_REQUIRED` with `PREREQUISITE_LOGIC_UNRESOLVED`; do not parse raw text. |
| `source_conflict` | Return `REVIEW_REQUIRED` with `PREREQUISITE_SOURCE_CONFLICT`; do not infer a replacement or equivalency. |

The present unresolved targets are `0200105`, `0200106`, `1505311`, and
`1505461`. The source-conflict targets are `1505320` and `1505366`.

## 9. Dependency evaluation algorithm

For a `verified` target, load only `dependency_type = prerequisite` rows from
the canonical plan snapshot.

1. Confirm that at least one dependency group exists and every group has one
   or more options. Otherwise return `REVIEW_REQUIRED` with
   `VERIFIED_PREREQUISITE_MODEL_INCOMPLETE`.
2. Sort groups by `group_number` and options by stable course code for stable
   output.
3. For each group, an option is satisfied if a student attempt with exactly the
   option course code has outcome `PASSED`.
4. A group is satisfied if **any** option is satisfied (OR).
5. The target is `ELIGIBLE` only when **all** groups are satisfied (AND).
6. If one or more groups are unsatisfied, return `NOT_ELIGIBLE` and include
   each missing group with all of its allowed option codes.

The current Plan 12 catalog has 32 verified single-option structures. The
algorithm remains generic: a future verified group can represent
`(A OR B) AND C` without engine changes.

The evaluator must never use `raw_prerequisite_text` to override, supplement,
or contradict persisted dependency rows.

## 10. Referenced-only and equivalency behavior

A `referenced_only` course is a valid dependency identity. If a future
verified dependency points to it and student history contains an exact-code
`PASSED` attempt, the generic algorithm can satisfy that option. Its absence
from the selected plan does not invalidate it as a prerequisite.

The current source-conflict rows remain `REVIEW_REQUIRED`, so this capability
does not activate an inferred interpretation for `0300103` or `0301241`.
There are currently zero equivalencies. In particular, the engine must not
assume either `0300103 = 0300104` or `0301241 = 0301245`.

## 11. Structured output contract

```text
CanTakeResponse = CanTakeDecision | CanTakeError

CanTakeDecision
  kind: "decision"
  decision: ELIGIBLE | NOT_ELIGIBLE | REVIEW_REQUIRED
  study_plan_id: string
  target_course_code: string
  prerequisite_logic_status: not_applicable | verified | unresolved | source_conflict
  target_attempt_state:
    has_passed_target: boolean
    has_in_progress_target: boolean
  satisfied_dependency_groups: DependencyGroupEvidence[]
  missing_dependency_groups: DependencyGroupEvidence[]
  reasons: DecisionReason[]
  review_reasons: ReviewReason[]
  explanation_data:
    raw_prerequisite_text: string | null
    target_name_ar: string | null

CanTakeError
  kind: "error"
  error_code: RequestErrorCode
  study_plan_id: string | null
  target_course_code: string | null
```

`DependencyGroupEvidence` contains `group_number`, `dependency_type`, and a
stable list of option course codes split into passed and not-passed evidence.
It supplies presentation data only; the core engine contains no Arabic UI
copy.

## 12. Stable codes

Decision reasons:

- `NO_PREREQUISITES`
- `PREREQUISITES_SATISFIED`
- `MISSING_PREREQUISITE_GROUP`
- `PREREQUISITE_LOGIC_UNRESOLVED`
- `PREREQUISITE_SOURCE_CONFLICT`
- `VERIFIED_PREREQUISITE_MODEL_INCOMPLETE`
- `TARGET_ALREADY_COMPLETED`
- `TARGET_CURRENTLY_ENROLLED`

`TARGET_ALREADY_COMPLETED` and `TARGET_CURRENTLY_ENROLLED` are facts attached
to the response, not duplicate-registration rulings.

Request/domain error codes:

- `INVALID_REQUEST`
- `STUDY_PLAN_NOT_FOUND`
- `TARGET_NOT_FOUND`
- `TARGET_NOT_IN_STUDY_PLAN`

## 13. Database, repository, and module boundaries

```text
Supabase catalog repository
  -> canonical catalog mapper
  -> pure can-take evaluator
  -> structured decision/error result
  -> backend API adapter
  -> frontend renderer
```

Proposed future modules, not implementation work in this phase:

- `catalog_repository`: retrieves a consistent study-plan snapshot from the
  catalog tables and enforces repository ownership boundaries.
- `catalog_mapper`: converts UUID-based database rows to code-keyed canonical
  rules input, including dependency groups/options and status.
- `can_take_evaluator`: pure deterministic function over `CanTakeCatalog` and
  `CanTakeRequest`.
- `can_take_contracts`: shared input, output, and reason-code definitions.
- `eligibility_api`: validates transport/auth concerns, invokes the evaluator,
  and maps the result to an HTTP response.
- `eligibility_presenter`: future Arabic UI explanation layer that renders
  structured data without making decisions.

## 14. Proposed API boundary

No route is implemented in this phase. The proposed HTTP shape is:

```text
POST /api/v1/eligibility/can-take

Request
  study_plan_id
  target_course_code
  student_attempts[]

Response
  CanTakeDecision | CanTakeError
```

The backend, not the frontend, loads the canonical catalog and runs the pure
evaluator. Browser code may render reason codes and evidence but must never
calculate eligibility or substitute cached catalog logic for the backend.

## 15. Deterministic guarantees

For identical canonical catalog data, target, and attempt list, the evaluator
returns an identical structured result. It has no current-time dependency,
randomness, side effect, network operation, model call, external search, or
semantic matching. Ordering of equivalent duplicate attempts is immaterial.

## 16. Specification test matrix

| # | Case | Expected result |
| ---: | --- | --- |
| 1 | `not_applicable` target, no target attempt | `ELIGIBLE` + `NO_PREREQUISITES` |
| 2 | Verified single prerequisite, passed | `ELIGIBLE` |
| 3 | Verified single prerequisite, failed | `NOT_ELIGIBLE` |
| 4 | Verified single prerequisite absent from history | `NOT_ELIGIBLE` |
| 5 | Verified prerequisite only in progress | `NOT_ELIGIBLE` |
| 6 | Verified prerequisite withdrawn | `NOT_ELIGIBLE` |
| 7 | Multiple attempts: failed then passed | prerequisite satisfied |
| 8 | Duplicate passed attempts | same deterministic result as one passed attempt |
| 9 | Unresolved target | `REVIEW_REQUIRED` + unresolved reason |
| 10 | Source-conflict target | `REVIEW_REQUIRED` + source-conflict reason |
| 11 | Missing target code | `TARGET_NOT_FOUND` error |
| 12 | Referenced-only course requested as target | `TARGET_NOT_IN_STUDY_PLAN` error |
| 13 | Course existing only in another plan | `TARGET_NOT_IN_STUDY_PLAN` error |
| 14 | Referenced-only dependency, verified structure, passed exact code | option may satisfy |
| 15 | Future OR group, one option passed | group satisfied |
| 16 | Future OR group, no option passed | group missing |
| 17 | Future multiple AND groups, all satisfied | `ELIGIBLE` |
| 18 | Future multiple AND groups, one missing | `NOT_ELIGIBLE` |
| 19 | Verified target with no group/option data | `REVIEW_REQUIRED` + model-incomplete reason |
| 20 | Raw text contradicts/extends dependency rows | raw text does not change decision |
| 21 | No explicit equivalency row | no code replacement or name matching |
| 22 | Target already passed | prerequisite decision plus `TARGET_ALREADY_COMPLETED` fact |
| 23 | Target currently in progress | prerequisite decision plus `TARGET_CURRENTLY_ENROLLED` fact |
| 24 | Same logical attempts in a different input order | identical result |
| 25 | Unknown attempt outcome or empty code | `INVALID_REQUEST` error |
| 26 | Current `1505320` and `1505366` cases | no inferred equivalency; `REVIEW_REQUIRED` |

## 17. Known limitations and future extensions

This specification deliberately does not determine the meaning of
comma-separated unresolved prerequisite text. It also does not determine
duplicate-registration policy, concurrent prerequisite policy, grades/minimum
grades, term availability, or any registration hold.

Future extensions may add persisted student records, verified corequisite
semantics, explicit verified equivalencies, grade thresholds, repeat policy,
and registration constraints. Each extension must add verified data, explicit
contract semantics, pure-engine tests, and a separate review; it must not
reinterpret existing raw text or change this engine through AI inference.
