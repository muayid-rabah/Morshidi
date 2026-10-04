# Phase P8.1 — Grounded Knowledge & Decision Trace Policy Gate

Policy Version: **1.0**
Phase: **P8.1 — Policy and Contracts Only**
Governing Principle: **AI Explains — Rules / Auditable Models Decide**
Status: **APPROVED POLICY CONTRACT**
Predecessor Phases: Phase 1–10 (Core Academic Stack), P3 (Student Intelligence), P4 (Decision Intelligence & Delay Consequence), P5 (Academic Digital Twin & What-If), P6 (Mock Registration & Institutional Demand), P7 (Advisor Copilot & Institutional Intelligence).

---

## 1. Scope of Phase P8 & Executive Summary

Phase P8 establishes the architectural policy, data contracts, and verification boundaries for **Grounded Knowledge and Decision Trace** across the Morshidi Academic Intelligence Operating System.

Morshidi operates under the strict foundational axiom:
\\text{AI Explains} \\quad \\text{---} \\quad \\text{Rules / Auditable Models Decide}

Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG) pipelines must **NEVER** serve as authoritative sources for:
- Prerequisite evaluation,
- Degree eligibility,
- Academic requirement satisfaction,
- Graduation clearance,
- Official course registration,
- Course capacity or timetable facts,
- Individual student records or standing.

Phase P8.1 defines the formal, implementation-ready governance policies, data structures, boundaries, and validation contracts for:
1. **Decision Trace Ledger (WC-040)**: An append-only, privacy-preserving, cryptographically verifiable ledger envelope capturing material decisions with exact versions, provenance, and replayability.
2. **University Regulation RAG & Policy Retrieval (WC-038)**: An authoritative, cited retrieval boundary (\\InstitutionalPolicyProvider\\) that explains academic bylaws and regulations with exact source anchors, abstains when evidence is missing or conflicting, and strictly defers computable logic to deterministic engines.
3. **Academic Explainability Graph (WC-007)**: A typed Directed Acyclic Graph (DAG) formalizing the causal and evidential links between decisions, rules, factors, and policy passages.
4. **Change Impact Engine (WC-046)**: An analysis-only simulation and evaluation boundary calculating the downstream consequences of catalog, policy, and curriculum updates without writing to authoritative state.
5. **Institutional AI Query Experience (WC-039)**: A strictly constrained natural-language interface over the governed institutional metric catalog that forbids arbitrary SQL execution and prevents student record exposure.

---

## 2. Relationship to Phase P7

Phase P8 builds directly upon the accepted and locked outcomes of Phase P7:
- **P7.4 Advisor Authorization Gate**: Enforces authenticated identity, active \\ACADEMIC_ADVISOR\\ role, active explicit assignment record, and exact university match. P8 reuses this exact authorization boundary prior to exposing student-level traces or explainability subgraphs.
- **P7.5 Closed Advisor Copilot Read-Only Tools**: The 11 read-only deterministic tools provide the foundation for student academic state inspection, recommendations, and simulations. Routine tool queries remain ephemeral domain operations and are not persisted to the permanent ledger.
- **P7.1–P7.3 Institutional Intelligence**: Governed aggregate signals and threshold alerts establish the institutional scope boundaries inherited by P8.

---

## 3. Entry and Exit Gates

- **Entry Gate**: Acceptance of Phase P7 (Advisor Copilot, Human Review, Institutional Analytics). Satisfied by accepted commit \\4aab138\\.
- **Exit Gate**: Cited policy retrieval contracts, canonical ledger envelope, explainability DAG specifications, change impact analysis boundaries, institutional query constraints, and an exhaustive 54-scenario test matrix documented and verified.
- **Policy and implementation distinction**: P8.1 remains the normative policy
  contract. Subsequent implementation slices now provide Decision Trace and
  structured Policy Retrieval runtime foundations. The P8.1 policy-contract
  inventory and verification matrix are distinct from the roadmap's narrower
  P8 local delivery evidence (cited retrieval plus a replayable trace ledger).
  Neither gate changes this document's authority boundaries or certifies every
  matrix scenario, full WC completion, production deployment, or institutional
  validation.

---

## 4. Deterministic-Engine Precedence

Highest authority strictly supersedes lower layers. A lower layer can never override or relax a higher layer:
1. **Canonical Identity, Tenant Isolation & Authorization**: Authenticated identity, active role, explicit assignment, and exact university match.
2. **Phase 5 Academic Legality**: Prerequisite rules and eligibility decisions (\\ELIGIBLE\\, \\NOT_ELIGIBLE\\, \\REVIEW_REQUIRED\\).
3. **Phase 6 Academic Requirements**: Monotonic degree progress, completed credit hours, requirement groups, and audit status.
4. **Phase 7–9 Structural Policies**: Baseline recommendation priority tuples, planner constraints, and monotonic degree paths.
5. **Phase 4 Approved Deterministic Factors**: Verified student readiness and delay consequence indicators.
6. **User Optimization Preferences**: Explicit, bounded constraints (e.g., maximum credit hours) within allowed engine parameters.
7. **Institutional Policies & Regulations**: Textual bylaws and regulatory constraints ingested through \\InstitutionalPolicyProvider\\.
8. **AI Explanation & RAG**: Natural language synthesis of verified structured data and cited policy text.

---

## 5. Strict No-Write Boundaries

Phase P8.1 establishes that knowledge retrieval, explainability graph construction, and change impact evaluation are strictly **READ-ONLY / ANALYSIS-ONLY**:
- No evaluation can mutate student academic state, insert attempt records, alter course catalog entries, or create official SIS enrollments.
- Change impact evaluations identify affected decisions and flag recomputations without creating side-effecting mutations or automatic advisor queue records.
- Decision Trace Ledger recording occurs only as an append-only audit side-car for material milestone transactions, never rewriting existing historical records.

---

## 6. Privacy & Redaction Baseline

Phase P8 preserves the canonical privacy and suppression foundations established in Phase P6 (Institutional Demand Privacy Policy) and Phase P7:
- **Aggregate-First Access**: Institutional queries operate exclusively on aggregate metrics. Individual student identities, records, and attempts are completely excluded.
- **Suppression Integration**: Governed queries inherit the versioned \\minimum_disclosure_group_size\\ policy (integer \\(\\ge 2\\), with synthetic sandbox default 3). Counts below the threshold return \\SUPPRESSED\\ with reason \\DEMAND_PRIVACY_SUPPRESSED\\ and quality flag \\SUPPRESSED_FOR_PRIVACY\\.
- **Role-Scoped Redaction**: Individual student ledger entries are accessible exclusively to the student themselves (\\STUDENT_SAFE\\) or their actively assigned academic advisor (\\ADVISOR_SAFE\\). Institutional analysts have zero access to student-level traces.

---

## 7. Implementation status (not a policy change)

No capability advances merely because this policy exists. The following is a
repository implementation snapshot, not a claim of production deployment or
institutional adoption.

### Implemented now

- **WC-040 Decision Trace Ledger — PARTIAL:** canonical domain model, hashing,
  validation, evidence references, replay availability, immutable PostgreSQL
  ledger/evidence persistence, service-role append RPC, P6 outbox integration,
  bounded processor RPCs, and a read-only student-owner Decision History V1
  timeline/detail surface are present. The viewer enforces `STUDENT_SAFE`,
  verifies canonical hashes before projection, and displays safe evidence,
  historical replay status, supersession, and limitations without replaying.
  The advisor's read-only list/detail API reuses exact P7 role, tenant, and
  assignment authorization, and permits `STUDENT_SAFE` plus `ADVISOR_SAFE` only.
  Institutional analysts have no student-level trace access. Retention V1 has
  **no automatic deletion**; export V1 is **disabled / not implemented**.
- **WC-038 University Regulation RAG / Policy Retrieval — PARTIAL:** governed
  document/version/passage model, exact citation anchors, deterministic
  computation handoff, Supabase persistence, atomic structured ingestion,
  verified-only student read API, lexical and semantic retrieval, deterministic
  hybrid fusion, and bounded grounded answers with server-built citations and
  authenticated frontend viewing are present. An empty verified corpus abstains.
- **WC-007 Academic Explainability Graph — PARTIAL:** the closed typed DAG
  projects existing deterministic eligibility, course recommendation, semester
  planner, and degree-path results into read-only student explanations. An
  assigned advisor can read the same supported graphs only after the exact P7
  active-role/tenant/assignment predicate; analysts are denied. Arabic RTL
  student sections show typed facts, constraints, reasons, and exact engine
  policy versions where the engine exposes them. Exact academic source-document
  versions are unavailable in those result contracts and explicitly limited;
  no graph is stored or generated by an LLM.

### Remaining

- **WC-040:** material-event runtime coverage remains incomplete: of the eight
  `LEDGER_REQUIRED` registered types, `MOCK_REGISTRATION_SUBMIT` has a trusted
  P6 outbox producer and `CHANGE_IMPACT_EVALUATION` has a trusted WC-046
  evaluator producer. New P6 submit revisions with a private immutable
  `P6_REPLAY_ARTIFACT_V1` are mapped `REPLAYABLE_EXACT` and can be reconstructed
  and rerun by a trusted internal P6 V1 executor. Old P6 and WC-046 traces
  remain `NOT_REPLAYABLE`. Version-aware availability and comparison helpers
  alone do not rerun a historical executable. The browser cannot
  append, mutate, replay, delete, or export traces.
- **WC-038:** document/PDF import and parsing, real institutional source
  onboarding and verification, approved conflict resolution, and the final
  institutional cited-retrieval validation remain incomplete. These are full
  capability and external-validation gaps, not a failure of bounded local
  cited-retrieval runtime evidence.
- **WC-007:** progress/material-ledger adapters, exact academic source-document
  version propagation, and any advisor frontend remain outside this slice.
- **WC-046 Change Impact Engine — PARTIAL:** owner-approved V1 analyzes four
  closed proposed-delta types using bounded immutable copies, existing
  eligibility/progress engines, analyst structural and P7 assigned-advisor
  endpoints, a focused Arabic institutional form, and a required trusted
  `CHANGE_IMPACT_EVALUATION` ledger producer. It makes no academic-state write,
  student population scan, advisor queue, or notification. Reports are ephemeral
  and explicitly not historically replayable; published-source authority and
  some exact source-version verification remain outside V1.
- **WC-039 Institutional AI Query Experience — PARTIAL:** owner-approved V1
  maps one Arabic/English question to one of the 13 existing governed signals,
  executes only the existing tenant-scoped Institutional Intelligence service,
  and presents a focused analyst-only Arabic RTL interpretation/result surface.
  It inherits suppression, creates no SQL, query history, student drill-down,
  or Decision Trace entry, and safely abstains on unsupported/provider failure.
  Real institutional source data and representative intent/metric validation
  remain open; synthetic Local Supabase evidence is not that validation.

The standing deterministic-engine, citation, source-admission, tenant-isolation,
privacy, and no-write requirements in this policy remain unchanged.

### Phase-exit reconciliation (2026-09-29)

Controlled Local Supabase tests establish cited, verified/current policy
retrieval and bounded grounded answers against a synthetic corpus. They do not
establish an approved institutional corpus; the owner-confirmed production
policy document, version, passage, and embedding counts are all zero. The
official roadmap additionally requires a **replayable trace ledger**. New P6
replay-contract traces now have reconstructable historical inputs and a
trusted deterministic rerun; old P6 and WC-046 traces do not. The existing
replay helpers still only check availability/compare references; the distinct
trusted P6 V1 executor actually reruns historical validation. Together these
tested local paths satisfy the roadmap's stated P8 exit evidence, **cited
policy retrieval and replayable trace ledger**, for local implementation and
delivery. The P8.1 policy-contract gate has its documented companion
specifications and exhaustively classified 54-scenario matrix; it does not
say that every future/full-capability scenario must be VERIFIED to close the
narrower roadmap delivery phase. Partial and blocked matrix rows remain
honest full-capability, future-surface, or external-governance gaps. Phase P8
is **locally delivered, pending owner closure**; no full WC, production, or
institutional acceptance is implied. This reconciliation changes no
normative policy or runtime.

---

## 8. Companion Policy Documents

The detailed specifications governing Phase P8 are established in:
1. [decision-trace-ledger-policy.md](decision-trace-ledger-policy.md): approved canonical Decision Trace contract; student-owner and assigned-advisor read runtime remains a bounded partial slice.
2. [institutional-policy-retrieval-policy.md](institutional-policy-retrieval-policy.md): approved canonical policy-retrieval contract; runtime implementation remains partial.
3. [academic-explainability-graph-policy.md](academic-explainability-graph-policy.md): approved canonical graph contract; eligibility and material recommendation/planning projections are implemented, with broader capability status partial.
4. [change-impact-policy.md](change-impact-policy.md): Analysis-only version diff evaluation, affected decision identification, and no-write guarantees.
5. [institutional-ai-query-policy.md](institutional-ai-query-policy.md): approved canonical contract and bounded V1 local runtime; representative real-data validation remains open.
6. [p8-grounded-knowledge-test-matrix.md](p8-grounded-knowledge-test-matrix.md): Exhaustive 54-scenario closed verification matrix.

---

## 9. Remaining runtime roadmap

The following full-capability and external work remains after local P8 delivery:
- **Remaining Decision Trace capability work**: trusted producers for uncovered required
  material event types and any separately approved viewer/export/erasure capability.
- **Remaining Policy Retrieval capability work**: institutional source onboarding and
  verification, document ingestion/parsing, conflict governance, and institutional acceptance.
- **Further capability work**: additional approved explainability graph adapters, change impact batch evaluators, and separately governed institutional query expansion/real-data validation.
