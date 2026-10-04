# Student performance data contract

## Purpose and boundary

This is the authoritative Phase P2 entry contract. It specifies required semantics before any migration, importer, repository, or intelligence engine is built. It does not select database field names or invent Zarqa grading values. The implemented storage-only foundation is recorded in [student-performance-foundation.md](student-performance-foundation.md); it does not authorize intelligence implementation.

**Traceability:** PROP-002, PROP-007, PROP-077, and PROP-078 require the foundation; PROP-011--014, PROP-017--018, PROP-054--055, PROP-058, PROP-081--082 consume later approved outputs. Each external dependency is identified in [official-data-source-request-pack.md](official-data-source-request-pack.md).

## 1. Normalized input layers

| Layer | Contains | Must not contain |
|---|---|---|
| Authoritative raw student record | source identifiers, official course attempts, official outcome, supplied grade representation, term values, credits, repeat/transfer/withdrawal flags, source version | derived GPA, inferred outcomes, model labels |
| Verified policy metadata | policy issuer, version/effective scope, grade representation/range, mappings, pass/repeat/withdrawal/transfer/zero-credit rules | guessed defaults or unversioned generic rules |
| Derived deterministic observation | reproducible as-of snapshot, input/source/policy versions, calculation version | source facts rewritten as derived facts |
| Model output | validated output version, input snapshot, drivers, uncertainty, applicability | unvalidated labels or LLM-invented conclusions |

No student-reported fact may silently move into the authoritative raw-record layer.

## 2. Course-attempt record contract

| Classification | Semantic requirement | Evidence ID / PROP IDs |
|---|---|---|
| REQUIRED | Source-system record identifier and immutable import/batch/version reference. | EVID-009; PROP-002, 007, 077, 078 |
| REQUIRED | Pseudonymous internal student mapping, with a controlled mapping process; no names in analytics exports. | EVID-009; PROP-002, 077, 078 |
| REQUIRED | Official course code and course-identity/version resolution outcome. Unknown codes must be reported, not auto-created. | EVID-009, EVID-016; PROP-002, 007, 077 |
| REQUIRED | Explicit authoritative attempt outcome, including the source system's exact representation. | EVID-009, EVID-012, EVID-014; PROP-007, 077, 078 |
| REQUIRED | Stable institutional academic-period identity and ordering. | EVID-010; PROP-007, 078 |
| REQUIRED | Attempt sequence or source ordering sufficient to distinguish repeats. | EVID-009, EVID-011; PROP-007, 077, 078 |
| REQUIRED when supplied by the institution | Numeric grade plus its representation/scale/policy version; absent values remain absent. | EVID-008, EVID-009, EVID-013; PROP-007, 077, 081 |
| REQUIRED when supplied by the institution | Letter grade and grade points, each with policy/version context. | EVID-008, EVID-009, EVID-013; PROP-007, 077, 081 |
| REQUIRED | Attempt credit value and whether it is institutional attempt credit versus catalog credit. | EVID-009, EVID-015; PROP-007, 077, 078 |
| REQUIRED | Repeat, transfer/equivalent, and withdrawal indication exactly as the source provides. | EVID-008, EVID-009, EVID-011, EVID-014; PROP-007, 077, 078 |
| REQUIRED | Provenance class, authority, verification/reconciliation state, observed/exported timestamp, and correction/supersession reference. | EVID-008--010; PROP-002, 007, 077, 078 |
| OPTIONAL | Course completion date or period bounds when officially supplied. | EVID-009, EVID-010; PROP-078 |
| OPTIONAL | Official cumulative/semester GPA snapshots, retained as supplied facts with policy version. | EVID-008, EVID-009, EVID-013; PROP-007, 077, 081 |
| DERIVED | Normalized grade interpretation, GPA calculation, earned-credit reconciliation, and feature snapshots. | Verified policy plus authoritative raw records; PROP-007, 078 |
| NOT_NEEDED | Names, emails, phone numbers, addresses, free-text adviser notes, demographic attributes, attendance, or instructor ratings. | Not required for P2 foundation. |

Existing `PASSED`/`FAILED`/`IN_PROGRESS`/`WITHDRAWN` records remain historical operational outcomes. A numeric or letter grade never retroactively changes them without a versioned official reconciliation policy.

## 3. Grades and policy contract

Before grade-based processing, the issuer and effective version must explicitly state: numeric range/precision; whether numeric and/or letter grades are transcript fields; letter mapping; grade points and GPA scale/conversion/rounding; pass threshold; handling of failed, repeated, withdrawn, transfer/equivalent, and zero-credit attempts; and whether those policies vary by date, program, plan, or course. Every imported grade must reference the applicable policy version or be held as `UNVERIFIED`/unusable for deterministic intelligence.

## 4. Academic-period contract

The official source must supply a stable academic-year value plus institution term identifier, term type/name, and deterministic ordering. A later internal canonicalization may normalize formatting only after it maps losslessly to those official values and preserves source version. Creation/import timestamps never substitute for the period of study.

## 5. Repeats, transfers, withdrawals, and zero-credit attempts

The source must distinguish repeated attempts rather than collapse them. Policy determines whether the latest, highest, all, or another official treatment applies to GPA/credits; Morshidi must retain raw history and the policy result separately. Transfers/equivalencies require source-provided status and approved institutional treatment; catalog equivalency structure is not proof of a student's transfer credit. Withdrawal and zero-credit behavior requires the applicable official policy even though current Plan 12 structural accounting safely models two zero-credit requirements.

## 6. Provenance and authority rules

| Provenance | Exact meaning | May drive eligibility/progress | May drive ranking/intelligence |
|---|---|---|---|
| `OFFICIAL_VERIFIED` | Authenticated institutional source, policy/version matched, and reconciliation completed. | Yes, within modeled rule scope. | Yes, when the relevant approved policy/engine exists. |
| `STUDENT_RECORD` | Authenticated student-entered factual record awaiting verification. | Current explicit outcomes only under existing product semantics; never silently upgraded. | No grade-based or model-based use. |
| `DERIVED_DETERMINISTIC` | Reproducible computation tied to fixed authoritative inputs and versions. | As explicitly defined by the relevant engine. | Yes only as an approved input/result, never as source replacement. |
| `MODEL_OUTPUT` | Validated, versioned output with drivers and applicability. | No. | Only where policy approves the specific model. |
| `MANUAL_ACADEMIC_REVIEW` | Authorized decision/correction tied to retained evidence and reviewer. | Yes if the approved review policy permits it. | Yes only under the same approved policy. |
| `UNVERIFIED` | Incomplete, unknown, or unvalidated source/semantics. | No new deterministic decision authority. | No. |

Missing required evidence yields `INSUFFICIENT_DATA` (or a machine-readable equivalent), never an estimate. This includes missing grade representation, policy, period, taxonomy, or cohort data.

## 7. Privacy, minimization, and retention

| Data class | Need / affected claims | Sensitivity | Pseudonymization / retention |
|---|---|---|---|
| Individual academic record | P2 foundation; PROP-002, 007, 077, 078 | Sensitive | Pseudonymize analytics use; retain only under approved correction/audit schedule. |
| Grade/policy metadata | PROP-007, 081 | Sensitive when individual; policy itself public/internal | Keep source versions needed to reproduce decisions. |
| Derived observations/model outputs | PROP-011--014, 078, 081--082 | Highly sensitive | Owner-scoped, versioned, expiry/review and correction path. |
| Cohort outcomes | PROP-013, 078, 082 | Restricted aggregate | Pseudonymous/de-identified; minimum necessary time period and approved retention. |

The system will not request names, emails, contact data, addresses, free-text notes, demographics, attendance, instructor ratings, or raw documents unless a later approved claim-specific contract proves necessity.

## 8. Future import boundary

An eventual importer must: validate source/batch/version metadata; reject or quarantine unknown courses rather than create them; validate period values against the approved period reference; validate grade representation only against its policy version; preserve source outcome; distinguish duplicate delivery from a distinct repeat; be idempotent by source-system record identity plus source version; reject records missing required provenance/identity/period fields; accept optional grade fields only as null/absent when the official source omits them; and produce a non-sensitive audit/error report with accepted, duplicate, rejected, quarantined, and superseded counts/reasons. Partial batches require an explicit all-or-nothing versus approved quarantine policy before implementation.

## 9. Phase P2 gate and deferrals

### P1.2 minimum safe foundation — P2_READY

Phase P2 may now model the following conceptual fields without inventing university semantics. `READY_TO_MODEL` means nullable/raw preservation only unless a listed policy becomes verified.

| Conceptual field | Status | P2 rule |
|---|---|---|
| Explicit attempt outcome (`PASSED`, `FAILED`, `IN_PROGRESS`, `WITHDRAWN`) | READY_TO_MODEL | Preserve current semantics exactly. |
| Attempt sequence | READY_TO_MODEL | Keep optional; do not derive authoritative ordering. |
| Numeric grade, letter grade, grade points | READY_TO_MODEL | Optional supplied raw values only; no range check, mapping, GPA calculation, or inferred outcome. |
| Source record reference, batch/version, provenance, verification/review state | READY_TO_MODEL | Required for new imported/reviewed facts; no source may be silently elevated. |
| Academic-year/term raw values | READY_TO_MODEL | Optional opaque source values; no canonical identity/order until EVID-010. |
| Course/attempt credit, repeat, transfer/equivalent, withdrawal flags | READY_TO_MODEL | Preserve supplied raw values; do not derive credit/GPA effects. |
| Policy version/effective scope | READY_TO_MODEL | Optional reference until an approved policy record exists. |
| Grade range/mapping/pass threshold/GPA conversion | BLOCKED_BY_EVIDENCE | EVID-008, EVID-012, EVID-013 required. |
| Canonical academic period and importer validation | BLOCKED_BY_EVIDENCE | EVID-009 and EVID-010 required. |
| Official identity reconciliation, zero-credit and transfer treatment | BLOCKED_BY_EVIDENCE | EVID-009, EVID-015, EVID-016 required. |
| Course domains, cohort features, offering data | DEFERRED | EVID-017, EVID-018, EVID-019 required. |

Synthetic fixtures and non-sensitive deterministic records are permitted for unit, migration, and integration testing. They must be visibly synthetic, carry no real student identifier, and never be represented as university data. Real student records are not required to begin P2 engineering.

### Gate checklist

| P2 prerequisite | Result | Basis |
|---|---|---|
| Data provenance semantics | PASS | Internal contract is closed. |
| Record authority hierarchy | PASS | Internal contract is closed. |
| Attempt-outcome compatibility | PASS | Existing explicit outcomes are preserved. |
| Safe synthetic test-data policy | PASS | Synthetic, non-sensitive fixtures are permitted. |
| Grade-field semantics sufficient for storage | PASS | Raw optional storage only; interpretation is blocked. |
| Academic-period semantics sufficient for storage | PASS | Raw opaque values only; canonicalization is blocked. |
| Privacy/minimization baseline | PASS | Internal purpose/minimization and correction rules are closed; institutional duration remains a placeholder. |
| Correction/update semantics | PASS | Provenance, review, and supersession boundary is defined. |
| Import validation contract | PASS | Boundary is defined; live implementation awaits EVID-009/010. |

**Exact decision: P2_READY.** This authorized the schema/data-model foundation described above, implemented by migration `20260921175041_add_student_performance_foundation.sql` and the pure `app.student.performance_import` boundary. It does not authorize importing real data, applying institutional policy, or producing grade-derived intelligence.

### Deferred without blocking the P2 foundation

- EVID-001--007 and EVID-016: required for complete Plan 12 source closure, but current `REVIEW_REQUIRED` behavior remains safe.
- EVID-017: required before strengths, weaknesses, or domain-based readiness outputs.
- EVID-018: required before predictive/population academic risk.
- EVID-019: required before offering-aware delay, scheduling, or workload claims.

Therefore **Phase P2 can begin before cohort data and before live university import access, but it must remain limited to the P1.2 raw-storage boundary until individual authoritative-record, policy, and period semantics are approved.**

## 10. Course-domain review template

This is a review template, not production taxonomy data: course code; official course title; proposed domain(s); whether multiple domains are approved; approved weight(s), if any; supporting curriculum source; issuer/version/effective date; reviewer; review decision; and change reason. The AI department/curriculum committee approves it. No domain label or weight is inferred from a course name.
