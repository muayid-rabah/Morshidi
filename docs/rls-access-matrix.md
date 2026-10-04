# Morshidi System-Wide RLS and Access Matrix

**Document Version:** 1.0
**Phase Coverage:** Phase P6 (Mock Registration) & Phase P7.4 (Advisor Authorization & Assignment Persistence)

---

## 1. Governance Principles

Row Level Security (RLS) and table privilege grants are complementary, defense-in-depth controls:
1. Every exposed relational table must have RLS enabled.
2. Privileges on security-critical or authority-bearing tables are revoked from `public`, `anon`, and `authenticated` roles by default.
3. Server credentials (`service_role`) bypass RLS; application services utilizing `service_role` must enforce strict tenant isolation, actor authentication, and exact parameterized queries before reading or writing data.
4. Client self-service is prohibited on authority-bearing records.

---

## 2. Table-by-Table RLS Matrix

| Resource / Table | Actor Role | SELECT | INSERT | UPDATE | DELETE | Scope Condition / Filter | Enforcement Layer | Security Rationale |
|---|---|---:|---:|---:|---:|---|---|---|
| `mock_registration_target_periods` | Anonymous | No | No | No | No | None | RLS + Revoked Grants | Period identity and status are private. |
| `mock_registration_target_periods` | Student | No direct | No | No | No | Accessible only via owner-scoped service API | Application Service | Prevents tampering with official/synthetic period state. |
| `mock_registration_target_periods` | Institutional Analyst | No direct | No | No | No | Scoped through aggregate demand service | Application Service | Analyst inspects aggregate demand, not provider facts. |
| `mock_registration_target_periods` | Academic Advisor | No direct | No | No | No | Tool-specific evaluation context only | Application Service | Advisor inspects student intent for a specific period. |
| `mock_registration_target_periods` | Service Role | Yes | Controlled | Controlled | No delete | Exact university + provider namespace | Service Role | Provider-managed period authority. |
| `mock_registration_intent_revisions` | Anonymous | No | No | No | No | None | RLS + Revoked Grants | Intent revisions are private student records. |
| `mock_registration_intent_revisions` | Student Owner | Yes | No direct | No | No | `(select auth.uid()) = owner_user_id` | RLS Policy | Students may read their own history; writes require validation CAS. |
| `mock_registration_intent_revisions` | Other Student | No | No | No | No | Ownership predicate fails | RLS Policy | Prevents Insecure Direct Object References (IDOR). |
| `mock_registration_intent_revisions` | Institutional Analyst | No direct | No | No | No | No raw-row policy | Application Service | Analyst receives privacy-suppressed aggregates only. |
| `mock_registration_intent_revisions` | Academic Advisor | No direct | No | No | No | Via `AdvisorCopilotService` (P7.5) | Application Service | Read-only inspection of assigned advisee intent only. |
| `mock_registration_intent_revisions` | Service Role | Yes | Yes (Stored Proc) | No | Retention only | Tenant-scoped repository queries | Service Role | Atomic immutable revision persistence. |
| `mock_registration_intent_courses` | Anonymous | No | No | No | No | None | RLS + Revoked Grants | Course selections are private student data. |
| `mock_registration_intent_courses` | Student Owner | Yes | No direct | No | No | Parent revision `owner_user_id = (select auth.uid())` | RLS Policy | Owner read access; immutable atomic child persistence. |
| `mock_registration_intent_courses` | Other Student | No | No | No | No | Ownership predicate fails | RLS Policy | Prevents BOLA/IDOR disclosure of course selections. |
| `mock_registration_intent_courses` | Institutional Analyst | No direct | No | No | No | No raw-row policy | Application Service | Suppressed aggregate demand only. |
| `mock_registration_intent_courses` | Academic Advisor | No direct | No | No | No | Via `AdvisorCopilotService` (P7.5) | Application Service | Assigned student inspection only. |
| `mock_registration_intent_courses` | Service Role | Yes | Yes (Stored Proc) | No | Retention only | Exact revision foreign key | Service Role | Normalized child selections. |
| `institutional_memberships` | Anonymous | No | No | No | No | None | RLS + Revoked Grants | Membership records are private security data. |
| `institutional_memberships` | Authenticated Users | No direct | No | No | No | Server-side role resolution only | RLS + Revoked Grants | Users cannot inspect or self-grant institutional roles. |
| `institutional_memberships` | Service Role | Yes | Governed | Governed | Governed | Exact `subject_user_id`, `university_id`, `role` | Service Role | Server-managed role provisioning. |
| `advisor_student_assignments` | Anonymous | No | No | No | No | None | RLS + Revoked Grants | Assignment records are authority-bearing security data. |
| `advisor_student_assignments` | Authenticated Advisor | No direct | No | No | No | Server-side authorization service only | RLS + Revoked Grants | Advisors cannot query or self-grant authority rows via browser client. |
| `advisor_student_assignments` | Authenticated Student | No direct | No | No | No | Server-side authorization service only | RLS + Revoked Grants | Students cannot assign advisors or mutate assignment rows. |
| `advisor_student_assignments` | Service Role | Yes | Yes | Yes | Yes | Exact `advisor_user_id`, `student_user_id`, `university_id` | Service Role | Trusted server-side authorization and administrative provisioning. |

---

## 3. Policy Minimization Rationale

For `advisor_student_assignments`:
- **RLS Enabled:** True.
- **Anon Policies:** 0.
- **Authenticated Direct Write Policies:** 0.
- **Authenticated Direct Read Policies:** 0.
- **Enforcement Principle:** All advisor authorization decisions occur server-side through `AdvisorAuthorizationService` with parameter-bound repository queries. Direct client database access to authority-bearing assignment tables is unnecessary and prohibited.
