# Institutional Intelligence Pure-Domain Engine Implementation

Implementation document: **1.0**
Phase: **P7.2 — Institutional Intelligence Pure-Domain Engine**
Package: `apps/api/app/institutional_intelligence/`
Predecessor phases: P7.1 (Policy & Contracts), P6 (Mock Registration & Institutional Demand), P5 (Academic Digital Twin), P4 (Decision Intelligence), P3 (Student Intelligence).

---

## 1. Architectural Purpose and Core Principle

The Institutional Intelligence pure-domain engine converts the locked P7.1 contracts into auditable, deterministic, side-effect-free Python domain logic.

Foundational architectural principle:
$$\text{AI Explains} \quad \text{---} \quad \text{Rules / Auditable Models Decide}$$

This subsystem computes and explains privacy-preserving aggregate signals regarding course demand, capacity pressure, structural curricular bottlenecks, and advising review volume across defined academic scopes and target planning periods.

---

## 2. Pure-Domain Package Structure

The package is strictly decoupled from I/O, database access, network connections, web frameworks, and authentication.

```text
apps/api/app/institutional_intelligence/
├── __init__.py           # Public symbols and package exports
├── registries.py         # Closed 13-signal registry, 6-alert registry, 5-status vocabulary, enums
├── models.py             # Immutable dataclasses for facts, signals, alerts, traces, and results
├── capacity.py           # Capacity arithmetic, deficit calculation, ratio, and pressure state machine
├── structure.py          # Prerequisite DAG analysis, sound AND/OR necessity, structural gateway evaluation
├── alerts.py             # Deterministic evaluation of all 6 institutional alerts with privacy withholding
├── trace.py              # Auditable decision trace construction
└── engine.py             # Main entrypoint: evaluate_institutional_intelligence()
```

---

## 3. Strict Input Boundary & P6 Demand Reuse

### 3.1 Allowed Inputs
- Authoritative study plan catalog (`AcademicProgressCatalog`).
- Canonical prerequisite dependency rules (`CanTakeCatalog`).
- Sourced P6 aggregate demand outputs (`DemandAggregationResult`).
- External institutional offering facts (`OfferingFact`), with explicit `authority` (`InstitutionalFactAuthority`) and `source_version`.
- External institutional capacity facts (`CapacityFact`), with explicit `authority` (`InstitutionalFactAuthority`) and `source_version`.
- Explicit privacy configuration (`InstitutionalPrivacyConfiguration`).
- Tenant and planning period scope identifiers (`university_id`, `target_period_key`).

### 3.2 Prohibited Inputs
Zero raw student academic records are ingested:
- NO student IDs, user IDs, names, or emails.
- NO student grades, GPA, or transcript rows.
- NO individual student course attempts.
- NO raw Mock Registration revision rows.

### 3.3 Demand Reuse Boundary & Missing Metric Semantics
Institutional Intelligence **does not** recalculate demand or count distinct student owners. It strictly consumes aggregate outputs from the accepted Phase P6 Institutional Demand engine (`apps.mock_registration.aggregation`).
The metric `INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT` inherits distinct-current-owner semantics from P6 (`DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT`). Historical revisions and multiple submissions by the same student are never double-counted.

**Missing P6 Metric $\neq$ Zero:**
If a P6 demand metric is absent from `demand_result.metrics` (e.g. `REVIEW_REQUIRED_INTENT_OWNER_COUNT` when review metrics were not requested), its signal status strictly evaluates to `SignalStatus.INSUFFICIENT_DATA` (value `None`), and never silently defaults to 0. All 5 reused P6 metrics (`COURSE_INTENT_OWNER_COUNT`, `COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS`, `TOTAL_DECLARED_CREDIT_LOAD`, `REQUIREMENT_GROUP_INTENT_OWNER_COUNT`, `REVIEW_REQUIRED_INTENT_OWNER_COUNT`) pass through exact P6 values without re-computation or re-rounding.

---

## 4. Closed Registries and Status Vocabularies

### 4.1 Closed 13-Signal Registry (`InstitutionalSignalId`)
1. `INST_SIG_DECLARED_DEMAND_COUNT`: Distinct active intent owners selecting the course.
2. `INST_SIG_DECLARED_DEMAND_SHARE`: Proportion of total valid intent owners selecting the course.
3. `INST_SIG_TOTAL_DECLARED_CREDIT_LOAD`: Total credits represented by declared valid courses.
4. `INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT`: Distinct owners selecting $\ge 1$ course in the requirement group.
5. `INST_SIG_SUPPLIED_CAPACITY_COUNT`: Total verified supplied scheduled seats.
6. `INST_SIG_DECLARED_CAPACITY_DEFICIT`: Signed arithmetic difference ($\text{Demand} - \text{Capacity}$).
7. `INST_SIG_CAPACITY_PRESSURE_STATE`: Categorical capacity pressure state.
8. `INST_SIG_DEMAND_TO_CAPACITY_RATIO`: Descriptive ratio of declared demand to supplied capacity.
9. `INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT`: Count of courses where candidate is a direct prerequisite.
10. `INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT`: Total count of downstream courses reachable in DAG.
11. `INST_SIG_STRUCTURAL_MANDATORY_ROLE`: Course degree role (`MANDATORY_REQUIRED` vs `CHOICE_ELECTIVE`).
12. `INST_SIG_STRUCTURAL_BOTTLENECK_STATUS`: Categorical structural gateway status (`STRUCTURAL_GATEWAY`, `NON_GATEWAY`, `REVIEW_REQUIRED`).
13. `INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT`: Distinct current owners whose intent requires human review.

### 4.2 Closed 6-Alert Registry (`InstitutionalAlertId`)
1. `INST_ALERT_CAPACITY_DEFICIT_DETECTED`: Declared demand exceeds supplied capacity ($\Delta > 0$).
2. `INST_ALERT_ZERO_CAPACITY_WITH_DEMAND`: Supplied capacity is 0 with positive declared demand ($C = 0, D > 0$).
3. `INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE`: Structural gateway course has unsuppressed capacity deficit ($\Delta > 0$).
4. `INST_ALERT_REVIEW_REQUIRED_PRESENT`: Distinct review-required intent owner volume present ($n > 0$).
5. `INST_ALERT_CAPACITY_DATA_MISSING`: Seat capacity fact is missing for an offered or unverified course.
6. `INST_ALERT_OFFERING_DATA_MISSING`: Course timetable offering fact is absent for target period.

### 4.3 Signal Status Vocabulary (`SignalStatus`)
- `AVAILABLE`: Signal successfully computed from unsuppressed, verified inputs.
- `SUPPRESSED`: Signal withheld to preserve student privacy under threshold policy ($0 < n < k$).
- `INSUFFICIENT_DATA`: Missing required external input facts (e.g. missing capacity).
- `REVIEW_REQUIRED`: Underlying data is subject to an unresolved prerequisite conflict or cycle.
- `NOT_APPLICABLE`: Operation structurally invalid (e.g. division by zero, capacity for non-offered course).

---

## 5. Capacity Semantics & State Machine

### 5.1 Exact Capacity Arithmetic
- Deficit: $\Delta = D - C$ (signed integer). Negative deficit represents available headroom, never "wasted resources".
- Ratio: $\frac{D}{C}$ (rounded to 4 decimal places using `ROUND_HALF_UP`).
- Division by Zero: If $C = 0$, ratio is `NOT_APPLICABLE`. If $D > 0$, deficit $= D$ and `INST_ALERT_ZERO_CAPACITY_WITH_DEMAND` is emitted.

### 5.2 Offering Applicability Invariants
- Missing Offering $\neq$ `NOT_OFFERED`: If offering fact is missing, offering status is `UNAVAILABLE` (`INSUFFICIENT_DATA`), never inferred as `NOT_OFFERED`. Emits `INST_ALERT_OFFERING_DATA_MISSING`.
- Missing Capacity $\neq$ Zero Capacity: Missing capacity evaluates to `INSUFFICIENT_DATA` and state `NO_CAPACITY_DATA`. Emits `INST_ALERT_CAPACITY_DATA_MISSING`.
- Verified `NOT_OFFERED`: If `OfferingFact.status == PlannedOfferingStatus.NOT_OFFERED`:
  - `INST_SIG_SUPPLIED_CAPACITY_COUNT` $\implies$ `NOT_APPLICABLE`.
  - `INST_SIG_DECLARED_CAPACITY_DEFICIT` $\implies$ `NOT_APPLICABLE`.
  - `INST_SIG_CAPACITY_PRESSURE_STATE` $\implies$ `NOT_APPLICABLE`.
  - `INST_SIG_DEMAND_TO_CAPACITY_RATIO` $\implies$ `NOT_APPLICABLE`.
  - `INST_ALERT_CAPACITY_DATA_MISSING` is **NOT** emitted.

---

## 6. Privacy Suppression and Transitive Propagation

To prevent reverse-engineering of student volume through arithmetic differencing ($D = \Delta + C$), privacy suppression is transitive:
1. If demand $D$ is `SUPPRESSED`:
   - Deficit $\Delta$ is `SUPPRESSED`.
   - Ratio $\frac{D}{C}$ is `SUPPRESSED`.
   - Capacity pressure state is `SUPPRESSED`.
   - Demand-dependent alerts (`INST_ALERT_CAPACITY_DEFICIT_DETECTED`, `INST_ALERT_ZERO_CAPACITY_WITH_DEMAND`, `INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE`, and `INST_ALERT_REVIEW_REQUIRED_PRESENT`) are strictly **withheld**.
2. Catalog Structural Immunity: Catalog structural facts (`direct_downstream_count`, `transitive_downstream_count`, `structural_mandatory_role`, `structural_gateway_status`) contain zero student data and are **never suppressed** by student privacy rules.
3. Data Hygiene Alerts: `INST_ALERT_CAPACITY_DATA_MISSING` and `INST_ALERT_OFFERING_DATA_MISSING` are public institutional facts and remain immune to demand suppression.

---

## 7. Prerequisite Structural Analysis & AND/OR Necessity

### 7.1 Direct and Transitive Downstream Counts
- Direct downstream dependencies count unique course codes where the candidate appears in any prerequisite option.
- Transitive downstream dependencies perform cycle-safe BFS traversal across directed dependency edges.

### 7.2 Sound Recursive/DP Boolean Necessity Model
Universal curricular indispensability uses a recursive boolean necessity formula over prerequisite groups:

$$\text{Must}(T) = \bigcup_{G \in T.\text{groups}} \bigcap_{O \in G.\text{options}} (\{O\} \cup \text{Must}(O))$$

- **AND-Groups:** Every prerequisite group must be satisfied ($\bigcup$).
- **OR-Options:** Within a group, only courses indispensable to every alternative option branch survive the intersection ($\bigcap$).
- **Common-Ancestor Recognition:** If downstream target $M$ requires $A$ OR $B$, and both $A$ and $B$ require $X$, $X$ is recognized as indispensable to $M$.
- **Bypass Recognition:** If $M$ requires $A$ OR $B$, where $A$ requires $X$ but $B$ does not, $X$ is not indispensable to $M$.

### 7.3 Structural Gateway Classification
A candidate course $X$ is evaluated against all individually mandatory degree requirements $M$ ($M \neq X$):
- `STRUCTURAL_GATEWAY`: Candidate $X$ is indispensable to at least one individually mandatory completion path ($X \in \text{Must}(M)$ for mandatory $M$).
- `NON_GATEWAY`: Candidate $X$ has 0 downstream dependencies, all downstream paths have alternative bypass options, or it only gates optional elective paths.
- `REVIEW_REQUIRED`: An unresolved prerequisite source conflict or dependency cycle exists on the candidate-relevant dependency path.
- **Elective Gateway Capability:** An elective course that is indispensable to a mandatory downstream completion path is correctly classified as `STRUCTURAL_GATEWAY`.
- **Zero-Credit Courses:** Zero-credit courses participate fully in mandatory determination and structural classification regardless of credit weight.

### 7.4 Outcome-Sensitive Source-Conflict Propagation
Conflict propagation is outcome-sensitive and does not lazily poison candidates:
- **Verified OR Bypass:** If candidate $X$ is part of an OR prerequisite option but another independent, verified prerequisite branch exists without $X$, candidate $X$ evaluates to `NON_GATEWAY`. A source conflict on an alternative branch that does not alter $X$'s bypassability does not poison $X$.
- **Outcome-Relevant Conflicts:** If an unresolved source conflict or ambiguity on a prerequisite path makes it impossible to determine whether candidate $X$ is indispensable to a mandatory course, candidate $X$ evaluates to `REVIEW_REQUIRED`.
- **Dependency Cycles:** Direct cycles involving candidate $X$ or cycles on candidate $X$'s prerequisite path evaluate to `REVIEW_REQUIRED`.
- **Unrelated Conflicts:** Conflicts elsewhere in the university catalog that do not touch candidate $X$'s dependency subgraphs never affect $X$'s evaluation.

### 7.5 Referenced-Only Courses in Prerequisite Topology
Courses may appear in prerequisite rules (`can_take_catalog`) without being listed in the degree program's plan courses (`catalog.plan_courses`):
- **Topology Participation:** Referenced-only courses participate fully in the prerequisite DAG, upstream/downstream dependency tracking, and transitive count calculations.
- **Mandatory Role:** For referenced-only courses, `evaluate_mandatory_role` returns `StructuralMandatoryRole.CHOICE_ELECTIVE` (no artificial plan course entries are manufactured).
- **Mandatory Role:** For referenced-only courses, `evaluate_mandatory_role` returns `None`, causing `INST_SIG_STRUCTURAL_MANDATORY_ROLE` to evaluate to `SignalStatus.NOT_APPLICABLE` (value `None`). It is not a study plan course, so no mandatory or elective role is manufactured.
- **Structural Gateway Status:** If a referenced-only course is indispensable to at least one individually mandatory degree course, it correctly evaluates to `STRUCTURAL_GATEWAY`.

---

## 8. Determinism and Auditability

- Zero clock calls (`datetime.now()`, `time.time()`).
- Zero random numbers or UUID generation (`uuid4()`).
- Zero manufactured defaults: `computed_at` and `deterministic_trace_id` are caller-supplied or `None`.
- When `deterministic_trace_id` is omitted, stable deterministic trace IDs are derived strictly from scope (`f"{univ_id}:{period_key}:{course_code}"`).
- When `deterministic_trace_id` is omitted, `trace_id` evaluates to `None` (zero fake event identities manufactured).
- Exact pass-through of P6 demand metrics without re-computation or re-rounding.
- Missing P6 demand metrics evaluate to `SignalStatus.INSUFFICIENT_DATA` (missing $\neq$ 0).
- All returned dictionaries, alerts, quality flags, and traces have fixed, stable sorting.
- Every signal generates an immutable `InstitutionalDecisionTrace` detailing inputs, formula rule, status, and value.

---

## 9. Deferred Service & API Boundary (P7.3+)

P7.2 implements pure-domain logic only. The following responsibilities remain deferred:
- FastAPI routes and HTTP request schemas (`/api/v1/institutional/intelligence`) $\to$ **P7.3**.
- Authenticated service layer and database repository loaders $\to$ **P7.3**.
- Institutional analyst membership and tenant isolation enforcement $\to$ **P7.3**.
- Advisor authorization, assignments, and RLS policies $\to$ **P7.4**.
- Advisor Copilot tools and orchestrator $\to$ **P7.5**.
