# Phase 6.4 student profile API validation

## Architecture and authentication

Authenticated self-service requests use FastAPI's bearer security dependency.
The bearer value is verified server-side with `GET /auth/v1/user`; the backend
does not trust locally decoded JWT claims. The verified response is reduced to
`CurrentUser(user_id)`. A shared lifespan-owned `httpx.AsyncClient` serves Auth
and Data API calls, and credentials are never placed in response bodies or
application logs.

The request path is: verified current user -> `StudentService` -> explicit
owner-scoped student repository operation. Eligibility continues through the
existing `EligibilityService` and unchanged Phase 5 evaluator.

## Routes

- `GET|POST|PATCH|DELETE /api/v1/me/academic-profile`
- `GET|POST /api/v1/me/academic-profile/attempts`
- `PATCH|DELETE /api/v1/me/academic-profile/attempts/{attempt_id}`
- `GET /api/v1/me/eligibility/{target_course_code}`

The existing request-backed `POST /api/v1/eligibility/can-take` remains
unchanged.

## Contracts and ownership

Profile creation accepts `study_plan_id` and optional reported GPA, GPA scale,
and earned-credit facts. GPA and scale remain paired. Profile updates accept
only the three reported summary fields; `study_plan_id` is immutable because a
safe plan transition would require a separate atomic compatibility workflow.
Responses omit `owner_user_id` and include profile identity, plan, reported
facts, and timestamps.

Attempt creation accepts an exact strict-text `course_code`, explicit outcome,
and the existing optional sequence, term, date, raw-grade, and source fields.
Optional term and raw-grade text is rejected when empty or whitespace-only, in
agreement with the database constraints, so invalid client values map to 422
rather than an infrastructure error.
Updates omit course identity, profile identity, ownership, IDs, and creation
time. Responses expose the attempt ID and course code rather than `course_id`.
Raw grade text is evidence only and never changes outcome.

Profile writes filter by the verified owner ID. Attempt writes first resolve
that owner's immutable profile ID and then filter by both profile and attempt
ID. A foreign attempt is indistinguishable from a missing attempt. Profile
deletion relies on the existing FK cascade and never touches catalog data.

## Exact course resolution

Attempt creation derives the plan university through study plan -> major ->
faculty, then resolves the exact course-code text. Leading zeroes are preserved;
there is no trimming, normalization, fuzzy/name matching, course creation, or
equivalency inference. Same-university known and `referenced_only` courses are
accepted. Missing codes and codes found only at another university are distinct
typed failures.

## HTTP mapping

- `401`: missing, malformed, invalid, or expired bearer token
- `404`: profile, attempt, course, plan, or eligibility target missing
- `409`: duplicate profile, university mismatch, or target outside the plan
- `422`: strict request validation or invalid paired profile facts
- `500`: persisted catalog/student integrity failure
- `503`: repository/configuration transport failure
- `200`: all academic decisions, including `REVIEW_REQUIRED`

## Validation

Focused auth, repository-write, and student API tests cover all four attempt
outcomes, repeats, immutable identities, exact/leading-zero/referenced-only
codes, cross-owner denial, and every required profile-backed eligibility case.
The normal suite collects 154 tests and passes 148 with six local-only tests
skipped when their environment is absent.

The opt-in authenticated local E2E passed using local Supabase Auth, the real
FastAPI app, both real repositories, the catalog, RLS, and the Phase 5 engine.
It verified `1501112` eligibility from a passed `1501110`, exact `0300103`
history, repeat-attempt semantics, update/delete behavior, User B isolation,
and profile cascade deletion. Cleanup left zero temporary users and profiles.
The student-table policy count remained eight. No migration, RLS change,
frontend change, or remote Supabase access occurred.

OpenAPI contains all self-service paths, bearer security requirements, strict
course-code request schemas, the four-value attempt enum, and the existing
three-value eligibility decision enum. Python compilation and repository diff
hygiene pass.

## Known limitations

Study-plan and attempt-course identities are immutable in this phase. There is
no transcript import, GPA calculation, recommendation/planning feature, grade
interpretation, equivalency inference, or student UI.
