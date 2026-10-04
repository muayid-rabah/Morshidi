# Student performance data foundation (Phase P2)

## Scope and evidence boundary

Phase P2 implements a storage and validation foundation for `PROP-002`, `PROP-007`, `PROP-077`, and `PROP-078`. It is not a student-performance intelligence implementation. The authority for this limited scope is the P1.2 `P2_READY` decision in [student-performance-data-contract.md](student-performance-data-contract.md) and [evidence-closure-status.md](evidence-closure-status.md).

Local runtime closure is recorded in [student-performance-foundation-validation.md](student-performance-foundation-validation.md).

The implementation does not import live university data, select a grading policy, calculate GPA or earned credits, canonicalize periods, infer outcomes, create a taxonomy, rank students, score readiness/risk, or expose a new student-facing feature.

## Stored attempt facts

Migration `20260921175041_add_student_performance_foundation.sql` adds nullable raw fields to `student_course_attempts`:

- `raw_numeric_grade`, `raw_letter_grade`, and `raw_grade_points` preserve supplied source values without a range, mapping, scale, or GPA meaning.
- `raw_academic_year` and `raw_term` are nonblank opaque source strings. They are not identifiers, sort keys, or canonical academic periods.
- Existing nullable positive `attempt_sequence` is preserved as supplied. It remains neither inferred nor a canonical ordering signal; repeated null sequences remain backward compatible.
- `attempt_credit_hours` is nullable and nonnegative. It is explicitly distinct from catalog credit and is not used by progress, eligibility, recommendations, planning, degree paths, GPA, or earned-credit reconciliation.
- No repeat, transfer/equivalent, withdrawal, policy-version, or canonical-period field is added in this minimal migration: the current evidence does not define a safe source representation for those facts. Existing explicit outcomes, including `WITHDRAWN`, remain the only operational status representation.
- `performance_provenance` uses the P1.1 vocabulary: `OFFICIAL_VERIFIED`, `STUDENT_RECORD`, `DERIVED_DETERMINISTIC`, `MODEL_OUTPUT`, `MANUAL_ACADEMIC_REVIEW`, and `UNVERIFIED`.
- `performance_verification_state` is `UNVERIFIED`, `VERIFIED`, or `REVIEW_REQUIRED`. `OFFICIAL_VERIFIED` requires `VERIFIED`; this does not authorize any future engine to consume the fact.
- `performance_source_reference` is an optional, nonblank source/batch/reference identifier. It is not a document archive, student identity, or policy version.

Existing rows receive `UNVERIFIED` provenance and verification defaults. Existing `PASSED`, `FAILED`, `IN_PROGRESS`, and `WITHDRAWN` values are unchanged, and no raw grade can change an outcome.

## Ownership, privacy, and API boundary

The existing owner-scoped RLS policies remain in force. A new database trigger blocks direct authenticated clients from setting or changing Phase P2 performance fields. Trusted server/import paths use the server key; no live importer or import endpoint is included.

The existing authenticated self-service API deliberately does not accept or return the new performance fields. Its legacy `raw_grade_text` remains a backwards-compatible manual field and is not evidence of authority. The internal repository maps the new fields for controlled server-side use only. No names, contact details, free-text adviser notes, demographic data, document payloads, or other unrelated personal data are introduced.

## Pure import-boundary contract

`app.student.performance_import` accepts only synthetic/future in-memory records and returns accepted and quarantined records without persistence. It:

- requires a known course code, a supported explicit outcome, and provenance;
- checks only structural raw-value safety (nonblank supplied text, positive sequence, nonnegative supplied attempt credits, numeric parseability);
- requires `VERIFIED` state when provenance claims `OFFICIAL_VERIFIED`;
- quarantines duplicate source-record identities, or duplicate `(course_code, attempt_sequence)` identities where no source-record identity is supplied; and
- never auto-creates a course, derives period order, validates a grade against an institutional policy, deduplicates a repeat, or treats quarantine as a database state.

The synthetic unit fixtures use `SYN-*` course/period/source labels and contain no real student identity or institutional record.

## Explicit deferrals and P3 entry conditions

P3 cannot begin until the P2 migration is replayed and its focused/regression checks pass, and the P1.2 evidence gate is reconfirmed. Any performance intelligence additionally requires its own approved scope and the missing official evidence: transcript/export schema and record identity (`EVID-009`), canonical academic periods (`EVID-010`), complete grading/repeat/GPA policy (`EVID-008`, `EVID-012`, `EVID-013`), and the relevant domain/cohort governance evidence (`EVID-017`, `EVID-018`) before strengths, weaknesses, readiness, or risk work.
