# Phase 6.3 student profile repository and rules mapping

The read path is `SupabaseStudentAcademicRepository` ->
`StudentAcademicState` -> existing Phase 5 `StudentCourseAttempt` values ->
the unchanged eligibility service/evaluator. The repository accepts a trusted
explicit owner UUID; it does not resolve sessions or call Auth APIs.

It reads only `student_academic_profiles`, `student_course_attempts`, and the
nested `courses(course_code)` relation. Profile lookups filter by
`owner_user_id=eq.<owner>` at the Data API. Attempt lookups filter by profile
ID and specify `created_at.asc,id.asc`, giving deterministic output while
preserving every repeat attempt.

Each row maps only exact `courses.course_code` and the persisted closed outcome
set. Referenced-only and leading-zero codes remain exact text. Raw grade,
term, date, and record source are evidence-only and do not reach the rules
model. GPA, GPA scale, and earned credits are loaded as decimal snapshots,
without calculation or institutional-policy inference.

The adapter is GET-only and uses an injected server key only in the `apikey`
header. It exposes typed not-found, integrity, and transport errors; malformed
or incomplete rows fail the whole load rather than returning partial history.
No migrations, RLS changes, routes, frontend code, or remote Supabase access
are part of this phase. Existing RLS remains unchanged.

Repository-to-rules tests pass persisted `StudentAcademicState.attempts`
directly to the unchanged Phase 5 evaluator: `1501110` passed makes `1501112`
eligible; failed or absent makes it not eligible; either failed/passed order
is eligible; `1505311` and `1505320` remain review-required; and `0200115`
remains eligible. The opt-in local test creates two temporary local Auth users,
loads User A's Plan 12 profile and `1501110`/`0300103` attempts through the
real adapters, confirms User B receives `StudentProfileNotFound`, evaluates
the real local catalog, and deletes both users in `finally`. It requires only
runtime local environment variables and never prints or persists credentials.

Validation completed locally: 13 focused student repository/rules tests passed;
the opt-in real local student test passed; and the full API suite passed with
116 tests (one pre-existing API-local test remained opt-in). The local test's
`finally` cleanup deleted all temporary Auth users, which cascaded their
profiles and attempts. No remote Supabase project was accessed.
