# Student Intelligence Policy Specification — P3.1

## 1. Purpose

Policy version **1.0** defines auditable descriptions of academic evidence and modeled academic state. It is documentation-only: no engine, schema, API, ranking, or UI behavior changes. AI explains; deterministic rules/models decide.

## 2. Proposal traceability

| Class | Claims |
|---|---|
| DIRECT_P3 | PROP-011 strengths, PROP-012 difficulty, PROP-013 risk, PROP-014 readiness, PROP-078 continuous performance modeling |
| DEPENDENT_ON_LATER_PHASE | PROP-058 risk explanation; PROP-054/055 and PROP-050 decision integration; PROP-063 advisor personalization |
| EXTERNAL_DATA_DEPENDENT | PROP-013 predictive risk and PROP-078 cohort modeling require EVID-018; PROP-011/012/014 domain outputs require EVID-017; grade interpretation requires EVID-008/011–013; ordered trends require EVID-010. |

## 3. Governing principles

Morshidi describes academic evidence, structural state, and documented observations. It must not judge intelligence, worth, personality, motivation, wellbeing, or psychological capability. Forbidden conclusions include “weak student”, “lazy”, “not intelligent”, diagnosis, or guaranteed success/failure.

## 4. Capability taxonomy

| Capability | Question | V1 state | Required evidence / exclusion |
|---|---|---|---|
| PERFORMANCE_INTELLIGENCE | What explicit attempt and structural facts are recorded? | AVAILABLE when outcome/structure evidence exists | Explicit outcomes, attempts, progress, dependency/eligibility evidence; no grades or periods interpreted. |
| ACADEMIC_STRENGTH | What completed/recovery evidence is present? | AVAILABLE, narrowly | Explicit passed/recovery and requirement evidence only; not domain strength. |
| ACADEMIC_DIFFICULTY_SIGNAL | What repeated academic difficulty/bottleneck evidence is present? | AVAILABLE, narrowly | Explicit attempts and verified structural rules; never cause/ability inference. |
| ACADEMIC_PREPARATION_READINESS | What preparation evidence exists for a target? | AVAILABLE only where Phase 5 is determinate | Never permission, probability, or eligibility override. |
| STRUCTURAL_RISK_SIGNAL | What deterministic structural warning condition exists? | AVAILABLE, narrowly | Required-course/dependency evidence; no prediction. |
| PREDICTIVE_ACADEMIC_RISK | What is likely to occur? | BLOCKED_BY_EXTERNAL_DATA | EVID-018, approval, labels, calibration, fairness, evaluation. |

## 5. Shared status model

`AVAILABLE` means supported evidence produced an observation; `INSUFFICIENT_DATA` means necessary evidence is absent; `REVIEW_REQUIRED` means source/rule ambiguity prevents a conclusion; `NOT_SUPPORTED` means the construct has no V1 rule; `BLOCKED_BY_EXTERNAL_DATA` means external evidence/governance is required. Precedence: `REVIEW_REQUIRED` > `BLOCKED_BY_EXTERNAL_DATA` > `INSUFFICIENT_DATA` > `NOT_SUPPORTED` > `AVAILABLE` for the requested conclusion.

## 6. Evidence, reasons, missing inputs, and output contract

Evidence types: `ATTEMPT_OUTCOME`, `COURSE_ATTEMPT`, `VERIFIED_RAW_GRADE`, `REQUIREMENT_PROGRESS`, `COURSE_DEPENDENCY`, `ELIGIBILITY_RESULT`, `ACADEMIC_PROGRESS`, `PROVENANCE`, `VERIFICATION_STATE`. Attempt/course/progress evidence is sensitive owner data; raw grades are more sensitive and are internal by default. Student APIs expose only minimized derived references/reason text; advisors receive only authorized minimized evidence; AI may verbalize deterministic observations and limitations, never raw grades by default.

Finite versioned namespaces are `PERF_` (6), `STRENGTH_` (2), `DIFFICULTY_` (3), `READINESS_` (5), and `STRUCTURAL_RISK_` (3): 19 codes in the catalog. Missing inputs are `NO_ATTEMPT_HISTORY`, `NO_VERIFIED_PERFORMANCE_DATA`, `NO_APPROVED_GRADING_POLICY`, `NO_DOMAIN_TAXONOMY`, `NO_COHORT_DATA`, `UNRESOLVED_PREREQUISITE`, `SOURCE_CONFLICT`, `NO_CANONICAL_PERIOD_ORDER`, `NO_TARGET_COURSE_CONTEXT`.

Every conceptual result is `{policy_version, capability, status, observations, signals, reason_codes, evidence, missing_inputs, limitations}`. It contains no conversational explanation or mutable “now” timestamp. Any semantic behavior change requires a policy-version increment.

## 7. Performance intelligence and grade boundary

Safe V1 observations: passed/failed/withdrawn/in-progress attempt counts; repeat count; fail→pass recovery; repeated failures; requirement-group/required-course/zero-credit completion; dependency exposure; currently blocked required courses; and progress-state distribution. No academic-period trend exists because EVID-010 is open.

`raw_numeric_grade`, `raw_letter_grade`, and `raw_grade_points` have only SAFE_FACTUAL_USE: record that verified raw-grade data exists for a stated number of attempts. INTERPRETIVE_USE_BLOCKED includes thresholds, mappings, quality labels, GPA, pass/fail conversion, comparisons, or readiness/risk effects until complete applicable policy evidence is approved.

## 8. Strengths and difficulty policy

V1 strengths are evidence, not traits: consistent successful required-course completion and documented fail→pass recovery. Domain strength is `NOT_SUPPORTED` pending EVID-017. Difficulty signals are repeated failed attempts in the same course, repeated withdrawal attempts in a required course, and a required-course bottleneck; no severity level is assigned. Each rule is defined in the rule catalog and abstains on missing/ambiguous evidence.

## 9. Readiness and eligibility separation

Readiness means **academic preparation evidence**, not emotional/psychological readiness. Phase 5 answers permission and remains authoritative. Readiness may state `PREPARATION_EVIDENCE_AVAILABLE`, `CAUTION_EVIDENCE_AVAILABLE`, `INSUFFICIENT_DATA`, `NOT_APPLICABLE`, or `REVIEW_REQUIRED`; it never changes an eligibility decision or claims probability. Allowed V1 inputs are target prerequisite outcomes/history, repeats, IN_PROGRESS context, dependency history, and progress/requirement context. Grades remain blocked; unrelated GPA/personality inputs are forbidden. See [academic-readiness-matrix.md](academic-readiness-matrix.md).

## 10. Structural and predictive risk

Structural risk is a deterministic warning: repeated required-course failure, repeated withdrawal of a required course, unresolved prerequisite bottleneck, or concentrated dependency blockage. It says what happened and why it matters structurally, never that a student will fail. Predictive risk is `BLOCKED_BY_EXTERNAL_DATA` until governed cohort data, labels, temporal validation, calibration, subgroup/fairness analysis, institutional approval, monitoring, and retirement criteria exist. See [academic-risk-boundary.md](academic-risk-boundary.md).

## 11. Domain, provenance, repetitions, and special course semantics

`DOMAIN_INTELLIGENCE` is deferred pending approved versioned taxonomy; course names never classify a domain. `OFFICIAL_VERIFIED` and `MANUAL_ACADEMIC_REVIEW` may drive approved rules subject to the rule’s evidence requirements; `STUDENT_RECORD` may support factual history only; `UNVERIFIED` cannot drive deterministic conclusions; `DERIVED_DETERMINISTIC` is traceable output only; `MODEL_OUTPUT` never becomes ground truth.

History is never collapsed: FAIL→PASS is recovery evidence; FAIL→FAIL supports repeated difficulty; WITHDRAWN→PASS records recovery without assuming cause; FAILED→IN_PROGRESS remains caution evidence; multiple withdrawals remain factual withdrawal history. PASSED retains current Phase 5/6 semantics. Zero-credit required courses are structurally relevant and never weighted as unimportant. Referenced-only courses may appear as prerequisite history/evidence, never as Plan 12 progress or strength dimensions. Unresolved/source-conflict rules produce `REVIEW_REQUIRED`, no inferred relation or positive/negative judgment.

## 12. Privacy and AI boundary

Internal engines use minimum necessary owner-scoped evidence. Student APIs expose derived, minimized evidence; advisor access requires future authorization; institutional use requires approved aggregate governance. Raw grades, source references, and provenance detail are not copied by default.

LLMs may interpret questions, select supported capabilities, summarize deterministic results, and phrase limitations. They may not invent conclusions/evidence, reinterpret grades, assign probabilities, override eligibility, resolve conflicts, or create taxonomy. Morshidi has **no single overall student score**: collapsing heterogeneous, incomplete evidence into one number is arbitrary and harmful.

## 13. Future extensions

Domain strengths, workload intelligence, ordered trends, predictive risk, career/skills graphs, digital twins, what-if/delay simulation, mock registration, demand intelligence, advisor copilot, aggregates, and multi-institution use require separately versioned policies/data governance. Nothing here is Plan-12-specific.

## 14. P3.2 implementation contract and acceptance

After approval: (1) shared models/status/evidence/reason contracts, (2) performance observations, (3) strengths, (4) difficulty, (5) readiness, (6) structural-risk, (7) read-only orchestration/service, (8) golden/boundary/missing-data/provenance tests. No integration into recommendations/planning, no UI, no prediction, and no LLM decisioning. Acceptance requires catalog-rule fidelity, determinism, explicit abstention, provenance enforcement, Phase 5 invariance, and full regression evidence.
