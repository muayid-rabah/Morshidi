# Institutional Intelligence Policy

Policy version: **1.0**  
Phase: **P7.1 — Policy and Contracts Only**  
Predecessor phases: Phase 1–10 (core academic stack), P3 (Student Intelligence), P4 (Decision Intelligence & Delay Consequence), P5 (Academic Digital Twin & What-If), P6 (Mock Registration & Institutional Demand).

---

## 1. Purpose

This document establishes the authoritative policy and contracts for **Institutional Intelligence** within Morshidi.

Morshidi is an **Academic Intelligence Operating System** grounded in the foundational principle:
$$\text{AI Explains} \quad \text{---} \quad \text{Rules / Auditable Models Decide}$$

Institutional Intelligence provides auditable, privacy-preserving institutional decision-support signals derived from verified academic rules, authoritative catalogs, declared student registration intents, and supplied capacity facts. It equips university leadership, deans, department chairs, and registrars with factual operational signals regarding structural demand and capacity alignment without automating institutional governance or overriding human authority.

---

## 2. Traceability

### 2.1 World-Class Capabilities (WC-*)
- `WC-009` (Institutional Demand Intelligence): Directly reused for descriptive aggregate demand inputs.
- `WC-010` (Section Capacity Intelligence): Enabled in P7 through deterministic capacity-gap and capacity-pressure signals; full section scheduling remains P10.
- `WC-011` (Course Bottleneck Intelligence): Defined in P7 as auditable structural gateway evidence combined with observed demand pressure; no black-box scoring.
- `WC-015` (Institutional Analytics): Governed metric catalog and tenant-scoped signal aggregation framework established in P7.
- `WC-041` (Data Quality Dashboard): Reuses P6 data quality flags and establishes signal hygiene contracts.
- `WC-044` (Privacy Analytics and Student Data Controls): Inherits P6.1/P6.4 whole-result privacy suppression and tenant isolation.
- `WC-054` (Institutional Simulation): Future P10 dependency; P7 provides the deterministic signal foundation.

### 2.2 Proposal Obligations (PROP-*)
- `PROP-032` ("Faculty and departments can use the same verified intelligence layer"): Addressed via tenant-scoped, aggregate-only institutional signals.
- `PROP-033` ("University administration can use the same layer"): Addressed via privacy-safe demand, bottleneck, and capacity-pressure indicators.
- `PROP-040` ("Prerequisite traceability"): Reused to ensure bottleneck signals cite exact verified prerequisite graph edges.
- `PROP-064` ("AI explains academic decisions. Verified rules decide eligibility"): Strict decision/explanation boundary enforced.
- `PROP-070` ("Rules Engine uses deterministic logic"): 100% deterministic calculation; no probabilistic or LLM-generated metrics.

---

## 3. Definition

**Institutional Intelligence** is defined as:
> An auditable, deterministic decision-support subsystem that computes and explains privacy-preserving aggregate signals regarding course demand, capacity pressure, structural curricular bottlenecks, and advising review volume across defined academic scopes and target planning periods.

---

## 4. Non-Goals and Strict Prohibitions

Institutional Intelligence strictly **DOES NOT**:
1. Autonomous Institutional Decisions: Never opens sections, closes courses, cancels classes, or modifies published timetables.
2. Capacity & Scheduling Operations: Never creates official course sections, allocates classrooms, or assigns instructors.
3. Staffing & Workload Mandates: Never determines faculty workload hours, staffing requirements, or hiring needs.
4. Predictive Enrollment Forecasting: Never predicts total final enrollment, registration drop-out rates, or multi-year trends.
5. Black-Box Scoring: Never outputs a single composite "University Health Score", "Bottleneck Score", or "Efficiency Index".
6. Student-Level Exposure: Never exposes individual student identities, records, attempts, or intents to institutional analysts.
7. Student Prioritization: Never ranks students, scores merit, or prioritizes students for seat allocation.
8. LLM Authority: Never allows large language models to compute, adjust, or override institutional signals.

---

## 5. Signal vs Decision Boundary

A strict boundary is maintained between operational signals and institutional decisions:

$$\text{INSTITUTIONAL\_SIGNAL} \neq \text{INSTITUTIONAL\_DECISION}$$

| Operational Signal (Morshidi Domain) | Institutional Decision (Human Authority) |
|---|---|
| Declared demand for `1501221` exceeds supplied capacity by 18 seats | Open an additional section of `1501221` |
| Course `1501110` is a mandatory prerequisite for 8 downstream courses | Prioritize staffing for `1501110` |
| 14 intent submissions require human academic review | Assign advisors to the academic review queue |
| Offering data is unavailable for target period `2026/2027-1` | Request registrar to publish section schedules |

Morshidi surfaces **signals**, **evidence**, and **limitations**. Human academic leaders make **decisions**.

---

## 6. Fact, Derived, and Decision Classes

All entities in Institutional Intelligence belong to exactly one of three mutually exclusive classes:

1. `INSTITUTIONAL_FACT`: Direct, verified external facts supplied to the system:
   - Canonical study plan memberships, course credit hours, verified prerequisite graph edges.
   - Supplied section capacity numbers (`CapacityFact`).
   - Supplied course offering availability (`OfferingFact`).
2. `DERIVED_SIGNAL`: Factual, deterministic computations produced by Morshidi:
   - Valid intent counts, demand shares, capacity deficit/surplus arithmetic.
   - Downstream dependency counts, structural bottleneck indicators.
   - Review-required intent counts.
3. `HUMAN_DECISION_REQUIRED`: Policy questions explicitly flagged for university personnel:
   - Prerequisite source conflict resolution.
   - Capacity deficit remediation.
   - Review-required intent disposition.

---

## 7. Data Source Hierarchy

Institutional Intelligence consumes inputs strictly in accordance with this hierarchy:

$$\text{Verified Academic Catalog} \succ \text{Privacy-Safe Revalidated Demand (P6)} \succ \text{Supplied Institutional Facts} \succ \text{Synthetic Sandbox Facts} \succ \text{Unavailable}$$

1. **Authoritative Study Plans & Catalogs:** Plan 12 structure, courses, verified prerequisite DAG.
2. **Privacy-Safe Revalidated Institutional Demand (P6):** Sourced strictly from P6.2/P6.5 aggregate demand outputs.
3. **Supplied Institutional Facts:** Explicit capacity and offering facts (`CapacityFact`, `OfferingFact`).
4. **Synthetic Sandbox Facts:** Explicitly watermarked non-authoritative fixtures.
5. **Unavailable Data:** Explicitly flagged missing data (`UNAVAILABLE`); never imputed.

**Critical P7.2 Input Boundary:**
Institutional Intelligence does **NOT** ingest raw individual student academic records (student IDs, course attempts, individual grades, or transcripts). Student-level state is consumed upstream exclusively by P6 during current revalidation. P7.2 ingests only privacy-preserving aggregate demand representations, verified catalog structures, verified institutional facts, and explicit data quality flags. Zero raw student records cross into Institutional Intelligence.

---

## 8. Current Demand Reuse

Institutional Intelligence **DOES NOT** implement a separate demand-counting engine.  
It directly consumes the output of the accepted Phase P6.2/P6.5 Institutional Demand engine (`app.mock_registration.aggregation.aggregate_institutional_demand`).

All demand metrics:
- Re-use the existing 9-metric registry (`DemandMetricId`).
- Inherit P6.2 content fingerprints and atomic validation.
- Inherit P6.5 dynamic current-state revalidation.
- Respect whole-result privacy suppression.

---

## 9. Capacity Fact Boundary

Capacity facts (`CapacityFact`) are external inputs representing the total scheduled seats for a course in a specific period:
- Allowed Provenance: `VERIFIED_INSTITUTIONAL_FACT` or `SYNTHETIC_SANDBOX_FACT`.
- Missing Data Rule: If capacity is not supplied for an offered or unverified course, it is classified as `UNAVAILABLE` (or `INSUFFICIENT_DATA`).
- Verified Not-Offered Applicability: If a course is verified `NOT_OFFERED` in the target period, seat capacity is structurally `NOT_APPLICABLE` rather than missing or defective. No missing capacity alert is raised for a verified non-offered course.
- Prohibited Behavior: Missing capacity is **NEVER** treated as zero capacity. Zero capacity means an explicit, verified fact stating zero seats are offered for an active offering.

---

## 10. Offering Fact Boundary

Offering facts (`OfferingFact`) represent whether a course is scheduled to run in a target period:
- Allowed Provenance: `VERIFIED_INSTITUTIONAL_FACT` or `SYNTHETIC_SANDBOX_FACT`.
- Missing Data Rule: If offering data is absent, the course offering state is `UNAVAILABLE`.
- Prohibited Behavior: Missing offering data is **NEVER** treated as `NOT_OFFERED`. Verified `NOT_OFFERED` status requires an explicit, positive institutional declaration that the course is not scheduled for that period.

---

## 11. V1 Institutional Signal Registry

Institutional Intelligence V1 defines a finite, stable registry of 13 signals (`INST_SIG_*`):

### 11.1 Demand Family
1. `INST_SIG_DECLARED_DEMAND_COUNT`: Count of distinct active intent owners selecting the course.
2. `INST_SIG_DECLARED_DEMAND_SHARE`: Proportion of total active intent owners selecting the course.
3. `INST_SIG_TOTAL_DECLARED_CREDIT_LOAD`: Total credits represented by active intents for the scope.
4. `INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT`: Count of intent owners selecting at least one course in the requirement group.

### 11.2 Capacity Pressure Family
5. `INST_SIG_SUPPLIED_CAPACITY_COUNT`: Total verified supplied seats (or `NOT_APPLICABLE` when verified `NOT_OFFERED`).
6. `INST_SIG_DECLARED_CAPACITY_DEFICIT`: Arithmetic difference: $\text{demand} - \text{capacity}$ (or `NOT_APPLICABLE` when verified `NOT_OFFERED`).
7. `INST_SIG_CAPACITY_PRESSURE_STATE`: Categorical pressure state (`NO_CAPACITY_DATA`, `WITHIN_SUPPLIED_CAPACITY`, `DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY`, `NOT_APPLICABLE`).
8. `INST_SIG_DEMAND_TO_CAPACITY_RATIO`: Descriptive ratio $\frac{\text{demand}}{\text{capacity}}$ (when capacity > 0 and demand unsuppressed; `NOT_APPLICABLE` when capacity = 0 or verified `NOT_OFFERED`).

### 11.3 Academic Structure & Bottleneck Family
9. `INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT`: Count of courses in the active plan for which this course is an immediate prerequisite.
10. `INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT`: Total count of downstream courses depending directly or transitively on this course.
11. `INST_SIG_STRUCTURAL_MANDATORY_ROLE`: Authoritative mandatory role in the study plan (`MANDATORY_REQUIRED` vs `CHOICE_ELECTIVE`), derived from the parent requirement group's `requirement_type == RequirementType.REQUIRED` (encompassing Major, Faculty, University, and Supporting Compulsory requirements).
11. `INST_SIG_STRUCTURAL_MANDATORY_ROLE`: Authoritative mandatory role in the study plan (`MANDATORY_REQUIRED` vs `CHOICE_ELECTIVE`), derived from the parent requirement group's `requirement_type == RequirementType.REQUIRED` (in canonical 132-credit Plan 12: University Compulsory 18cr, Faculty Compulsory 21cr, Supporting Compulsory 12cr, and Major Compulsory 63cr; totaling 114 required credits out of 132).
12. `INST_SIG_STRUCTURAL_BOTTLENECK_STATUS`: Categorical plan-structural classification (`NON_GATEWAY`, `STRUCTURAL_GATEWAY`, `REVIEW_REQUIRED`).

### 11.4 Review & Workload Family
13. `INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT`: Count of distinct current intent owners in the target period whose active intent requires human academic review.

---

## 12. Rejection of Black-Box Scores

Morshidi firmly rejects composite scoring:
- NO "Institutional Health Score"
- NO "Bottleneck Risk Index (0-100)"
- NO "Curriculum Efficiency Grade"

Composite scores obscure actionable causes, hide trade-offs, and create perverse incentives. Every signal in Morshidi represents an inspectable, isolated physical or structural fact.

---

## 13. Capacity Utilization Semantics

When computed, `INST_SIG_DEMAND_TO_CAPACITY_RATIO` is explicitly labeled:
$$\text{"Declared Intent to Supplied Capacity Ratio"}$$
It is **NOT** labeled "Actual Section Utilization" or "Enrollment Rate". Intent does not guarantee enrollment.
- If capacity = 0: Ratio is `NOT_APPLICABLE` (cannot divide by zero).
- If capacity is missing: Ratio is `UNAVAILABLE`.
- If demand is suppressed: Ratio is `SUPPRESSED`.

---

## 14. Capacity Pressure States

The capacity pressure state (`INST_SIG_CAPACITY_PRESSURE_STATE`) is strictly deterministic and three-valued:

```text
                                 [Capacity Fact Supplied?]
                                        /         \
                                      No           Yes
                                      /             \
                       [NO_CAPACITY_DATA]      [Demand <= Capacity?]
                                                    /         \
                                                  Yes          No
                                                  /             \
                           [WITHIN_SUPPLIED_CAPACITY]     [DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY]
```

No arbitrary "LOW / MEDIUM / HIGH" labels are permitted without institutional SLA contracts.

---

## 15. Structural Academic Gateway Definition

A course's structural gateway status is defined **EXCLUSIVELY BY CURRICULAR STRUCTURE**, completely decoupled from student demand volume or seat capacity availability.

A **Structural Gateway** requires threshold-free curricular evidence:
1. **Mandatory Curricular Role (Authoritative Plan Semantics):** The course satisfies an individually mandatory degree requirement. A course is individually mandatory if and only if its parent requirement group in the study plan has `requirement_type == RequirementType.REQUIRED` (or `"required"`). In canonical Plan 12, this includes University Compulsory (`UNIVERSITY_REQUIRED`), Faculty Compulsory (`FACULTY_REQUIRED`), Major Compulsory (`MAJOR_REQUIRED`), and Supporting Requirements (`SUPPORTING_REQUIRED` / `المتطلبات المساندة`). It excludes elective pools (`requirement_type == RequirementType.ELECTIVE`), where students choose from a pool to satisfy credit thresholds. Elective courses are always classified as `NON_GATEWAY` even if they have downstream dependencies, though their downstream counts remain factual.
2. **Verified Downstream Dependencies:** The course gates subsequent coursework in the active study plan (`transitive_downstream_count > 0`). There is no arbitrary count threshold (e.g. no $\ge 3$ cutoff).
3. **Indispensable Prerequisite (Absence of Bypass / OR Alternatives):** If a course is a prerequisite for downstream coursework, but all downstream dependencies offer alternative bypass options (e.g., downstream course requires Course A OR Course B, and Course B is an active alternative path), Course A is NOT an indispensable gateway. To be a `STRUCTURAL_GATEWAY`, Course A must be an indispensable prerequisite on at least one downstream path in the study plan.
4. **Credit Independence (Zero-Credit Course Participation):** Structural gateway status is completely independent of credit value. Zero-credit mandatory courses (e.g., `0200115` Community Service, `1509999` IT Research Seminar) participate fully in mandatory determination and structural gateway classification.
5. **Decoupled from Capacity:** Capacity pressure is an operational reality tracked separately by `INST_SIG_DECLARED_CAPACITY_DEFICIT`. A gateway course remains structurally critical regardless of whether seats are abundant, scarce, zero, unrecorded, or not offered.
### 15.1 Disentangling Structural Concepts
Morshidi strictly separates three independent structural dimensions:
1. **Individually Required for Degree (`is_individually_mandatory`):** Evaluates whether every student under the study plan must complete this specific course. A course is individually mandatory if and only if its parent requirement group has `requirement_type == RequirementType.REQUIRED`. In canonical Plan 12 (132 total credits), this encompasses the 4 required groups (`UNIVERSITY_REQUIRED` 18cr, `FACULTY_REQUIRED` 21cr, `SUPPORTING_REQUIRED` 12cr, and `MAJOR_REQUIRED` 63cr; totaling 114 required credits). It excludes the 2 choice elective groups (`UNIVERSITY_ELECTIVE` 9cr and `MAJOR_ELECTIVE` 9cr; totaling 18 elective credits), where students complete credit thresholds rather than specific courses.
2. **Has Downstream Dependencies (`transitive_downstream_count > 0`):** Evaluates whether subsequent coursework in the study plan DAG depends directly or transitively on this course. This factual graph metric is reported by `INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT` and is **NEVER erased or obscured**, regardless of whether the course is mandatory or elective.
3. **Indispensable to a Mandatory Completion Path (`has_indispensable_mandatory_path`):** Evaluates whether the course cannot be bypassed on a path required for degree completion.

### 15.2 Canonical Dependency Structure & OR-Option Semantics
Traversal of prerequisite paths strictly reuses the canonical prerequisite engine structures (`PlanCourseRule` and `DependencyGroup`):
- **AND-Groups:** A course's prerequisites are partitioned into `DependencyGroup` records ($g_1, g_2, \dots$), representing an **AND** relation (every prerequisite group must be satisfied).
- **OR-Options:** Inside each `DependencyGroup` $g$, `option_course_codes` represent an **OR** relation (passing any option satisfies group $g$).
- **Indispensable Edge:** A prerequisite course $X$ is an indispensable direct prerequisite for downstream course $Y$ if and only if $X$ is the **sole option** in at least one prerequisite group of $Y$ ($\text{len}(g.\text{option\_course\_codes}) == 1$ and $g.\text{option\_course\_codes} == (X,)$).
- **Bypassable Option:** If $X$ is only present in multi-option groups ($\text{len}(g.\text{option\_course\_codes}) > 1$), $X$ is a bypassable option; alternative verified courses can satisfy the prerequisite, so $X$ alone is not indispensable for $Y$.
- **Path Indispensability:** A course $X$ is indispensable to a mandatory completion path if there exists a directed path of indispensable prerequisite edges leading to an individually mandatory degree course (or if $X$ is itself individually mandatory and has $\ge 1$ indispensable downstream course).

### 15.3 Gateway Invariants
- **Credit Independence:** Structural gateway status is completely independent of credit value. Zero-credit mandatory courses (e.g., `0200115` Community Service in `UNIVERSITY_REQUIRED`, `1509999` IT Research Seminar in `FACULTY_REQUIRED`) participate fully in mandatory determination and structural classification.
- **Decoupled from Capacity:** Capacity pressure is an operational reality tracked separately by `INST_SIG_DECLARED_CAPACITY_DEFICIT`. A gateway course remains structurally critical regardless of whether seats are abundant, scarce, zero, unrecorded, or not offered.

---

## 16. Structural Gateway Evidence and Classification

Structural status is never collapsed into an opaque score. It surfaces as inspectable, deterministic catalog facts:
- `transitive_downstream_count`: Integer
- `transitive_downstream_count`: Integer ($\ge 0$)
- `is_mandatory`: Boolean (true iff parent group `requirement_type == RequirementType.REQUIRED`)
- `has_indispensable_downstream_path`: Boolean (true iff at least one downstream course cannot be satisfied without this course)
- `has_indispensable_mandatory_path`: Boolean (true iff the course is an indispensable prerequisite on at least one path required for degree completion)
- `prerequisite_rule_status`: Status of underlying prerequisite definitions

### 16.1 Deterministic Evaluation Logic
1. **Prerequisite Source Conflict:** If an underlying prerequisite rule suffers from an unresolved source conflict, status evaluates to `REVIEW_REQUIRED`.
2. **Structural Gateway:** If `transitive_downstream_count > 0` AND the course is individually mandatory (`group.requirement_type == RequirementType.REQUIRED`) AND it is an indispensable prerequisite on at least one downstream path, status evaluates to `STRUCTURAL_GATEWAY`.
3. **Non-Gateway:** If `transitive_downstream_count == 0` OR the course belongs to an elective requirement group (`group.requirement_type == RequirementType.ELECTIVE`) OR all downstream paths can be satisfied via alternative OR prerequisite options, status evaluates to `NON_GATEWAY`.
4. **Immunity to Demand Suppression:** Because structural classification depends solely on public catalog and study plan DAGs, its status vocabulary is strictly `AVAILABLE` or `REVIEW_REQUIRED`. It is **NEVER SUPPRESSED** by student demand privacy rules.
5. **Combined Operational Alert:** The operational intersection of a structural gateway course and an unsuppressed capacity deficit is captured separately by the deterministic alert `INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE`.
1. **Prerequisite Source Conflict:** If an underlying prerequisite rule suffers from an unresolved source conflict (`prerequisite_logic_status in (UNRESOLVED, SOURCE_CONFLICT)`), status evaluates to `REVIEW_REQUIRED`.
2. **Structural Gateway:** If the course is indispensable to at least one mandatory degree completion path (`has_indispensable_mandatory_path == True`), status evaluates to `STRUCTURAL_GATEWAY`.
3. **Non-Gateway:** If the course is NOT indispensable to any mandatory degree completion path, status evaluates to `NON_GATEWAY`. Specifically:
   - Terminal courses with zero downstream dependencies (`transitive_downstream_count == 0`), OR
   - Courses whose downstream edges are all bypassable via alternative OR options, OR
   - Elective courses that only gate optional elective paths (the degree can be completed without taking this course or its downstream branch).
4. **Preservation of Structural Facts:** An elective course with downstream dependencies is classified as `NON_GATEWAY` regarding mandatory degree bottlenecks, but its `INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT` reports its exact factual dependency count (e.g., 4 courses). Structural facts are never erased.
5. **Immunity to Demand Suppression:** Because structural classification depends solely on public catalog and study plan DAGs, its status vocabulary is strictly `AVAILABLE` or `REVIEW_REQUIRED`. It is **NEVER SUPPRESSED** by student demand privacy rules.
6. **Combined Operational Alert:** The operational intersection of a structural gateway course and an unsuppressed capacity deficit is captured separately by the deterministic alert `INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE`.

---

## 17. Course Criticality Language

All user-facing language must remain objective and non-alarmist:
- Permitted: `STRUCTURAL_GATEWAY`, `HAS_DOWNSTREAM_DEPENDENCIES`, `CAPACITY_DEFICIT_PRESENT`.
- Forbidden: `CRITICAL_FAILURE`, `HIGH_RISK_COURSE`, `DANGEROUS_BOTTLENECK`.

---

## 18. Prerequisite Graph Reuse

Institutional Intelligence strictly traverses the verified canonical dependency graph (`study_plan_prerequisites`, `prerequisite_dependency_groups`, `prerequisite_dependency_options`). It never infers alternative prerequisites.

---

## 19. Delay Consequence Boundary (Advisor Copilot vs Institutional Signals)

The Phase P4 Delay Consequence engine (`app.decision_intelligence.delay.analyze_delay_consequence`) computes structural critical-path disruption for an individual student under an explicit transcript, catalog version, and study plan context.  
- **Institutional Signal Boundary:** P4 Delay Consequence is **NOT** a course-level institutional signal in V1. Downstream disruption cannot be treated as an unparameterized generic course property across an entire student body without introducing unstated assumptions. Therefore, `INST_SIG_DELAY_CONSEQUENCE_POTENTIAL` is excluded from the institutional signal registry.
- **Advisor Copilot Access:** Individual-student delay consequence analysis remains fully available to authorized advisors inspecting an assigned advisee via `ADVISOR_TOOL_CHECK_DELAY_CONSEQUENCE`.
- **Future Institutional Simulation:** Any future aggregate curriculum delay modeling belongs to institutional simulation extensions (`WC-012`), not core V1 descriptive signals.

---

## 20. Degree Path Aggregation Decision

Phase 9 Degree Path simulation is computationally intensive and models individual student journeys.  
**Policy Decision:** P7 Institutional Intelligence **DOES NOT** run batch Degree Path simulations across the student body to derive aggregate metrics. Aggregate analysis in V1 relies on static graph analysis and aggregate demand.

---

## 21. Cross-Plan Demand Behavior

A single canonical course (e.g., `1501110` Programming Fundamentals) may belong to multiple study plans.
- Course-Level Scope: Aggregates declared intents across all study plans in the university where the course is a valid member.
- Plan-Level Scope: Constrains the signal strictly to intents submitted under that specific study plan.
- Rules: Denominators and scopes are never mixed. Every signal output explicitly states its scope (`UNIVERSITY_WIDE` vs `PLAN_SCOPED`).

---

## 22. Requirement-Group Pressure

Demand by requirement group (`INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT`) indicates the volume of students seeking credits within that category (e.g., Major Electives).  
It provides departmental decision support without prescribing section counts.

---

## 23. Zero-Credit Course Semantics

Zero-credit courses (e.g., `0200115` Community Service, `1509999` IT Research Seminar) are mandatory academic requirements:
- In canonical Plan 12, `0200115` belongs to University Compulsory (`UNIVERSITY_REQUIRED`) and `1509999` belongs to Major Compulsory (`MAJOR_REQUIRED`). Both have `requirement_type == RequirementType.REQUIRED`.
- In canonical Plan 12 (132 credits), `0200115` belongs to University Compulsory (`UNIVERSITY_REQUIRED`) and `1509999` belongs to Faculty Compulsory (`FACULTY_REQUIRED`). Both have `requirement_type == RequirementType.REQUIRED`.
- In canonical Plan 12, both `0200115` and `1509999` have zero downstream dependencies (`transitive_downstream_count == 0`) and thus evaluate to `NON_GATEWAY`.
- Zero-credit courses participate fully in mandatory determination, demand, dependency, structural bottleneck, and capacity signals independent of credit weight.
- Credit load signals report `0.00` credits, but owner counts and capacity deficit reflect the true demand.

---

## 24. Review-Load Signal

The review-load signal (`INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT`) reports the exact count of distinct current intent owners in the target period whose active intent requires human academic review.  
- Sourced directly from the P6 authoritative demand metric `REVIEW_REQUIRED_INTENT_OWNER_COUNT`.
- **Distinct Owners Only:** Does NOT count historical revisions, multiple submissions from the same current owner, or withdrawn/superseded revisions.
- **Purpose:** Provides administrative visibility into prerequisite ambiguities requiring human academic attention without double-counting.

---

## 25. Advising-Load Boundaries

Review volume must **NEVER** be converted into advisor FTE (Full-Time Equivalent) staffing requirements.  
Permitted: "14 distinct intent owners require academic review."  
Forbidden: "Department needs 2 more advisors."

---

## 26. Data Quality Signals

Institutional Intelligence inherits all P6.2 Data Quality flags and surfaces signal hygiene:
- `MISSING_CAPACITY_DATA`: Capacity fact is missing for an analyzed course scheduled to be offered or with unverified offering status. (Not applicable when verified `NOT_OFFERED`).
- `MISSING_OFFERING_DATA`: Offering fact is absent for the target period. (Never inferred as `NOT_OFFERED`).
- `OBSERVED_INTENTS_ONLY`
- `SUPPRESSED_FOR_PRIVACY`
- `REVIEW_REQUIRED_INTENTS_EXCLUDED`

---

## 27. Coverage Semantics

Mock Registration is a voluntary planning activity. Unless complete institutional coverage is explicitly verified:
- All demand-derived signals carry `OBSERVED_INTENTS_ONLY`.
- Extrapolating declared intent to non-participating students is strictly prohibited.

---

## 28. Privacy Suppression

Institutional Intelligence strictly enforces the P6.1 Privacy Policy:
- Minimum Disclosure Threshold: Configurable integer $k \ge 2$ (Development/Sandbox default: `3`).
- If the contributing owner population is $0 < n < k$, the signal is `SUPPRESSED`.
- Zero student identifiers appear in any institutional output schema.

---

## 29. Suppression Propagation to Derived Signals and Alerts

**Critical Privacy Invariants:**
1. **Catalog Structural Signals are Immune to Demand Suppression:** Catalog-derived structural facts (`INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT`, `INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT`, `INST_SIG_STRUCTURAL_MANDATORY_ROLE`, and `INST_SIG_STRUCTURAL_BOTTLENECK_STATUS`) depend strictly on the public curriculum DAG and requirement definitions. They are **NEVER SUPPRESSED** because they contain zero student-derived inputs. Privacy suppression of student demand does not alter, convert, or fabricate structural academic facts.
2. **Derived Capacity Signals:** If a course's declared demand count is suppressed, **ALL DERIVED CAPACITY SIGNALS** that depend on that count (demand share, capacity deficit, capacity ratio, capacity pressure state) **MUST BE SUPPRESSED**. A derived signal must never be exposed if doing so allows mathematical reverse-engineering of a suppressed demand count:
$$\text{Suppressed}(\text{Demand}) \implies \text{Suppressed}(\text{Demand} - \text{Capacity})$$
3. **Derived Alerts Withholding:** Any alert triggered by student volume (`INST_ALERT_CAPACITY_DEFICIT_DETECTED`, `INST_ALERT_ZERO_CAPACITY_WITH_DEMAND`, `INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE`, and `INST_ALERT_REVIEW_REQUIRED_PRESENT`) **MUST BE WITHHELD / SUPPRESSED** when the underlying demand or review-required count is suppressed ($0 < n < k$). Raising an alert when underlying counts are suppressed would leak the existence of a hidden student population.
4. **Data Hygiene Alerts are Scope-Based:** `INST_ALERT_CAPACITY_DATA_MISSING` and `INST_ALERT_OFFERING_DATA_MISSING` are triggered purely by the absence of verified institutional facts for an explicitly requested course or target period, independent of whether student demand exists. However, `INST_ALERT_CAPACITY_DATA_MISSING` is **NOT** emitted if the course is verified `NOT_OFFERED` (where capacity is structurally `NOT_APPLICABLE`). They never inspect student demand volume and cannot act as a privacy side-channel.

---

## 30. Cross-Filter Privacy and Subtraction Risk

Queries across overlapping scopes (e.g., querying Course X university-wide, then querying Course X for Plan A) create potential differencing/subtraction attack vectors.
- V1 Policy: Institutional Intelligence allows exact-scope queries only. Arbitrary multi-dimensional slicing or automated cohort differencing is prohibited.
- Production Requirement: Production deployment requires rate limiting and query auditing.

---

## 31. Multi-University Tenant Isolation

Every institutional intelligence computation is strictly partitioned by `university_id`. Cross-university aggregations, benchmarking, or shared memory caches are strictly prohibited.

---

## 32. Target-Period Scope

Institutional Intelligence V1 is strictly exact-period scoped. Cross-period combining or automatic chronological rolling is deferred.

---

## 33. Historical Trend Analytics

Historical trend analysis is **DEFERRED** in V1. Immutable historical revisions must not be converted into longitudinal time-series models without an approved temporal governance contract.

---

## 34. Signal Status Vocabulary

Every institutional signal returns exactly one of five typed statuses (`SignalStatus`):
1. `AVAILABLE`: Signal successfully computed from unsuppressed, verified inputs.
2. `SUPPRESSED`: Signal withheld to preserve student privacy under threshold policy.
3. `INSUFFICIENT_DATA`: Missing required input facts (e.g., missing capacity facts).
4. `REVIEW_REQUIRED`: Underlying data is subject to an unresolved academic conflict.
5. `NOT_APPLICABLE`: Operation structurally invalid (e.g., ratio when capacity = 0).

---

## 35. Signal Provenance

Every signal payload includes an immutable `SignalProvenance` block:
- `university_id`: UUID
- `target_period_id`: UUID
- `scope`: Typed academic scope
- `source_versions`: Tuple of catalog, prerequisite, and intent versions
- `policy_version`: Policy version (`"1.0"`)
- `computed_at`: ISO timestamp

---

## 36. Explainability

Institutional signals do not require LLM generation. Explainability is achieved through structured evidence:
- Input facts cited with versions.
- Exact formula or logic rule declared.
- Output value and status.
- Explicit limitations and data quality flags.

---

## 37. Institutional Decision Trace

Every institutional response generates an auditable `InstitutionalDecisionTrace`:
- `trace_id`: UUID
- `signal_id`: Stable identifier
- `inputs`: Key-value map of input facts
- `rule_id`: Evaluation rule reference
- `result_status`: `SignalStatus`
- `result_value`: Typed scalar value
- `limitations`: List of applicable warnings

---

## 38. Signal Comparison Rules

Factual side-by-side comparison between two courses or two plans is permitted **ONLY IF**:
1. Both compared signals are in status `AVAILABLE`.
2. Both share identical target periods and tenant contexts.
3. No overall "winner", "better plan", or evaluative ranking is produced.

---

## 39. Rejection of Departmental Ranking

Institutional Intelligence strictly prohibits ranking academic departments, faculties, or instructors based on demand or bottleneck metrics.

---

## 40. Morshidi Sandbox University Compatibility

All Institutional Intelligence contracts must execute with 100% fidelity against the synthetic **Morshidi Sandbox University** fixture suite. Outputs derived from sandbox data must carry `SYNTHETIC_SANDBOX_FACT` and `SYNTHETIC_SANDBOX_INTENT` provenance.

---

## 41. Real University Adapter Boundary

When integrating with live university systems, external adapters supply `CapacityFact` and `OfferingFact`. Institutional Intelligence consumes these normalized contracts without coupling to specific SIS or ERP vendor APIs.

---

## 42. Human Decision & Official Override Boundary

Institutional Intelligence is purely descriptive. All operational changes—scheduling sections, modifying course offerings, adjusting degree requirements—require human institutional deliberation and execution outside of Morshidi V1.
- **Provider-Neutral Waivers and Overrides:** Any official waiver or prerequisite override must originate from an authoritative institutional system or governed institutional process and enter Morshidi only as a verified institutional fact.
- **No Shadow Records:** Morshidi does NOT create shadow records, does NOT accept unverified in-app advisor waivers, and does NOT assume an SIS is the only possible upstream provider.

---

## 43. P7.2 Pure-Domain Implementation Contract

Phase P7.2 will implement Institutional Intelligence as a **pure domain package** (`app.institutional_intelligence`):
- Pure Python dataclasses and enums.
- Zero network, database, or framework dependencies.
- Consumes verified catalog facts, privacy-safe P6 aggregate demand, and verified institutional facts — **zero raw student records** (no student attempts, grades, GPA, or PII).
- Complete unit test coverage across all 13 signals and alert conditions.
- Strict suppression propagation and error handling.

