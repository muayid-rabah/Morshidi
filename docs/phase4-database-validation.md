# Phase 4 Database and Academic Catalog Acceptance

## Acceptance record

- Validation date: 2026-09-17
- Git HEAD: `37ed973` — `feat: model AI Plan 12 prerequisites`
- Supabase project: `Morshidi` (`lzwttbjnuhdllesfuzzs`)
- Result: accepted for deterministic Rules Engine consumption, subject to the
  known academic limitations below.

## Reproducibility and migration parity

A clean local `supabase db reset --no-seed` completed without manual
intervention. It reapplied the complete committed migration chain:

1. `0001_academic_catalog.sql`
2. `20260916224842_seed_ai_plan12_foundation.sql`
3. `20260916230222_seed_ai_plan12_courses.sql`
4. `20260916231030_model_ai_plan12_prerequisites.sql`

The linked remote migration history contains the same four migrations. A
remote `supabase db push --dry-run` reported that the database is up to date.

## Foundation and catalog counts

| Item | Count |
| --- | ---: |
| Universities | 1 |
| Faculties | 1 |
| Majors | 1 |
| Academic sources | 1 |
| Study plans | 1 |
| Requirement groups | 6 |
| Known courses | 68 |
| Referenced-only courses | 6 |
| Total courses | 74 |
| Study-plan courses | 68 |
| Dependency groups | 32 |
| Dependency options | 32 |
| Course equivalencies | 0 |

The accepted hierarchy is Zarqa University → Faculty of Information Technology
→ Artificial Intelligence → Study Plan 12. The plan has 132 total credit
hours.

## Requirement structure

| Group | Required hours | Listed rows | Listed hours |
| --- | ---: | ---: | ---: |
| `UNIVERSITY_REQUIRED` | 18 | 9 | 18 |
| `UNIVERSITY_ELECTIVE` | 9 | 11 | 33 |
| `FACULTY_REQUIRED` | 21 | 8 | 21 |
| `SUPPORTING_REQUIRED` | 12 | 4 | 12 |
| `MAJOR_REQUIRED` | 63 | 23 | 63 |
| `MAJOR_ELECTIVE` | 9 | 13 | 39 |

Required hours total 132. Elective listed hours are available pools, not
additional graduation requirements.

## Workbook reconciliation

The Phase 1 workbook and rebuilt local database were compared programmatically
across all 68 listed rows for course code, Arabic name, requirement group,
credit hours, raw prerequisite text, and plan membership.

- Workbook rows / unique codes / database plan rows: 68 / 68 / 68
- Mismatches: 0
- `1505320` membership rows: 1
- Zero-credit courses: `0200115`, `1509999`
- Leading-zero course codes: preserved as text

## Prerequisites and referenced-only courses

| Prerequisite logic status | Count |
| --- | ---: |
| `not_applicable` | 30 |
| `verified` | 32 |
| `unresolved` | 4 |
| `source_conflict` | 2 |

There are 38 raw-prerequisite-bearing plan-course rows. Each of the 32
`verified` rows has exactly one source-safe dependency representation; the
four unresolved and two source-conflict rows have no dependency rows.

Referenced-only, non-selectable Zarqa University course codes are:

- `0200150`
- `0200151`
- `0201001`
- `0202001`
- `0300103`
- `0301241`

They have `catalog_status = 'referenced_only'`, no invented names, and no
Study Plan 12 membership.

Intentional unresolved rows are:

- `0200105`: `0200150,0201001`
- `0200106`: `0200151,0202001`
- `1505311`: `1505101,1505201`
- `1505461`: `1505366,1505415`

Intentional source-conflict rows are:

- `1505320`: `0300103,1505311`
- `1505366`: `0301241,1505101`

No equivalency, replacement, or legacy-code relationship is asserted for
`0300103` / `0300104` or `0301241` / `0301245`.

## Local and remote parity

Local and remote values matched for foundation counts, requirement-group
definitions, catalog-status counts, plan membership, prerequisite statuses,
referenced-only codes, dependency counts, and equivalency count.

The deterministic academic-content fingerprint is identical locally and
remotely:

`6994296916299abf7f0699a73392e2ce`

It is an MD5 hash over ordered stable values only: each plan-course row as
`course_code|name_ar|group_code|credit_hours|raw_prerequisite_text|prerequisite_logic_status`,
followed by each dependency as
`target_course_code|dependency_type|group_number|dependency_course_code`.
The canonical row ordering is by course code; no UUIDs or timestamps are
included.

## Security and integrity

For all 11 catalog tables, both local and remote checks confirmed:

- RLS enabled: 11 / 11
- Catalog RLS policies: 0
- `anon` SELECT/INSERT/UPDATE/DELETE: all false
- `authenticated` SELECT/INSERT/UPDATE/DELETE: all false

Local invariant checks reported zero violations for nameless known courses,
negative plan-course credit hours, invalid requirement bounds, duplicate course
identity, duplicate plan membership, cross-university plan courses,
cross-university dependencies, mismatched requirement-group plan ownership,
and invalid academic-source university ownership. No equivalencies exist.

`supabase db lint --local --schema public --fail-on error` completed with no
schema errors.

## Advisor review

No blocking advisor issue or performance warning was found.

- Intentional: `rls_enabled_no_policy` informational findings on catalog
  tables. End-user access has not yet been designed, and direct table
  privileges are revoked.
- Non-blocking: mutable `search_path` findings on the eight catalog trigger
  functions created by the initial schema migration.
- Supabase-owned/platform: `public.rls_auto_enable()` is reported as callable
  by `anon` and `authenticated`; it was not created by the Morshidi migration
  chain.

No new advisor finding appeared during this acceptance review.

## Known limitations

Morshidi deliberately does not infer AND/OR meaning for unresolved
comma-separated prerequisite expressions. The raw official prerequisite text
remains authoritative until academic evidence verifies the intended logic.

Morshidi also assumes no equivalency between `0300103` and `0300104`, nor
between `0301241` and `0301245`, unless a verified official source is added in
a future phase.
