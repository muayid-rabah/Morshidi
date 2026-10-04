# Morshidi Persistence & Authorization Threat Model

**Document Version:** 1.0
**Phase Coverage:** Phase P6 (Mock Registration) & Phase P7.4 (Advisor Authorization & Assignment Persistence)

---

## 1. Trust Boundaries & Taxonomy

The system enforces strict boundary transitions:
- `CLIENT_UNTRUSTED`: Raw requests from web browsers, mobile apps, or external callers.
- `AUTHENTICATED_IDENTITY`: Verified subject identity established by Supabase Auth (`auth.users.id`).
- `AUTHORIZED_INSTITUTIONAL_MEMBERSHIP`: Server-managed role state in `institutional_memberships` (`INSTITUTIONAL_ANALYST`, `ACADEMIC_ADVISOR`). Client token metadata claims are never trusted.
- `AUTHORIZED_ADVISOR_ASSIGNMENT`: Server-managed active explicit assignment in `advisor_student_assignments`.
- `AUTHORITATIVE_ACADEMIC_STATE`: Server-side academic profiles, catalog plans, and verified course attempts.
- `PRIVILEGED_SERVICE_ROLE`: Server-side backend executing with service-role database credentials.

---

## 2. Threat Analysis & Mitigations

### 2.1 Advisor Authorization & Assignment Threats (Phase P7.4)

| Threat | Attack Path | Trust Boundary | Primary Control | Secondary Control | Failure Mode | Residual Limitation |
|---|---|---|---|---|---|---|
| Self-Assignment Attack | Advisor attempts to create assignment over themselves | `CLIENT_UNTRUSTED` to `AUTHORIZED_ADVISOR_ASSIGNMENT` | Database check constraint `check (advisor_user_id <> student_user_id)` | Service layer validates `auth_user_id != target_student_id` | `403 ADVISOR_STUDENT_SCOPE_MISMATCH`; insert rejected | Database administrator operating outside application |
| Role-Only Escalation | Advisor with active role attempts to access unassigned student | `AUTHENTICATED_IDENTITY` to `AUTHORITATIVE_ACADEMIC_STATE` | `AdvisorAuthorizationService` requires active explicit assignment | Scoped query `where is_active = true` returns empty | `403 ADVISOR_STUDENT_SCOPE_MISMATCH`; zero student data loaded | None; strict zero-trust per student record |
| Assignment-Only Escalation | Inactive or de-authorized advisor attempts to use stale assignment | `AUTHENTICATED_IDENTITY` to `AUTHORIZED_ADVISOR_ASSIGNMENT` | `AdvisorAuthorizationService` verifies active `ACADEMIC_ADVISOR` membership first | Inactive membership rejects before assignment lookup | `403 ADVISOR_ROLE_REQUIRED`; access denied | None; dual-condition gate |
| Inactive Assignment Replay | Advisor attempts to use expired / revoked assignment row | `AUTHENTICATED_IDENTITY` to `AUTHORIZED_ADVISOR_ASSIGNMENT` | Repository query filters strictly `is_active = true` | Unique active index prevents ambiguous active rows | `403 ADVISOR_STUDENT_SCOPE_MISMATCH` | Historical audit rows preserved for governance |
| Cross-Tenant Assignment Corruption | Mismatched assignment pairs Advisor at Univ A with Student at Univ B | `AUTHORIZED_ADVISOR_ASSIGNMENT` to `AUTHORITATIVE_ACADEMIC_STATE` | Service resolves authoritative student university from academic profile | Verifies `student_univ == assignment_univ == advisor_univ` | `403 ADVISOR_STUDENT_SCOPE_MISMATCH`; tenant mismatch flagged | Corrupted profile record requires registrar remediation |
| Student Enumeration via Error Probing | Attacker probes student UUIDs to determine existence | `CLIENT_UNTRUSTED` to `AUTHENTICATED_IDENTITY` | Authorization evaluated before student existence or data lookup | Uniform `403 ADVISOR_STUDENT_SCOPE_MISMATCH` returned regardless of student presence | Zero existence signal leaked to unauthorized caller | Timing differences minimized by early failure exits |
| Direct Supabase Table Mutation | Malicious browser client invokes Supabase REST API directly | `CLIENT_UNTRUSTED` to database | RLS enabled; all privileges revoked from `anon` and `authenticated` | Zero client write policies exist on `advisor_student_assignments` | Database rejects operation with 401/403 | Service-role secret must never be exposed to clients |
| Institutional Analyst Escalation | User with `INSTITUTIONAL_ANALYST` role queries student record | `AUTHORIZED_INSTITUTIONAL_MEMBERSHIP` to `AUTHORITATIVE_ACADEMIC_STATE` | Service requires explicit `ACADEMIC_ADVISOR` role; analyst role ignored | Separate endpoints and authorization models | `403 ADVISOR_ROLE_REQUIRED`; analyst denied | Dual-role users must have active explicit assignment |
| Automated Override / Waiver Tampering | Advisor attempts to bypass prerequisites via copilot | `CLIENT_UNTRUSTED` to `AUTHORITATIVE_ACADEMIC_STATE` | Advisor system is strictly read-only decision support | Zero waiver or override methods implemented in service or repo | Request rejected; provider-neutral facts only | Official institutional waivers managed in external SIS |

---

### 2.2 Mock Registration Persistence Threats (Phase P6)

| Threat | Attack Path | Trust Boundary | Primary Control | Secondary Control | Failure Mode |
|---|---|---|---|---|---|
| Student submits another owner's ID | Add or replace `owner_user_id` in command | `CLIENT_UNTRUSTED` to `AUTHENTICATED_IDENTITY` | API derives owner strictly from verified `auth.users.id` | Repository requires derived owner in key predicate | `401` or privacy-safe `404` |
| Direct Supabase Insert on Revision Tables | Browser writes intent tables directly | Browser to database schema | No student INSERT grant or policy on revision tables | RPC / stored procedure execution restricted to `service_role` | Database rejects direct table write |
| Replay / Concurrency Races | Retrying timed-out requests or concurrent writes | Client to serialization point | Compare-and-swap on `expected_current_revision` | Advisory lock on composite intent key | `409 REVISION_CONFLICT` or `IDEMPOTENT_REPLAY` |
| Small-Cohort Privacy Inference | Repeated narrow plan queries to unmask student identity | Aggregate API to caller | Deterministic $k$-anonymity suppression ($k=5$) | Zero row counts or student identifiers emitted | Suppressed metrics returned (`value: None`) |
