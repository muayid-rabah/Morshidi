# Advisor Copilot Policy

Policy version: **1.0**  
Phase: **P7.1 — Policy and Contracts Only**  
Predecessor phases: Phase 5 (Eligibility), Phase 6 (Progress), Phase 7 (Recommendations), Phase 8 (Planner), Phase 9 (Degree Paths), Phase 10 (Advisor Backend), P3 (Student Intelligence), P4 (Decision Intelligence & Delay Consequence), P5 (Digital Twin), P6 (Mock Registration).

---

## 1. Purpose

This document establishes the authoritative policy and contracts for **Advisor Copilot** within Morshidi.

Advisor Copilot is designed to empower human academic advisors by synthesizing, explaining, and surfacing deterministic student academic facts and forward-looking scenario models during advising interactions. It operates under the core system axiom:
$$\text{AI Explains} \quad \text{---} \quad \text{Rules / Auditable Models Decide}$$

Advisor Copilot acts strictly as an auditable, read-only decision-support assistant. It never replaces human academic judgment, never mutates student records, and never exercises autonomous administrative authority.

---

## 2. Definition

**Advisor Copilot** is defined as:
> A read-only, auditable academic decision-support interface that enables an authorized human academic advisor to orchestrate deterministic engines, inspect student academic state, explore non-destructive What-If scenarios, and review rule-based guidance for an assigned student.

---

## 3. Strict Non-Goals and Prohibitions

Advisor Copilot strictly **DOES NOT**:
1. Record Mutation: Never inserts, updates, or deletes student course attempts, grades, GPA, or academic standing.
2. Registration Execution: Never registers a student for courses, drops sections, or executes SIS transactions.
3. Intent Tampering: Never creates, updates, submits, or withdraws student Mock Registration intents.
4. Rule Overrides: Never bypasses prerequisite rules, overrides eligibility decisions, or grants graduation clearance.
5. Autonomous Advising: Never issues unreviewed binding advice or signs off on degree petitions automatically.
6. Student Profiling: Never ranks students, scores student merit, or infers psychological/personality traits.
7. Predictive Risk Claims: Never outputs predictive failure or dropout probabilities.

---

## 4. Advisor Authorization Model

### 4.1 Separation from Institutional Analyst
- **Critical Security Invariant:** The existing role `INSTITUTIONAL_ANALYST` grants access **ONLY** to aggregate institutional demand. It confers **ZERO** authority to access individual student records.
- **Advisor Role Requirement:** Individual student advising requires a distinct, server-enforced institutional role: `ACADEMIC_ADVISOR`.
- **Role Insufficiency:** Possession of the `ACADEMIC_ADVISOR` role is necessary but **NOT SUFFICIENT**. An advisor cannot browse students across the university, department, or faculty.

---

## 5. Advisor-Student Access Relation

Individual student access strictly requires an **Active Explicit Advisor-Student Assignment**:
1. **Active Explicit Assignment Mandatory:** The target student must be explicitly assigned to the authenticated advisor via an active assignment record (`advisor_student_assignments`).
2. **Global Authorization Foundation:** Every advisor request must bind strictly to:
   - Authenticated advisor `user_id`
   - Active `ACADEMIC_ADVISOR` role
   - Active explicit assignment record
   - Active `university_id` (matching tenant)
   - Target `student_id`
3. **Target Period is Tool-Specific, NOT Global:** `target_period_id` is **NOT** a universal advisor authorization requirement. It is required only for tools whose domain logic explicitly demands an academic planning period (such as `ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION`). Non-period tools (snapshot, progress, eligibility, recommendations, intelligence, delay) evaluate the student's current verified records without requiring a target period.
4. **Conceptual Assignment Identity (P7.4 Foundation):** The future P7.4 assignment entity is uniquely identified by:
   - `advisor_user_id`: UUID
   - `student_user_id`: UUID
   - `university_id`: UUID
   - `is_active`: bool
   - `authority_source`: str (versioned institutional assignment authority)
   - `created_at` / `updated_at`: audit timestamps
   `target_period_id` is NOT part of the assignment primary key.
5. **Departmental / Cohort Browsing Deferred:** Department-wide, faculty-wide, or cohort-wide student browsing is **DEFERRED** in V1. There is **NO** "departmental scope" bypass.
6. **Peer Advisor Isolation:** An advisor assigned to student A cannot inspect student B, even if both belong to the same academic department.
7. **Denial by Default:** Any attempt by an advisor to access an unassigned student record fails with `403 FORBIDDEN` (`ADVISOR_STUDENT_SCOPE_MISMATCH`). An institutional analyst attempting to access an individual student fails with `403 FORBIDDEN` (`ANALYST_STUDENT_ACCESS_PROHIBITED`).

---

## 6. Read-Only Boundary

Advisor Copilot is strictly **READ-ONLY**:
- All operations are read or ephemeral simulation operations.
- Zero state changes occur in authoritative academic database tables.
- All Copilot tool definitions must specify: `side_effects = NONE`.

---

## 7. Existing-Engine Composition and Reuse

Advisor Copilot **DOES NOT** duplicate academic logic. It composes the accepted deterministic backend engines:
- **Phase 5:** `evaluate_can_take` (prerequisite verification)
- **Phase 6:** `calculate_academic_progress` (group and plan credit audit)
- **Phase 7:** `recommend_courses` (deterministic candidate ranking)
- **Phase 8:** `plan_semester` (next-semester registration sets)
- **Phase 9:** `plan_degree_paths` (multi-semester simulation)
- **Phase P3:** `student_intelligence` (rule-based difficulty, readiness, strengths)
- **Phase P4:** `decision_intelligence` (decision traces, delay consequences)
- **Phase P5:** `academic_digital_twin` (ephemeral What-If simulation)
- **Phase P6:** `mock_registration` (current declared intent status)

---

## 8. Student Intelligence Boundary

Advisor Copilot exposes P3 Student Intelligence observations strictly as rule-based evidence:
- If evidence is insufficient: Surfaces `INSUFFICIENT_DATA`.
- If rules detect an anomaly: Surfaces `REVIEW_REQUIRED`.
- Prohibition: The system must never use an LLM to guess missing student intelligence or fill data gaps.

---

## 9. Decision Intelligence & Delay Consequence Reuse

Advisor Copilot leverages the Phase P4 Delay Consequence engine:
- It explains structural prerequisite bottlenecks caused by course delays.
- Language Rule: Must strictly describe **structural delays** (e.g., *"Delaying Course X prevents taking Courses Y and Z next semester"*). It must **NEVER** guarantee a calendar delay or predict a specific graduation semester.

---

## 10. Academic Digital Twin & What-If Boundary

An advisor may evaluate What-If scenarios with the student using the authoritative Phase P5 Digital Twin engine:
- **Full Operation Coverage:** Supports all three accepted V1 operations via the typed `ScenarioOperation` contract:
  1. `TWIN_OP_MODEL_COURSE_COMPLETION`: Models passing a prerequisite or gateway course (`target_course_code`).
  2. `TWIN_OP_OMIT_NEXT_PLAN_COURSE`: Models delaying or omitting a planned course (`target_course_code`).
  3. `TWIN_OP_SET_PLANNING_CONSTRAINTS`: Models adjusted credit caps and options via `PlanningConstraintBundle`.
- **Ephemeral and Non-Mutating:** Scenarios are fingerprinted in-memory models; they never mutate authoritative student attempts, transcript records, or degree audit profiles.
- **Intent Separation:** An ephemeral scenario evaluated by an advisor does **NOT** create, alter, or submit a student Mock Registration intent.

---

## 11. Mock Registration Boundary

Advisor Copilot can inspect and explain the student's latest current resolved Mock Registration intent:
- It explains submission validity and revalidation status.
- It cannot submit, amend, or withdraw Mock Registration intents on behalf of the student.
- Access requires a specific `target_period_id` because Mock Registration intents are period-scoped.

---

## 12. Degree Path Language Requirements

Advisor Copilot must communicate degree path projections with strict non-predictive precision:
- Permitted: *"Under the specified assumptions, the modeled path spans 4 future academic registration periods."*
- Strictly Forbidden: *"The student will graduate in Spring 2028."*

---

## 13. Handling of `REVIEW_REQUIRED`

Whenever an underlying engine emits `REVIEW_REQUIRED`:
1. Advisor Copilot must immediately highlight the review requirement.
2. It must present the exact conflicting or ambiguous evidence (e.g., conflicting prerequisite source versions).
3. It must formulate the precise academic policy question requiring human review.
4. It must **NEVER** allow an LLM or heuristic to resolve the ambiguity autonomously.

---

## 14. Response Authority Classification

Every response generated by Advisor Copilot carries a strict authority classification:
- `DETERMINISTIC_EVIDENCE`: Sourced directly from verified deterministic engine calculations.
- `REVIEW_REQUIRED`: Contains unverified or conflicting academic facts requiring human decision.
- `EPHEMERAL_SIMULATION`: Sourced from an unpersisted What-If scenario.
- `GENERAL_INFORMATION`: General catalog or curriculum text explanation.
- `INSUFFICIENT_CONTEXT`: Required student or catalog facts are unavailable.

---

## 15. Advisor Copilot Tool Registry

Advisor Copilot V1 defines an exact, finite registry of 11 read-only tools (`ADVISOR_TOOL_*`):
1. `ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT`: Reads authoritative student profile and progress baseline.
2. `ADVISOR_TOOL_GET_PROGRESS`: Reads requirement group and plan completion facts.
3. `ADVISOR_TOOL_CHECK_ELIGIBILITY`: Verifies prerequisite eligibility for a specific course.
4. `ADVISOR_TOOL_GET_RECOMMENDATIONS`: Retrieves deterministic priority course recommendations.
5. `ADVISOR_TOOL_GET_SEMESTER_PLANS`: Generates modeled next-semester registration options.
6. `ADVISOR_TOOL_GET_DEGREE_PATHS`: Generates simulated multi-semester paths.
7. `ADVISOR_TOOL_GET_STUDENT_INTELLIGENCE`: Reads P3 difficulty, readiness, and strength observations.
8. `ADVISOR_TOOL_CHECK_DELAY_CONSEQUENCE`: Runs P4 Delay Consequence analysis for a course.
9. `ADVISOR_TOOL_RUN_WHAT_IF`: Evaluates an isolated, ephemeral What-If scenario via the typed P5 `ScenarioOperation` contract (supports course completion, course omission, and planning constraints).
10. `ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION`: Reads current resolved intent and revalidation status for a specific planning period.
11. `ADVISOR_TOOL_EXPLAIN_RECOMMENDATION_DECISION`: Evaluates and returns the deterministic P4 decision intelligence trace (`DecisionIntelligenceTrace`) explaining baseline vs final candidate ordering, applied factors, relative order changes, and limitations.

---

## 16. Prohibition of Generic Database Tools

Advisor Copilot is strictly prohibited from possessing:
- Unrestricted SQL query tools.
- Raw ORM/Supabase client execution.
- Arbitrary student search across unauthorized tenants.
All queries must route through explicit, typed, authorized engine interfaces.

---

## 17. Student Privacy & Data Minimization

Advisor Copilot enforces strict data minimization:
- Advisors can view only academically necessary student data (attempts, transcripts, plan status).
- Private conversations between the student and the student-facing Advisor are not exposed to the human advisor unless explicitly shared by the student.
- Demographic, financial, or disciplinary records are strictly excluded from Copilot schemas.

---

## 18. Rejection of Automated Advisor Overrides
 
In V1, **NO IN-SYSTEM OVERRIDE** is supported:
- Advisors cannot click "Override Prerequisite" or grant ad-hoc exemptions inside Morshidi.
- **Provider-Neutral Fact Ingestion:** Any official waiver or prerequisite override must originate from an authoritative institutional system or governed institutional process and enter Morshidi only as a verified institutional fact.
- **No Shadow Records:** Morshidi does NOT create shadow records, does NOT accept unverified in-app advisor waivers, and does NOT assume an SIS is the only possible upstream provider.
- This maintains Morshidi strictly as an auditable intelligence system, not an unverified shadow registrar.

---

## 19. Future AI / LLM Boundary

When natural-language interaction is connected:
- The LLM will serve solely as a **Semantic Router and Explainer**.
- It translates advisor queries into structured tool calls.
- It formats deterministic structured results into professional Arabic/English prose.
- It is physically barred from computing academic eligibility, generating advice independently, or altering outputs.

---

## 20. Auditability and Logging

Every Advisor Copilot session generates an immutable audit record:
- `advisor_user_id`: Authenticated advisor UUID
- `student_user_id`: Target student UUID
- `assignment_authorization_ref`: Basis of access
- `tools_invoked`: List of tools and parameters
- `timestamp`: UTC access time
- `session_id`: Unique trace identifier

---

## 21. Implementation Phasing Split

- **P7.1:** Policy & Contracts (Documentation only - CURRENT).
- **P7.4:** Advisor Authorization & Assignment Persistence / RLS (Database tables, security policies, unit tests).
- **P7.5:** Advisor Copilot Deterministic Orchestration & API (Application services, tool handlers, read-only guards).

