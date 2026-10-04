# Official academic evidence and data-source request pack

## Use and evidence register

This pack is for Zarqa University academic owners. It requests evidence; it neither treats an answer as received nor changes any Morshidi rule. All requests support the rules-first boundary: AI may explain an authoritative result, but rules/models decide only from approved evidence.

**Repository and official-source re-audit result:** the only stored Plan 12 source is the seeded official-study-plan URL, with `source_status = unknown`. The live Zarqa University page confirms it is the AI Department Plan 12 page and independently reproduces the six stored raw prerequisite strings. It does not provide an effective date/version, referenced-only identities, AND/OR semantics, minimum-grade conditions, grading policy, transcript schema, academic-period policy, taxonomy, cohort export, course-offering dataset, or competing prerequisite artifact. Therefore **no prerequisite-rule issue is closed**; EVID-001 is partially evidenced and all other requests remain open.

| Evidence ID | Class | Affected PROP IDs | Purpose | Required authority | Minimum acceptable evidence | Preferred source | Fallback source | Status | Can P2 foundation proceed without it? | Final closure evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| EVID-001 | CURRICULUM_RULE | PROP-003, PROP-037, PROP-040 | Establish issuing authority, effective date/version, and scope for the Plan 12 source. | Registrar or curriculum authority | Dated approved Plan 12/curriculum document identifying plan number and effective version. | Official issued plan PDF or signed electronic record. | Registrar-signed curriculum extract. | PARTIAL — live official page confirms plan identity and raw rows, but not version/effective date. | Yes; prerequisite semantics remain `REVIEW_REQUIRED`. | Source record with issuer, version/effective date, file/URL, snapshot and approval. |
| EVID-002 | PREREQUISITE_RESOLUTION | PROP-003, PROP-037, PROP-040 | Resolve `0200105`. | Curriculum authority / registrar | Exact prerequisite expression, identities of cited codes, AND/OR semantics, and minimum-grade condition if any. | Current official course catalog/plan. | Dated signed academic ruling. | OPEN | Yes; no rule change until received. | Approved, versioned source linked to structured dependency update. |
| EVID-003 | PREREQUISITE_RESOLUTION | PROP-003, PROP-037, PROP-040 | Resolve `0200106`. | Curriculum authority / registrar | Exact prerequisite expression, identities of cited codes, AND/OR semantics, and minimum-grade condition if any. | Current official course catalog/plan. | Dated signed academic ruling. | OPEN | Yes; no rule change until received. | Approved, versioned source linked to structured dependency update. |
| EVID-004 | PREREQUISITE_RESOLUTION | PROP-003, PROP-037, PROP-040 | Resolve `1505311`. | AI department curriculum authority | Exact prerequisite grouping and any minimum-grade condition. | Current official AI plan/catalog. | Dated signed academic ruling. | OPEN | Yes; no rule change until received. | Approved, versioned source linked to structured dependency update. |
| EVID-005 | PREREQUISITE_RESOLUTION | PROP-003, PROP-037, PROP-040 | Resolve source conflict for `1505320`. | Curriculum authority / registrar | Competing source artifacts or superseding ruling, exact final expression, identity of `0300103`, and effective date. | Official plan/catalog versions. | Dated conflict-resolution decision. | OPEN | Yes; no rule change until received. | Both sources and decision, or superseding authority, retained and linked. |
| EVID-006 | PREREQUISITE_RESOLUTION | PROP-003, PROP-037, PROP-040 | Resolve source conflict for `1505366`. | Curriculum authority / registrar | Competing source artifacts or superseding ruling, exact final expression, identity of `0301241`, and effective date. | Official plan/catalog versions. | Dated conflict-resolution decision. | OPEN | Yes; no rule change until received. | Both sources and decision, or superseding authority, retained and linked. |
| EVID-007 | PREREQUISITE_RESOLUTION | PROP-003, PROP-037, PROP-040 | Resolve `1505461`. | AI department curriculum authority | Exact prerequisite grouping and confirmation after the `1505366` rule is resolved. | Current official AI plan/catalog. | Dated signed academic ruling. | OPEN | Yes; no rule change until received. | Approved, versioned source linked to structured dependency update. |
| EVID-008 | GRADING_POLICY | PROP-002, PROP-007, PROP-077, PROP-081 | Establish official grading-policy version and scope. | Registrar / academic regulations owner | Approved policy covering grade representation, grade points, GPA calculation, repeat, withdrawal, transfer, and zero-credit handling. | Official regulations/PDF. | Registrar-certified extract. | PARTIAL — public bachelor guide and GPA calculator provide limited evidence, not a complete applicable policy package. | Yes for raw optional storage; no for grade interpretation. | Versioned policy with issuer, effective dates, and retained source. |
| EVID-009 | TRANSCRIPT_SCHEMA | PROP-002, PROP-007, PROP-077, PROP-078 | Define authoritative individual-record export and identifier mapping. | Registrar / IT data office | Field dictionary plus one de-identified representative export and source/version semantics. | SIS export specification. | Registrar-approved data dictionary and sample. | OPEN | **No**. | Approved schema, sample validation, and data-governance approval. |
| EVID-010 | ACADEMIC_PERIOD_POLICY | PROP-007, PROP-078 | Define stable institutional academic period identity and ordering. | Registrar | Academic-year and term code/name/order policy, including effective history. | Registrar term calendar/data dictionary. | Registrar-signed extract. | OPEN | **No**. | Versioned period reference and accepted canonicalization mapping. |
| EVID-011 | REPEATED_COURSE_POLICY | PROP-007, PROP-077, PROP-078, PROP-081 | Define attempt ordering, replacement/accumulation, and transcript representation of repeats. | Registrar / regulations owner | Official repeat treatment for transcript, GPA, earned credits, and authoritative outcome. | Regulations/PDF. | Registrar-certified policy extract. | PARTIAL — public bachelor guide contains repeat provisions; transcript/version semantics remain open. | Yes for raw preservation; no for derivation. | Policy section/version linked to EVID-008. |
| EVID-012 | PASS_THRESHOLD | PROP-007, PROP-011, PROP-012, PROP-014 | Define authoritative pass thresholds by applicable grade policy/version. | Registrar / regulations owner | Policy mapping from grade representation to pass/fail outcome, including exceptions. | Regulations/PDF. | Registrar-certified policy extract. | PARTIAL — public guide/calculator provide limited grade evidence; applicable version/exceptions remain open. | Yes for raw storage; no for outcome derivation. | Policy section/version linked to EVID-008. |
| EVID-013 | GPA_SCALE | PROP-007, PROP-077, PROP-081 | Define GPA scale and grade-point conversion where applicable. | Registrar / regulations owner | Scale range, conversion/mapping, rounding, and effective version. | Regulations/PDF. | Registrar-certified policy extract. | PARTIAL — public guide/calculator establish GPA-related functionality, not complete conversion/rounding semantics. | Yes for raw snapshots; no for calculation. | Policy section/version linked to EVID-008. |
| EVID-014 | WITHDRAWAL_POLICY | PROP-007, PROP-077, PROP-078 | Define withdrawal symbols, attempt status, GPA/credit effects, and timing. | Registrar / regulations owner | Applicable withdrawal-policy section and transcript representation. | Regulations/PDF. | Registrar-certified policy extract. | PARTIAL — public bachelor guide contains withdrawal provisions; current transcript semantics remain open. | Yes for raw flag; no for derivation. | Policy section/version linked to EVID-008. |
| EVID-015 | ZERO_CREDIT_POLICY | PROP-007, PROP-077, PROP-078 | Distinguish official academic-record treatment from current structural Plan 12 zero-credit behavior. | Registrar / regulations owner | Credit, outcome, GPA, and completion treatment for zero-credit attempts. | Regulations/PDF. | Registrar-certified policy extract. | OPEN | Yes for raw optional flag; no for derivation. | Policy section/version linked to EVID-008. |
| EVID-016 | COURSE_IDENTITY | PROP-003, PROP-037, PROP-040 | Establish official identity for six referenced-only codes. | Registrar / curriculum authority | Code, Arabic/English title if officially published, status, and whether it is a prerequisite-only external-to-plan course. | Official catalog. | Registrar-certified course extract. | OPEN | Yes; preserve `referenced_only`. | Source-linked identities without Plan 12 membership inference. |
| EVID-017 | COURSE_DOMAIN_TAXONOMY | PROP-011, PROP-012, PROP-014 | Approve versioned domains for later strengths/weaknesses/readiness. | AI department / curriculum committee | Reviewed course-to-domain mapping with source/evidence and version. | Approved taxonomy attachment. | Signed review worksheet. | OPEN | Yes; blocks domain-based outputs only. | Approved mapping and change-control record. |
| EVID-018 | COHORT/HISTORICAL_DATA | PROP-013, PROP-078, PROP-082 | Support a governed population-based risk model. | Registrar / institutional data-governance owner | Approved de-identified longitudinal export and use approval. | Governed SIS research export. | Approved aggregate/limited extract if adequate for validation. | OPEN | Yes; blocks predictive risk only. | Data dictionary, approval, quality report, and validation protocol. |
| EVID-019 | COURSE_OFFERING_DATA | PROP-023, PROP-054, PROP-055 | Support future offering-aware delay/workload claims. | Department / registrar | Versioned course/section offering data with term scope. | Official scheduling export. | Registrar-approved schedule extract. | OPEN | Yes; blocks offering-aware or delay claims only. | Source/versioned offering dataset and coverage test. |

## A. Prerequisite resolutions

Please answer the following exactly, by returning either a dated official catalog/plan page or a signed written academic ruling. A comma-separated code list alone is insufficient.

| Evidence ID | Canonical course | Current raw text / status | Exact question |
|---|---|---|---|
| EVID-002 | `0200105` — مهارات الاتصال والتواصل (اللغة العربية 1) | `0200150,0201001` / `unresolved` | What are the official identities of both codes, and must a student complete both, either one, or another condition? Is a minimum grade required? |
| EVID-003 | `0200106` — مهارات الاتصال والتواصل (اللغة الانجليزية 1) | `0200151,0202001` / `unresolved` | What are the official identities of both codes, and must a student complete both, either one, or another condition? Is a minimum grade required? |
| EVID-004 | `1505311` — تعلم الالة | `1505101,1505201` / `unresolved` | Must both courses be completed, may either satisfy the prerequisite, or is another rule intended? Is a minimum grade required? |
| EVID-005 | `1505320` — تعلم الآلة المتقدم | `0300103,1505311` / `source_conflict` | Which official source governs, what is the complete rule, and what is the official identity/status of `0300103`? Please provide both conflicting sources or a superseding decision. |
| EVID-006 | `1505366` — معالجة الصور الرقمية | `0301241,1505101` / `source_conflict` | Which official source governs, what is the complete rule, and what is the official identity/status of `0301241`? Please provide both conflicting sources or a superseding decision. |
| EVID-007 | `1505461` — الرؤية الحاسوبية | `1505366,1505415` / `unresolved` | Must both courses be completed, may either satisfy the prerequisite, or is another rule intended? Please confirm this after resolving `1505366`. |

These items are needed to replace safe `REVIEW_REQUIRED` behavior only after written evidence is received; they affect PROP-003, PROP-037, and PROP-040.

## B. Grading policy

For EVID-008 and EVID-011--015, please provide the current and applicable historical policy version(s), effective dates, and issuing authority. Confirm, without supplying values in this request: numeric grade range; pass threshold; letter-grade mapping; GPA scale; grade-point conversion; repeat, failed, withdrawal, transfer/equivalent, and zero-credit treatment; and whether a transcript exposes numeric grade, letter grade, both, or neither. Morshidi needs this to preserve official outcomes and avoid inventing grade-derived intelligence.

## C. Transcript/data-export schema

For EVID-009, please provide a data dictionary and a de-identified representative sample matching [student-record-import-template.csv](templates/student-record-import-template.csv). It must explain identifier mapping, source record identity, grade representation, official outcome, period values, repeats, transfers/equivalencies, withdrawals, credits, corrections, and export version. Morshidi needs this to validate and reconcile an authoritative record without treating self-report as official history.

## D. Academic periods

For EVID-010, please provide academic-year and term identifiers, names/types, ordering, applicable dates, and historical validity/effective period. Morshidi needs a stable period identity; an import timestamp cannot substitute for the term in which a course was attempted.

## E. Course-domain academic review

For EVID-017, please review—not infer—the attached conceptual taxonomy template in the student-performance contract. Confirm domain membership, source/rationale, effective version, whether multiple domains are allowed, whether weights are approved, and the reviewer/change-control path. Morshidi needs this before it can make domain-based strength, weakness, or readiness claims.

## F. Historical cohort data

For EVID-018, please provide only the de-identified fields in [cohort-outcomes-template.csv](templates/cohort-outcomes-template.csv), subject to institutional approval. Names, emails, phone numbers, addresses, and free-text notes are not requested. Morshidi needs a longitudinal, governed dataset only for a future validated population-risk model; it is not required for the Phase P2 foundation.

## G. Course offerings

For EVID-019, please provide a versioned schedule/offerings extract only when Morshidi later implements offering-aware delay or workload claims. Current structural planning does not claim section availability.

## Phase P2 gate

Phase P1.2 evidence review establishes a narrower safe boundary: P2 may model optional raw supplied values and internal provenance without interpreting them. A live importer, canonical period model, grade calculation/validation, and intelligence remain gated by the corresponding official evidence. EVID-001--007 and EVID-016 remain mandatory for full Plan 12 source closure; EVID-017 is required before domain outputs; EVID-018 before predictive risk; EVID-019 before offering-aware claims.

## Remaining-request priority

| Priority | Evidence IDs | Reason |
|---|---|---|
| URGENT_P2 | EVID-009, EVID-010 | Required before a live authoritative import or canonical academic-period processing. |
| REQUIRED_P3 | EVID-001--007, EVID-016, EVID-008, EVID-011--015, EVID-017 | Required for complete source closure, verified grade-derived/domain outputs, or their policy basis. |
| ADVANCED_MODEL | EVID-018 | Required only for predictive/population risk. |
| FUTURE_INTEGRATION | EVID-019 | Required only for offering-aware future capabilities. |
