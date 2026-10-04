# Student performance foundation runtime validation (P2.1)

## Scope

P2.1 validates Phase P2's local Supabase migration and access boundaries only. It adds no schema, product, intelligence, importer, GPA, grade-policy, or API capability.

## Migration and clean replay

Two independent `supabase db reset --local --no-seed` runs completed successfully. Each replay applied six migrations in order: `0001_academic_catalog.sql`, `20260916224842_seed_ai_plan12_foundation.sql`, `20260916230222_seed_ai_plan12_courses.sql`, `20260916231030_model_ai_plan12_prerequisites.sql`, `20260917085254_create_student_academic_profile.sql`, and `20260921175041_add_student_performance_foundation.sql`.

## Runtime schema and constraints

Local `student_course_attempts` has nullable `raw_numeric_grade`, `raw_letter_grade`, `raw_grade_points`, `raw_academic_year`, `raw_term`, `attempt_credit_hours`, and `performance_source_reference`. `performance_provenance` and `performance_verification_state` are non-null with `UNVERIFIED` defaults. Runtime checks enforce the P1 provenance vocabulary, verification-state vocabulary, nonblank source reference, and require `VERIFIED` for `OFFICIAL_VERIFIED` provenance.

Legacy-style attempts insert with unchanged outcome semantics and safe null/default P2 facts. Runtime tests cover explicit PASSED/FAILED/IN_PROGRESS/WITHDRAWN outcomes without any grade-derived outcome inference.

## Access boundaries

Existing owner RLS policies passed configured local-Supabase tests. The runtime trigger `prevent_client_managed_performance_facts_on_write` protects direct authenticated-client performance-field writes; existing allowed owner behavior remains intact. Server-side repository mapping round-trips P2 facts while the public FastAPI self-service schemas neither accept nor return protected P2 fields. The pure import contract remains non-persistent and has no SIS/API endpoint.

## Test evidence

- Configured local-Supabase suite: 11 passed, 0 skipped, 2 dependency deprecation warnings (285.33s).
- Focused P2 plus Phase 5–10 regression selection: 441 passed, 2 dependency deprecation warnings (22.92s).
- Full pytest: 933 passed, 11 opt-in local-runtime tests skipped because that final command intentionally used no local environment variables, 2 dependency deprecation warnings (43.52s).

No real transcript, grade, student identifier, or credential was added to repository files during validation.

## Evidence limitations and P3 entry conditions

This validates only the P2 raw-storage boundary. Official transcript schema/identity, canonical periods, grade/GPA/repeat policy, domain taxonomy, and cohort governance remain external evidence dependencies. P3 remains prohibited until its scope and those applicable evidence gates are separately approved.

## Final acceptance

P2.1 runtime migration, local RLS, direct-client protection, repository mapping, API privacy, and regression verification are accepted.
