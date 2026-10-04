# Proposal data governance

## 1. Purpose and scope

This document is the Phase P1 evidence baseline for the Morshidi proposal. It records what the repository can prove now, what it deliberately does not claim, and the smallest approved contract boundary for a later student-performance foundation. It does not implement strengths, weaknesses, risk, readiness, grade-derived recommendations, or a schema migration.

Phase P1.1 turns each external dependency into an actionable request in [official-data-source-request-pack.md](official-data-source-request-pack.md), and formalizes the Phase P2 entry boundary in [student-performance-data-contract.md](student-performance-data-contract.md). It also re-checked the live official Plan 12 page: it confirms the captured raw prerequisite strings but does not resolve their semantics or version. Templates are header-only and explicitly non-sensitive: [student-record-import-template.csv](templates/student-record-import-template.csv) and [cohort-outcomes-template.csv](templates/cohort-outcomes-template.csv).

### Proposal traceability

Phase P1 directly owns **PROP-002, PROP-007, PROP-037, PROP-040, and PROP-077**. The data prerequisites documented here also gate **PROP-011--014, PROP-017--018, PROP-054--055, PROP-058, PROP-078, and PROP-081--082**. Their compliance statuses are unchanged: documenting a gap is not implementation evidence.

## 2. Existing authoritative data inventory

`supabase/migrations/0001_academic_catalog.sql` establishes the catalog. The current Plan 12 seed identifies Zarqa University, its Faculty of Information Technology, Artificial Intelligence major, Plan 12, six requirement groups, 68 plan-course memberships, and 132 required credit hours. Its sole registered plan source is the Zarqa study-plan URL in `20260916224842_seed_ai_plan12_foundation.sql`; it is typed `official_study_plan` but has `source_status = unknown` and no retrieved timestamp, snapshot, hash, or formal version populated.

| Entity / facts | Current fields or contract | Data classification |
|---|---|---|
| University, faculty, major | identity, Arabic/English names, country, active status | VERIFIED_SOURCE only to the extent represented by the seeded catalog; no current per-fact verification record |
| Study plan and requirement groups | plan number, total credits, effective year/status, group scope/type/credit requirements | VERIFIED_SOURCE for encoded Plan 12 structure; source version is not verified |
| Courses | code, names, catalog status, active status | VERIFIED_SOURCE for known seeded identities; six prerequisite-only identities are `referenced_only` |
| Study-plan course | membership, credit hours, learning/delivery mode, display order, raw prerequisite text, prerequisite and verification statuses, source link | VERIFIED_SOURCE for structured entries only where status is `verified` or `not_applicable`; raw text is a SNAPSHOT, not executable authority |
| Dependency groups/options | prerequisite/corequisite grouping, options, minimum grade text, verification status | VERIFIED_SOURCE only for `verified` groups/options; `referenced_only`, `unresolved`, and `source_conflict` retain their stated limits |
| Equivalencies | source and target course relationship with verification status | NOT_PRESENT for a verified Plan 12 equivalency dataset; schema capability alone is not evidence |
| Academic sources | university, type, URL, title, retrieval, plan number, availability, snapshot/hash, notes | SNAPSHOT / metadata capability; the seeded Plan 12 source is not fully populated or independently verified |
| Student academic profile | owner, plan, reported cumulative GPA/scale, reported earned credits | USER/ADMIN_ENTERED snapshot; no per-field provenance or reconciliation state |
| Student course attempt | course, explicit outcome, sequence, term label/date, free-text reported grade, record source | USER/ADMIN_ENTERED unless an actual import/integration record is supplied; explicit outcome is the current operational fact |

`student_academic_profiles` and `student_course_attempts` are owner-scoped with authenticated-user RLS. Current Phase 5--10 decisions consume explicit attempt outcomes and verified prerequisite structures. They do not parse raw prerequisite text or infer outcomes from a grade.

## 3. Student-performance inventory

| Requirement | Status | Evidence and limit |
|---|---|---|
| Attempt status | SUPPORTED | `PASSED`, `FAILED`, `IN_PROGRESS`, `WITHDRAWN` are explicit values. |
| Numeric grade | ABSENT | No numeric per-attempt field exists. |
| Letter / reported grade | PARTIAL | `reported_grade_text` is free text; it has no scale, mapping, or authority state. |
| Grade points | ABSENT | No per-attempt grade-points field exists. |
| Term / semester identifier | PARTIAL | `term_label` and optional `attempted_on` exist, but no stable academic-term identity/order. |
| Academic year | ABSENT | No academic-year field or referenced term entity exists. |
| Attempt order | PARTIAL | Optional positive `attempt_sequence`; uniqueness permits repeated attempts but does not make the sequence authoritative. |
| Course credits | SUPPORTED | Plan-course credit hours are catalog facts; not a transcript-credit record. |
| Cumulative GPA | PARTIAL | Profile stores reported GPA with a reported scale; it is passed through, not calculated or verified. |
| Semester GPA | ABSENT | No semester GPA or academic-period model. |
| Earned credits | PARTIAL | Profile stores reported earned credits; progress also derives plan/group credits from outcomes. The two are not reconciled. |
| Withdrawal | SUPPORTED | Explicit `WITHDRAWN` attempt outcome. |
| Repeated attempts | PARTIAL | Repeated rows are supported through `attempt_sequence`; repeat policy and authoritative ordering are absent. |
| Transfer / equivalent credit | ABSENT | Catalog equivalency capability is not student transfer-credit evidence. |
| Pass threshold | ABSENT | No verified policy is stored. |
| Grading scale | PARTIAL | A reported GPA scale exists, but no verified institutional grade-scale/version policy exists. |

## 4. Required contracts before performance intelligence

The following are minimum inputs, not algorithms or permission to collect them.

| Capability | Minimum required inputs | Optional inputs | Current data sufficient? | Official policy / cohort need | Deterministic V1 without cohort? |
|---|---|---|---|---|---|
| STRENGTHS_ANALYSIS | authoritative attempts, normalized grade observation, stable term ordering, approved course-domain taxonomy, grade/repeat policy | validated mastery thresholds, assessment evidence | No | grading/taxonomy policy required; cohort not necessarily | Only an approved, evidence-labeled rules V1; not from free text or self-report |
| WEAKNESSES_ANALYSIS | same as strengths plus approved definition of insufficient mastery | prerequisite/domain mapping, assessment evidence | No | grading/taxonomy policy required; cohort not necessarily | Only an approved, evidence-labeled rules V1 |
| ACADEMIC_RISK | longitudinal authoritative performance, course context, validated target/outcome definition | workload and offerings data | No | policy and representative historical cohort data required | No population/predictive risk claim; structural prerequisite blockers already exist but are not risk |
| PERSONAL_READINESS | approved readiness definition, authoritative performance, prerequisite mastery, term/repeat context | workload/capacity and advising evidence | No | policy and expert validation required; cohort if statistical | Only a formally approved deterministic rule, with explicit limitations |
| PERFORMANCE_INTELLIGENCE | source-versioned observations, provenance, stable academic periods, reproducible as-of snapshot | cohort measures and model monitoring data | No | official records/policy required; cohort for statistical outputs | A deterministic feature snapshot only, not labels or prediction |

No current course-domain taxonomy exists. The proposal requires domain-level claims (for example programming or mathematics); Plan structure is not a substitute for approved domain labels. A later taxonomy must be a versioned, academically reviewed mapping from course code to one or more domains, with source and effective-date evidence.

No historical pass rates, average grades, prerequisite-failure patterns, cohort statistics, or verified difficulty labels are in the repository. They must never be fabricated or inferred from course names.

## 5. Numeric grades, academic periods, and grading policy

The current model preserves historical `PASSED`/`FAILED`/`IN_PROGRESS`/`WITHDRAWN` outcomes. Any future normalized grade observation must not retroactively recalculate or overwrite those outcomes without an explicit, versioned institutional reconciliation policy.

A later minimal normalized observation contract must be approved before implementation. Its semantics must distinguish: the observed grade value and representation; its grade-scale/policy version; optional official letter grade and grade points where supplied; authoritative institutional outcome; source record/batch; verification/reconciliation state; and as-of/correction history. Field names, types, and mappings are intentionally not chosen in P1 because Zarqa's policy and source format are not yet verified.

`term_label` and `attempted_on` are insufficient for longitudinal analytics. The later academic-period contract needs a stable institutional term identifier, academic year, term name/number, ordered start/end or completion bounds, and a defined relation to each attempt. Wall-clock audit timestamps are not an academic term identity.

There is no verified Zarqa grading policy in the repository for pass thresholds, letter mappings, GPA scale, repeated courses, withdrawals, failed attempts, or zero-credit courses. Each item is **OFFICIAL_SOURCE_REQUIRED**; generic university or Jordanian assumptions are prohibited.

## 6. Provenance, authority, and missing-data behavior

### Proposed provenance vocabulary

Future intelligence-relevant facts must be classified as exactly one primary provenance state:

| State | Meaning | Current support |
|---|---|---|
| `OFFICIAL_VERIFIED` | Source record and policy/version have been authenticated and reconciled. | Partial: attempt `record_source` can name an import/integration, but lacks per-fact verification/version linkage. |
| `STUDENT_RECORD` | Authenticated student-entered factual record, not yet institutionally verified. | Partial: owner-scoped profile/attempts and `manual_entry`. |
| `DERIVED_DETERMINISTIC` | Reproducible output from identified inputs and versioned rules. | Partial: progress/eligibility/recommendation outputs exist, but no generic provenance record. |
| `MODEL_OUTPUT` | Versioned validated model output with snapshot, drivers, and uncertainty. | Absent. |
| `MANUAL_ACADEMIC_REVIEW` | Authorized correction or decision linked to the reviewer and evidence. | Partial: `admin_correction` label only; no reviewer/evidence linkage. |
| `UNVERIFIED` | Source exists but authority, completeness, or semantics are not established. | Partial: `reported_grade_text`, unknown source status, and unresolved catalog facts. |

### Authority hierarchy

1. Official SIS/transcript or officially published catalog/policy, reconciled to the applicable source version.
2. Authorized academic correction/review tied to retained official evidence.
3. Authenticated student self-report, displayed as such and awaiting reconciliation.
4. Unverified input or imported material without confirmed policy/version.

Only levels 1--2 may drive future grade-based deterministic intelligence. Level 3 can support review workflows but cannot silently become authoritative academic history. Level 4 cannot drive such intelligence. Existing explicit attempt outcomes remain the authoritative operational input for current eligibility/progress behavior only as represented in the student record; a numeric grade cannot redefine them without the approved policy above.

Future engines must return an explicit `INSUFFICIENT_DATA` (or an equally machine-readable not-applicable state) when required evidence is missing. No numeric grades means no grade-based strength/weakness measure; no historical cohort means no population-risk claim; no official scale means no derived GPA or grade classification; no approved taxonomy means no domain claim. An LLM may explain an authoritative result but may not fill these gaps.

## 7. Plan 12 source closure and referenced-only identities

The detailed source-resolution backlog is `docs/plan12-source-closure.md`. Current Plan 12 target-course counts are **30 `not_applicable`, 32 `verified`, 4 `unresolved`, and 2 `source_conflict`**. Thus 62 of 68 target courses have a source-closed status (`verified` or `not_applicable`), but only 32 have verified prerequisite logic. The remaining six must continue to return `REVIEW_REQUIRED`; no raw-text parser fallback is permitted.

The six identities `0200150`, `0200151`, `0201001`, `0202001`, `0300103`, and `0301241` are `referenced_only`: their codes are known, names and credit hours are null, they are not Plan 12 memberships, and they occur only as prerequisite options. They must not be promoted to requirements without official catalog evidence.

## 8. Academic source registry and governance status

`academic_sources` can hold title, type, URL, plan number, retrieval timestamp, source availability, snapshot reference, content hash, and notes. It is not yet sufficient for proposal-grade source closure because the current model has no explicit issuing authority field (only its university link), source-issued/effective date or version, assertion-level scope, fact-verification status, or conflict relationship. `source_status` means availability, not correctness.

Keep Phase 5 prerequisite statuses unchanged: `not_applicable`, `verified`, `unresolved`, and `source_conflict`. The governance overlay for a later approved source record should use `VERIFIED`, `UNRESOLVED`, `SOURCE_CONFLICT`, and `OFFICIAL_SOURCE_REQUIRED`, separately from rule-evaluation semantics. A minimal future extension would link an academic assertion or source-resolution decision to the source, issuing authority, scope, issued/effective version, verification state, extraction/review notes, and any conflicting source/decision. P1 does **not** create it because no official records or approved assertion semantics are available to populate it.

## 9. External dependency register

| ID | Data needed | Claims affected | Authority / provider | Can local implementation proceed? | Demo fallback | Final evidence |
|---|---|---|---|---|---|---|
| EXT-01 | Written resolution of six Plan 12 prerequisite expressions | PROP-003, PROP-037, PROP-040 | Zarqa curriculum authority / AI department | No source closure; current safe behavior continues | Show `REVIEW_REQUIRED` | dated, authoritative rule evidence and source-linked structured update |
| EXT-02 | Grading scale, pass threshold, repeat/withdrawal/zero-credit rules | PROP-002, PROP-007, PROP-077, PROP-081 | Registrar / academic regulations owner | No grade normalization or grade intelligence | Existing outcome-only demo | versioned official policy |
| EXT-03 | De-identified authoritative transcripts and import format | PROP-002, PROP-007, PROP-077, PROP-078 | Registrar / IT data office | Contract design only | no fake grades; use current explicit outcomes | approved sample, dictionary, provenance and reconciliation evidence |
| EXT-04 | Course-domain taxonomy and review criteria | PROP-011, PROP-012, PROP-014 | AI department / curriculum owner | No domain intelligence | structural progress only | approved versioned mapping |
| EXT-05 | Historical cohort outcomes and approved use basis | PROP-013, PROP-078, PROP-082 | Registrar / institutional data-governance owner | No predictive risk | no risk claim | governed de-identified export and validation protocol |
| EXT-06 | Workload/offerings/capacity definitions if included | PROP-014, PROP-023, PROP-054--055 | Department / registrar | No workload or delay claims | current structural plans only | versioned official dataset/policy |

## 10. Privacy and minimization

| Class | Examples | Minimum handling |
|---|---|---|
| Public catalog data | plans, courses, official rule sources | preserve source/version and restrict editing to approved workflows |
| Student academic record | attempts, grades, transcript import, GPA, term history | owner-scoped access, RLS, encryption/platform controls, audit/correction path, purpose limitation |
| Derived student intelligence | strength/weakness/readiness/risk outputs and drivers | no output without validated basis; owner-scoped access, version/expiry, explainability and correction/review path |
| Aggregate analytics | cohort outcomes and calibration data | de-identify, minimum cohort thresholds, controlled access, approved purpose and retention |
| Pilot survey data | consent, responses, usability results | separate consent/purpose, pseudonymize where possible, do not merge beyond approved protocol |

Collect only data that maps to a proposal claim and an approved capability. Do not collect demographics, workload, attendance, or broad document archives “just in case.” Retain source snapshots and decision provenance only for the approved audit/correction period; define deletion, correction, import-batch rollback, access review, and source-version supersession before Phase P2 implementation.

## 11. Schema gap decision and Phase P2 acceptance

**P1 decision (superseded by P1.2): NO MIGRATION YET.** Current gaps were real, but their semantics depended on missing official grading, transcript, academic-period, taxonomy, and source-resolution evidence. P1.2 subsequently authorized nullable/raw preservation only. Phase P2 implements that limited foundation in [student-performance-foundation.md](student-performance-foundation.md), without encoding grading, period, or intelligence semantics.

The original P1 gate required the following before an authoritative import or grade-derived intelligence could begin; P1.2 supersedes it for the narrower raw-storage foundation only:

1. The six-row Plan 12 closure backlog has an assigned official owner, source request, and no inferred resolution; structured rule changes wait for written evidence.
2. Zarqa grade, pass, repeat, withdrawal, zero-credit, and GPA policy is supplied with effective/version metadata.
3. The transcript/import record layout and reconciliation authority are approved, including official versus student-reported semantics.
4. The stable academic-period contract is approved.
5. The minimal provenance/source-resolution data contract is approved, including retention, correction, deletion, and owner-isolation requirements.
6. A de-identified representative record set and permitted test strategy are available before importer/feature-snapshot implementation.

### P1.1 readiness classification

| State | Evidence contract result |
|---|---|
| READY_FOR_P2 | The contract, provenance vocabulary, import boundary, templates, and precise evidence requests are documented. No implementation is authorized by this state alone. |
| BLOCKING_FOR_AUTHORITATIVE_IMPORT_OR_GRADE_INTERPRETATION | EVID-008--015 (grading-policy package), EVID-009 (transcript schema and test-data permission), EVID-010 (academic period), and approved privacy/correction/retention semantics. |
| DEFERRED_TO_EXTERNAL_DATA | EVID-001--007 and EVID-016 for full Plan 12 closure; EVID-017 for domain outputs; EVID-018 for predictive risk; EVID-019 for offering-aware claims. These do not block a safe P2 foundation. |

### P1.2 gate decision

**P2_READY.** Official public material partially verifies Plan 12 provenance and several grading-policy concepts, while the internal provenance, privacy/minimization, correction, backward-compatibility, and synthetic-test-data decisions are closed. Phase P2 now models optional raw supplied grade/period/credit facts with provenance and preserves current outcomes; the implementation evidence is [student-performance-foundation.md](student-performance-foundation.md). It does not validate, normalize, calculate, infer, import live university data, or produce intelligence from those facts until the remaining external evidence is supplied. The complete status register is [evidence-closure-status.md](evidence-closure-status.md).

## 12. Open official-source requests

- Curriculum authority: exact AND/OR/course semantics and source version for `0200105`, `0200106`, `1505311`, `1505320`, `1505366`, and `1505461`.
- Registrar/regulations owner: official grading policy, transcript dictionary, repeat and withdrawal treatment, and Plan 12 source effective/version date.
- AI department: approved course-domain taxonomy and any future readiness/strength/weakness definitions.
- Institutional data-governance owner: approved de-identified cohort dataset and governance basis before predictive-risk work.
