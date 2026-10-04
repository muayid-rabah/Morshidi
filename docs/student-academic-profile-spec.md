# Student Academic Profile Specification

## 1. Purpose

This specification defines the future persistent, private academic state that
will supply deterministic attempt history to Morshidi's Phase 5 CAN TAKE rules
engine. It is a design record only: it creates no table, migration, API,
authentication flow, Row Level Security (RLS) policy, or frontend behavior.

The design supports a selected study plan, repeated course attempts, the four
Phase 5 outcomes, and optional official/reported academic summary facts. It
does not make Morshidi the authority for university registration or grading
policy.

## 2. Scope and non-goals

In scope for a later implementation:

- one user-owned academic profile with a selected `study_plan_id`;
- appendable and correctable course-attempt history;
- optional reported cumulative GPA and earned-credit snapshots;
- deterministic mapping of attempts into the existing pure rules engine.

Out of scope:

- migrations, tables, API routes, authentication, RLS, frontend, or package
  installation;
- a GPA calculator, grade conversion, repeat-course policy, transfer credit,
  equivalency, substitution, registration, recommendation, or semester plan;
- storing national ID, phone, address, birth date, university number, or any
  other identity-sensitive field not required for academic-state evaluation.

## 3. Domain separation

The academic catalog remains the verified shared source of truth:

```text
universities -> faculties -> majors -> study_plans
                                      -> study_plan_courses -> courses
```

Student state is private, user-owned data that references but never edits that
catalog:

```text
auth.users -> student_academic_profiles -> student_course_attempts -> courses
                         |
                         -> study_plans
```

Student input must never create or amend a catalog Course, Study Plan,
dependency group, equivalency, or raw prerequisite interpretation.

## 4. MVP identity and profile lifecycle

### Decision: one profile per user for the MVP

The MVP supports exactly one academic profile per authenticated user, rather
than multiple concurrent profiles. This is sufficient for the first
user-owned-history workflow and avoids unresolved questions around active vs.
historical degrees, cross-major history, and UI selection.

The profile uses its own UUID primary key plus an `owner_user_id` foreign key to
`auth.users.id`, with a unique constraint on `owner_user_id`.

| Option | Result |
| --- | --- |
| Use `auth.users.id` as the profile primary key | Simpler strict one-to-one relation, but makes future multiple profiles a primary-key redesign. |
| **Own profile UUID plus `owner_user_id`** | **Chosen.** Keeps the MVP one-to-one through a unique owner constraint while allowing a future migration to remove that uniqueness and introduce explicit profile status/history. |

The selected study plan may be changed only while the profile has no attempts.
Once history exists, silently moving that history to another plan would change
its academic meaning. A future multi-profile or explicit plan-transition
workflow must handle such a change deliberately.

Profile lifecycle in the future MVP:

1. An authenticated user creates their one profile and selects an existing
   Study Plan.
2. The user may edit reported summary facts and add/correct/delete their own
   attempts.
3. The user may delete their profile; its attempts are then deleted with it.
4. Morshidi does not automatically create a profile on sign-up in this phase;
   the eventual creation trigger/service decision remains separate.

## 5. Proposed entity: `StudentAcademicProfile`

This is a proposed future table, not SQL.

| Field | Proposed type / nullability | Source of truth and purpose | Important future constraint |
| --- | --- | --- | --- |
| `id` | UUID, non-null primary key | Internal profile identity | Generated UUID; stable across edits. |
| `owner_user_id` | UUID, non-null | Authenticated owner, referencing `auth.users.id` | Unique for the MVP; cascade on Auth-user deletion. |
| `study_plan_id` | UUID, non-null | Student-selected catalog plan | FK to `study_plans.id`; restrict catalog-plan deletion. |
| `reported_cumulative_gpa` | numeric, nullable | Student-reported or official GPA snapshot | Non-negative; paired with scale. |
| `reported_gpa_scale` | numeric, nullable | Declared scale for the reported GPA | Positive; either both GPA fields are present or both absent. |
| `reported_earned_credit_hours` | numeric, nullable | Student-reported or official earned-credit snapshot | Non-negative; not a calculated graduation determination. |
| `created_at` | timestamptz, non-null | Audit and support chronology | Set on creation. |
| `updated_at` | timestamptz, non-null | Audit and correction chronology | Updated on profile edits. |

No `student_id`, course list, GPA-derived status, eligibility cache, or
current-course list belongs on the profile. These would either duplicate
normalized attempts or create stale derived facts.

## 6. Proposed entity: `StudentCourseAttempt`

One row represents one recorded attempt fact, not one course's latest status.
Its own UUID is the attempt identity, so repeated attempts remain possible even
when term information is unavailable.

| Field | Proposed type / nullability | Source of truth and purpose | Important future constraint |
| --- | --- | --- | --- |
| `id` | UUID, non-null primary key | Internal attempt identity | Generated UUID. |
| `profile_id` | UUID, non-null | Owning academic profile | FK to profile; cascade on profile deletion. |
| `course_id` | UUID, non-null | Canonical catalog Course identity | FK to `courses.id`; restrict Course deletion. |
| `outcome` | text, non-null | Explicit attempt result for Phase 5 | Closed values: `PASSED`, `FAILED`, `IN_PROGRESS`, `WITHDRAWN`. |
| `attempt_sequence` | integer, nullable | Optional user/import ordering when known | Positive when present; unique per profile/course/sequence when present. |
| `term_label` | text, nullable | Optional source-provided term descriptor | Nonblank when present; no Zarqa-specific codes are invented. |
| `attempted_on` | date, nullable | Optional generic chronology fact | No calendar inference required. |
| `reported_grade_text` | text, nullable | Optional raw display/import fact | Nonblank when present; never interpreted by Phase 5. |
| `record_source` | text, non-null | Minimal provenance | Closed values: `manual_entry`, `transcript_import`, `university_integration`, `admin_correction`; default `manual_entry`. |
| `created_at` | timestamptz, non-null | Record chronology | Set on creation. |
| `updated_at` | timestamptz, non-null | Correction chronology | Updated on edit. |

There is intentionally no unique constraint on `(profile_id, course_id)`.
The optional sequence uniqueness is only an integrity aid for a supplied
sequence; multiple null sequences remain valid. The UUID identity and complete
row history preserve repeated attempts without requiring term metadata.

### Editing and deletion policy

Manual entry needs practical correction. The MVP should permit an owner to add,
edit, and hard-delete their own mistaken attempt. `updated_at` records the last
correction. No event-sourcing, immutable audit trail, or enterprise correction
workflow is proposed until a verified need exists. Imported or institutional
sources remain provenance labels, not a claim that Morshidi has verified them.

## 7. Course identity and catalog safety

Attempts reference `courses.id`; names are display data, never authoritative
attempt identifiers. The Course's `(university_id, course_code)` identity
preserves leading zeroes because the canonical code remains text.

The future write boundary must resolve user-entered code text to exactly one
existing Course in the selected plan's university. It must reject an unknown
code with an explicit unsupported/unrecognized-course error. It must not create
a Course from student input or maintain a second unmapped-attempt table in the
MVP. An unmapped transcript/import workflow can be designed later if needed.

`referenced_only` Courses are valid attempt targets in history if they exist in
the same university catalog. For example, a student may have passed `0300103`.
It remains invalid as a selectable Plan 12 CAN TAKE target unless it later gains
verified plan membership; it may satisfy a future verified dependency only by
its exact code, never by inferred equivalency.

### Cross-university invariant

For every attempt, the Course's `university_id` must equal the university
derived from the profile's Study Plan through `study_plans -> majors ->
faculties`. A future migration must enforce this in the database, using a
dedicated validation trigger or another equivalent database-level invariant;
application validation alone is insufficient. Transfer credit is a separate
future model and must not be represented as a normal foreign-university Course
attempt.

## 8. Attempt outcome semantics and multiple attempts

Storage uses the exact uppercase Phase 5 vocabulary; no second status
translation is introduced.

| Stored outcome | Phase 5 `AttemptOutcome` | CAN TAKE prerequisite meaning |
| --- | --- | --- |
| `PASSED` | `PASSED` | Qualifying completion. |
| `FAILED` | `FAILED` | Does not qualify. |
| `IN_PROGRESS` | `IN_PROGRESS` | Does not qualify as completed. |
| `WITHDRAWN` | `WITHDRAWN` | Does not qualify. |

The model does not assert broader university repeat, withdrawal, grade, or
registration policy. It preserves all rows rather than computing a latest
status. Therefore `FAILED` then `PASSED`, `PASSED` then `FAILED`, and duplicate
`PASSED` rows all map to histories containing at least one exact-code `PASSED`;
the current pure evaluator deterministically treats the prerequisite as
satisfied.

No separate current-courses relation is proposed. An `IN_PROGRESS` attempt is
the normalized source of that fact.

## 9. GPA, credits, grades, and derived data

### Reported facts

`reported_cumulative_gpa`, `reported_gpa_scale`, and
`reported_earned_credit_hours` are optional reported/official snapshots. They
are not calculated from attempts. GPA must be non-negative; its supplied scale
must be positive; the two GPA fields must be populated together. Earned credit
hours must be non-negative. The design does not hardcode a 4.0 or 100 scale.

`reported_grade_text` is optional raw attempt evidence for future display or
import reconciliation. Numeric grade, grade points, and grade-scale-per-attempt
fields are intentionally deferred. Phase 5 eligibility consumes only the
explicit `outcome`; it must never derive `PASSED` or `FAILED` from a raw grade
until a verified institutional grading policy exists.

### Derived values

The following are future computed values, not persisted sources of truth:

- the set of exact passed course codes;
- a count of passed Plan 12 courses;
- prerequisite satisfaction and missing-group evidence;
- eligible-course sets;
- estimated completed plan credits.

In particular, summing passed `study_plan_courses.credit_hours` must not replace
reported earned credits: repeats, transfers, substitutions, zero-credit
courses, elective selection, and future equivalencies can make the total differ
from the university's official value.

## 10. Deterministic mapping to the Phase 5 Rules Engine

For a chosen profile, load all its attempt rows and their canonical Courses,
then map each row without inference:

```text
student_course_attempt.course.course_code
student_course_attempt.outcome
        ↓
StudentCourseAttempt(course_code, AttemptOutcome(outcome))
        ↓
evaluate_can_take(CanTakeCatalog, CanTakeRequest)
```

Course names, raw prerequisite text, grade text, GPA, credits, attempt order,
and attempt IDs are not inputs to prerequisite satisfaction. Missing rows are
missing history, not `FAILED`. For a verified prerequisite, the current engine
returns `NOT_ELIGIBLE` when Morshidi has no qualifying exact-code `PASSED`
attempt; this is limited to the history Morshidi knows and is not transcript
verification.

## 11. Future database constraints and indexes

These are design requirements for a later migration, not SQL.

### Constraints

- Profile: primary key `id`; unique `owner_user_id`; non-null owner and Study
  Plan FKs; paired-null GPA fields; non-negative GPA and earned credits;
  positive GPA scale.
- Attempt: primary key `id`; non-null profile and Course FKs; four-value
  outcome check; four-value provenance check; positive optional sequence;
  nonblank optional term/grade text; optional sequence unique within a
  profile/course when supplied.
- Database-level same-university validation for a profile's plan and each
  attempted Course; referenced-only is allowed when university ownership
  matches.
- Unknown-course input is rejected before insertion; it never mutates catalog
  data.

### Indexes

- Unique index on `student_academic_profiles.owner_user_id` for one-profile
  MVP lookup and owner RLS filtering.
- Index on `student_academic_profiles.study_plan_id` for catalog reference
  checks.
- Index on `student_course_attempts.profile_id` for owner history reads,
  deletes, and RLS joins.
- Composite index on `student_course_attempts(profile_id, course_id)` for
  deterministic history loading.
- Index on `student_course_attempts.course_id` for catalog-reference integrity
  and future catalog impact checks.

## 12. Foreign-key and deletion policy

| Relationship | Future behavior | Reason |
| --- | --- | --- |
| Auth user → profile | Cascade | Removing the account removes its private state and prevents orphan profiles. |
| Profile → attempts | Cascade | Attempts have no independent meaning after profile deletion. |
| Study Plan → profile | Restrict | Catalog plans must not be silently deleted while student state references them. |
| Course → attempt | Restrict | Catalog Course identity must remain stable while student history references it. |

The catalog already favors restrictive deletion for academic evidence. Student
profile deletion is the contained exception because it removes only user-owned
dependent records.

## 13. Future ownership, RLS, and privacy model

Authentication and RLS are not implemented in Phase 6.1. The future migration
must enable RLS on both student tables, deny `anon`, and grant only required
operations to `authenticated` after explicit policy design.

The intended ownership predicate is the profile's `owner_user_id` equal to the
authenticated subject (`auth.uid()`). Profile SELECT/INSERT/UPDATE/DELETE must
check that identity; UPDATE requires both existing-row and resulting-row checks
so ownership cannot be reassigned. Attempt policies must permit access only
through a profile owned by the same user. Policy-filter columns must be indexed.

Trusted server-side operations use a server key only where explicitly required;
that key never reaches frontend code. Frontend input may collect facts, but the
backend/database will enforce authentication, ownership, structural validation,
and catalog identity. The frontend never evaluates eligibility authoritatively.

## 14. Future API direction

Phase 5's current endpoint intentionally accepts a request-supplied history:

```text
POST /api/v1/eligibility/can-take
```

A future authenticated profile-backed operation should resolve the current
owner's profile and attempts server-side, load the same canonical catalog, and
pass the mapped `StudentCourseAttempt` values to the unchanged pure evaluator.
It may be a profile-context `POST` or a user-scoped course read; route naming
is deferred until authentication and authorization are designed. The Phase 5
request-supplied endpoint remains valuable for deterministic testing and does
not need to change the evaluator.

## 15. Implementation test matrix

| # | Future implementation case | Expected outcome |
| ---: | --- | --- |
| 1 | Create one profile for an existing Study Plan | Success. |
| 2 | Create profile for nonexistent Study Plan | Reject. |
| 3 | Create second profile for same user in MVP | Reject unique owner constraint. |
| 4 | Add `PASSED` known plan Course | Success. |
| 5 | Add `FAILED` known Course | Success. |
| 6 | Add `IN_PROGRESS` known Course | Success. |
| 7 | Add `WITHDRAWN` known Course | Success. |
| 8 | Repeat same Course with separate rows | Both attempts preserved. |
| 9 | `FAILED` then `PASSED` | Rules history satisfies exact prerequisite. |
| 10 | `PASSED` then `FAILED` | Rules history still satisfies it. |
| 11 | Duplicate `PASSED` rows | Same eligibility decision as one passed row. |
| 12 | Store same-university referenced-only Course | Allowed. |
| 13 | Request referenced-only Course as Plan target | Still rejected as target. |
| 14 | Unknown course code input | Reject; do not create catalog Course. |
| 15 | Foreign-university Course attempt | Reject invariant. |
| 16 | Leading-zero code lookup | Exact text identity preserved. |
| 17 | No attempt for a prerequisite | Not equivalent to `FAILED`; engine sees no pass. |
| 18 | `IN_PROGRESS` prerequisite | Does not satisfy. |
| 19 | GPA snapshot omitted | Allowed. |
| 20 | Negative GPA | Reject. |
| 21 | GPA without scale, or scale without GPA | Reject paired-field constraint. |
| 22 | Non-positive GPA scale | Reject. |
| 23 | Earned-credit snapshot omitted | Allowed. |
| 24 | Negative earned credits | Reject. |
| 25 | Correct/edit mistaken manual attempt | Owner may correct; timestamp updates. |
| 26 | Delete profile | Dependent attempts cascade. |
| 27 | Delete mistaken attempt | Owner may delete own row. |
| 28 | One user reads/edits another's profile | Denied by future RLS. |
| 29 | `anon` reads/writes profile or attempts | Denied. |
| 30 | Persisted history maps to Phase 5 attempts | Exact code/outcome rows only. |
| 31 | Profile-backed `1501112` + `1501110 PASSED` | `ELIGIBLE`. |
| 32 | Profile-backed `1501112` + `1501110 FAILED` | `NOT_ELIGIBLE`. |
| 33 | Profile-backed unresolved `1505311` | `REVIEW_REQUIRED`. |
| 34 | Profile-backed source conflict `1505320` | `REVIEW_REQUIRED`. |
| 35 | Profile plan change after history exists | Reject/defer to explicit future transition. |
| 36 | Attempt raw grade differs from explicit outcome | Eligibility follows explicit outcome; no grade inference. |

## 16. Known academic limitations

- No verified GPA calculation or repeat-course GPA policy exists.
- No transfer-credit model, substitution model, or course equivalency is active.
- No equivalency is inferred for `0300103` / `0300104` or `0301241` /
  `0301245`.
- Unresolved prerequisite expressions remain `REVIEW_REQUIRED`.
- Source-conflict prerequisites remain `REVIEW_REQUIRED`.
- CAN TAKE remains prerequisite eligibility only, not complete university
  registration permission.
- Student history may be incomplete until transcript verification/import is
  designed; no recorded attempt is not a recorded failure.

## 17. Future extensions

Later reviewed phases may add multiple historical profiles per user, explicit
profile status/archival, transcript reconciliation, verified university
integration, transfer-credit evaluation, approved equivalencies, grading policy,
term structure, audit history, and a profile-backed eligibility API. Each must
preserve exact course identity and the Phase 5 pure evaluator boundary.
