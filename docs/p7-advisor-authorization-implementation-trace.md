# Phase P7.4 Implementation & Verification Trace: Advisor Authorization, Assignment Persistence & RLS

**Phase:** P7.4
**Date:** 2026-09-23
**Status:** VALIDATED
**Predecessor Commits:** `ae86728` (P7.3), `aaf6f40` (P7.2), `0455ed5` (P7.1)

---

## 1. Traceability Matrix: Contracts to Implementation

| Contract Requirement | Architectural Layer | Implementation Symbol | Verification / Test Symbol | Result |
|---|---|---|---|:---:|
| `ACADEMIC_ADVISOR` Role Persistence | Database Schema | `institutional_memberships_role_check` in `20260923150000_add_advisor_authorization_persistence.sql` | `test_sql_migration_file_static_verification` | **PASSED** |
| Explicit Assignment Table | Database Schema | `public.advisor_student_assignments` in `20260923150000_add_advisor_authorization_persistence.sql` | `test_sql_migration_file_static_verification` | **PASSED** |
| Self-Assignment Disallowed | Schema & Repository | `check_advisor_student_distinct` & `create_assignment` validation | `test_self_assignment_rejected_by_service_and_db_constraint` | **PASSED** |
| Unique Active Authority | Database Index | `idx_advisor_student_assignments_active_unique` (`where is_active`) | `test_sql_migration_file_static_verification` | **PASSED** |
| RLS Posture | Security & Grants | `enable row level security`, `revoke all`, `grant to service_role` | `test_advisor_cannot_self_grant_assignment_via_rls`, `test_student_cannot_grant_assignment_via_rls` | **PASSED** |
| Typed Assignment Entity | Persistence Model | `AdvisorStudentAssignmentRecord` (`apps/api/app/advisor_persistence/models.py`) | `test_supabase_repository_load_active_assignment_transport` | **PASSED** |
| Typed Access Context | Authorization Model | `AdvisorAccessContext` (`apps/api/app/advisor_persistence/models.py`) | `test_p7_aut_001_authenticated_assigned_advisor_access_granted` | **PASSED** |
| Scoped Assignment Repository | Repository | `SupabaseAdvisorAssignmentRepository` (`apps/api/app/advisor_persistence/repository.py`) | `test_exact_query_scoping_no_bulk_loading`, `test_supabase_repository_*` | **PASSED** |
| Finite Error Hierarchy | Service Errors | `AdvisorAuthorizationErrorCode` & `AdvisorAuthorizationError` (`apps/api/app/advisor_service/errors.py`) | `test_unauthenticated_request_rejected_with_401`, `test_persistence_unavailable_maps_to_503` | **PASSED** |
| Predicate Authorization Engine | Service Layer | `AdvisorAuthorizationService.authorize_advisor_for_student` (`apps/api/app/advisor_service/authorization.py`) | Canonical scenarios 001–010 & supplemental suite | **PASSED** |

---

## 2. Canonical Authorization Test Scenarios (`docs/institutional-intelligence-advisor-test-matrix.md`)

| Canonical ID | Test Scenario Description | Actor / Target | Expected Behavior | Pytest Test Function | Status |
|---|---|---|---|---|:---:|
| `P7-TEST-AUT-001` | Authenticated assigned advisor | Active `ACADEMIC_ADVISOR` + Active assignment | Access granted (`200 OK`, `AdvisorAccessContext` returned) | `test_p7_aut_001_authenticated_assigned_advisor_access_granted` | **PASSED** |
| `P7-TEST-AUT-002` | Unassigned student access | Active `ACADEMIC_ADVISOR` + Unassigned student | `403 FORBIDDEN` (`ADVISOR_STUDENT_SCOPE_MISMATCH`) | `test_p7_aut_002_unassigned_student_access_rejected` | **PASSED** |
| `P7-TEST-AUT-003` | Institutional analyst role access | `INSTITUTIONAL_ANALYST` only | `403 FORBIDDEN` (`ADVISOR_ROLE_REQUIRED`, zero student access) | `test_p7_aut_003_institutional_analyst_role_access_rejected` | **PASSED** |
| `P7-TEST-AUT-004` | Departmental / cohort browsing attempt | Target student omitted / cohort query | `403 FORBIDDEN` (Cohort browsing deferred; explicit assignment required) | `test_p7_aut_004_departmental_or_cohort_browsing_attempt_rejected` | **PASSED** |
| `P7-TEST-AUT-005` | Advisor snapshot without target period | Assigned student, NO period | Access granted (`200 OK`; target period not required) | `test_p7_aut_005_advisor_snapshot_without_target_period_access_granted` | **PASSED** |
| `P7-TEST-AUT-006` | Advisor progress without target period | Assigned student, NO period | Access granted (`200 OK`; target period not required) | `test_p7_aut_006_advisor_progress_without_target_period_access_granted` | **PASSED** |
| `P7-TEST-AUT-007` | Cross-tenant advisor access | Advisor at Univ A, Student at Univ B | `403 FORBIDDEN` (`ADVISOR_STUDENT_SCOPE_MISMATCH`) | `test_p7_aut_007_cross_tenant_advisor_access_rejected` | **PASSED** |
| `P7-TEST-AUT-008` | Inactive advisor profile | Advisor with `active = false` | `403 FORBIDDEN` (`ADVISOR_ROLE_REQUIRED`) | `test_p7_aut_008_inactive_advisor_profile_rejected` | **PASSED** |
| `P7-TEST-AUT-009` | Expired / inactive advising assignment | Assignment with `is_active = false` | `403 FORBIDDEN` (`ADVISOR_STUDENT_SCOPE_MISMATCH`) | `test_p7_aut_009_expired_or_inactive_advising_assignment_rejected` | **PASSED** |
| `P7-TEST-AUT-010` | In-system waiver/override attempt | Prerequisite override request | Rejected (`403` / `NOT_SUPPORTED`; read-only boundary preserved) | `test_p7_aut_010_in_system_waiver_override_attempt_rejected` | **PASSED** |

---

## 3. Supplemental Security & Integrity Verification

| Scenario / Invariant | Purpose | Test Function | Status |
|---|---|---|:---:|
| Unauthenticated Access | Unauthenticated request rejected with HTTP 401 | `test_unauthenticated_request_rejected_with_401` | **PASSED** |
| Self-Assignment Disallowed | Rejection in service layer and database schema | `test_self_assignment_rejected_by_service_and_db_constraint` | **PASSED** |
| Dual-Role User Without Assignment | Dual-role user (analyst + advisor) still requires explicit student assignment | `test_dual_role_user_without_assignment_rejected` | **PASSED** |
| Dual-Role User With Assignment | Dual-role user with explicit assignment succeeds | `test_dual_role_user_with_active_assignment_granted` | **PASSED** |
| Role Spoofing Rejected | Untrusted token/client claims ignored; server membership checked | `test_role_spoofing_via_client_claims_rejected` | **PASSED** |
| Authorization Before Data Load | Spy repository verifies zero student attempts, progress, or profile data loaded on denial | `test_authorization_before_student_data_load_enforced` | **PASSED** |
| Persistence Failure Mapping | Network/DB failure maps to 503 PERSISTENCE_UNAVAILABLE (does not mask as missing assignment) | `test_persistence_unavailable_maps_to_503` | **PASSED** |
| Multi-University Advisor Matching | Advisor with roles in multiple universities resolves to correct tenant | `test_multi_university_advisor_exact_tenant_resolution` | **PASSED** |
| Negative Lookup Not 500 | Missing assignment returns privacy-safe 403, not unhandled 500 error | `test_negative_assignment_lookup_is_not_500` | **PASSED** |
| Strict Parameterized Scoping | Repository queries enforce parameterized lookup (no bulk loading or python filtering) | `test_exact_query_scoping_no_bulk_loading` | **PASSED** |
| Supabase Assignment Load Transport | Mock HTTPX transport verification for assignment lookup | `test_supabase_repository_load_active_assignment_transport` | **PASSED** |
| Supabase Assignment Create Transport | Mock HTTPX transport verification for assignment insert | `test_supabase_repository_create_assignment_transport` | **PASSED** |
| Supabase Tenant University Transport | Mock HTTPX transport verification for student tenant lookup | `test_supabase_repository_load_student_authoritative_university_transport` | **PASSED** |
| Static SQL Migration Verification | Verifies table name, column definitions, excluded fields, constraints, and RLS | `test_sql_migration_file_static_verification` | **PASSED** |
| RLS Advisor Self-Grant Guard | Verifies authenticated users cannot insert/update assignments via RLS | `test_advisor_cannot_self_grant_assignment_via_rls` | **PASSED** |
| RLS Student Grant Guard | Verifies students cannot create or mutate advisor assignments via RLS | `test_student_cannot_grant_assignment_via_rls` | **PASSED** |
| Strict Non-Goals Check | Verifies zero tools, zero LLM, zero OpenAI, and zero public routes exist in P7.4 packages | `test_advisor_persistence_and_service_have_no_tools_or_llm` | **PASSED** |

---

## 4. Acceptance Criteria Validation Summary

- [x] Canonical role `ACADEMIC_ADVISOR` supported and enforced.
- [x] Role `INSTITUTIONAL_ANALYST` confers zero authority to view individual student data.
- [x] Explicit `advisor_student_assignments` table implemented with university scope.
- [x] `target_period_id` excluded from assignment table by contract.
- [x] Departmental, faculty, and cohort browsing deferred.
- [x] Active advisor role and active assignment both required.
- [x] Exact student ID match enforced.
- [x] Student authoritative university verified from academic profile.
- [x] Authorization evaluated strictly before any academic student data load.
- [x] Self-assignment rejected at schema and service layers.
- [x] RLS enabled, all privileges revoked from `public`, `anon`, and `authenticated`; granted strictly to `service_role`.
- [x] All 10 canonical scenarios mapped and passing without deviation.
- [x] All regressions green (P7.3, P7.2, P6, rules, progress, eligibility, recommendations, planner, paths, full suite).
