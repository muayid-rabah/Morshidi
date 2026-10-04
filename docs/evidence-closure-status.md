# Evidence closure status — Phase P1.2

## Decision basis

This register applies exactly one Phase P1.2 status to each evidence item. `CLOSED_VERIFIED` requires the complete final-closure evidence specified in the request pack; none meets that bar. Public Zarqa University material was rechecked alongside all repository reference material.

Two official web sources add limited, verifiable evidence:

- The [AI Department Plan 12 page](https://www.zu.edu.jo/ar/Collage/Science_and_Technology/Dept_Artificial/GetStudyPlan.aspx?Dept=1505&fac=15&id=110&page=205) confirms the stored Plan 12 title and all six raw prerequisite strings, but not their grouping semantics, effective version, or referenced-only identities.
- The [Admission and Registration GPA calculator](https://www.zu.edu.jo/ar/AdmissionAndRegisteration/calculate.aspx?id=65&page=16) exposes fields for current cumulative GPA, included credits, expected grade, credits, course state, and prior grade. Its UI displays expected grade `35`–`100` and prior grade `35`–`59`.
- The published [Guide2025.pdf](https://zu.edu.jo/ar/deans/files/Guide2025.pdf) includes the university's bachelor-degree instructions and provisions on grading classification, repeated courses, withdrawal, transfer, and minimum cumulative GPA. It is useful policy evidence, but it does not establish the complete import-schema, source-version applicability, or every field-level semantic required for automatic processing.

| ID | Purpose | PROP IDs | Status | Evidence | Remaining question | P2 blocking | Advanced-model blocking | External owner | Next action |
|---|---|---|---|---|---|---|---|---|---|
| EVID-001 | Plan 12 authority/version | 003, 037, 040 | PARTIALLY_VERIFIED | Official Plan 12 page confirms title/raw rows. | Effective date, approved version, and assertion scope. | No | No | Registrar/curriculum authority | Obtain dated approved plan or signed extract. |
| EVID-002 | Resolve `0200105` | 003, 037, 040 | OPEN_EXTERNAL | Official page repeats `0200150,0201001`. | Identities, AND/OR semantics, minimum grade. | No | No | Curriculum authority/registrar | Provide dated rule or ruling. |
| EVID-003 | Resolve `0200106` | 003, 037, 040 | OPEN_EXTERNAL | Official page repeats `0200151,0202001`. | Identities, AND/OR semantics, minimum grade. | No | No | Curriculum authority/registrar | Provide dated rule or ruling. |
| EVID-004 | Resolve `1505311` | 003, 037, 040 | OPEN_EXTERNAL | Official page repeats `1505101,1505201`. | Exact grouping and minimum-grade condition. | No | No | AI curriculum authority | Provide dated rule or ruling. |
| EVID-005 | Resolve `1505320` conflict | 003, 037, 040 | OPEN_EXTERNAL | Official page repeats `0300103,1505311`. | Governing source, competing artifacts, `0300103` identity, final rule. | No | No | Curriculum authority/registrar | Provide conflict-resolution decision. |
| EVID-006 | Resolve `1505366` conflict | 003, 037, 040 | OPEN_EXTERNAL | Official page repeats `0301241,1505101`. | Governing source, competing artifacts, `0301241` identity, final rule. | No | No | Curriculum authority/registrar | Provide conflict-resolution decision. |
| EVID-007 | Resolve `1505461` | 003, 037, 040 | OPEN_EXTERNAL | Official page repeats `1505366,1505415`. | Exact grouping after `1505366` is resolved. | No | No | AI curriculum authority | Provide dated rule or ruling. |
| EVID-008 | Complete grading policy | 002, 007, 077, 081 | PARTIALLY_VERIFIED | Official bachelor guide and official GPA calculator. | Applicable policy version/scope and full machine-readable policy. | No for raw optional storage; Yes for grade interpretation. | Yes | Registrar/regulations owner | Certify current/historical policy package. |
| EVID-009 | Transcript schema | 002, 007, 077, 078 | OPEN_EXTERNAL | Student portal exists; no export dictionary/sample is public. | Field names, identifiers, corrections, provenance, export version. | No for schema-only foundation; Yes for importer. | No | Registrar/IT data office | Provide approved dictionary and de-identified sample. |
| EVID-010 | Academic-period policy | 007, 078 | OPEN_EXTERNAL | Schedule page exposes no stable period values/order. | Academic year, term identity/type/order, history. | No for raw opaque storage; Yes for canonicalization/import validation. | No | Registrar | Provide period reference/data dictionary. |
| EVID-011 | Repeat policy | 007, 077, 078, 081 | PARTIALLY_VERIFIED | Official bachelor guide contains repeated-course provisions. | Applicable version, exact transcript representation, and machine-readable GPA/credit treatment. | No for raw preservation; Yes for derivation. | Yes | Registrar/regulations owner | Certify policy section and applicability. |
| EVID-012 | Pass threshold | 007, 011, 012, 014 | PARTIALLY_VERIFIED | Official guide contains grade-classification/pass provisions; calculator exposes grade input ranges. | Applicable scope/version and exceptions. | No for raw storage; Yes for outcome derivation. | Yes | Registrar/regulations owner | Certify threshold policy. |
| EVID-013 | GPA scale | 007, 077, 081 | PARTIALLY_VERIFIED | Official guide and GPA calculator establish GPA-related public functionality. | Full conversion, rounding, scale, and version. | No for raw snapshots; Yes for calculation. | Yes | Registrar/regulations owner | Certify GPA policy. |
| EVID-014 | Withdrawal policy | 007, 077, 078 | PARTIALLY_VERIFIED | Official bachelor guide contains withdrawal provisions. | Current applicability and exact transcript/outcome/credit semantics. | No for raw flag; Yes for derivation. | Yes | Registrar/regulations owner | Certify policy section. |
| EVID-015 | Zero-credit policy | 007, 077, 078 | OPEN_EXTERNAL | Plan 12 shows zero-credit catalog courses only. | Official record, GPA, credit, and outcome treatment. | No for raw optional flag; Yes for derivation. | Yes | Registrar/regulations owner | Provide policy section. |
| EVID-016 | Referenced-only identities | 003, 037, 040 | OPEN_EXTERNAL | Codes appear only in raw prerequisites. | Official identities/status; no plan-membership inference. | No | No | Registrar/curriculum authority | Provide catalog extract. |
| EVID-017 | Course-domain taxonomy | 011, 012, 014 | DEFERRED_ADVANCED_MODEL | No approved taxonomy is available. | Reviewed domains, weights, version/change control. | No | Yes | AI department/curriculum committee | Approve review template. |
| EVID-018 | Cohort/historical outcomes | 013, 078, 082 | DEFERRED_ADVANCED_MODEL | No governed cohort export is available. | Approved pseudonymous dataset and validation use basis. | No | Yes | Registrar/data-governance owner | Approve export and protocol. |
| EVID-019 | Course offerings | 023, 054, 055 | NOT_REQUIRED_FOR_P2 | Current schedule page has no versioned offering dataset. | Term/course/section availability data. | No | No | Department/registrar | Request only before offering-aware capability. |

## Field availability from currently accessible material

| Record fact | Evidence-based result |
|---|---|
| Numeric grade | VERIFIED_AVAILABLE as a public GPA-calculator input; transcript representation remains UNKNOWN. |
| Letter grade | UNKNOWN. |
| Grade points | UNKNOWN. |
| Academic term/year | UNKNOWN as a stable record identity. |
| Attempt sequence / repeat marker | UNKNOWN as a transcript field; repeat policy is partially verified. |
| Withdrawal state | VERIFIED_AVAILABLE as a governed concept; transcript encoding remains UNKNOWN. |
| Transfer/equivalent marker | UNKNOWN as a transcript field; guide addresses transfer context, not export representation. |
| Cumulative GPA | VERIFIED_AVAILABLE as a public calculator input; transcript/export semantics remain UNKNOWN. |
| Semester GPA | UNKNOWN. |
| Credits | VERIFIED_AVAILABLE as a public calculator input; transcript/export semantics remain UNKNOWN. |

## Internal closure and P2 decision

The provenance vocabulary, authority hierarchy, purpose limitation, minimum collection, correction provenance, and synthetic-test-data policy are internal Morshidi decisions and are **CLOSED_VERIFIED internally**. They do not claim university policy.

**P2_READY** means a schema foundation may preserve existing outcomes and store supplied source facts as optional raw values with provenance. It does not authorize a live importer, automatic grade validation/conversion, canonical period ordering, GPA calculation, source-rule resolution, or any intelligence output. Those remain constrained by the open evidence above.
