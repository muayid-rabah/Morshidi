# Advisor Authorization & Assignment Persistence

**Document Version:** 1.0
**Phase:** Phase P7.4 — Advisor Authorization, Assignment Persistence & RLS
**Parent Contract:** Phase P7.1 (`docs/advisor-copilot-policy.md`, `docs/advisor-copilot-tool-matrix.md`, `docs/institutional-intelligence-advisor-test-matrix.md`)

---

## 1. Overview & Purpose

This document specifies the persistence architecture, security controls, Row Level Security (RLS) posture, and authorization service for **Academic Advisor** access to individual student records in Morshidi.

Under the system core axiom:
$$\text{AI Explains} \quad \text{---} \quad \text{Rules / Auditable Models Decide}$$

Advisor Copilot acts strictly as an auditable, read-only decision-support assistant. Phase P7.4 establishes **WHO** an advisor may access. It enforces explicit, auditable, server-managed advisor-to-student authority before any student academic data can be loaded.

---

## 2. The Core Authorization Predicate

Access to an individual student record by an advisor is governed by a strict conjunction:

$$\text{Authenticated User} \land \text{Active } \texttt{ACADEMIC\_ADVISOR} \text{ Role} \land \text{Active Explicit Assignment} \land \text{Tenant Consistency} \land \text{Exact Student} \implies \text{Authorized}$$

### Step-by-Step Evaluation Order:
1. **Authenticated User:** The caller must present a verified JWT identifying a valid `auth.users.id`. Unauthenticated requests immediately fail with `401 AUTH_REQUIRED`.
2. **Distinct Subject / Target:** `advisor_user_id` cannot equal `student_user_id`. Self-advising is strictly prohibited (`403 ADVISOR_STUDENT_SCOPE_MISMATCH`).
3. **Active Institutional Role:** The caller must hold an active `ACADEMIC_ADVISOR` role in `institutional_memberships` (`active = true`). Users possessing only `INSTITUTIONAL_ANALYST` or inactive memberships are denied with `403 ADVISOR_ROLE_REQUIRED`.
4. **Explicit Active Assignment:** An active assignment row must exist in `advisor_student_assignments` matching the exact `(advisor_user_id, student_user_id, university_id)` tuple where `is_active = true`. Missing or inactive assignments fail with `403 ADVISOR_STUDENT_SCOPE_MISMATCH`.
5. **Tenant Consistency Verification:** The student's authoritative university derived from `student_academic_profiles -> study_plans -> majors -> faculties -> university_id` must match the assignment's `university_id` and the advisor's active role `university_id`. Cross-tenant mismatches fail with `403 ADVISOR_STUDENT_SCOPE_MISMATCH`.
6. **Authorization Before Data Load:** Academic attempts, GPA, progress, recommendations, semester plans, and degree paths are **NEVER** loaded before steps 1–5 pass completely. Probing unauthorized or unassigned student IDs reveals zero information about student existence.

---

## 3. Database Schema & Migration

The persistence schema is defined in `supabase/migrations/20260923150000_add_advisor_authorization_persistence.sql`.

### 3.1 Role Schema Extension (`institutional_memberships`)
The existing `institutional_memberships` table check constraint is updated to include `ACADEMIC_ADVISOR`:
```sql
alter table public.institutional_memberships
  drop constraint if exists institutional_memberships_role_check,
  add constraint institutional_memberships_role_check
    check (role in ('INSTITUTIONAL_ANALYST', 'ACADEMIC_ADVISOR'));
```

### 3.2 Assignment Table (`advisor_student_assignments`)
```sql
create table public.advisor_student_assignments (
  id uuid primary key default gen_random_uuid(),
  advisor_user_id uuid not null references auth.users(id) on delete restrict,
  student_user_id uuid not null references auth.users(id) on delete restrict,
  university_id uuid not null references public.universities(id) on delete restrict,
  is_active boolean not null default true,
  authority_source text not null check (btrim(authority_source) <> ''),
  authority_version text not null check (btrim(authority_version) <> ''),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint check_advisor_student_distinct check (advisor_user_id <> student_user_id)
);
```

### 3.3 Explicit Exclusion of Speculative Fields
The following fields are strictly **EXCLUDED** from `advisor_student_assignments`:
- `target_period_id`: Target periods are tool-specific (e.g. mock registration), not global assignment identity.
- `study_plan_id`: Student plan changes over time do not invalidate the institutional advisor-student relationship.
- `department_id`, `faculty_id`, `cohort_id`: Departmental and cohort browsing is deferred in V1.
- `permission_score`, `confidence`, `advisor_rank`: Authority is deterministic and auditable; not heuristic.

### 3.4 Indexes
- **Unique Active Constraint:**
  ```sql
  create unique index idx_advisor_student_assignments_active_unique
    on public.advisor_student_assignments (advisor_user_id, student_user_id, university_id)
    where is_active;
  ```
  Prevents duplicate active authority records from creating ambiguity.
- **Composite Lookup Index:**
  ```sql
  create index idx_advisor_student_assignments_lookup
    on public.advisor_student_assignments (advisor_user_id, student_user_id, university_id, is_active);
  ```
  Ensures exact parameterized index lookups for authorization queries.

---

## 4. Row Level Security (RLS) Posture

| Resource | Actor | SELECT | INSERT | UPDATE | DELETE | Enforcement Mechanism | Rationale |
|---|---|---:|---:|---:|---:|---|---|
| `advisor_student_assignments` | Anonymous | Denied | Denied | Denied | Denied | RLS enabled; revoked privileges | Authority records are private security state. |
| `advisor_student_assignments` | Authenticated Advisor | Denied directly | Denied | Denied | Denied | RLS enabled; no authenticated policies | Advisors cannot query or self-grant authority rows via browser client. |
| `advisor_student_assignments` | Authenticated Student | Denied directly | Denied | Denied | Denied | RLS enabled; no authenticated policies | Students cannot assign advisors or tamper with assignment records. |
| `advisor_student_assignments` | Server Service Role | Granted | Granted | Granted | Granted | Service-role bypass with server validation | Provisioning and authorization occur exclusively server-side. |

---

## 5. Software Architecture

### 5.1 Persistence Layer (`apps/api/app/advisor_persistence/`)
- `models.py`:
  - `AdvisorStudentAssignmentRecord`: Immutable typed representation of a persisted database row.
  - `AdvisorAccessContext`: Minimal typed context emitted upon successful authorization:
    - `advisor_user_id: UUID`
    - `student_user_id: UUID`
    - `university_id: UUID`
    - `assignment_id: UUID`
    - `authority_source: str`
    - `authority_version: str`
- `errors.py`:
  - `AdvisorPersistenceError`: Base transport/database exception.
  - `AdvisorPersistenceIntegrityError`: Raised on integrity violations (e.g. duplicate active rows).
- `repository.py` (`SupabaseAdvisorAssignmentRepository`):
  - `load_active_assignment(advisor_user_id, student_user_id, university_id)`
  - `create_assignment(advisor_user_id, student_user_id, university_id, authority_source, authority_version, is_active=True)`
  - `load_active_advisor_memberships_for_user(subject_user_id)`
  - `load_student_authoritative_university(student_user_id)`

### 5.2 Service Layer (`apps/api/app/advisor_service/`)
- `errors.py`:
  - `AdvisorAuthorizationErrorCode`: `AUTH_REQUIRED`, `ADVISOR_ROLE_REQUIRED`, `ADVISOR_ASSIGNMENT_REQUIRED`, `ADVISOR_STUDENT_SCOPE_MISMATCH`, `ADVISOR_ACCESS_DENIED`, `PERSISTENCE_UNAVAILABLE`.
  - `AdvisorAuthorizationError`: Exception carrying error code, privacy-safe message, and HTTP status code (`401`, `403`, `503`).
- `authorization.py` (`AdvisorAuthorizationService`):
  - `authorize_advisor_for_student(authenticated_user_id, target_student_user_id) -> AdvisorAccessContext`

---

## 6. Threat Model & Security Mitigations

1. **Self-Assignment Attack:**
   - *Threat:* An advisor assigns themselves to inspect records or grant arbitrary permissions.
   - *Mitigation:* Database constraint `check (advisor_user_id <> student_user_id)` and service-level rejection.
2. **Role Spoofing via Client Claims:**
   - *Threat:* A malicious caller crafts a JWT or request parameter asserting `role=ACADEMIC_ADVISOR`.
   - *Mitigation:* Role validation strictly queries server-side `institutional_memberships` with `active = true`. Client claims are completely ignored.
3. **Analyst Privilege Escalation:**
   - *Threat:* An institutional analyst possessing `INSTITUTIONAL_ANALYST` role queries individual student data.
   - *Mitigation:* Analyst role provides zero student access. Membership lookup explicitly filters by `role = 'ACADEMIC_ADVISOR'`. Dual-role users must still hold an active explicit assignment.
4. **Cross-Tenant Assignment Corruption:**
   - *Threat:* An assignment record is injected associating an advisor from University A with a student from University B.
   - *Mitigation:* Authorization service independently resolves the student's authoritative university from their academic profile and verifies `student_univ == assignment_univ == advisor_univ`.
5. **Student Enumeration via Error Behavior:**
   - *Threat:* An attacker tests student UUIDs to see if they exist.
   - *Mitigation:* Authorization failure returns identical `403 FORBIDDEN` (`ADVISOR_STUDENT_SCOPE_MISMATCH`) whether the student exists or not. Zero student queries occur before advisor role and assignment are confirmed.
6. **Direct Supabase Mutation:**
   - *Threat:* Browser client executes `POST /rest/v1/advisor_student_assignments`.
   - *Mitigation:* Privileges are revoked from `authenticated` and `anon`. Zero write policies exist.

---

## 7. Future Phase P7.5 Boundary

Phase P7.4 establishes the foundation. In Phase P7.5:
- Advisor Copilot tools (`ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT`, `ADVISOR_TOOL_GET_PROGRESS`, etc.) will invoke `AdvisorAuthorizationService.authorize_advisor_for_student(...)` as their initial gate.
- Upon receiving `AdvisorAccessContext`, the tool dispatcher proceeds to invoke the respective deterministic domain engine with authorized tenant and student IDs.
- Zero tools, zero LLM orchestrators, and zero public routes are implemented in P7.4.
