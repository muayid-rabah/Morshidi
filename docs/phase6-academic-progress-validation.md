# Phase 6.5 academic progress validation

## Scope and architecture

Phase 6.5 adds a deterministic academic-progress read path only. The request
flow is: authenticated user -> owner-scoped student state -> read-only plan
snapshot -> pure progress engine -> response. It adds no recommendation,
ranking, scheduling, prediction, transcript import, grade interpretation, GPA
calculation, equivalency inference, or catalog write.

`calculate_academic_progress(catalog, student_attempts, *, reported_...)`
depends only on immutable domain values. It has no FastAPI, HTTP, Supabase,
clock, random, or AI dependency. The catalog adapter performs explicit-field
`GET` requests for the selected study plan, its requirement groups, and its
actual `study_plan_courses` memberships. Results are ordered by persisted
`display_order`, with stable identity/code tie-breakers.

## Course-state semantics

Every attempt for the exact course code participates; the latest row is not
special. The fixed priority is:

1. any `PASSED` -> `COMPLETED`
2. otherwise any `IN_PROGRESS` -> `IN_PROGRESS`
3. otherwise any `FAILED` or `WITHDRAWN` -> `ATTEMPTED_NOT_COMPLETED`
4. no attempt -> `NOT_ATTEMPTED`

Consequently, a prior pass cannot be undone by a later failure or withdrawal,
and repeated passes complete one course once. Raw grade text and raw
prerequisite text are not engine inputs.

Only actual plan memberships form the course universe. An attempted
`referenced_only` course outside the plan remains available to the existing
attempt/prerequisite paths but is absent from progress and contributes no plan
credit. No substitution or equivalency is inferred.

## Requirement groups and credit accounting

Groups come dynamically from the selected plan. Each result exposes identity,
names, scope/type, required and listed credits, completed listed credits,
credited progress, factual in-progress listed credits, remaining credits,
state counts, total listed count, and `is_satisfied`.

For every group:

`credited_toward_requirement = min(completed_listed_credits, required_credits)`

`remaining_required_credits = max(required_credits - credited_toward_requirement, 0)`

For an elective group, reaching the persisted credit target is sufficient;
all listed options are not mandatory. Thus Plan 12 University Elective and
Major Elective each use their 9-credit target even though their available
pools are larger. Excess completed options remain visible in
`completed_listed_credits` but cannot inflate credited plan progress.

For a required group, both the persisted credit condition and completion of
every listed course are required. This deliberately keeps the mandatory
zero-credit courses `0200115` and `1509999` relevant: each contributes zero
credits but an incomplete row prevents its required group from being
satisfied.

Overall completed plan credits are the sum of group credited amounts, capped
at `study_plans.total_credit_hours`. Remaining plan credits are bounded at
zero. In-progress plan credits are a separate factual sum of in-progress plan
memberships and are never described as earned. `all_modeled_plan_requirements_satisfied`
means only that these modeled groups are satisfied; it is not official
graduation clearance.

## Reported and derived facts

The response preserves `reported_cumulative_gpa`, `reported_gpa_scale`, and
`reported_earned_credit_hours` unchanged. They are intentionally separate from
`completed_plan_credits`. The engine neither calculates GPA nor reconciles
reported earned credits against derived plan credits.

## API

`GET /api/v1/me/academic-progress` is bearer-authenticated through the existing
`get_current_user` boundary. It accepts no owner, plan, or attempt inputs. The
service loads only the verified owner's profile and uses that profile's plan.
Missing profiles map to 404, catalog integrity failures to 500, and transport
or configuration failures to 503 through existing handlers.

## Validation evidence

- Focused progress/repository/service/API suite: 45 passed.
- Full normal suite: 176 passed, 8 local-only tests skipped when local
  environment variables are absent.
- Full suite with every local-only integration enabled: 184 passed.
- Opt-in local suite: 4 passed using the real local Supabase student and
  catalog repositories, service, engine, Auth boundary, and API.
- Real Plan 12 assertions: 132 total credits, six groups, 68 plan-course rows,
  both elective targets at 9, and both required zero-credit courses present.
- Scenarios validated: empty history; passed; failed then passed; repeated
  pass; referenced-only pass; elective over-completion; and a required group
  whose credit target is met while a zero-credit course remains incomplete.
- The authenticated local flow preserved reported GPA/earned-credit facts and
  denied User B access to User A progress.
- Temporary local users and their cascade-owned student rows are removed by
  test cleanup.
- OpenAPI documents the secured, parameter-free progress operation and all
  nested response enums/models.
- Python compilation and repository diff hygiene are part of final validation.

No migration, RLS/policy, frontend, or remote Supabase change was made.

## Known limitations

- Derived plan progress is not official graduation clearance.
- There is no GPA calculation.
- There is no transfer-credit, equivalency, or substitution model.
- There is no institutional graduation-rule engine (for example residency or
  minimum-GPA policy).
- Reported earned credits may differ from derived plan credits.
- Recommendations, course priority, semester planning, and graduation-date
  prediction are outside this phase.
