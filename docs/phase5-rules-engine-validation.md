# Phase 5 Rules Engine Acceptance

## Acceptance record

- Validation date: 2026-09-17
- Git HEAD: `4c425b9` — `feat: expose deterministic eligibility API`
- Scope: deterministic CAN TAKE prerequisite eligibility for Zarqa University,
  Artificial Intelligence, Study Plan 12.
- Result: accepted. No catalog data, schema, RLS, migration, remote Supabase,
  or student-record change was made during this acceptance gate.

## Accepted architecture

```text
Local PostgreSQL / Supabase catalog
  -> SupabaseAcademicCatalogRepository (read only)
  -> CanTakeCatalog / canonical rules models
  -> evaluate_can_take (pure deterministic evaluator)
  -> EligibilityService
  -> POST /api/v1/eligibility/can-take
```

The endpoint accepts `study_plan_id`, `target_course_code`, and request-only
student attempts (`PASSED`, `FAILED`, `IN_PROGRESS`, `WITHDRAWN`). It returns
`ELIGIBLE`, `NOT_ELIGIBLE`, or `REVIEW_REQUIRED` with stable evidence and
reason codes. These are successful academic results, not registration rulings.

## Clean rebuild and catalog inventory

`supabase db reset --local --no-seed` completed from the four committed
migrations, without manual repair. The rebuilt local database matched the
accepted catalog baseline:

| Item | Result |
| --- | ---: |
| Courses | 74 |
| Known courses | 68 |
| Referenced-only courses | 6 |
| Study-plan courses | 68 |
| Dependency groups | 32 |
| Dependency options | 32 |
| Equivalencies | 0 |
| Raw-prerequisite-bearing plan rows | 38 |
| `not_applicable` | 30 |
| `verified` | 32 |
| `unresolved` | 4 |
| `source_conflict` | 2 |

The all-target, read-only local inventory retained course code, Arabic course
name, prerequisite status, raw-text presence, and canonical dependency output
for every one of the 68 selectable plan courses.

## Exhaustive eligibility validation

The acceptance harness derived targets and persisted prerequisite options from
the rebuilt local catalog, then exercised repository → service → pure evaluator.

| Cohort / history | Result |
| --- | --- |
| All 30 `not_applicable` targets, empty history | 30 / 30 `ELIGIBLE`; zero fabricated groups |
| All 32 `verified` targets, empty history | 32 / 32 `NOT_ELIGIBLE` |
| All 32 `verified` targets, exact persisted prerequisites `PASSED` | 32 / 32 `ELIGIBLE` |
| All 32 `verified` targets, `FAILED` | 32 / 32 `NOT_ELIGIBLE` |
| All 32 `verified` targets, `IN_PROGRESS` | 32 / 32 `NOT_ELIGIBLE` |
| All 32 `verified` targets, `WITHDRAWN` | 32 / 32 `NOT_ELIGIBLE` |
| All 32 verified targets: failed→passed, passed→failed, duplicate passed | 32 / 32 `ELIGIBLE` for each sequence |
| All 4 `unresolved` targets: empty, broad passed, unrelated history | Always `REVIEW_REQUIRED` |
| Both `source_conflict` targets: empty and broad passed history | Always `REVIEW_REQUIRED` |

The unresolved set was read from the database and matched `0200105`, `0200106`,
`1505311`, and `1505461`. The source-conflict set matched `1505320` and
`1505366`. Passing `0300104` and `1505311` did not make `1505320` eligible;
passing `0301245` and `1505101` did not make `1505366` eligible.

Every one of the 68 canonical targets was evaluated twice with identical input;
all structured results were identical. Input-order tests also confirm that
attempt ordering and duplicate passed attempts do not change satisfaction.

## Target and API acceptance

The live local endpoint is `POST /api/v1/eligibility/can-take`.

| Request / condition | Result |
| --- | --- |
| `0300103` and `0301241` referenced-only targets | `TARGET_NOT_IN_STUDY_PLAN`, HTTP 409 |
| Nonexistent target | `TARGET_NOT_FOUND`, HTTP 404 |
| Nonexistent study plan | `STUDY_PLAN_NOT_FOUND`, HTTP 404 |
| Numeric target course code | HTTP 422; never coerced to text |
| Target already passed, prerequisites satisfied | `ELIGIBLE` plus `has_passed_target: true` |
| Target in progress, prerequisites satisfied | `ELIGIBLE` plus `has_in_progress_target: true` |

`/docs` and `/openapi.json` expose the POST operation, its UUID plan selector,
strict text target code, attempt enum, decision enum, and structured response.
The response keeps `ELIGIBLE`, `NOT_ELIGIBLE`, and `REVIEW_REQUIRED` at HTTP
200. Request validation is 422; pure-engine invalid-request fallback is 400;
catalog integrity is 500; and catalog transport/configuration failures are 503.
Infrastructure failures are never represented as `REVIEW_REQUIRED`.

## Safety and layer audits

- Raw prerequisite text is stored, mapped, and returned as evidence only. No
  production Phase 5 code parses, splits, regexes, or derives rules from it.
- No equivalency, code similarity, name match, legacy substitution, or model
  inference exists. There are still zero equivalency rows. In particular,
  `0300103` / `0300104` and `0301241` / `0301245` are not treated as equal.
- The pure rules package imports no FastAPI, Pydantic, Supabase, httpx,
  settings, or catalog infrastructure. The catalog package imports no FastAPI
  and makes no eligibility decision. The route has no direct catalog query;
  the service only orchestrates repository and evaluator.
- The repository issues only GET requests. It exposes no mutation or RPC
  helper. Each not-applicable, unresolved, or source-conflict target performs
  four Data API reads (plan, course, plan membership, groups); a verified target
  performs five reads, adding one batched dependency-options read. There is no
  per-group N+1 option query.
- Trusted reads use server-side `SUPABASE_SECRET_KEY` only. No publishable or
  anon key is used, no secret was printed, and no real credential or
  frontend-exposed credential variable was found. The one package-lock pattern
  match was dependency integrity metadata, not a secret.
- Student attempts remain request input only: no student ID, table, profile,
  insert, update, or delete behavior was added.

## Test results

| Validation | Result |
| --- | --- |
| Normal backend `pytest` without local credentials | 99 passed, 4 skipped |
| Complete opt-in local suite after clean reset | 103 passed |
| Exhaustive rebuilt-catalog acceptance harness | 68 deterministic target evaluations; all cohort assertions passed |
| API unit tests | 26 passed |
| Service tests | 3 passed |
| Python compilation | Passed |
| `git diff --check` | Passed |

## Known limitations and follow-up

1. Student profiles and persistent attempt history do not exist yet.
2. The API temporarily uses internal `study_plan_id` UUID because the accepted
   schema lacks a safe, unique public natural study-plan selector.
3. Unresolved comma-separated prerequisite expressions remain
   `REVIEW_REQUIRED`.
4. Source conflicts remain `REVIEW_REQUIRED`.
5. No equivalency is inferred for `0300103` / `0300104` or `0301241` /
   `0301245`.
6. CAN TAKE means prerequisite eligibility only; it is not final university
   registration permission and does not cover sections, capacity, holds, GPA,
   repeat policy, or timetable constraints.

Potential future optimization should evaluate whether the four/five bounded
Data API reads can become a single catalog snapshot query without weakening the
repository boundary or changing academic semantics.
