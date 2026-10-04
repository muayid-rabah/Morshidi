# Institutional Intelligence & Advisor Copilot Test Matrix

Policy version: **1.0**  
Phase: **P7.1 — Policy and Contracts Only**  
Test Matrix: `P7-TEST-*`

This matrix specifies the comprehensive suite of contract acceptance scenarios that will govern implementations in P7.2 through P7.5.

---

## 1. Test Suite Summary

| Family | ID Range | Scenario Count | Governing Phase | Primary Contract Tested |
|---|---|---:|---|---|
| Demand & Capacity Pressure | `P7-TEST-CAP-001` .. `020` | 20 | P7.2 | `institutional-capacity-pressure-policy.md` |
| Curricular Structure & Bottleneck | `P7-TEST-STR-001` .. `015` | 15 | P7.2 | `institutional-intelligence-signal-matrix.md` |
| Privacy & Suppression Propagation | `P7-TEST-PRV-001` .. `012` | 12 | P7.2 | `institutional-intelligence-policy.md` |
| Institutional Alerts | `P7-TEST-ALT-001` .. `008` | 8 | P7.2 | `institutional-alert-matrix.md` |
| Advisor Authorization & Security | `P7-TEST-AUT-001` .. `010` | 10 | P7.4 | `advisor-copilot-policy.md` |
| Advisor Copilot Orchestration | `P7-TEST-ADV-001` .. `020` | 20 | P7.5 | `advisor-copilot-tool-matrix.md` |
| **Total Scenarios** | | **85** | | |

---

## 2. Demand & Capacity Pressure Scenarios (`P7-TEST-CAP-*`)

| Scenario ID | Test Name | Input Demand | Input Capacity | Expected Deficit | Expected State | Quality / Status Flags |
|---|---|---|---|---|---|---|
| `P7-TEST-CAP-001` | Verified offered course with missing capacity | $D = 40$ (unsuppressed) | None (offering verified `OFFERED`) | `None` | `NO_CAPACITY_DATA` | `MISSING_CAPACITY_DATA`, `INSUFFICIENT_DATA`; `INST_ALERT_CAPACITY_DATA_MISSING` emitted |
| `P7-TEST-CAP-002` | Valid demand with verified capacity | $D = 50$, verified | $C = 45$, verified | $+5$ | `DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY` | `AVAILABLE`, ratio $= 1.1111$ |
| `P7-TEST-CAP-003` | Synthetic offered course with supplied capacity | $D = 30$, sandbox | $C = 30$, sandbox | $0$ | `WITHIN_SUPPLIED_CAPACITY` | `AVAILABLE`, ratio $= 1.0000$, synthetic provenance flags |
| `P7-TEST-CAP-004` | Demand strictly less than capacity | $D = 25$ | $C = 40$ | $-15$ | `WITHIN_SUPPLIED_CAPACITY` | `AVAILABLE`, ratio $= 0.6250$ |
| `P7-TEST-CAP-005` | Demand equal to capacity | $D = 35$ | $C = 35$ | $0$ | `WITHIN_SUPPLIED_CAPACITY` | `AVAILABLE`, ratio $= 1.0000$ |
| `P7-TEST-CAP-006` | Demand exceeds capacity | $D = 65$ | $C = 50$ | $+15$ | `DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY` | `AVAILABLE`, ratio $= 1.3000$ |
| `P7-TEST-CAP-007` | Verified zero capacity with positive demand | $D = 20$ | $C = 0$ (verified fact) | $+20$ | `DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY` | Ratio `NOT_APPLICABLE`, alert emitted |
| `P7-TEST-CAP-008` | Zero demand with positive capacity | $D = 0$ | $C = 30$ | $-30$ | `WITHIN_SUPPLIED_CAPACITY` | Ratio $= 0.0000$ |
| `P7-TEST-CAP-009` | Verified not-offered course with missing capacity | $D = 10$ | None (offering verified `NOT_OFFERED`) | `None` (`NOT_APPLICABLE`) | `NOT_APPLICABLE` | Capacity status `NOT_APPLICABLE`; `INST_ALERT_CAPACITY_DATA_MISSING` NOT emitted |
| `P7-TEST-CAP-010` | Missing offering facts with missing capacity | $D = 30$ | None (offering is `None`) | `None` | `NO_CAPACITY_DATA` | Both `MISSING_OFFERING_DATA` and `MISSING_CAPACITY_DATA` set; missing offering NEVER inferred as `NOT_OFFERED` |
| `P7-TEST-CAP-011` | Partial adoption coverage caveat | $D = 40$ | $C = 50$ | $-10$ | `WITHIN_SUPPLIED_CAPACITY` | Carries `OBSERVED_INTENTS_ONLY` flag |
| `P7-TEST-CAP-012` | Suppressed demand with missing capacity | $D < k$ (suppressed) | None | `None` | `SUPPRESSED` | Deficit and state both suppressed |
| `P7-TEST-CAP-013` | Suppressed demand with positive capacity | $D < k$ (suppressed) | $C = 50$ | `None` | `SUPPRESSED` | Deficit withheld to prevent reverse calculation |
| `P7-TEST-CAP-014` | Review-required intent owner volume | Multiple revisions by same owner, superseded revisions | N/A | N/A | `AVAILABLE` | Distinct owners counted once; superseded excluded; non-review demand unaffected |
| `P7-TEST-CAP-015` | Zero-credit course demand & capacity | $D = 45$ (`0200115`) | $C = 40$ | $+5$ | `DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY` | Credit load $= 0.00$, seats evaluated |
| `P7-TEST-CAP-016` | Same course across two study plans | $D_1 = 20, D_2 = 25$ | $C = 40$ (univ) | $+5$ (univ) | `DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY` | Course-level vs plan-level scope isolated |
| `P7-TEST-CAP-017` | Different target periods isolation | Period 1 vs Period 2 | Period 1 only | Isolated | Exact period evaluated | No temporal bleeding across periods |
| `P7-TEST-CAP-018` | Different universities isolation | Univ A vs Univ B | Univ A only | Univ B denied | Tenant mismatch error | Complete tenant isolation |
| `P7-TEST-CAP-019` | Capacity fact with study plan scope | $D_{\text{plan}} = 20$ | $C_{\text{plan}} = 15$ | $+5$ | `DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY` | Plan-constrained capacity evaluated |
| `P7-TEST-CAP-020` | Empty demand population | $D = 0$, unsuppressed | $C = 40$ | $-40$ | `WITHIN_SUPPLIED_CAPACITY` | Evaluates cleanly without error |

---

## 3. Curricular Structure & Bottleneck Scenarios (`P7-TEST-STR-*`)

| Scenario ID | Test Name | Course Code | Structural Properties | Observed Demand & Capacity | Expected Classification |
|---|---|---|---|---|---|
| `P7-TEST-STR-001` | Terminal elective course | `1501392` | Downstream $= 0$, parent group `RequirementType.ELECTIVE` | $D = 20, C = 25$ | `NON_GATEWAY` |
| `P7-TEST-STR-002` | One downstream dependency | Course A | Transitive downstream $= 1$, parent group `RequirementType.REQUIRED` | $D = 45, C = 50$ | `STRUCTURAL_GATEWAY` (threshold-free: any $>0$ gates curriculum) |
| `P7-TEST-STR-003` | Required Supporting course with downstream dependency | `1401101` | `SUPPORTING_REQUIRED` (`RequirementType.REQUIRED`), Transitive $= 5$ | $D = 50, C = 45$ | `STRUCTURAL_GATEWAY` (mandatory supporting course gates degree path) |
| `P7-TEST-STR-004` | Required Supporting course without downstream dependency | `1401102` | `SUPPORTING_REQUIRED` (`RequirementType.REQUIRED`), Transitive $= 0$ | $D = 30, C = 35$ | `NON_GATEWAY` (no downstream dependency) |
| `P7-TEST-STR-003` | Required Supporting course with downstream dependency | `SYNTH_SUPP_GATEWAY` | `SUPPORTING_REQUIRED` (`RequirementType.REQUIRED`), Transitive $= 5$, indispensable | $D = 50, C = 45$ | `STRUCTURAL_GATEWAY` (mandatory supporting course gates degree path) |
| `P7-TEST-STR-004` | Required Supporting course without downstream dependency | `0300101` | Canonical `SUPPORTING_REQUIRED` (`RequirementType.REQUIRED`), Transitive $= 0$ | $D = 30, C = 35$ | `NON_GATEWAY` (no downstream dependency in canonical Plan 12) |
| `P7-TEST-STR-005` | Deep transitive prerequisite chain | `1501110` | Transitive downstream $= 14$, `RequirementType.REQUIRED` | $D = 55, C = 40$ | `STRUCTURAL_GATEWAY` |
| `P7-TEST-STR-006` | Source conflict prerequisite | `1505320` | Prerequisite source conflict | $D = 25$ | Structural status `REVIEW_REQUIRED` |
| `P7-TEST-STR-007` | Required zero-credit course with downstream dependency | `1509999` | Transitive downstream $> 0$, `RequirementType.REQUIRED`, 0 credits | $D = 35, C = 30$ | `STRUCTURAL_GATEWAY` (classification does not depend on credit value) |
| `P7-TEST-STR-008` | Required zero-credit course without downstream dependency | `0200115` | Transitive downstream $= 0$, `RequirementType.REQUIRED`, 0 credits | $D = 60, C = 50$ | `NON_GATEWAY` (participates in structural model; non-gateway due to 0 downstream) |
| `P7-TEST-STR-006` | Source conflict prerequisite | `1505320` | Prerequisite source conflict (`0300103,1505311`) | $D = 25$ | Structural status `REVIEW_REQUIRED` |
| `P7-TEST-STR-007` | Required zero-credit course with downstream dependency | `SYNTH_ZERO_GATEWAY` | Transitive downstream $= 2$, `RequirementType.REQUIRED`, 0 credits, indispensable | $D = 35, C = 30$ | `STRUCTURAL_GATEWAY` (classification does not depend on credit value) |
| `P7-TEST-STR-008` | Required zero-credit course without downstream dependency | `0200115` | Canonical `UNIVERSITY_REQUIRED`, 0 credits, Transitive downstream $= 0$ | $D = 60, C = 50$ | `NON_GATEWAY` (participates in structural model; non-gateway due to 0 downstream) |
| `P7-TEST-STR-009` | Structural status unchanged by demand suppression | `1501221` | Transitive $= 6$, `RequirementType.REQUIRED` | Demand suppressed ($0 < n < k$) | `STRUCTURAL_GATEWAY` (public catalog structure immune to suppression) |
| `P7-TEST-STR-010` | Structural status unchanged by missing capacity | `1501221` | Transitive $= 6$, `RequirementType.REQUIRED` | Capacity missing (`INSUFFICIENT_DATA`) | `STRUCTURAL_GATEWAY` (decoupled from capacity availability) |
| `P7-TEST-STR-011` | Elective course with downstream dependency | `1501391` | Transitive $= 4$, parent group `RequirementType.ELECTIVE` | $D = 80, C = 40$ | `NON_GATEWAY` (elective courses are non-gateways; dependency count remains factual at 4) |
| `P7-TEST-STR-011` | Elective course with downstream dependency | `SYNTH_ELEC_GATEWAY` | Transitive $= 3$ (gates only elective courses), parent group `RequirementType.ELECTIVE` | $D = 80, C = 40$ | `NON_GATEWAY` (elective courses gating optional paths are non-gateways; dependency count remains factual at 3) |
| `P7-TEST-STR-012` | Mandatory course with OR prerequisite alternative | Course X | Transitive $> 0$, but downstream course has verified OR bypass option | Any | `NON_GATEWAY` (alternative bypass options prevent indispensable gateway status) |
| `P7-TEST-STR-013` | Mandatory classification derived from plan semantics, not whitelist | Course S | `group.requirement_type == RequirementType.REQUIRED`, Transitive $= 3$ | Any | `STRUCTURAL_GATEWAY` (derived from authoritative plan semantics, not hardcoded labels) |
| `P7-TEST-STR-013` | Mandatory classification derived from plan semantics, not whitelist | Course S | `group.requirement_type == RequirementType.REQUIRED`, Transitive $= 3$, indispensable | Any | `STRUCTURAL_GATEWAY` (derived from authoritative plan semantics, not hardcoded labels) |
| `P7-TEST-STR-014` | Structural gateway with balanced capacity | `1501221` | Transitive $= 6$, `RequirementType.REQUIRED` | $D = 30, C = 40$ ($\Delta = -10$) | `STRUCTURAL_GATEWAY` (structural status independent of deficit) |
| `P7-TEST-STR-015` | Multi-plan structural difference | Course X | Mandatory in Plan A, Elective in Plan B | Evaluated per plan | `STRUCTURAL_GATEWAY` in Plan A; `NON_GATEWAY` in Plan B |

---

## 4. Privacy & Suppression Propagation Scenarios (`P7-TEST-PRV-*`)

| Scenario ID | Test Name | Condition | Expected Privacy Behavior |
|---|---|---|---|
| `P7-TEST-PRV-001` | Demand below threshold $k$ | Contributing owners $n = 2 < 3$ | Demand count is `SUPPRESSED` |
| `P7-TEST-PRV-002` | Suppression propagation to deficit | Demand count is `SUPPRESSED`, Capacity $= 30$ | Deficit is `SUPPRESSED`; capacity arithmetic withheld |
| `P7-TEST-PRV-003` | Suppression propagation to ratio | Demand count is `SUPPRESSED`, Capacity $= 30$ | Ratio is `SUPPRESSED` |
| `P7-TEST-PRV-004` | Suppression propagation to combined alert | Demand is `SUPPRESSED`, Transitive $= 5$ | Structural status remains `STRUCTURAL_GATEWAY`; combined alert withheld |
| `P7-TEST-PRV-005` | Zero identity fields in schema | Inspect all institutional response models | Verify zero `student_id`, `user_id`, `email`, `name` |
| `P7-TEST-PRV-006` | Review-required owner count suppression | Review distinct owners $n = 1 < 3$ | Review count is `SUPPRESSED`; `INST_ALERT_REVIEW_REQUIRED_PRESENT` withheld |
| `P7-TEST-PRV-007` | No raw bypass parameter | Request with `include_raw=true` or similar | Parameter rejected or ignored; schema lacks raw fields |
| `P7-TEST-PRV-008` | Cross-filter subtraction mitigation | Sequential overlapping exact-scope queries | Scopes are independent; no automated delta API |
| `P7-TEST-PRV-009` | Multi-university tenant isolation | Request with Tenant A analyst for Tenant B | `403 INSTITUTIONAL_ACCESS_DENIED` |
| `P7-TEST-PRV-010` | Non-member user access | Authenticated student without analyst role | `403 INSTITUTIONAL_ACCESS_DENIED` |
| `P7-TEST-PRV-011` | Inactive analyst membership | Analyst user with `active = false` | `403 INSTITUTIONAL_ACCESS_DENIED` |
| `P7-TEST-PRV-012` | Minimum allowed threshold validation | Instantiate config with $k = 1$ | Raises `ValueError` ($k$ must be $\ge 2$) |

---

## 5. Institutional Alert Scenarios (`P7-TEST-ALT-*`)

| Scenario ID | Test Name | Trigger Condition | Expected Alert Emitted |
|---|---|---|---|
| `P7-TEST-ALT-001` | Capacity deficit present | $D = 55, C = 40$ | `INST_ALERT_CAPACITY_DEFICIT_DETECTED` |
| `P7-TEST-ALT-002` | Zero capacity with active demand | $D = 25, C = 0$ | `INST_ALERT_ZERO_CAPACITY_WITH_DEMAND` |
| `P7-TEST-ALT-003` | Structural bottleneck pressure | `structural_gateway_status == STRUCTURAL_GATEWAY` AND Deficit $> 0$ (unsuppressed) | `INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE` |
| `P7-TEST-ALT-004` | Review volume present | Review-required distinct owners $= 8$ (unsuppressed) | `INST_ALERT_REVIEW_REQUIRED_PRESENT` |
| `P7-TEST-ALT-005` | Verified offered course with missing capacity | Course is offered, `capacity_fact is None` | `INST_ALERT_CAPACITY_DATA_MISSING` emitted |
| `P7-TEST-ALT-006` | Missing offering with missing capacity | `offering_fact is None`, `capacity_fact is None` | Both `INST_ALERT_OFFERING_DATA_MISSING` and `INST_ALERT_CAPACITY_DATA_MISSING` emitted; missing offering NEVER inferred as `NOT_OFFERED` |
| `P7-TEST-ALT-007` | Verified not-offered course with missing capacity | `offering_fact.status == NOT_OFFERED`, `capacity_fact is None` | Capacity is `NOT_APPLICABLE`; `INST_ALERT_CAPACITY_DATA_MISSING` is NOT emitted |
| `P7-TEST-ALT-008` | Suppressed count suppresses alerts & zero side-effects | $0 < n < k$ on volume metrics | Alerts withheld; database state unchanged (zero side-effects) |

---

## 6. Advisor Authorization & Security Scenarios (`P7-TEST-AUT-*`)

| Scenario ID | Test Name | Actor / Role | Target / Parameters | Expected Authorization Outcome |
|---|---|---|---|---|
| `P7-TEST-AUT-001` | Authenticated assigned advisor | `ACADEMIC_ADVISOR` | Assigned student | Access granted (`200 OK`) |
| `P7-TEST-AUT-002` | Unassigned student access | `ACADEMIC_ADVISOR` | Unassigned student | `403 FORBIDDEN` (`ADVISOR_STUDENT_SCOPE_MISMATCH`) |
| `P7-TEST-AUT-003` | Institutional analyst role access | `INSTITUTIONAL_ANALYST` | Student profile | `403 FORBIDDEN` (Analyst has zero student read access) |
| `P7-TEST-AUT-004` | Departmental / cohort browsing attempt | `ACADEMIC_ADVISOR` | Departmental cohort query | `403 FORBIDDEN` (Cohort browsing deferred; explicit assignment required) |
| `P7-TEST-AUT-005` | Advisor snapshot without target period | `ACADEMIC_ADVISOR` | Assigned student, NO period | Access granted (`200 OK`; target period not required for snapshot) |
| `P7-TEST-AUT-006` | Advisor progress without target period | `ACADEMIC_ADVISOR` | Assigned student, NO period | Access granted (`200 OK`; target period not required for progress) |
| `P7-TEST-AUT-007` | Cross-tenant advisor access | Advisor at Univ A | Student at Univ B | `403 FORBIDDEN` |
| `P7-TEST-AUT-008` | Inactive advisor profile | Advisor with `active = false` | Assigned student | `403 FORBIDDEN` |
| `P7-TEST-AUT-009` | Expired advising assignment | Assignment expired last term | Former advisee | `403 FORBIDDEN` |
| `P7-TEST-AUT-010` | In-system waiver/override attempt | `ACADEMIC_ADVISOR` | Override prerequisite request | Rejected (`403` / `NOT_SUPPORTED`; provider-neutral facts only) |

---

## 7. Advisor Copilot Orchestration Scenarios (`P7-TEST-ADV-*`)

| Scenario ID | Test Name | Tool Invoked | Target Condition | Expected Output / Behavior |
|---|---|---|---|---|
| `P7-TEST-ADV-001` | Read student snapshot | `GET_ACADEMIC_SNAPSHOT` | Student with 45 credits (no period) | Returns verified profile, active Plan 12 |
| `P7-TEST-ADV-002` | Evaluate progress | `GET_PROGRESS` | Student progress state (no period) | Returns completed credits per group |
| `P7-TEST-ADV-003` | Check passed course eligibility | `CHECK_ELIGIBILITY` | Course already completed | Returns `ELIGIBLE` fact with passed note |
| `P7-TEST-ADV-004` | Check missing prerequisite | `CHECK_ELIGIBILITY` | Prerequisite not taken | Returns `NOT_ELIGIBLE` with missing groups |
| `P7-TEST-ADV-005` | Check ambiguous prerequisite | `CHECK_ELIGIBILITY` | Prerequisite conflict | Returns `REVIEW_REQUIRED` with conflict evidence |
| `P7-TEST-ADV-006` | Get baseline recommendations | `GET_RECOMMENDATIONS` | Normal student | Returns deterministic priority-ranked options |
| `P7-TEST-ADV-007` | Get readiness-aware recommendations | `GET_RECOMMENDATIONS` | `mode=READINESS_AWARE` | Re-orders ties under P4 rules; baseline options preserved |
| `P7-TEST-ADV-008` | Get semester plan options | `GET_SEMESTER_PLANS` | Max options $= 3$ | Returns up to 3 valid semester sets |
| `P7-TEST-ADV-009` | Get degree path projection | `GET_DEGREE_PATHS` | Multi-term simulation | Non-predictive language: "Modeled path spans N periods" |
| `P7-TEST-ADV-010` | Student intelligence difficulty | `GET_STUDENT_INTELLIGENCE` | P3 difficulty signals | Returns rule-based difficulty observations |
| `P7-TEST-ADV-011` | Predictive risk block verification | Copilot query | Any risk question | System refuses: predictive risk strictly blocked |
| `P7-TEST-ADV-012` | Check delay consequence | `CHECK_DELAY_CONSEQUENCE` | Delaying `1501221` | Returns P4 structural downstream delay facts |
| `P7-TEST-ADV-013` | What-If course completion operation | `RUN_WHAT_IF` | `ScenarioOperation(MODEL_COURSE_COMPLETION)` | Computes 16 deltas; student attempts UNCHANGED |
| `P7-TEST-ADV-014` | What-If omit course operation | `RUN_WHAT_IF` | `ScenarioOperation(OMIT_NEXT_PLAN_COURSE)` | Computes 16 deltas; student attempts UNCHANGED |
| `P7-TEST-ADV-015` | What-If planning constraints operation | `RUN_WHAT_IF` | `ScenarioOperation(SET_PLANNING_CONSTRAINTS, bundle)` | Computes deltas with `PlanningConstraintBundle` |
| `P7-TEST-ADV-016` | Read Mock Registration intent WITH period | `GET_CURRENT_MOCK_REGISTRATION` | Student has intent in target period | Returns resolved intent; advisor CANNOT edit |
| `P7-TEST-ADV-017` | Read Mock Registration intent WITHOUT period | `GET_CURRENT_MOCK_REGISTRATION` | Omit `target_period_id` | `422 UNPROCESSABLE_ENTITY` (target period required for Mock Reg) |
| `P7-TEST-ADV-018` | Explain recommendation decision trace | `EXPLAIN_RECOMMENDATION_DECISION` | Assigned advisee, `mode=READINESS_AWARE` | Returns ephemeral P4 `DecisionIntelligenceTrace` with factor rank changes |
| `P7-TEST-ADV-019` | Cross-system data isolation | Copilot query | "Show me total campus demand" | Refused: Copilot does not expose institutional aggregates |
| `P7-TEST-ADV-020` | LLM authority isolation | Provider failure / mock | Any tool execution | Tool output is deterministic; provider cannot alter facts |

