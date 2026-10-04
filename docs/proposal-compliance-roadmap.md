# Morshidi proposal-compliance completion roadmap

## Completion rule

The original proposal is the product definition of done. Morshidi is not proposal-complete until every implementable `PROP-*` item in `proposal-compliance-matrix.md` is `IMPLEMENTED` and has final acceptance evidence. No `PARTIAL` or `MISSING` implementable item may remain at final closure. External dependencies must retain explicit evidence/status and may not be silently relabeled complete.

The complementary world-class product direction is locked in `morshidi-world-class-product-roadmap.md`, with canonical scope in `morshidi-world-class-capability-matrix.md`, provider boundaries in `morshidi-external-adapter-strategy.md`, and safe demonstration rules in `morshidi-sandbox-university-spec.md`. That roadmap does not replace this mandatory proposal-compliance track or change any `PROP-*` status. Both tracks align on **P4 — Decision Intelligence Integration** as the immediate next phase.

This roadmap preserves completed Phase 1–10.7A work. It does not authorize implementation during the audit. Phase 10.7’s advisor/student frontend remains paused until the data and intelligence dependencies below are ready.

## Ordered roadmap

1. Proposal Data Governance and Plan 12 Source Closure
2. Student Performance Data Foundation
3. Auditable Student Intelligence Engines
4. Decision Integration and Delay Consequences
5. Grounded Advisor Continuity and Institutional Knowledge
6. Arabic Student Experience and Visual Roadmap
7. University Stakeholder Roles and Governance
8. Pilot Instrumentation, Privacy, and Readiness
9. Real-Student Pilot and Metric Validation
10. SIS/SSO Integration and Multi-Institution Scale

The dependency chain is deliberate:

```text
verified data definitions
  → longitudinal performance data
  → validated strengths/weaknesses/risk/readiness
  → recommendation/planner/path integration
  → grounded advisor and student UI
  → measurement-ready product
  → real pilot evidence
  → institutional integration and scale
```

## Phase 1 — Proposal Data Governance and Plan 12 Source Closure

**Purpose:** Close source ambiguity and define the governance contracts required before student-performance intelligence can be credible.

**Proposal claim IDs:** PROP-002, PROP-007, PROP-037, PROP-040, PROP-077.

**Inputs/data required:** Official clarification for the four unresolved and two source-conflict prerequisite expressions; Zarqa grading scale and repeat policy; definitions of authoritative versus self-reported records; source version/effective-date policy.

**Implementation scope:**

- Resolve all six ambiguous Plan 12 prerequisite expressions through an academic authority; update structured dependency groups and source provenance only after written evidence.
- Specify grade, attempt, term, repeat, GPA, earned-credit, transcript-import, reconciliation, verification-status, and source-version semantics.
- Define stable provenance states such as authoritative import, advisor verified, student reported, and simulated/demo.
- Add an automated traceability report covering all 68 plan courses and every eligibility status.
- Define retention, correction, audit, and source-change behavior before schema work.

**Explicit non-goals:** No risk/readiness score, no recommendation-policy changes, no advisor/frontend implementation, and no inferred prerequisite logic.

**Tests required:** Migration/source reconciliation; all-course prerequisite trace audit; source-version transition tests; no raw-text parsing fallback; regression of current Phase 5–10 behavior.

**Acceptance criteria:** Every Plan 12 course is either verified `not_applicable` or has source-backed executable prerequisite logic; the traceability report reaches 100%; grade/provenance contracts are approved and versioned.

**Dependencies:** Zarqa curriculum authority and grading-policy owners.

**User-visible outcome:** Review-required prerequisite warnings caused solely by the six known source ambiguities disappear after verified resolution; provenance language becomes available for later UI.

## Phase 2 — Student Performance Data Foundation

**Purpose:** Replace free-text/manual-only performance facts with a longitudinal, provenance-aware foundation suitable for validated intelligence.

**Proposal claim IDs:** PROP-002, PROP-007, PROP-077, PROP-078.

**Inputs/data required:** Numeric grades, grade scale/version, attempt sequence, term identity/order, course domain/taxonomy, repeat history, GPA policy, outcome provenance, course outcomes, and representative historical records.

**Implementation scope:**

- Extend the student data model for normalized numeric grade observations without changing explicit institutional outcomes into inferred outcomes.
- Add transcript/import batches, source records, reconciliation status, correction history, and as-of timestamps.
- Model academic terms and longitudinal ordering.
- Build secure importer interfaces and a deterministic simulated-data adapter for local tests.
- Produce versioned, reproducible feature snapshots; do not yet classify strength, weakness, risk, or readiness.
- Preserve owner isolation, RLS, data minimization, and deletion behavior.

**Explicit non-goals:** No prediction labels, no LLM classification, no recommendation reranking, and no live SIS connector yet.

**Tests required:** Migration replay; RLS/owner isolation; import idempotency; repeat/reconciliation cases; grading-scale changes; provenance preservation; as-of feature reproducibility; privacy deletion.

**Acceptance criteria:** A student’s verified longitudinal performance record can be imported, reconciled, queried as of a point in time, and transformed into a deterministic versioned feature snapshot without losing source provenance.

**Dependencies:** Phase 1 contracts; sample de-identified institutional records and grading policy.

**User-visible outcome:** A future profile screen can distinguish official/imported, verified, self-reported, and simulated facts instead of presenting all records as equivalent.

## Phase 3 — Auditable Student Intelligence Engines

**Purpose:** Implement the proposal’s missing student-performance intelligence through validated rules/models, never free-form LLM guesses.

**Proposal claim IDs:** PROP-011, PROP-012, PROP-013, PROP-014, PROP-058, PROP-078.

**Inputs/data required:** Phase 2 feature snapshots; course-domain taxonomy; expert definitions and labeled examples for strengths/weaknesses/readiness; historical course outcomes for risk; cohort/time splits; demographic attributes only if legally and ethically approved for fairness evaluation.

**Implementation scope:**

- Define versioned contracts for strength evidence, weakness evidence, course/current academic risk, and personal readiness.
- Start with transparent deterministic rules when constructs can be academically justified; use statistical/ML models only where validated historical data supports them.
- Record model/rule version, feature timestamp, output, drivers, uncertainty/applicability, limitations, and calibration metadata.
- Add abstain/insufficient-data behavior and human-review thresholds.
- Add monitoring plans for drift, calibration, subgroup performance, and model retirement.
- Expose read-only authenticated outputs; AI may explain them but cannot generate or override them.

**Explicit non-goals:** No diagnosis, wellbeing inference, personality scoring, protected-attribute targeting, fabricated precision, automatic academic sanctions, or unvalidated “AI risk” prose.

**Tests required:** Golden expert cases; boundary/abstention cases; temporal held-out validation; calibration; leakage checks; fairness/subgroup analysis; determinism/version reproducibility; missing/stale data; explanation fidelity.

**Acceptance criteria:** Each claimed output has an approved construct definition, adequate validation result, versioned mechanism, drivers, safe abstention, API contract, and final acceptance report. Risk must meet an approved calibration threshold before use in decisions.

**Dependencies:** Phases 1–2; institutional subject-matter experts, historical data, privacy/model governance approval.

**P3 delivery gates:** P3.1 closes policy/contracts only. P3.2 may implement only approved deterministic outcome/structure observations with provenance and abstention. Grade, ordered-trend, domain, and predictive extensions remain gated by EVID-008/010/017/018 and separate validation/governance approval.

**User-visible outcome:** Students can receive evidence-backed strengths, weaknesses, risk, and readiness results with clear limitations rather than LLM speculation.

## Phase 4 — Decision Integration and Delay Consequences

**Purpose:** Make the validated intelligence materially affect “should take” recommendations, semester plans, and paths while preserving rules-first eligibility.

**Proposal claim IDs:** PROP-001, PROP-013, PROP-014, PROP-017, PROP-018, PROP-021, PROP-023, PROP-050, PROP-054, PROP-055, PROP-063, PROP-081, PROP-082, PROP-085, PROP-095, PROP-100.

**Inputs/data required:** Phase 3 outputs and versions; approved recommendation/risk/readiness policy; current structural outputs; definition of “delay”; term/offering data if real calendar consequences are claimed.

**Delivery sequence:** P4.1 locked Decision Intelligence Integration policy version 1.0. P4.2 now implements shared immutable contracts, the pure delay engine, bounded Phase 7 readiness tie-breaking, Phase 8/9 annotations, read-only orchestration, and isolation/regression evidence. General Digital Twin and What-If work remains after P4.

**P5.1 dependency clarification:** The next domain slice is governed by the Academic Digital Twin, What-If, Scenario Comparison, operation, delta, and test contracts. It reuses P4 Delay Consequence and unchanged Phase 5–9 engines; it does not close PROP-001, PROP-014, PROP-017, PROP-018, PROP-021, PROP-023, PROP-050, PROP-062, or PROP-078 through documentation. P5.2 is pure/domain-only and ephemeral; authorized API/UI delivery, predictive-risk evidence, live offerings, and continuous lifecycle behavior remain separate gates.

**P5.2 implementation evidence:** The pure domain slice now provides immutable fingerprinted snapshots, exact current-versus-modeled separation, three bounded operations, P4 Delay composition, the 16-delta registry, and same-base factual comparison with all 51 committed scenarios traced. This closes the P5.2 domain dependency for later authorized delivery but does not close any proposal claim whose acceptance requires UI, API, persistence, real-data validation, predictive risk, live offerings, or continuous lifecycle behavior.

**P6.1 policy gate:** Mock Registration and Institutional Demand now have authoritative documentation contracts for explicit student confirmation, deterministic revisions/current intent, Phase 5/6-backed validation, descriptive demand, exact denominators, privacy suppression, provenance, missing offerings/capacity, and multi-plan/university isolation. This policy directly supports the planner/intent separation in PROP-050, enables later PROP-032/033/066/088 workflows, and preserves PROP-073/074/078/089/090/091/098 as later dependencies. Documentation changes no proposal status. P6.2 may implement pure domain logic only; persistence, API/auth, providers, UI, forecasting, and institutional actions remain later gates.

**P6.2 implementation gate:** The pure Mock Registration and Institutional Demand engine now enforces explicit non-binding intent, exact Phase 5/6-backed validation, deterministic revisions/idempotency, privacy-minimized aggregation, all nine metrics, coverage flags, disclosure suppression, and optional supplied-fact arithmetic. This strengthens existing PROP-050 evidence and provides domain foundations for PROP-032/033/066/088 without changing proposal statuses. The next authorized slice must separately close persistence, owner/institutional authorization, API/UI, production privacy controls, and real provider/adoption evidence; PROP-073/074/078/089/090/091/098 remain later dependencies.

**P6.3 policy gate:** The persistence, authorization, and API contracts now define immutable owner-scoped revisions, exact-key CAS and retry behavior, server-side validation, withdrawal and revalidation semantics, explicit grants/RLS, server-authoritative institutional membership, tenant isolation, aggregate-only responses, privacy suppression, and a 72-scenario future test gate. This is direct policy evidence for PROP-050 and enables later PROP-032/033/066/088 delivery; it does not implement or change the status of any proposal claim. P6.4 is persistence/security only and P6.5 is services/APIs; PROP-031/073/074/078/089/090/091/098 remain later dependencies.

**P6.4 implementation gate:** Additive normalized storage now preserves immutable student intent revisions, exact target-period authority, atomic course children, server-assigned CAS revisions, idempotent fingerprint replay, owner RLS, direct-client write denial, server-managed institutional membership, and cross-university isolation. Two clean local migration replays plus real concurrency, rollback, CRUD, membership, and tenant tests strengthen the persistence/security evidence for PROP-050 and the foundation for later PROP-032/033/066/088. No proposal status changes: P6.5 authenticated services/APIs, frontend delivery, real provider data, representative validation, SIS/SSO, production privacy governance, and continuous lifecycle evidence remain open.

**P6.5 implementation gate:** Four authenticated FastAPI routes now derive student ownership and plan scope server-side, rerun P6.2 validation/revalidation, persist through P6.4 CAS, authorize active institutional membership before tenant-scoped candidate loading, and return P6.2 aggregate/suppression output through privacy-safe schemas. This materially strengthens PROP-050 and the backend foundations for future PROP-032/033/066/088, but changes no compliance status because frontend delivery, real provider/adoption evidence, institutional validation, SIS/SSO, broader privacy/query governance, and continuous lifecycle outcomes remain open.

This bounded V1 does not yet close risk-based ranking or planner/path ranking claims: structural risk remains non-predictive and explanation-only, while Phase 8/9 rankings remain baseline-equivalent. Any later material factor requires validated evidence, a versioned policy increment, an exact precedence position, and new isolation/fairness regressions.

**P4.2 closure evidence:** `decision-intelligence-implementation.md`, `delay-consequence-implementation.md`, and `p4-decision-delay-implementation-trace.md`. Remaining dependencies are an authorized delivery surface for readiness/delay, institutional construct validation, governed predictive-risk evidence, and a separately approved policy before readiness or risk may alter Phase 8/9 ordering.

**Implementation scope:**

- Specify a new versioned recommendation policy showing exactly where risk/readiness enter the priority calculation.
- Preserve Phase 5 eligibility as a hard gate; models must never make an ineligible course eligible.
- Integrate strengths/weaknesses only where an approved academic policy defines their effect.
- Propagate factors into semester and degree-path ranking with complete audit traces.
- Implement an explicit now-versus-delay counterfactual over the verified dependency/path model; clearly separate structural consequences from real offering/graduation timing.
- Add safe insufficient-data behavior rather than silently dropping claimed factors.

**Explicit non-goals:** No opaque LLM ranking, no promised graduation date, no course-offering prediction without data, no autonomous registration, and no mutation of academic records.

**Tests required:** Factor-isolation ranking cases; eligibility invariants; monotonic/path regressions; counterfactual cases; missing/stale model outputs; policy-version migration; fairness/calibration integration; full Phase 5–10 regression.

**Acceptance criteria:** Controlled fixtures prove each approved factor changes or does not change ranks exactly as specified; every result records source/model/policy versions and drivers; delay results are reproducible and disclose assumptions.

**Dependencies:** Phase 3; academic/product approval of policy; offerings data for real-term claims.

**User-visible outcome:** “What should I take?” and “what happens if I delay?” have auditable, complete proposal-backed answers distinct from “what can I take?”

## Phase 5 — Grounded Advisor Continuity and Institutional Knowledge

**Purpose:** Complete grounded follow-up behavior and the proposal’s later RAG promise without weakening academic authority.

**Proposal claim IDs:** PROP-004, PROP-019, PROP-022, PROP-058, PROP-063, PROP-072, PROP-079, PROP-084, PROP-096, PROP-100.

**Inputs/data required:** Versioned Phase 3–4 outputs; official regulations, study-plan documents, course catalog, advising policies, effective dates, source ownership, and access classification.

**Implementation scope:**

- Add bounded conversation references to prior authoritative result IDs/snapshots; do not treat chat memory as academic state.
- Make `OPTION_COMPARISON` load only the referenced server-owned result and reject stale/foreign references.
- Build official-material ingestion, chunk/source versioning, access control, retrieval, citations, and stale-source invalidation.
- Keep retrieved text informational unless an explicit deterministic engine consumes a verified structured rule.
- Expand explanation guards for new intelligence outputs and citations.
- Provide deterministic degraded responses when retrieval/provider services fail.

**Explicit non-goals:** No unrestricted web RAG, no private chain-of-thought, no conversation-derived record updates, no retrieved prose overriding structured rules/models, and no uncited institutional claims.

**Tests required:** Multi-turn coreference; stale/foreign result isolation; retrieval relevance; citation/source version; access control; prompt injection; poisoned document resistance; provider/retrieval failure; Arabic grounding; model-result fidelity.

**Acceptance criteria:** Follow-ups resolve to the same authorized snapshot; material answers cite versioned official sources; disabling AI/RAG never changes deterministic academic truth.

**Dependencies:** Phase 4; official source corpus and document owners; LLM/retrieval infrastructure.

**User-visible outcome:** Students can ask Arabic follow-ups and inspect authoritative evidence/citations without the advisor inventing policy or personal facts.

## Phase 6 — Arabic Student Experience and Visual Roadmap

**Purpose:** Resume the paused Phase 10.7 work only after core intelligence is available, delivering the proposal’s student-facing product.

**Proposal claim IDs:** PROP-001, PROP-004, PROP-020, PROP-021, PROP-022, PROP-045, PROP-046, PROP-047, PROP-048, PROP-049, PROP-050, PROP-063, PROP-076, PROP-079, PROP-080, PROP-084, PROP-094, PROP-095, PROP-096, PROP-099, PROP-100.

**Inputs/data required:** Existing authenticated client; Phase 4/5 APIs; status aggregation contract; Arabic content; accessibility requirements; approved high-priority semantics.

**Implementation scope:**

- Build an Arabic-first protected student dashboard for profile provenance, progress, eligibility, recommendations, semester options, and degree paths.
- Build one visual roadmap with distinct `COMPLETED`, `AVAILABLE`, `BLOCKED`, `RECOMMENDED`, and approved `HIGH PRIORITY` states.
- Provide exact evidence/details, review-required warnings, model/rule versions, limitations, and source citations.
- Build the advisor/chat experience with loading, retry, empty, unavailable, clarification, and safe failure states.
- Keep all calls behind `useAuthenticatedApi()` and the existing owner-scoped backend.
- Meet keyboard, screen-reader, contrast, RTL, responsive, and no-content-flash requirements.

**Explicit non-goals:** No frontend authorization, JWT parsing, direct Supabase academic reads, direct LLM calls, browser persistence of academic/chat state, or simulated recommendation labels.

**Tests required:** Component tests; visual-state fixtures for all roadmap statuses; RTL/accessibility audits; browser E2E; auth expiry/logout; API error states; evidence consistency; no-secret/no-provider scan.

**Acceptance criteria:** An authenticated Arabic-speaking student can complete the full “where I stand / can / should / why / delay” flow; every displayed decision matches backend evidence; no protected flash or frontend authority exists.

**Dependencies:** Phases 4–5 and existing Phase 10.7A foundation.

**User-visible outcome:** The first proposal-faithful student experience, including the visual roadmap and grounded advisor.

## Phase 7 — University Stakeholder Roles and Governance

**Purpose:** Support the proposal’s advisor, faculty/department, and administration beneficiaries under explicit authorization and privacy rules.

**Proposal claim IDs:** PROP-031, PROP-032, PROP-033.

**Inputs/data required:** University role model, organizational hierarchy, advisor-student assignment/consent, approved aggregate definitions, audit/retention policy.

**Sub-phase sequence:**
- **Phase P7.1 (Policy & Contracts):** Define Institutional Intelligence (signals vs decisions, bottleneck decomposition, capacity pressure) and Advisor Copilot (read-only, non-mutating tool registry, separation from `INSTITUTIONAL_ANALYST`, and assignment authorization).
- **Phase P7.2 (Institutional Intelligence Pure Domain):** Implement pure signal models, capacity pressure rules, structural bottleneck evidence, alerts, and deterministic tests (zero I/O).
- **Phase P7.3 (Institutional Intelligence Service & API):** Implement FastAPI routes, context loader, analyst authorization, and aggregation integration.
- **Phase P7.4 (Advisor Authorization & Persistence):** Implement `ACADEMIC_ADVISOR` role, advisor-student assignment tables, RLS policies, and security tests.
- **Phase P7.5 (Advisor Copilot Orchestration & API):** Implement read-only tool orchestration, student context guards, and advising workspace endpoints.

**P7.1 Policy Gate Evidence:**
`institutional-intelligence-policy.md`, `institutional-capacity-pressure-policy.md`, `advisor-copilot-policy.md`, `institutional-intelligence-signal-matrix.md`, `advisor-copilot-tool-matrix.md`, `institutional-alert-matrix.md`, and `institutional-intelligence-advisor-test-matrix.md` establish implementation-ready contracts and the 85-scenario acceptance gate for PROP-031, PROP-032, and PROP-033. This policy gate adds documentation evidence only; no proposal compliance status changes.

**Implementation scope:**

- Add tenant-scoped roles and least-privilege permission contracts.
- Implement student consent or institution-approved advisor assignment and audited access.
- Provide advisor case review, faculty privacy-safe aggregates, and administration views only for approved use cases.
- Prevent role/tenant inference from frontend claims; enforce server and RLS boundaries.

**Explicit non-goals:** No unrestricted faculty access to individual records, no deanonymizing small cohorts, no performance surveillance, and no bypass of student/tenant ownership.

**Tests required:** Cross-role/cross-tenant denial; consent/assignment lifecycle; audit log integrity; small-cell suppression; export controls; revoked-role behavior.

**Acceptance criteria:** Each beneficiary has an approved documented workflow, minimum necessary data, auditable access, and adversarial authorization coverage.

**Dependencies:** University governance/IAM decisions; Phase 6 core student experience can proceed before this phase unless pilot protocol requires advisor tooling.

**User-visible outcome:** Authorized advisors and institutional stakeholders use the same verified layer through role-appropriate interfaces.

## Phase 8 — Pilot Instrumentation, Privacy, and Readiness

**Purpose:** Make the product capable of honestly measuring every proposal pilot target before involving real students.

**Proposal claim IDs:** PROP-005, PROP-030, PROP-041, PROP-042, PROP-043, PROP-044, PROP-086, PROP-087, PROP-088.

**Inputs/data required:** Pilot protocol, participant criteria, consent text/version, survey instrument, task script, metric definitions, event taxonomy, retention/anonymization rules, advisor validation rubric.

**Implementation scope:**

- Define numerator, denominator, exclusion, missing-data, and analysis rules for 80% usefulness.
- Define useful/clear/trustworthy questionnaire items and response scale.
- Define paired baseline/post planning task and time measurement.
- Define missed-prerequisite, graduation-progress clarity, and repetitive-question metrics.
- Add privacy-minimized session/event/survey storage and reproducible exports.
- Build pilot admin/research controls without fabricating participants or results.
- Complete security, accessibility, reliability, data-protection, and incident-readiness checks.

**Explicit non-goals:** No synthetic pilot results, no silently captured raw chat/transcripts, no production-wide analytics before approval, and no claim that instrumentation equals target achievement.

**Tests required:** Event completeness/idempotency; consent gating; withdrawal/deletion; clock ordering; questionnaire versioning; metric reproduction from fixture data; missing-data behavior; export anonymization; pilot dry run.

**Acceptance criteria:** An independent reviewer can reproduce all proposed metrics from a synthetic rehearsal export; consent/privacy approval and go/no-go checklist are signed before recruitment.

**Dependencies:** Phase 6 usable product; institutional ethics/privacy/security approval; possibly Phase 7 advisor review workflow.

**User-visible outcome:** Participants see clear consent, tasks, and post-session feedback while the product records only approved measurement data.

## Phase 9 — Real-Student Pilot and Metric Validation

**Purpose:** Execute—not simulate—the proposal’s Zarqa pilot and collect final evidence for pilot/impact claims.

**Proposal claim IDs:** PROP-005, PROP-030, PROP-041, PROP-042, PROP-043, PROP-044, PROP-086, PROP-087, PROP-088.

**Required product state before pilot:** Phases 1–6 complete; Phase 8 approved; no open critical security/accessibility defects; complete Plan 12 traceability; stable model/policy versions frozen for the study.

**Participant target:** At least 30 consented Zarqa University students in the AI program/Plan 12 target population. Replacements, withdrawals, and incomplete sessions must be reported transparently.

**Consent/privacy:** Approved participant information; explicit consent; minimal pseudonymous linkage; withdrawal/deletion process; restricted researcher access; retention deadline; incident contact; no portal passwords.

**Metrics:**

- 100% prerequisite traceability: automated pre-pilot gate over all Plan 12 eligibility decisions.
- 30+ real students: count only consented completed guided sessions.
- 80%+ perceived usefulness: declared positive-response threshold and denominator.
- Usefulness, clarity, trustworthiness: post-session survey distributions with instrument version.
- Planning time: paired baseline versus Morshidi-assisted task on the same participants; no invented reduction threshold.
- Recommendation validation: advisor review against real records with disagreement adjudication.
- Fewer missed prerequisites, clearer progress, fewer repetitive questions: baseline/post definitions and evidence; report as exploratory if sample/power is insufficient.

**Questionnaires/feedback:** Arabic-first Likert items, optional structured reason categories, limited free text, usability/accessibility feedback, and advisor discrepancy form.

**Baseline/post measurement:** Freeze scenario/task rules, record baseline before exposure, run guided session, then repeat comparable planning task and survey. Preserve paired IDs and analysis exclusions.

**Explicit non-goals:** No fake data, no changing thresholds after results, no hiding negative findings, no model retraining on evaluation participants before reporting, and no broad deployment claim from one pilot.

**Tests required:** Final dry run; metric reproduction; participant-flow audit; consent audit; frozen-version verification; data-quality checks; adverse-event process rehearsal.

**Acceptance criteria:** ≥30 completed real sessions; every quantitative result includes numerator/denominator and confidence/uncertainty where appropriate; raw de-identified evidence and reproducible analysis are archived; failed targets remain gaps and drive remediation/retest.

**Dependencies:** Phase 8 go/no-go approval, Zarqa recruitment/data access, faculty/advisor reviewers.

**User-visible outcome:** Real students use Morshidi in guided sessions; results—not assumptions—determine whether pilot claims pass.

## Phase 10 — SIS/SSO Integration and Multi-Institution Scale

**Purpose:** Replace simulated/manual data paths with approved university integration and prove scale beyond one study plan.

**Proposal claim IDs:** PROP-002, PROP-034, PROP-073, PROP-074, PROP-080, PROP-089, PROP-090, PROP-091, PROP-098.

**Inputs/data required:** University SIS/API contract and sandbox; identity-provider metadata/claims; authoritative identifiers; incremental-change semantics; official plans/policies for additional majors/institutions; tenancy, localization, hosting, and regulatory requirements.

**Implementation scope:**

- Build secure SIS adapters with mapping, idempotent sync, reconciliation, retries, audit, and source freshness.
- Add university SSO/federation and role mapping without storing portal passwords.
- Prove multi-plan and multi-major configuration at Zarqa before adding a second institution.
- Add tenant isolation, per-institution policy/data versions, localization, deployment observability, backup/recovery, capacity testing, and onboarding tooling.
- Revalidate every intelligence model for each materially different institution/population; do not assume portability.
- Progress through gates: additional IT majors → wider Zarqa University → second Jordanian university → regional partner.

**Explicit non-goals:** No screen scraping with stored passwords, no silent schema coercion, no one-model-fits-all assumption, no cross-tenant analytics leakage, and no declaring regional scale from schema generality alone.

**Tests required:** Connector contract/replay/failure tests; SSO login/logout/claim/role tests; reconciliation; tenant isolation; load/SLO; disaster recovery; policy variance; localization; second-institution regression; security assessment.

**Acceptance criteria:** Approved SIS/SSO integration operates without portal credentials; at least two additional IT majors pass full reconciliation/E2E; a second institution runs in an isolated tenant with verified rules and revalidated models; production SLOs are measured.

**Dependencies:** University IT/IAM/security teams, data-sharing agreements, official curricula, hosting and regulatory approvals.

**User-visible outcome:** Students use institutional sign-in and current authoritative records; the same governed core supports multiple plans and institutions with explicit adapters.

## External blockers and locally buildable scope

| External dependency | Exact access/data needed | Fully buildable/testable locally first | Requires cooperation | Fallback/demo strategy |
|---|---|---|---|---|
| Plan 12 academic authority | Written resolution of six prerequisite expressions | Rule versioning, review workflow, trace report | Approve exact AND/OR/course semantics | Keep `REVIEW_REQUIRED`; never guess |
| Historical academic data | De-identified grades, attempts, terms, outcomes, cohorts, policies | Schemas, import contracts, synthetic fixtures, evaluation harness | Data sharing, interpretation, validation | Demonstrate plumbing only; intelligence stays unavailable |
| Pilot participants | ≥30 real AI-program students and advisor reviewers | Complete rehearsal with synthetic participants | Recruitment, consent, guided sessions | No fake pilot; mark target unexecuted |
| Ethics/privacy | Consent, retention, survey, analytics approval | Privacy architecture, deletion/export tests | Institutional approval | Disable analytics/pilot collection |
| SIS/API | Sandbox/spec, identifiers, feeds, credentials | Adapter interface, contract simulator, retries/reconciliation | University IT access | Manual versioned import with explicit provenance |
| SSO/IAM | IdP metadata, claims, roles, security requirements | OIDC/SAML adapter tests against local provider | University IAM setup/approval | Supabase email/password for demo only |
| Official materials | Versioned regulations/catalog/advising policies | RAG ingestion/access/citation harness with public fixtures | Source ownership and update process | Restrict advisor to structured Phase 5–9 facts |
| Additional institutions | Official plans, rules, policies, language/regulatory needs | Multi-tenant architecture and synthetic second tenant | Partner validation and deployment | Do not claim scale completion |

## Traceability coverage check

Every current `PARTIAL` or `MISSING` matrix item is assigned to at least one roadmap phase:

- **Phase 1:** PROP-002, PROP-007, PROP-037, PROP-040, PROP-077
- **Phase 2:** PROP-002, PROP-007, PROP-077, PROP-078
- **Phase 3:** PROP-011, PROP-012, PROP-013, PROP-014, PROP-058, PROP-078
- **Phase 4:** PROP-001, PROP-013, PROP-014, PROP-017, PROP-018, PROP-021, PROP-023, PROP-050, PROP-054, PROP-055, PROP-063, PROP-081, PROP-082, PROP-085, PROP-095, PROP-100
- **Phase 5:** PROP-004, PROP-019, PROP-022, PROP-058, PROP-063, PROP-072, PROP-079, PROP-084, PROP-096, PROP-100
- **Phase 6:** PROP-001, PROP-004, PROP-020, PROP-021, PROP-022, PROP-045, PROP-046, PROP-047, PROP-048, PROP-049, PROP-050, PROP-063, PROP-076, PROP-079, PROP-080, PROP-084, PROP-094, PROP-095, PROP-096, PROP-099, PROP-100
- **Phase 7:** PROP-031, PROP-032, PROP-033
- **Phases 8–9:** PROP-005, PROP-030, PROP-041, PROP-042, PROP-043, PROP-044, PROP-086, PROP-087, PROP-088
- **Phase 10:** PROP-002, PROP-034, PROP-073, PROP-074, PROP-080, PROP-089, PROP-090, PROP-091, PROP-098

## Final closure gate

Final proposal closure requires:

1. Matrix recount shows every implementable item as `IMPLEMENTED` and zero `PARTIAL`/`MISSING` items.
2. Each row contains executable evidence, tests, and user-visible or operational acceptance evidence appropriate to the claim.
3. Pilot metrics are backed by real consented participants and reproducible analysis, not fixtures.
4. External integrations have explicit partner evidence and cannot be closed from local mocks alone.
5. AI explanations remain subordinate to rules/models: **AI explains; verified rules/models decide.**
