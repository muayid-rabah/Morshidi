# Morshidi Recommendation Policy & Scoring Specification

## Document status

Phase: 7.1 — Recommendation Policy & Scoring Specification  
Status: SPECIFICATION ONLY — no implementation  
Policy version: `1.0`  
Date: 2026-09-17  

---

## 1. Purpose

This specification defines the deterministic policy by which Morshidi decides
which incomplete plan courses a student **SHOULD CONSIDER taking next**, and
how those courses are ranked.

Phase 5 already answers: **CAN TAKE?** (prerequisite eligibility)  
Phase 7 answers: **SHOULD TAKE?** (degree-progress recommendation)

These are distinct questions with distinct answer contracts. Phase 7 is a
transparent, deterministic recommendation layer built exclusively on verified
academic facts and the student's current academic state. It never overrides
the eligibility engine and never makes registration decisions.

The governing principle remains: **AI explains — Rules decide.**

---

## 2. Scope

In scope for Phase 7.1 (this specification):

- Candidate universe definition
- Exclusion and filtering rules
- Recommendation factors, individually specified
- Ranking strategy selection and justification
- Scoring/priority tuple definition
- Reason-code vocabulary
- Result and response model contracts
- Pure engine and service architecture
- Future API shape
- Performance strategy
- Auditability requirements
- Safety language requirements
- Edge cases
- Complete test matrix
- Real Plan 12 examples using verified repository data
- Known limitations

---

## 3. Non-goals

The following are explicitly outside the scope of Phase 7 and this
specification:

- Semester schedule generation or credit-load optimization
- Timetable conflict solving
- Section or seat availability filtering
- Instructor or professor ranking
- Course difficulty or workload prediction
- GPA impact prediction
- Career-based specialization ranking
- Any form of AI, ML, collaborative filtering, or probabilistic scoring
- Official registration guarantee or approval
- Transfer credit, course equivalency, or substitution evaluation
- Repeat-course policy enforcement
- Graduation clearance determination
- Any modification to Phase 5 eligibility semantics
- Any modification to Phase 6 progress semantics
- Any new database tables, migrations, or RLS changes
- Any new Python modules, API routes, or frontend changes in this phase

---

## 4. CAN TAKE vs SHOULD TAKE

### 4.1 CAN TAKE (Phase 5)

**Question:** Are this student's verified prerequisite dependencies satisfied
for this course in their study plan?

**Source:** Phase 5 Rules Engine — `evaluate_can_take()`

**Possible decisions:**
- `ELIGIBLE` — all verified prerequisite dependency groups are satisfied
- `NOT_ELIGIBLE` — at least one verified dependency group is unsatisfied
- `REVIEW_REQUIRED` — prerequisite logic is unresolved or has a source conflict

`ELIGIBLE` means *prerequisites satisfied*, not *registration permitted*.

### 4.2 SHOULD TAKE (Phase 7)

**Question:** Among eligible candidates, how useful is this course toward the
student's modeled degree progress?

**Source:** Phase 7 Recommendation Engine — deterministic, built on top of
Phase 5 and Phase 6 engines.

**Fundamental constraint:** The recommendation engine **never transforms**:

```
NOT_ELIGIBLE → recommended
REVIEW_REQUIRED → eligible
```

Phase 5 eligibility is the hard gate through which every candidate must pass
before entering recommendation ranking.

---

## 5. Candidate Universe

### 5.1 Definition

A course enters the recommendation candidate set if and only if all of the
following conditions are true:

1. The course is an actual `StudyPlanCourse` in the student's selected Study
   Plan (i.e., a plan member, not a referenced-only course).
2. The course is **not** in state `COMPLETED` (Phase 6 progress semantics).
3. The course is **not** in state `IN_PROGRESS` (Phase 6 progress semantics).
4. The Phase 5 decision for this course is `ELIGIBLE`.

### 5.2 Course-state mapping

Per Phase 6 progress semantics:

```
COMPLETED        → EXCLUDED (course already passed; no need to recommend)
IN_PROGRESS      → EXCLUDED (already being taken this period)
ATTEMPTED_NOT_COMPLETED → MAY BE CANDIDATE if Phase 5 says ELIGIBLE
NOT_ATTEMPTED    → MAY BE CANDIDATE if Phase 5 says ELIGIBLE
```

### 5.3 What is excluded

| Condition | Disposition |
| --- | --- |
| `referenced_only` course (not a plan member) | Not a candidate; ineligible as Phase 5 target |
| `COMPLETED` plan course | Excluded |
| `IN_PROGRESS` plan course | Excluded |
| Phase 5 decision `NOT_ELIGIBLE` | Excluded from ranking; may be shown separately as informational |
| Phase 5 decision `REVIEW_REQUIRED` | Excluded from normal ranking; placed in `review_required_courses` |
| Phase 5 decision is an error (plan/target not found) | Integrity error; not a candidate |

---

## 6. REVIEW_REQUIRED Handling

### 6.1 Policy

Courses receiving `REVIEW_REQUIRED` from Phase 5 **must not** appear in the
normal ranked recommendation list as if they are safe to register.

The current `REVIEW_REQUIRED` plan courses in Plan 12 are:

- `0200105` — مهارات الاتصال والتواصل (اللغة العربية 1) — `PREREQUISITE_LOGIC_UNRESOLVED`
- `0200106` — مهارات الاتصال والتواصل (اللغة الانجليزية 1) — `PREREQUISITE_LOGIC_UNRESOLVED`
- `1505311` — تعلم الالة — `PREREQUISITE_LOGIC_UNRESOLVED`
- `1505461` — الرؤية الحاسوبية — `PREREQUISITE_LOGIC_UNRESOLVED`
- `1505320` — تعلم الآلة المتقدم — `PREREQUISITE_SOURCE_CONFLICT`
- `1505366` — معالجة الصور الرقمية — `PREREQUISITE_SOURCE_CONFLICT`

### 6.2 Separate representation

The recommendation response must expose `review_required_courses` as a
distinct collection. Each entry carries:

- `course_code`
- `course_name_ar`
- `credit_hours`
- `requirement_group_code`
- `requirement_type`
- `review_reason` — the Phase 5 `DecisionReason` code
  (`PREREQUISITE_LOGIC_UNRESOLVED` or `PREREQUISITE_SOURCE_CONFLICT`)
- `previous_attempt_context` — whether the student has any prior history

### 6.3 User-facing context

The engine may attach a stable context note:

> "Academic prerequisite information for this course requires verification
> before a recommendation can be made."

`REVIEW_REQUIRED` courses must not be scored against or ranked alongside
normal `ELIGIBLE` candidates.

---

## 7. NOT_ELIGIBLE Handling

`NOT_ELIGIBLE` courses are excluded from the recommendation ranking.

Future UI may display them separately with:

- the unmet prerequisite group(s) from Phase 5 `missing_dependency_groups`
- stable reason code `MISSING_PREREQUISITES`

This is informational only. They do not receive a recommendation rank or score.

---

## 8. Course-State Handling

### 8.1 ATTEMPTED_NOT_COMPLETED

An `ATTEMPTED_NOT_COMPLETED` course (student has prior `FAILED` or `WITHDRAWN`
attempt, but no `PASSED`) is treated as a normal candidate if Phase 5 says
`ELIGIBLE`.

Previous failure or withdrawal history:

- **does not** automatically penalize the course in ranking
- **does not** automatically boost the course
- **is preserved** as `previously_attempted = true` in result context, for
  future explanation

Rationale: Morshidi does not know why the student failed (difficulty, personal
circumstances, etc.), and no verified academic policy exists to model
failure-based ranking.

### 8.2 History override rule

If a student has a `PASSED` attempt for a course, Phase 6 marks it `COMPLETED`
and it is excluded from candidates. A later `FAILED` attempt after a `PASSED`
does not change `COMPLETED` status (Phase 6 priority: any `PASSED` → `COMPLETED`).
This is correctly handled by Phase 6 before recommendation sees it.

---

## 9. Recommendation Factors

The following factors are computed for each candidate and used in ranking.
All factors are derived exclusively from currently verified model data.

### Factor 1: Is Required Plan Course (boolean)

**Definition:** Is this course in a `requirement_type = required` requirement
group?

**Values:** `true` | `false`

Required courses are mandatory plan components. An incomplete required course
structurally must be completed for degree satisfaction. This factor captures
that structural priority.

This is product recommendation logic. It does not claim official registration
priority or supersede the student's judgment.

**Plan 12 context:** The required groups are:
- UNIVERSITY_REQUIRED (متطلبات الجامعة الإجبارية) — 18 credits
- FACULTY_REQUIRED (متطلبات الكلية الإجبارية) — 21 credits
- SUPPORTING_REQUIRED (المتطلبات المساندة) — 12 credits
- MAJOR_REQUIRED (متطلبات التخصص الإجبارية) — 63 credits

### Factor 2: Requirement Group Still Needs Progress (boolean)

**Definition:** Does the candidate's requirement group currently have
`remaining_required_credits > 0`?

For required groups: Always true while any course or credit requirement is
unmet.

For elective groups: True only while `remaining_required_credits > 0`.

If a University Elective group requires 9 credits and the student already has
9 credited elective hours, additional University Elective candidates receive
`requirement_group_has_remaining_need = false`. They provide no structural
graduation-progress value from this factor.

### Factor 3: Effective Credit Contribution (Decimal)

**Definition:** How many credits can this candidate realistically contribute
toward the group's remaining requirement?

For required groups:
```
effective_contribution = candidate.credit_hours
```
(All credit hours count toward mandatory completion.)

For elective groups:
```
effective_contribution = min(
    candidate.credit_hours,
    group.remaining_required_credits
)
```

**Example — elective group needs 3 more credits, candidate is 3 credits:**
```
effective_contribution = min(3, 3) = 3
```

**Example — elective group needs 1 more credit, candidate is 3 credits:**
```
effective_contribution = min(3, 1) = 1
```

This prevents inflated credit values for oversized elective candidates when
only fractional credits are needed.

**Special case — zero-credit required course:**
A zero-credit required course (e.g. `0200115`, `1509999`) has
`credit_hours = 0` and `effective_contribution = 0`. The effective credit
contribution factor alone would incorrectly give these courses zero ranking
value. Factor 4 compensates explicitly.

### Factor 4: Is Mandatory Zero-Credit Required Course (boolean)

**Definition:** Is this course a required-group course with
`credit_hours = 0`?

**Values:** `true` | `false`

A zero-credit required course (e.g., `0200115 — تنمية المجتمع والعمل التطوعي`,
`1509999 — حلقة بحث لطلبة كلية تكنولوجيا المعلومات`) contributes no credits
but remains a mandatory plan component. A required group whose credit target
is satisfied is still `is_satisfied = false` while zero-credit required
courses remain incomplete (Phase 6 `mandatory_condition` logic).

This factor ensures zero-credit required courses are treated as structurally
important and not discarded by a credit-only ranking.

In the ranking tuple (see Section 17), this factor is incorporated into the
required-course dimension, not as a separate standalone factor. See ranking
policy below.

### Factor 5: Newly Eligible Course Count (integer) — via simulation

**Definition:** How many currently NOT_ELIGIBLE plan courses would become
ELIGIBLE if this candidate were hypothetically passed?

**Method:** Eligibility simulation (defined in Section 13).

**Value:** `newly_eligible_count` — a non-negative integer.

Zero means completing this course does not unlock any additional plan courses.

### Factor 6: Completes Requirement Group (boolean)

**Definition:** Would hypothetically passing this candidate cause the
candidate's requirement group to transition from unsatisfied (`is_satisfied =
false`) to satisfied (`is_satisfied = true`)?

**Method:** Progress simulation (defined in Section 12).

**Value:** `completes_requirement_group` — `true` | `false`.

For required groups, group satisfaction requires both full credit completion
AND completion of all mandatory courses, so this can only be true when the
candidate is the last missing required course or credit.

For elective groups, group satisfaction requires reaching the credit target,
so this is true when the candidate's credit contribution closes the remaining
gap.

---

## 10. Required-Course Logic

A required course that remains incomplete is a mandatory degree component.
The recommendation engine applies a structural priority advantage to required
courses over elective candidates.

A required zero-credit course (`credit_hours = 0`, `requirement_type = required`)
is treated as a mandatory course and must not be discarded or ranked last
purely on the basis of its credit value. It receives a required-course
structural advantage in ranking.

In the scoring tuple, required courses receive the highest boolean dimension,
ensuring they rank above non-required courses with equal downstream impact.

---

## 11. Elective Requirement Logic

### 11.1 Unsatisfied elective group

An elective candidate contributes `requirement_group_has_remaining_need = true`
and a non-zero `effective_contribution` while the group's
`remaining_required_credits > 0`.

### 11.2 Satisfied elective group

**Decision:** When an elective requirement group is already satisfied
(`remaining_required_credits = 0`), additional elective candidates from that
group:

- Receive `requirement_group_has_remaining_need = false`
- Receive `effective_contribution = 0`
- **Are excluded from the default `ranked_recommendations` list**

**Rationale:** Morshidi's recommendation goal is degree-progress support. A
satisfied elective group needs no further completion. Additional courses from
that group provide no modeled graduation-progress value. Including them in
ranked recommendations would imply progress value that does not exist.

These courses remain academically eligible and may still be taken. The engine
may expose them in a separate `zero_value_eligible_courses` collection for
informational purposes if future UI design requires it, but they do not
compete with active progress candidates in the ranked list.

This is a clear MVP policy, not an academic restriction.

### 11.3 Plan 12 elective pools

- University Elective (UNIVERSITY_ELECTIVE): requires 9 credits of 33 credits listed (11 courses × 3 credits)
- Major Elective (MAJOR_ELECTIVE): requires 9 credits of 39 credits listed (13 courses × 3 credits)

Once 9 elective credits are satisfied in either group, remaining elective
options are excluded from ranked recommendations.

---

## 12. Progress-Delta Simulation

### 12.1 Architecture

The progress simulation uses the existing `calculate_academic_progress()` from
`app/progress/engine.py` directly. The recommendation engine does **not**
reimplement progress credit accounting or group satisfaction logic.

### 12.2 Protocol for each candidate

```
current_progress = calculate_academic_progress(
    catalog,
    student_attempts,
    ...reported_facts
)

hypothetical_attempts = student_attempts + (
    StudentCourseAttempt(
        course_code = candidate.course_code,
        outcome = AttemptOutcome.PASSED,
    ),
)

hypothetical_progress = calculate_academic_progress(
    catalog,
    hypothetical_attempts,
    ...reported_facts
)
```

Derived recommendation factors from comparison:

```
group_now    = current_progress.group_result_for(candidate.requirement_group_id)
group_after  = hypothetical_progress.group_result_for(candidate.requirement_group_id)

completes_requirement_group = (
    not group_now.is_satisfied
    and group_after.is_satisfied
)

credited_plan_delta = (
    hypothetical_progress.completed_plan_credits
    - current_progress.completed_plan_credits
)
```

### 12.3 Critical constraint

**Hypothetical `PASSED` attempts used for simulation are never persisted.**
They exist only inside pure in-memory recommendation computation. The
simulation function must not write to any database, repository, or mutable
state.

### 12.4 Idempotency

If the student already has an `IN_PROGRESS` or `ATTEMPTED_NOT_COMPLETED`
attempt for the candidate, the simulation adds a hypothetical `PASSED` attempt.
Because Phase 6 applies priority (any `PASSED` → `COMPLETED`), this is
idempotent: the hypothetical pass correctly overrides all earlier
non-qualifying outcomes.

If the student already has a `PASSED` attempt (i.e., course is `COMPLETED`),
the course would have been excluded from candidates before simulation. This
case should not occur.

---

## 13. Eligibility/Unlock Simulation (Newly Eligible Count)

### 13.1 Authoritative architecture

The `newly_eligible_count` is computed by re-running the Phase 5 rules engine,
not by counting prerequisite option occurrences.

**Why simulation instead of occurrence counting:**

Occurrence counting is incorrect because it ignores AND/OR logic.
Course A appearing as an option in 5 target courses' prerequisites does not
mean passing A makes 5 courses eligible. Each target may have multiple AND
groups that are all unsatisfied.

Simulation automatically respects AND/OR semantics because it delegates to the
existing `evaluate_can_take()` implementation.

### 13.2 Protocol for each candidate

```
remaining_incomplete_plan_courses = [
    course for course in plan_courses
    if course not in completed_set
    and course not in in_progress_set
    and course.course_code != candidate.course_code
]

eligibility_before = {
    course.course_code: evaluate_can_take(catalog, request(course, student_attempts))
    for course in remaining_incomplete_plan_courses
}

hypothetical_attempts = student_attempts + (
    StudentCourseAttempt(candidate.course_code, PASSED),
)

eligibility_after = {
    course.course_code: evaluate_can_take(catalog, request(course, hypothetical_attempts))
    for course in remaining_incomplete_plan_courses
}

newly_eligible_count = count of courses where:
    eligibility_before[code].decision != ELIGIBLE
    and eligibility_after[code].decision == ELIGIBLE
```

### 13.3 AND/OR correctness

This simulation automatically handles AND/OR because `evaluate_can_take()` is
the canonical implementation of Phase 5 dependency evaluation.

**Example:**

Target `1505311 — تعلم الالة` (if it were verified) would require both
`1505101` (Group 1) AND `1505201` (Group 2).

If candidate is `1505101` alone:
- Before: Group 1 unsatisfied, Group 2 depends on state → NOT_ELIGIBLE
- After adding hypothetical `1505101 PASSED`: Group 1 satisfied, but Group 2
  still requires `1505201`. If `1505201` is not passed → still NOT_ELIGIBLE.
- `newly_eligible_count` correctly records 0 for this scenario.

However, since `1505311` is currently `unresolved`, it produces
`REVIEW_REQUIRED` in both before and after states. Unresolved courses are
never counted as newly eligible (see Section 13.4).

### 13.4 Verified-only eligibility comparison

Only plan courses with `prerequisite_logic_status` = `not_applicable` or
`verified` participate in the eligibility-before/after comparison.

Courses with `unresolved` or `source_conflict` produce `REVIEW_REQUIRED` in
both before and after states. They must never count as `newly_eligible`.

A transition from `REVIEW_REQUIRED` to `ELIGIBLE` is impossible through a
hypothetical pass because the evaluator respects the stored
`prerequisite_logic_status` regardless of attempt history.

### 13.5 newly_eligible_course_codes

The engine also returns `newly_eligible_course_codes` — the exact course codes
of newly eligible courses — for explanation and UI use.

### 13.6 Transitive impact decision

**Decision: MVP uses direct unlock simulation only (Phase 5 re-evaluation),
not custom transitive graph traversal.**

**Rationale:**

The simulation protocol described in Section 13.2 already captures a bounded
form of transitive impact because:
- Adding candidate `A` to history
- Re-evaluating all remaining incomplete plan courses
- If `B` becomes eligible after `A`, and `B` is a prerequisite for `C`...
- `C`'s eligibility simulation (done separately for candidate `B`) captures
  that relationship.

When the engine ranks candidate `A`, `newly_eligible_count` reflects all
courses directly unlocked by `A` alone. The *recursive* transitive value
of `A` (what `B` further unlocks after being completed) is not summed into
`A`'s score, which is correct for MVP.

Adding recursive graph traversal in Phase 7 MVP would:
- Require building a custom prerequisite graph (duplicating Phase 5 logic)
- Risk exponential weighting (courses high in a dependency chain would
  dominate even when immediate value is similar)
- Be hard to explain to students

The MVP design is: **`newly_eligible_count` = direct simulation result only.**

Future extensions may add bounded transitive scoring once the engine matures.

---

## 14. AND/OR Prerequisite Correctness

The specification formally recognizes Phase 5 dependency semantics:

```
AND across dependency groups
OR within options inside one group
```

### 14.1 Distinction: dependency contribution vs actual unlock

**Dependency contribution:** The candidate's code appears as an option in some
target's prerequisite group. This alone does not mean the target becomes
eligible after the candidate is passed.

**Actual unlock (newly eligible):** The target transitions from `NOT_ELIGIBLE`
to `ELIGIBLE` after the hypothetical pass of the candidate. This requires ALL
prerequisite groups of the target to be satisfied.

The simulation approach (Section 13) inherently enforces this distinction.
The recommendation engine never counts "dependency contribution" occurrences
as "unlocks."

### 14.2 Example (real Plan 12 data)

Candidate: `1501110 — برمجة الحاسوب (1)` (prerequisite: `0300153`)

Direct unlock targets when `1501110` is hypothetically passed:
- `1501112 — برمجة الحاسوب (2)` has prerequisite `1501110` → becomes
  `ELIGIBLE` after hypothetical pass → counted.
- `1505101 — البرمجة بلغة بايثون` has prerequisite `1501110` → becomes
  `ELIGIBLE` → counted.
- `1506180 — برمجة ويب (1)` has prerequisite `1501110` → becomes
  `ELIGIBLE` → counted.

Also, `1501111 — مختبر برمجة الحاسوب (1)` has prerequisite `0300153`, not
`1501110`. Passing `1501110` does not unlock `1501111` directly. The
simulation correctly computes this.

---

## 15. Ranking Strategy

### 15.1 Weighted score vs Lexicographic — decision

**Decision: Lexicographic priority tuple.**

**Rationale:**

Weighted scoring problems:
- Weights (e.g., required +40, group progress +30) are arbitrary constants
- Small weight changes alter rankings unpredictably
- Hard to explain: "Why did Course A rank above Course B?"
- Cannot easily guarantee required courses always outrank electives

Lexicographic advantages:
- Deterministic: identical catalog + attempts → identical ranking
- Transparent: ranking can be mechanically explained from the tuple
- No arbitrary constants
- Structural priorities (required vs elective) are strict, not relative

---

## 16. Final Scoring/Priority Policy

### 16.1 Ranking tuple

Each candidate is scored by a tuple `T` that is compared lexicographically
(higher values preferred at each position):

```
T = (
    P1: required_mandatory_priority,    # int: 2, 1, or 0
    P2: group_has_remaining_need,       # int: 1 or 0 (boolean as int)
    P3: effective_credit_contribution,  # Decimal (higher is better)
    P4: completes_requirement_group,    # int: 1 or 0 (boolean as int)
    P5: newly_eligible_count,           # int (higher is better)
    P6: tie_breaker_display_order,      # int (lower is better → negate)
    P7: tie_breaker_course_code,        # str (lexicographic ascending)
)
```

**Comparison:** tuples are compared element by element, left to right. The
first dimension where candidates differ determines ranking. Higher values rank
first, except `P6` where lower `display_order` ranks first (negate for
comparison: use `-display_order`).

### 16.2 Dimension definitions

**P1 — `required_mandatory_priority`**

```
2  if requirement_type == REQUIRED and credit_hours > 0
1  if requirement_type == REQUIRED and credit_hours == 0   (zero-credit mandatory)
0  if requirement_type == ELECTIVE
```

Rationale: Required positive-credit courses rank highest. Zero-credit required
courses rank above electives (they remain mandatory plan components) but below
positive-credit required courses within the required tier.

This ensures `0200115` (0 credits, required) outranks any elective regardless
of the elective's credit hours, while a 3-credit required course outranks
`0200115`.

**P2 — `group_has_remaining_need`**

```
1  if group.remaining_required_credits > 0
0  otherwise
```

A candidate whose group is already satisfied provides no further graduation
progress. Candidates in unsatisfied groups are preferred within the same P1
tier.

Note: If P1 = 0 (elective) and P2 = 0 (group already satisfied), the
candidate is excluded from ranked_recommendations entirely (see Section 11.2).
The P2 dimension applies only to candidates that remain in the list.

**P3 — `effective_credit_contribution`**

The capped contribution value per Section 9, Factor 3. Higher is better.

For zero-credit required courses: `effective_contribution = 0`. They are
already protected by P1.

**P4 — `completes_requirement_group`**

```
1  if hypothetical pass satisfies the requirement group (is_satisfied transitions false → true)
0  otherwise
```

A candidate that completes a group is preferred over one that only partially
advances it, within the same P1/P2/P3 tier.

**P5 — `newly_eligible_count`**

Higher is better. Candidates that unlock more future courses are preferred.

**P6 — `-display_order`**

The `display_order` from `study_plan_courses` (plan-seeded integer). Lower
display order means the course appears earlier in the plan's canonical
ordering. Within a tie at P1–P5, use this as the primary catalog tie-breaker.

**P7 — `course_code`**

Lexicographic string comparison (ascending). Final deterministic tie-breaker
for courses with identical display order.

### 16.3 Examples of tuple comparisons

**Example A:** Required 3-credit course with 2 unlocks vs Elective 3-credit:

```
Required course:  T = (2, 1, 3, 0, 2, -46, "1501222")
Elective course:  T = (0, 1, 3, 0, 0, -33, "1501212")
```
→ Required course wins at P1 (2 > 0).

**Example B:** Two required courses, one completes its group:

```
Course X: T = (2, 1, 3, 1, 1, -52, "1505101")
Course Y: T = (2, 1, 3, 0, 1, -53, "1505201")
```
→ Course X wins at P4 (1 > 0).

**Example C:** Zero-credit required vs 3-credit elective:

```
0200115:  T = (1, 1, 0, 0, 0, -6,  "0200115")
Elective: T = (0, 1, 3, 0, 0, -10, "0200113")
```
→ `0200115` wins at P1 (1 > 0). Zero-credit required course correctly
outranks a 3-credit elective despite contributing 0 credits.

---

## 17. Tie-Breaking

Tie-breaking is fully specified by P6 and P7 in the ranking tuple.

**P6:** `-display_order` from `study_plan_courses`. This is the persisted,
stable catalog ordering from the official study plan data. Courses earlier in
the plan's canonical ordering are preferred.

**P7:** `course_code` (ascending lexicographic string comparison). Since
course codes are text and unique within a plan, this guarantees a unique final
rank for every pair of candidates.

Together, P6 and P7 guarantee stable, fully deterministic ranking with no
remaining ties. Ranking is independent of database row order, insertion time,
attempt order, or session state.

---

## 18. Recommendation Tiers/Labels

**Decision: Tiers are not used in MVP.**

**Rationale:**

Tiers like `STRONGLY_RECOMMENDED` / `RECOMMENDED` / `OPTIONAL` are subjective
thresholds. Morshidi does not know personal difficulty, semester workload, or
student preference. Tiers would require arbitrary boundary decisions and create
the appearance of knowledge that does not exist.

The ranking tuple is self-explanatory. The reason codes (Section 19) carry the
human-readable structural explanation without assigning subjective quality
tiers.

If future product requirements introduce tiers, they must be based on verified
academic criteria, not invented thresholds.

---

## 19. Reason Codes

Reason codes are stable machine-readable strings attached to each
recommendation candidate. They explain the factors contributing to the
candidate's structural value. Multiple reason codes may apply.

### 19.1 Vocabulary

| Reason code | Meaning |
| --- | --- |
| `REQUIRED_PLAN_COURSE` | Candidate is in a required requirement group |
| `MANDATORY_ZERO_CREDIT_COURSE` | Required plan course with `credit_hours = 0` |
| `ADVANCES_REQUIRED_GROUP` | Completion contributes credits toward an unsatisfied required group |
| `ADVANCES_ELECTIVE_REQUIREMENT` | Completion contributes credits toward an unsatisfied elective group |
| `COMPLETES_REQUIREMENT_GROUP` | Hypothetical pass satisfies the candidate's requirement group |
| `UNLOCKS_FUTURE_COURSE` | Hypothetical pass makes exactly one other plan course newly eligible |
| `UNLOCKS_MULTIPLE_FUTURE_COURSES` | Hypothetical pass makes two or more plan courses newly eligible |
| `NO_REMAINING_GROUP_NEED` | Candidate's requirement group is already satisfied (elective group only; candidate excluded from ranked list) |
| `PREVIOUSLY_ATTEMPTED` | Student has prior non-passing attempt(s) for this course |
| `NO_DIRECT_PREREQUISITE_IMPACT` | Hypothetical pass does not unlock any currently ineligible plan course |

### 19.2 Application rules

- `REQUIRED_PLAN_COURSE` is applied to any candidate with `requirement_type = required`.
- `MANDATORY_ZERO_CREDIT_COURSE` is applied in addition to `REQUIRED_PLAN_COURSE` when `credit_hours = 0`.
- `ADVANCES_REQUIRED_GROUP` is applied when the course is in a required group with `remaining_required_credits > 0`.
- `ADVANCES_ELECTIVE_REQUIREMENT` is applied when the course is in an elective group with `remaining_required_credits > 0`.
- `COMPLETES_REQUIREMENT_GROUP` is applied when the simulation detects a group satisfaction transition.
- `UNLOCKS_FUTURE_COURSE` is applied when `newly_eligible_count == 1`.
- `UNLOCKS_MULTIPLE_FUTURE_COURSES` is applied when `newly_eligible_count >= 2`.
- `NO_DIRECT_PREREQUISITE_IMPACT` is applied when `newly_eligible_count == 0`.
- `PREVIOUSLY_ATTEMPTED` is applied when `course_state == ATTEMPTED_NOT_COMPLETED`.

Reason codes allow future AI to explain deterministic output, not decide it.

---

## 20. Result Model

### 20.1 RecommendationCandidate

```
RecommendationCandidate:
  course_code:                str          — exact plan course code
  course_name_ar:             str          — Arabic course name from catalog
  credit_hours:               Decimal      — plan credit hours
  requirement_group_code:     str          — group code (e.g. "MAJOR_REQUIRED")
  requirement_type:           "required" | "elective"

  eligibility_decision:       "ELIGIBLE"   — always ELIGIBLE for ranked candidates
  course_state:               CourseProgressState  — ATTEMPTED_NOT_COMPLETED | NOT_ATTEMPTED

  effective_credit_contribution: Decimal   — capped credit contribution value
  completes_requirement_group:   bool      — True if hypothetical pass satisfies group
  group_remaining_credits_before: Decimal  — group remaining before this candidate
  group_remaining_credits_after:  Decimal  — group remaining after hypothetical pass

  newly_eligible_count:       int          — count of courses newly eligible after pass
  newly_eligible_course_codes: list[str]   — exact codes of those courses

  priority_tuple:             tuple        — (P1, P2, P3, P4, P5, P6, P7) for auditability
  rank:                       int          — 1-based rank within ranked_recommendations
  reason_codes:               list[str]    — applicable reason-code vocabulary
  previously_attempted:       bool         — True if course_state == ATTEMPTED_NOT_COMPLETED
```

### 20.2 ReviewRequiredCourse

```
ReviewRequiredCourse:
  course_code:            str
  course_name_ar:         str
  credit_hours:           Decimal
  requirement_group_code: str
  requirement_type:       "required" | "elective"
  review_reason:          str              — Phase 5 DecisionReason code
  previously_attempted:   bool
```

---

## 21. Recommendation Response Model

```
RecommendationResult:
  study_plan_id:              str          — authenticated student's study plan ID
  recommendation_policy_version: str       — "1.0"
  ranked_recommendations:     list[RecommendationCandidate]  — ordered by rank asc
  review_required_courses:    list[ReviewRequiredCourse]
  excluded_in_progress:       list[str]    — course codes currently IN_PROGRESS
  methodology_note:           str          — safety disclaimer (see Section 27)
  limitations:                list[str]    — see Section 31

Notes on fields:

- `ranked_recommendations` contains ALL ranked candidates, not a truncated set.
  API layer may optionally apply `limit`. This preserves auditability.
- `excluded_in_progress` is informational. Students may want to see which
  courses are already counted as in-progress.
- Internal UUIDs (profile_id, attempt_id, group_id) are not exposed.
- `owner_user_id` is never included in any response body.
```

---

## 22. Policy Versioning

**Decision: Policy version is included.**

`recommendation_policy_version = "1.0"` is a constant embedded in the future
recommendation engine module.

**Rationale:**

The recommendation policy may legitimately evolve (new factors, revised
weighting, new tie-breaking). Versioning allows:
- Clients and UI to know which policy produced a result
- Debugging when stored/cached results differ from current behavior
- Future migration of stored recommendations

No database migration is required. The version is a module-level constant
returned in every `RecommendationResult`. When the policy changes materially,
increment the version.

---

## 23. Pure Engine Architecture

### 23.1 Principle

The future recommendation engine must be a pure, deterministic function with
no I/O, framework, AI, database, HTTP, clock, or random dependency.

```python
def recommend_courses(
    progress_catalog: AcademicProgressCatalog,
    can_take_catalog: CanTakeCatalog,          # plan-wide version
    student_attempts: tuple[StudentCourseAttempt, ...],
    *,
    reported_cumulative_gpa: Decimal | None = None,
    reported_gpa_scale: Decimal | None = None,
    reported_earned_credit_hours: Decimal | None = None,
) -> RecommendationResult:
    ...
```

The engine:
1. Calls `calculate_academic_progress()` for current state
2. Filters and identifies eligible candidates
3. For each candidate: runs progress simulation and eligibility simulation
4. Computes priority tuple for each candidate
5. Sorts candidates by tuple (see Section 16)
6. Returns a fully formed `RecommendationResult`

### 23.2 Plan-wide CanTakeCatalog

The eligibility simulation requires evaluating Phase 5 for all remaining
plan courses. The current `EligibilityService.evaluate_can_take()` loads
catalog data per target. The future recommendation engine needs a plan-wide
version of the catalog — loaded once, held in memory, used for all evaluations.

The repository must expose a `load_plan_wide_rules(study_plan_id)` method
that returns a `CanTakeCatalog` containing all 68 plan courses' rules,
all dependency groups, and all course identities.

The pure engine receives this pre-loaded catalog and does not call the
repository itself.

### 23.3 Isolation requirements

The recommendation engine must not:
- Import FastAPI, Supabase client, httpx, or any I/O library
- Call `calculate_academic_progress()` via a service — call the pure function directly
- Call `evaluate_can_take()` via a service — call the pure function directly
- Write any simulated attempt to any mutable store
- Depend on current time or randomness

---

## 24. Service Orchestration

### 24.1 Conceptual flow

```
GET /api/v1/me/course-recommendations
     ↓
auth: get_current_user()
     ↓
student_service.get_course_recommendations(owner_user_id)
     ↓
[1] student_repository.load_student_academic_state(owner_user_id)
    → StudentAcademicState (profile, study_plan_id, attempts)
     ↓
[2] catalog_repository.load_progress_catalog(study_plan_id)
    → AcademicProgressCatalog
     ↓
[3] catalog_repository.load_plan_wide_rules(study_plan_id)
    → CanTakeCatalog (all 68 plan courses, all dependency groups)
     ↓
[4] recommend_courses(
        progress_catalog,
        can_take_catalog,
        student_attempts,
        ...reported_facts,
    )
    → RecommendationResult (pure, in-memory computation)
     ↓
API response mapper
```

### 24.2 Ownership safety

All operations use the verified `owner_user_id` from authenticated session.
The API route accepts no `owner_user_id`, `study_plan_id`, or attempt history
from the client. All facts come from persisted authenticated student state.

### 24.3 Single profile assumption

The MVP supports one profile per user. The service loads that unique profile.
If no profile exists, the service raises a `StudentProfileNotFound` equivalent
and the API returns 404.

---

## 25. Future API

### 25.1 Proposed endpoint

```
GET /api/v1/me/course-recommendations
```

- Bearer authentication required
- No request body
- No path parameters (identity comes from auth token)
- Response: `RecommendationResult` as JSON

### 25.2 Optional query parameter

The endpoint may support an optional `limit` parameter:

```
GET /api/v1/me/course-recommendations?limit=10
```

- Bounded: `1 <= limit <= 68` (max plan size)
- Affects presentation only — does not change ranking semantics
- Engine always computes full ranking; limit is applied after
- Default: return all ranked candidates

No other query parameters are defined. Filters requiring unmodeled data
(semester, difficulty, days off) must not be added until that data is
verified and modeled.

### 25.3 HTTP mapping

```
200   — successful recommendation result (may include empty ranked list)
401   — missing or invalid bearer token
404   — no student profile found
500   — catalog or student integrity error
503   — repository transport or configuration error
```

A `200` with `ranked_recommendations = []` is a valid academic result
(e.g., all plan courses completed or in-progress).

---

## 26. Performance Strategy

### 26.1 Anti-pattern to avoid

For 68 plan courses, evaluating Phase 5 per target with separate database
roundtrips would mean up to 68 × 4–5 Data API reads = 272–340 reads per
recommendation request. This is unacceptable.

### 26.2 Required approach: load once, evaluate in memory

The service orchestration layer performs exactly three data loads:

1. **Student state** (one read: profile + attempts)
2. **Progress catalog** (one read: plan + groups + plan courses)
3. **Plan-wide eligibility catalog** (one read: plan + all 68 plan courses +
   all 32 dependency groups + all 32 dependency options + all 74 course
   identities)

All recommendation computation then runs in memory using pure functions.

No Supabase query occurs inside the recommendation loop.

### 26.3 Computational complexity

For N plan courses (N = 68 for Plan 12):

- Phase 6 progress calculation: O(N) — one pass over all plan courses
- Eligibility filtering: O(N) — one evaluation per plan course
- Per-candidate simulation: O(N) — one additional progress calc + N eligibility evals
- Total: O(N²) — acceptable for N = 68

For the pure Phase 5 evaluator with pre-loaded catalog, each evaluation is
O(G × O) where G = dependency groups per course (max 2 in current data) and
O = options per group (max 1 in current data). For Plan 12, this is essentially
O(1) per evaluation.

---

## 27. Auditability and Explainability

### 27.1 Requirement

For any recommendation, a developer must be able to answer:
"Why was Course A ranked above Course B?"

The answer must derive mechanically from the `priority_tuple` field in each
`RecommendationCandidate`:

```
Course A ranked above Course B because:
  A.P1 = 2 (required course) > B.P1 = 0 (elective course)
```

or:

```
Course A ranked above Course B because:
  both are required (P1 = 2)
  both have group remaining need (P2 = 1)
  both have same credit contribution (P3 = 3)
  A.P4 = 1 (completes group) > B.P4 = 0
```

### 27.2 No hidden ranking

The `priority_tuple` is included in every `RecommendationCandidate` in the
response. No ranking factor is hidden or computed outside the tuple.

### 27.3 AI explainability

The `reason_codes` vocabulary provides structured data for future AI
explanation. The AI may use reason codes to generate natural-language
explanations in Arabic or English. The AI does not compute, reorder, or modify
the underlying ranking.

---

## 28. Safety Language

### 28.1 Methodology note

The `methodology_note` field in `RecommendationResult` must contain:

> "These recommendations are based on your modeled academic study plan and
> verified prerequisite structure. They indicate courses that are academically
> useful for your degree progress based on available data. They are not
> official registration approval, do not guarantee course availability, and
> do not represent institutional academic advice."

### 28.2 What the engine must never claim

The engine result must never state or imply:
- "You must register this course"
- "This course is available this semester"
- "Registration for this course is permitted"
- "This course is easy"
- "This is the optimal schedule"

All recommendation output is **academic decision support**, not official
registration approval.

---

## 29. Edge Cases

### 29.1 All modeled plan courses completed or in-progress

```
ranked_recommendations = []
review_required_courses = [possibly some REVIEW_REQUIRED courses]
methodology_note: "..."
```

An optional context code `NO_ELIGIBLE_INCOMPLETE_PLAN_COURSES` may be included.

This does not imply official graduation clearance.
`all_modeled_plan_requirements_satisfied` from Phase 6 is the relevant field
for progress context.

### 29.2 Only REVIEW_REQUIRED courses remain

When all incomplete plan courses produce `REVIEW_REQUIRED` from Phase 5:

```
ranked_recommendations = []
review_required_courses = [all REVIEW_REQUIRED courses]
```

Do not rank `REVIEW_REQUIRED` courses alongside eligible candidates.

### 29.3 Elective group already satisfied

All candidates from a satisfied elective group receive:
- `P2 = 0`
- `effective_contribution = 0`
- Excluded from `ranked_recommendations`

If future UI needs to show these courses (e.g., "also eligible, no graduation
progress needed"), they may appear in a separate `zero_value_eligible_courses`
list. They are never in `ranked_recommendations`.

### 29.4 Required zero-credit course

`0200115` and `1509999` appear with `credit_hours = 0` in required groups.

Both receive `P1 = 1` (zero-credit required). They rank above all elective
candidates. They rank below positive-credit required courses within the
required tier. Their `MANDATORY_ZERO_CREDIT_COURSE` reason code explicitly
marks their special structural status.

Example: If `0200115` is the only remaining zero-credit required course in
UNIVERSITY_REQUIRED, and all university required credit targets are met but
`0200115` is not passed, the group is still unsatisfied. `0200115` would
appear in `ranked_recommendations` with high structural priority.

### 29.5 Course already in-progress

Excluded. A student currently enrolled (IN_PROGRESS attempt) does not need it
recommended. Its code appears in `excluded_in_progress` for informational context.

### 29.6 Failed required course eligible again

A required course with prior `FAILED` outcome and current Phase 5 `ELIGIBLE`
decision is a normal candidate. It receives:
- `course_state = ATTEMPTED_NOT_COMPLETED`
- `previously_attempted = true`
- `PREVIOUSLY_ATTEMPTED` reason code
- No penalty to priority tuple

The student may have valid reasons to retake it. Morshidi does not penalize
prior failure.

### 29.7 Withdrawn eligible course

Same treatment as failed eligible course (Section 29.6).

### 29.8 Unresolved or source-conflict prerequisite course

The course receives `REVIEW_REQUIRED` from Phase 5. It is placed in
`review_required_courses`. It is never ranked alongside eligible candidates.
The eligibility simulation never treats it as a newly-eligible target after a
hypothetical pass (Section 13.4).

### 29.9 No profile

Future service raises `StudentProfileNotFound`. API returns 404. No
recommendation is generated.

### 29.10 Catalog integrity error

Future service raises `CatalogIntegrityError` or equivalent. API returns 500.
No partial recommendation is generated.

### 29.11 FAILED then PASSED (course is COMPLETED)

Phase 6 course state priority: any `PASSED` → `COMPLETED`. The course is
excluded from candidates. This is correct: the course is already done.

---

## 30. Complete Test Matrix

### Candidate Filtering

| # | Case | Expected |
| ---: | --- | --- |
| 1 | `COMPLETED` plan course | Excluded from candidates |
| 2 | `IN_PROGRESS` plan course | Excluded; appears in `excluded_in_progress` |
| 3 | `NOT_ATTEMPTED` course with Phase 5 `ELIGIBLE` | Included as candidate |
| 4 | `ATTEMPTED_NOT_COMPLETED` course with Phase 5 `ELIGIBLE` | Included as candidate |
| 5 | Phase 5 `NOT_ELIGIBLE` plan course | Excluded from ranking |
| 6 | Phase 5 `REVIEW_REQUIRED` plan course | In `review_required_courses` only |
| 7 | Referenced-only course (not a plan member) | Never a candidate (Phase 5 rejects as target) |

### Required / Elective

| # | Case | Expected |
| ---: | --- | --- |
| 8 | Incomplete required course, group unsatisfied | `P1 = 2` (or 1 if zero-credit); `REQUIRED_PLAN_COURSE` reason |
| 9 | Elective candidate in unsatisfied elective group | `P2 = 1`; `ADVANCES_ELECTIVE_REQUIREMENT` reason |
| 10 | Elective candidate in satisfied elective group | `P2 = 0`; excluded from `ranked_recommendations` |
| 11 | Student has 12 completed elective credits, group needs 9 | `remaining_required_credits = 0`; electives excluded from ranked list |
| 12 | Required zero-credit course (`0200115` or `1509999`) | `P1 = 1`; `MANDATORY_ZERO_CREDIT_COURSE` reason; ranks above all electives |

### Progress Simulation

| # | Case | Expected |
| ---: | --- | --- |
| 13 | Hypothetical pass increases group credited progress | `group_remaining_credits_after < group_remaining_credits_before` |
| 14 | Hypothetical pass causes group `is_satisfied` to flip | `completes_requirement_group = true`; `COMPLETES_REQUIREMENT_GROUP` reason |
| 15 | Hypothetical pass attempt is not persisted | No database write; simulation is pure in-memory |
| 16 | Student has repeated existing attempts; hypothetical adds one more `PASSED` | Progress engine correctly ignores duplicates; delta computed correctly |
| 17 | Referenced-only course in attempt history (e.g., `0300103 PASSED`) | Not a plan course; not in progress universe; does not affect plan progress delta |

### Eligibility / Unlock Simulation

| # | Case | Expected |
| ---: | --- | --- |
| 18 | Candidate has no downstream dependency relationships | `newly_eligible_count = 0`; `NO_DIRECT_PREREQUISITE_IMPACT` reason |
| 19 | Candidate passing makes exactly one plan course newly `ELIGIBLE` | `newly_eligible_count = 1`; `UNLOCKS_FUTURE_COURSE` reason |
| 20 | Candidate passing makes three plan courses newly `ELIGIBLE` | `newly_eligible_count = 3`; `UNLOCKS_MULTIPLE_FUTURE_COURSES` reason |
| 21 | Target course has two AND groups; candidate satisfies only one | Target remains `NOT_ELIGIBLE`; not counted in `newly_eligible_count` |
| 22 | Target course has OR group; candidate satisfies one option | Target transitions to `ELIGIBLE` if all other groups also satisfied |
| 23 | Downstream plan course has `unresolved` status | Never counted as newly eligible; `REVIEW_REQUIRED` before and after |
| 24 | Downstream plan course has `source_conflict` status | Never counted as newly eligible; `REVIEW_REQUIRED` before and after |
| 25 | Hypothetical evaluation reuses Phase 5 `evaluate_can_take()` | Same AND/OR semantics as Phase 5; no custom graph logic |

### Ranking

| # | Case | Expected |
| ---: | --- | --- |
| 26 | Required course vs elective (equal other factors) | Required course ranked first (`P1`: 2 > 0) |
| 27 | Zero-credit required course vs 3-credit elective | Zero-credit required ranked first (`P1`: 1 > 0) |
| 28 | Two required courses; one completes its group | Group-completing candidate ranked first at `P4` |
| 29 | Two candidates, same P1–P4; one unlocks 3 future courses, other 1 | Three-unlock candidate ranked first at `P5` |
| 30 | Perfect tie on P1–P5; different `display_order` | Lower display-order wins at P6 |
| 31 | Perfect tie on P1–P6; different course codes | Lexicographically smaller code wins at P7 |
| 32 | Identical ranking inputs across two runs | Identical ordering |

### History

| # | Case | Expected |
| ---: | --- | --- |
| 33 | `FAILED` then `PASSED` for a course | Course is `COMPLETED`; excluded from candidates |
| 34 | `FAILED`-only for a required course; currently `ELIGIBLE` | Candidate included; `previously_attempted = true`; no penalty |
| 35 | `WITHDRAWN`-only for an elective course; currently `ELIGIBLE` | Candidate included; `previously_attempted = true`; no penalty |
| 36 | Previous failure does not change priority tuple | Tuple identical to a course with no prior attempts, all else equal |

### Empty / Special

| # | Case | Expected |
| ---: | --- | --- |
| 37 | All modeled plan courses `COMPLETED` or `IN_PROGRESS` | `ranked_recommendations = []`; no fake recommendations |
| 38 | Only `REVIEW_REQUIRED` courses remain incomplete | `ranked_recommendations = []`; all in `review_required_courses` |
| 39 | No student profile | Service raises `StudentProfileNotFound`; API returns 404 |
| 40 | Catalog integrity inconsistency | `CatalogIntegrityError`; API returns 500; no partial result |
| 41 | Elective group satisfied; additional electives eligible | Excluded from `ranked_recommendations`; no graduation progress priority |

### Security / Service

| # | Case | Expected |
| ---: | --- | --- |
| 42 | `owner_user_id` comes from verified auth only | Not accepted as a request body field |
| 43 | `study_plan_id` not accepted from client | Comes from persisted profile only |
| 44 | Attempt history not accepted from client | Comes from persisted attempts only |
| 45 | Authenticated user requests recommendations | Sees only their own profile and recommendations |
| 46 | `anon` requests recommendations | 401 |
| 47 | User A's bearer token used to request User B's recommendations | Returns User A's recommendations (profile is owner-scoped); User B's data is not accessible |

---

## 31. Real Plan 12 Examples

All examples use verified repository data only. No prerequisites or
relationships are invented.

### 31.1 Required course with verified upstream dependency

**Candidate:** `1501112 — برمجة الحاسوب (2)` (FACULTY_REQUIRED, 3 credits)
- Prerequisite: `1501110 — برمجة الحاسوب (1)` (verified, group 1)
- If student has `1501110 PASSED` → `1501112` is `ELIGIBLE`

**Downstream unlock impact:**
Passing `1501112` makes the following courses newly eligible (as their
prerequisites are now satisfied):
- `1501221 — تراكيب البيانات` (prerequisite: `1501112`)
- `1501222 — نظم قواعد البيانات` (prerequisite: `1501112`)
- `1501340 — شبكات الحاسوب` (prerequisite: `1501112`)
- `1501385 — برمجة الهواتف الذكية` (prerequisite: `1501112`)
- `1505211 — لغات خاصة في البرمجة` (prerequisite: `1501112`)

That is `newly_eligible_count ≥ 5` (subject to the student's current history
and which of these are not already eligible or completed).

**Priority tuple (illustrative, student has nothing completed):**
```
T = (2, 1, 3, ?, 5+, -26, "1501112")
```

`1501112` would rank very high: required, group needs progress, full credit
contribution, multiple unlocks.

**Reason codes:** `REQUIRED_PLAN_COURSE`, `ADVANCES_REQUIRED_GROUP`, `UNLOCKS_MULTIPLE_FUTURE_COURSES`

**Ranking note:** "Course `1501112` ranks above `1501221` because while both
are required, `1501112` is a prerequisite for `1501221`; at this point
`1501221` is NOT_ELIGIBLE (requires `1501112`), so it is not yet a candidate."

### 31.2 Course completing a group

**Scenario:** Student has completed 6 of 9 required University Elective
credits. Remaining group need: 3 credits.

**Candidate:** `0200113 — تاريخ الاردن وفلسطين` (UNIVERSITY_ELECTIVE, 3 credits)
- `effective_contribution = min(3, 3) = 3`
- Hypothetical progress: `remaining_required_credits` for UNIVERSITY_ELECTIVE
  drops from 3 to 0 → `is_satisfied` transitions to true
- `completes_requirement_group = true`

**Priority tuple:**
```
T = (0, 1, 3, 1, 0, -10, "0200113")
```

**Reason codes:** `ADVANCES_ELECTIVE_REQUIREMENT`, `COMPLETES_REQUIREMENT_GROUP`, `NO_DIRECT_PREREQUISITE_IMPACT`

### 31.3 Satisfied elective group — exclusion

**Scenario:** Student has already completed 9 University Elective credits.

**Candidate:** `0200113 — تاريخ الاردن وفلسطين` (UNIVERSITY_ELECTIVE, 3 credits)
- `remaining_required_credits = 0` → `group_has_remaining_need = false`
- `effective_contribution = min(3, 0) = 0`
- `P2 = 0`

→ Excluded from `ranked_recommendations`.

Reason: No graduation-progress value remains for this group.

### 31.4 Major Elective group (9 of 39 credits)

**Scenario:** Student has completed 0 major elective credits.

**Candidate:** `1501360 — مناهج واخلاقيات البحث العلمي` (MAJOR_ELECTIVE, 3 credits, `not_applicable` prerequisite)
- Eligible immediately (no prerequisites)
- `effective_contribution = min(3, 9) = 3`
- `completes_requirement_group = false` (3 of 9 needed)
- `newly_eligible_count = 0` (no downstream dependencies through this course)

**Priority tuple:**
```
T = (0, 1, 3, 0, 0, -34, "1501360")
```

**Reason codes:** `ADVANCES_ELECTIVE_REQUIREMENT`, `NO_DIRECT_PREREQUISITE_IMPACT`

### 31.5 Zero-credit required course

**Candidate:** `0200115 — تنمية المجتمع والعمل التطوعي` (UNIVERSITY_REQUIRED, 0 credits)
- `not_applicable` prerequisite → `ELIGIBLE` immediately
- `effective_contribution = 0`
- `P1 = 1` (zero-credit required)
- Group UNIVERSITY_REQUIRED may have met its 18-credit target, but
  `is_satisfied = false` because mandatory zero-credit course is incomplete

**Priority tuple:**
```
T = (1, 1, 0, 0, 0, -6, "0200115")
```

→ Ranks above ALL elective candidates regardless of elective credit value.

**Reason codes:** `REQUIRED_PLAN_COURSE`, `MANDATORY_ZERO_CREDIT_COURSE`, `ADVANCES_REQUIRED_GROUP`, `NO_DIRECT_PREREQUISITE_IMPACT`

Similarly for `1509999 — حلقة بحث لطلبة كلية تكنولوجيا المعلومات`:

**Priority tuple:**
```
T = (1, 1, 0, 0, 0, -28, "1509999")
```

### 31.6 REVIEW_REQUIRED prerequisite case

**Course:** `1505311 — تعلم الالة` (MAJOR_REQUIRED, 3 credits)
- `prerequisite_logic_status = unresolved`
- Phase 5 → `REVIEW_REQUIRED`

→ Not in `ranked_recommendations`.
→ Appears in `review_required_courses` with:
  - `review_reason = "PREREQUISITE_LOGIC_UNRESOLVED"`

UI context: "Academic prerequisite information for تعلم الالة requires verification."

### 31.7 Source-conflict REVIEW_REQUIRED case

**Course:** `1505320 — تعلم الآلة المتقدم` (MAJOR_REQUIRED, 3 credits)
- `prerequisite_logic_status = source_conflict`
- Phase 5 → `REVIEW_REQUIRED`

→ Same treatment as 31.6. Appears in `review_required_courses`:
  - `review_reason = "PREREQUISITE_SOURCE_CONFLICT"`

### 31.8 Referenced-only history example

**Student history includes:** `0300103 PASSED` (referenced-only course, not a plan member)

Effect on recommendation:
- `0300103` is not a plan course → not in progress universe
- Not a candidate (Phase 5 rejects it as `TARGET_NOT_IN_STUDY_PLAN`)
- Does NOT contribute to plan credit progress (Phase 6 confirmed behavior)
- However, `0300103` IS a valid prerequisite option in the catalog — if a
  verified dependency referenced it, the Phase 5 evaluator could use it
- Since `1505320` (the only current course referencing `0300103`) is
  `source_conflict`, this pass cannot unlock `1505320`

Referenced-only history does not affect plan credit or ranked recommendations.

### 31.9 Scoring explanation example

**Scenario:** Student has passed `0300153`, `1501110`, `1501112`. No other
completed courses.

Two candidates: `1501221 — تراكيب البيانات` and `1501111 — مختبر برمجة الحاسوب (1)`.

`1501221` (FACULTY_REQUIRED, 3 credits, prerequisite `1501112` ✓ ELIGIBLE):
- Downstream unlock: `1501321` (requires `1501221`), `1501430` (requires `1501221`), etc.
- P1=2, P2=1, P3=3, P4=?, P5=2+, P6=-27

`1501111` (MAJOR_REQUIRED, 1 credit, prerequisite `0300153` ✓ ELIGIBLE):
- Downstream unlock: `1501113` (requires `1501111`), `1506181` (requires `1501111`)
- P1=2, P2=1, P3=1, P4=?, P5=2, P6=-46

Comparison at P3: `1501221` has `P3=3`, `1501111` has `P3=1`.

→ `1501221` ranks above `1501111`.

Explanation: "Course `1501221` ranks above `1501111` because both are required
eligible courses contributing to their groups, but `1501221` contributes 3
credits toward the requirement compared to `1501111`'s 1 credit."

---

## 32. Known Limitations

The following limitations must be documented in `RecommendationResult.limitations`:

1. Recommendation quality is bounded by modeled academic structure. The engine
   knows only what is in the verified catalog and student attempt history.

2. Course offering and section availability are unknown. A recommended course
   may not be offered in the current registration period.

3. Some prerequisite data for Plan 12 courses remains unresolved or has source
   conflicts. Affected courses appear only in `review_required_courses`.

4. No transfer-credit, course equivalency, or substitution model exists.
   External credits and equivalent courses are not reflected.

5. No course difficulty, workload, or student preference model exists.
   Recommendations do not account for personal study capacity.

6. Individual course ranking is not a complete semester plan. No credit-load
   optimization or timetable conflict resolution is performed.

7. No institutional administrative rules (GPA probation, adviser holds,
   registration windows, financial holds) are modeled.

8. No official GPA calculation engine exists. Reported GPA facts do not
   influence recommendations.

9. The derived plan progress used for simulation does not constitute official
   graduation clearance.

10. Referenced-only courses in student history contribute no plan credit and
    do not affect plan-based recommendations.

---

## 33. Future Extensions

Extensions that may be designed in later phases, each requiring verified data,
explicit contract semantics, and separate review:

- **Semester availability filter:** Add course-offering data and filter
  candidates to courses offered in the current/upcoming semester.
- **Credit-load optimizer:** Given a desired total credit load, select a
  combination of top-ranked candidates.
- **Timetable conflict resolver:** Given class meeting time data, eliminate
  conflicting combinations.
- **Transitive unlock scoring:** Bounded graph traversal for deeper dependency
  impact measurement.
- **Tier labels:** If product-verified criteria emerge for difficulty or
  urgency tiers, add them with explicit data backing.
- **User preference model:** Allow students to specify preferred days, maximum
  credits, or elective focus areas.
- **Transfer credit integration:** When a transfer-credit model is added,
  incorporate transferred credits into progress simulation.
- **Equivalency support:** If `course_equivalencies` are verified and activated,
  recommendation simulation can respect them.
- **Multi-plan recommendation:** For students transitioning between study plans.
- **Arabic explanation generation:** AI layer consuming reason codes and
  priority tuples to generate natural-language Arabic explanations.

---

## Appendix A: Plan 12 Prerequisite Dependency Map (Verified)

From migration `20260916231030_model_ai_plan12_prerequisites.sql`:

```
0300220  ← 0300153   (رياضيات متقطعة ← اساسيات تكنولوجيا المعلومات)
1501110  ← 0300153   (برمجة الحاسوب (1) ← اساسيات تكنولوجيا المعلومات)
1501112  ← 1501110   (برمجة الحاسوب (2) ← برمجة الحاسوب (1))
1501221  ← 1501112   (تراكيب البيانات ← برمجة الحاسوب (2))
0200215  ← 0200106   (ESP-IT ← English Comm 1)
1501212  ← 1501222   (برمجة مرئية ← نظم قواعد البيانات)
1501385  ← 1501112   (برمجة الهواتف الذكية ← برمجة الحاسوب (2))
1505211  ← 1501112   (لغات خاصة ← برمجة الحاسوب (2))
1505303  ← 0300220   (المنطق الضبابي ← رياضيات متقطعة)
1505351  ← 1505201   (علم الإدراك ← مقدمة في الذكاء الاصطناعي)
1505365  ← 1501222   (استرجاع المعلومات ← نظم قواعد البيانات)
1505414  ← 1505311   (تعلم الالة التطبيقي ← تعلم الالة) [1505311 is REVIEW_REQUIRED]
1505480  ← 1501222   (البيانات الضخمة ← نظم قواعد البيانات)
1505482  ← 1505381   (برمجة الروبوتات ← مقدمة في الروبوتات)
1506493  ← 1501340   (إنترنت الأشياء ← شبكات الحاسوب)
1501111  ← 0300153   (مختبر برمجة الحاسوب (1) ← اساسيات تكنولوجيا المعلومات)
1501113  ← 1501111   (مختبر برمجة الحاسوب (2) ← مختبر برمجة الحاسوب (1))
1501222  ← 1501112   (نظم قواعد البيانات ← برمجة الحاسوب (2))
1501321  ← 1501221   (تصميم وتحليل الخوارزميات ← تراكيب البيانات)
1501340  ← 1501112   (شبكات الحاسوب ← برمجة الحاسوب (2))
1501430  ← 1501221   (نظم التشغيل ← تراكيب البيانات)
1503270  ← 0300153   (مقدمة لهندسة البرمجيات ← اساسيات تكنولوجيا المعلومات)
1505101  ← 1501110   (البرمجة بلغة بايثون ← برمجة الحاسوب (1))
1505201  ← 0300153   (مقدمة في الذكاء الاصطناعي ← اساسيات تكنولوجيا المعلومات)
1505223  ← 1505101   (برمجة وأدوات الذكاء الإصطناعي ← البرمجة بلغة بايثون)
1505333  ← 1501222   (علم البيانات وتحليلها ← نظم قواعد البيانات)
1505381  ← 1505201   (مقدمة في الروبوتات ← مقدمة في الذكاء الاصطناعي)
1505415  ← 1505311   (التعلم العميق التطبيقي ← تعلم الالة) [1505311 is REVIEW_REQUIRED]
1505441  ← 1505311   (معالجة اللغات الطبيعية ← تعلم الالة) [1505311 is REVIEW_REQUIRED]
1505468  ← 1505467   (مشروع (2) ← مشروع (1))
1506180  ← 1501110   (برمجة ويب (1) ← برمجة الحاسوب (1))
1506181  ← 1501111   (مختبر برمجة ويب (1) ← مختبر برمجة الحاسوب (1))
```

REVIEW_REQUIRED in current data:
- `0200105`, `0200106`, `1505311`, `1505461` — PREREQUISITE_LOGIC_UNRESOLVED
- `1505320`, `1505366` — PREREQUISITE_SOURCE_CONFLICT

Note: `0200215` depends on `0200106` (currently REVIEW_REQUIRED).
If `0200106` is `REVIEW_REQUIRED`, and `0200215` has prerequisite `0200106`,
then `0200215` is also `REVIEW_REQUIRED` (its dependency status is `unresolved`
per the seed data). This cascades correctly through Phase 5.

---

## Appendix B: Key Design Decisions Summary

| # | Decision | Choice | Rationale |
| --- | --- | --- | --- |
| 1 | Weighted vs lexicographic ranking | Lexicographic | Deterministic, transparent, no arbitrary constants |
| 2 | Exact priority dimensions | (P1, P2, P3, P4, P5, P6, P7) | Covers all structural factors; fully deterministic |
| 3 | Unlock impact method | Phase 5 simulation (not occurrence counting) | Respects AND/OR automatically; no logic duplication |
| 4 | Transitive impact in MVP | No — direct simulation only | Simpler; sufficient; avoids exponential weighting |
| 5 | Satisfied elective group behavior | Exclude from ranked list | No graduation-progress value remains |
| 6 | Return all vs top N | Return all ranked candidates | Preserves auditability; API may apply limit |
| 7 | Reason code vocabulary | 10 stable codes defined | Covers all factors without over-specificity |
| 8 | Tie-breaking | display_order then course_code | Catalog-ordered, stable, no arbitrary constants |
| 9 | Policy versioning | Yes — `"1.0"` constant | Enables future policy evolution tracking |
| 10 | Previous failure behavior | Context only, no penalty | No verified policy for difficulty-based ranking |

