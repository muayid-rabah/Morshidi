# Advisor Copilot Read-Only Tools & API Specification

**Phase:** P7.5<br>
**Status:** VALIDATED<br>
**Predecessor Boundaries:** P7.4 Advisor Authorization (`apps/api/app/advisor_service/`), P7.3 Institutional Intelligence (`apps/api/app/institutional_service/`), P7.2 Institutional Demand Engine, P7.1 Contracts<br>
**Enforcement:** Strict Pre-Execution Authorization & Closed Dispatch<br>

---

## 1. Architectural Scope & Boundary Definition

The Advisor Copilot tool orchestration and API layer provides authorized human academic advisors with deterministic, read-only analytical access to a student's verified academic trajectory.

### Absolute Non-Goals & Invariants
1. **Zero LLM / External Chat in Dispatch Path:** No LLM, OpenAI, langchain, prompt template, or non-deterministic generation exists in the execution path.
2. **Zero Database Table Creation or Schema Migrations:** P7.5 introduces zero new tables or schema changes. The `supabase/migrations/` diff is exactly zero.
3. **Zero Frontend Modifications:** No changes to `apps/web`.
4. **Zero Student Record Mutation:** No tool can create, alter, or delete student academic profiles, course attempts, grades, GPA, or mock registration intents.
5. **Zero Persistent Decision Traces:** All explanations and decision traces are recomputed in-memory from verified underlying engine facts.
6. **Zero Cohort / Departmental Browsing:** Advisors cannot browse cohorts, search advisees, or enumerate all students in a department or university.

---

## 2. Machine-Locked Tool Registry

The Advisor Copilot layer defines a closed enum of exactly 11 read-only tools:

| Tool ID | Authority Class | Side Effects | Requires Target Period | Underlying Engine / Service Subsystem |
|---|---|---|:---:|---|
| `ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT` | `DETERMINISTIC_EVIDENCE` | `NONE` | No | Student Academic Profile & Attempts Repository (`app.student.repository`) |
| `ADVISOR_TOOL_GET_PROGRESS` | `DETERMINISTIC_EVIDENCE` | `NONE` | No | Pure Academic Progress Engine (`app.progress.engine`) |
| `ADVISOR_TOOL_CHECK_ELIGIBILITY` | `DETERMINISTIC_EVIDENCE` | `NONE` | No | Pure Rules Evaluator via Eligibility Service (`app.services.eligibility`) |
| `ADVISOR_TOOL_GET_RECOMMENDATIONS` | `DETERMINISTIC_EVIDENCE` | `NONE` | No | Deterministic Recommendation Engine & P4 Decision Integration (`app.recommendations.engine`, `app.decision_intelligence.recommendation`) |
| `ADVISOR_TOOL_GET_SEMESTER_PLANS` | `EPHEMERAL_SIMULATION` | `NONE` | No | Deterministic Semester Planner Engine (`app.planner.engine`) |
| `ADVISOR_TOOL_GET_DEGREE_PATHS` | `EPHEMERAL_SIMULATION` | `NONE` | No | Deterministic Degree Path Engine (`app.degree_path.engine`) |
| `ADVISOR_TOOL_GET_STUDENT_INTELLIGENCE` | `DETERMINISTIC_EVIDENCE` | `NONE` | No | Deterministic Student Intelligence Engine (`app.student_intelligence.engine`) |
| `ADVISOR_TOOL_CHECK_DELAY_CONSEQUENCE` | `DETERMINISTIC_EVIDENCE` | `NONE` | No | Decision Intelligence Delay Consequence Engine (`app.decision_intelligence.delay`) |
| `ADVISOR_TOOL_RUN_WHAT_IF` | `EPHEMERAL_SIMULATION` | `NONE` | No | Academic Digital Twin V1 Engine (`app.academic_digital_twin.engine`) |
| `ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION` | `DETERMINISTIC_EVIDENCE` | `NONE` | **Yes** | Mock Registration Student Service (`app.mock_registration_service.student_service.current`) |
| `ADVISOR_TOOL_EXPLAIN_RECOMMENDATION_DECISION` | `DETERMINISTIC_EVIDENCE` | `NONE` | No | Ephemeral Decision Intelligence Integration Trace (`app.decision_intelligence.recommendation`) |

---

## 3. Strict Pre-Execution Authorization Boundary

Every tool invocation is intercepted and gated by `AdvisorAuthorizationService.authorize_advisor_for_student` (committed in Phase P7.4) before any student data is accessed:

```
[Incoming HTTP POST /api/v1/advisor/tools/execute]
                       │
                       ▼
[1. Verify Supabase JWT & Extract Authenticated user_id]
                       │
                       ▼
[2. Step 1: P7.4 Authorization Gate]
     └── AdvisorAuthorizationService.authorize_advisor_for_student(advisor_id, student_id)
     └── Verifies active ACADEMIC_ADVISOR membership
     └── Verifies active explicit advisor_student_assignments row
     └── Verifies university match between advisor and student
     └── DENIAL -> Immediately raises 401 / 403 (Zero student data loaded)
                       │
                       ▼
[3. Step 2: Exact Student Matching Invariant Check]
     └── Assert auth_context.student_user_id == request.target_student_user_id
                       │
                       ▼
[4. Step 3: Closed Dispatch Map Resolution]
     └── Match request.tool_id against registered in-memory read-only adapters
                       │
                       ▼
[5. Step 4: Invoke In-Process Adapter & Return Allowlisted DTO]
```

---

## 4. API Endpoint Contract

### Endpoint
`POST /api/v1/advisor/tools/execute`

### Authentication
`Authorization: Bearer <supabase_jwt_token>` (Verified by `get_current_user`)

### Request Envelope (Discriminated Union on `tool_id`)

```json
{
  "target_student_user_id": "9df5428f-6ec6-4664-93b4-64d1539e20a2",
  "tool_id": "ADVISOR_TOOL_CHECK_ELIGIBILITY",
  "course_code": "1501221"
}
```

Tool-specific payloads:
- `ADVISOR_TOOL_GET_ACADEMIC_SNAPSHOT`: `{ target_student_user_id, tool_id }`
- `ADVISOR_TOOL_GET_PROGRESS`: `{ target_student_user_id, tool_id }`
- `ADVISOR_TOOL_CHECK_ELIGIBILITY`: `{ target_student_user_id, tool_id, course_code }`
- `ADVISOR_TOOL_GET_RECOMMENDATIONS`: `{ target_student_user_id, tool_id, opt_in_readiness?, limit? }`
- `ADVISOR_TOOL_GET_SEMESTER_PLANS`: `{ target_student_user_id, tool_id, max_credit_hours?, max_courses?, max_options? }`
- `ADVISOR_TOOL_GET_DEGREE_PATHS`: `{ target_student_user_id, tool_id, max_credit_hours_per_semester?, max_courses_per_semester?, max_semesters_ahead?, max_paths? }`
- `ADVISOR_TOOL_GET_STUDENT_INTELLIGENCE`: `{ target_student_user_id, tool_id }`
- `ADVISOR_TOOL_CHECK_DELAY_CONSEQUENCE`: `{ target_student_user_id, tool_id, course_code }`
- `ADVISOR_TOOL_RUN_WHAT_IF`: `{ target_student_user_id, tool_id, operation_id, target_course_code?, constraints? }`
- `ADVISOR_TOOL_GET_CURRENT_MOCK_REGISTRATION`: `{ target_student_user_id, tool_id, target_period_id }`
- `ADVISOR_TOOL_EXPLAIN_RECOMMENDATION_DECISION`: `{ target_student_user_id, tool_id, mode? }`

### Response Envelope

```json
{
  "tool_id": "ADVISOR_TOOL_CHECK_ELIGIBILITY",
  "authority_class": "DETERMINISTIC_EVIDENCE",
  "side_effects": "NONE",
  "student_user_id": "9df5428f-6ec6-4664-93b4-64d1539e20a2",
  "executed_at": "2026-09-23T15:47:50.123456Z",
  "result": {
    "course_code": "1501221",
    "decision": "ELIGIBLE",
    "is_eligible": true,
    "is_passed": false,
    "passed_note": null,
    "missing_groups": [],
    "review_reasons": [],
    "limitations": [
      "Eligibility evaluates prerequisite rule satisfaction only; does not verify section seat availability.",
      "REVIEW_REQUIRED courses require human academic authority resolution."
    ]
  }
}
```

---

## 5. Error Taxonomy & Status Mapping

| Service Error Code | HTTP Status | Description |
|---|:---:|---|
| `AUTH_REQUIRED` | 401 | Missing, malformed, or unauthenticated JWT |
| `ADVISOR_ACCESS_DENIED` | 403 | Missing `ACADEMIC_ADVISOR` role, inactive membership, inactive/missing student assignment, cross-tenant attempt, or student identity mismatch |
| `TOOL_NOT_FOUND` | 422 | Unrecognized tool ID string |
| `TOOL_INPUT_INVALID` | 422 | Missing required parameters (e.g. `target_period_id` for mock reg, course code for eligibility) |
| `DOMAIN_VALIDATION_FAILED` | 422 | Engine prerequisite or constraint validation rejection |
| `TARGET_RESOURCE_UNAVAILABLE` | 404 | Target planning period, course, or intent resource does not exist |
| `PERSISTENCE_UNAVAILABLE` | 503 | Database connectivity or upstream storage failure |

---

## 6. What-If Digital Twin Permitted Operations

The `ADVISOR_TOOL_RUN_WHAT_IF` tool strictly accepts only 3 operations from the Academic Digital Twin V1 specification:
1. `TWIN_OP_MODEL_COURSE_COMPLETION`: Models hypothetical completion of an eligible plan course.
2. `TWIN_OP_OMIT_NEXT_PLAN_COURSE`: Models delay/omission of a candidate course from next registration.
3. `TWIN_OP_SET_PLANNING_CONSTRAINTS`: Models credit hour and option limits.

Any attempt to request unmodeled operations (e.g., degree plan mutation, grade change, waiver override) is rejected with `TOOL_INPUT_INVALID` (422).
All What-If evaluations are ephemeral; authoritative student state is never modified.
