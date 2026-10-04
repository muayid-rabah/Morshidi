# Mock Registration Policy

Policy version: **1.0**

Phase: **P6.1 — policy and contracts only**

## 1. Purpose

Mock Registration is a student-owned, non-binding declaration of courses the student currently intends to request for a future academic registration period. It creates registration intent that may support privacy-preserving descriptive demand analysis. It is not actual enrollment, an SIS transaction, a seat reservation, registration approval, guaranteed availability, a Digital Twin scenario, an automatically accepted Semester Planner result, a prediction, an Advisor recommendation, or a course-offering claim.

P6.1 authorizes documentation only. It creates no code, API, database object, migration, frontend, provider integration, or transaction.

## 2. Traceability

| Classification | IDs | Relationship |
|---|---|---|
| `DIRECT_P6` | PROP-050 | Explicit confirmation separates a planner result from student registration intent. |
| `ENABLED_BY_P6` | PROP-032, PROP-033, PROP-066, PROP-088 | Aggregate contracts enable later faculty/administration workflows; synthetic intent supports a Sandbox demonstration; privacy-safe counts may later support advising-volume evaluation. |
| `LATER_DEPENDENCY` | PROP-073, PROP-074, PROP-078, PROP-089, PROP-090, PROP-091, PROP-098 | SIS/SSO, continuous state, multi-plan/institution scale, and regional validation require later adapters and evidence. |
| `DIRECT_P6` | WC-008, WC-009 | Mock Registration and Institutional Demand are the P6 contract outcomes. |
| `ENABLED_BY_P6` | WC-010, WC-011, WC-015 | Capacity, bottleneck, and broader institutional analytics may later consume governed aggregates. |
| `LATER_DEPENDENCY` | WC-035, WC-036, WC-037, WC-044 | SIS, SSO, offerings/capacity, and governance remain separate capabilities. |

Policy evidence changes no proposal or WC implementation status.

## 3. Definition

The closed terminology is:

- `ACADEMIC_SCENARIO`: an ephemeral P5 modeled question—“What happens academically if I model X?”
- `REGISTRATION_INTENT`: an explicit student declaration—“These are the courses I currently intend to request.”
- `OFFICIAL_REGISTRATION`: an authoritative institutional enrollment transaction or fact.
- `DEMAND_AGGREGATE`: a privacy-minimized deterministic result over current valid intents in one authorized scope and target period.
- `CAPACITY_FACT`: a versioned verified-institutional or explicitly synthetic count of available capacity for an exact course/period/scope.
- `OFFERING_FACT`: a versioned verified-institutional or explicitly synthetic statement that an exact course/section is represented for a period/scope.
- `DEMAND_SIGNAL`: a descriptive aggregate derived from current valid registration intents; it is not enrollment, guaranteed demand, future enrollment, or a forecast.

## 4. Non-goals

V1 does not enroll, reserve seats, consume capacity, modify an SIS, satisfy prerequisites, create academic history, change progress, mark courses `IN_PROGRESS`, generate attempts, predict registration, estimate sections, rank students, recommend institutional action, or infer offerings, capacity, equivalencies, retake rules, co-registration, or official periods.

## 5. Digital Twin distinction

A Digital Twin models academic consequences. Mock Registration records explicit student intent. A scenario, recommendation, semester plan, or degree path never becomes intent automatically. A future “use this plan” control must copy a candidate set, display its non-binding meaning, require explicit authenticated confirmation, and revalidate it against current authoritative state.

## 6. Official registration distinction

Mock Registration has no transaction authority and cannot imply official approval, enrollment, seat allocation, timetable compatibility, offering availability, or progress. Official registration requires a separate institutional API contract, authorization, confirmation, idempotency, reconciliation, and audit policy; official write-back is outside P6 V1.

## 7. Ownership

Each intent belongs to exactly one authenticated `owner_scope_id`. The owner reference is an opaque authorization-scoped identifier, not an email, name, student number, or credential. Future storage and APIs must enforce owner access. Institutional analytics receives aggregate input through an authorized boundary and exposes no owner identifiers by default.

## 8. Target period

`TargetPeriod` contains a nonblank provider-namespaced `period_key`, a period class, and source version. Period classes are `DECLARED_PLANNING_PERIOD`, `OFFICIAL_PERIOD_REFERENCE`, and `SYNTHETIC_SANDBOX_PERIOD`. Only the second may claim linkage to an institutional period, and only with a verified provider source. A declared or synthetic period is never called an official academic term. V1 aggregation is exact-period only.

## 9. Intent identity

The minimal typed identity is:

```text
RegistrationIntent
  contract_version = "1.0"
  intent_id
  owner_scope_id
  university_id
  major_id
  study_plan_id
  study_plan_version
  target_period
  revision
  lifecycle_status
  canonical_course_codes[]
  source_class
  source_version
  content_fingerprint
```

No wall-clock field is required for deterministic V1 semantics. Future persistence may record audit timestamps, but they do not resolve revision precedence.

## 10. Intent lifecycle

The minimal lifecycle is `SUBMITTED`, `WITHDRAWN`, and `EXPIRED`. `DRAFT` remains client-local and is not an intent record. `REPLACED` is not a stored lifecycle status; it is the derived `SUPERSEDED` disposition of a lower current-candidate revision. `EXPIRED` requires an explicit authoritative/provider period-state input—never an inferred current time.

Lifecycle is distinct from validation status (`VALID`, `INVALID`, `REVIEW_REQUIRED`) and current-resolution disposition (`CURRENT`, `SUPERSEDED`, `REVISION_CONFLICT`).

## 11. Revision/replacement

The current-intent key is exact `(owner_scope_id, university_id, major_id, study_plan_id, study_plan_version, target_period)`. Revisions are positive caller-supplied integers. Among valid, non-expired records for one key, the greatest revision is the current candidate (`LATEST_VALID_INTENT_WINS`). Lower revisions are `SUPERSEDED` and never counted.

Equal revision plus equal fingerprint is idempotent and resolves to one logical record. Equal revision plus different fingerprint is `REVISION_CONFLICT`; neither record becomes current until resolved. Timestamps and database row order never break ties. Historical storage is a later persistence concern.

## 12. Course-set semantics

A submitted intent contains 1–10 exact canonical course codes. Input order is not meaningful. Codes are trimmed only according to the existing canonical catalog contract, sorted lexicographically, and stored as a tuple. Duplicate input is invalid rather than silently deduplicated. A `WITHDRAWN` revision contains an empty course set and means the owner has no current intent for that key. A submitted empty set is invalid.

## 13. Eligibility validation

Every submitted course must be an active selected-plan member and receive Phase 5 `ELIGIBLE` against the same authoritative base. `NOT_ELIGIBLE` makes the whole intent `INVALID`. `REVIEW_REQUIRED` makes the whole intent `REVIEW_REQUIRED`. A separate unvalidated-interest concept is deferred; Mock Registration never treats blocked interest as validated demand.

Courses are evaluated independently against current authoritative attempts. Other courses in the same submitted set do not satisfy prerequisites.

## 14. Attempt-state behavior

- `PASSED`/completed target: invalid unless a future authoritative repeat-for-grade policy says otherwise.
- `IN_PROGRESS` target: invalid unless a future authoritative re-registration policy says otherwise.
- prior `FAILED`: not automatically invalid; current Phase 5 eligibility and every other V1 rule decide.
- prior `WITHDRAWN`: same as failed history; no special inferred retake rule.

Official history remains unchanged and is never converted into intent or modeled completion.

## 15. Elective behavior

An elective target must be a plan-listed option, Phase 5 `ELIGIBLE`, and belong to a Phase 6 elective group with remaining requirement need. If its group is already satisfied, Mock Registration returns `MOCK_REG_ELECTIVE_GROUP_ALREADY_SATISFIED`. This Mock Registration code is separate from the P5 Digital Twin code because one validates declared registration intent and the other validates scenario scope. Neither changes Phase 5 eligibility or claims the course lacks academic value.

## 16. Zero-credit behavior

An eligible, incomplete, selectable zero-credit course is valid. It contributes one course selection and one owner to course demand, but zero to declared credit load. It is never dropped solely because its credit value is zero.

## 17. Referenced-only behavior

A referenced-only identity may provide prerequisite evidence but is not a selectable plan member and cannot be an intent target, demand course, or requirement-group selection. No name matching, fuzzy matching, or inferred membership is allowed.

## 18. Source conflict

Phase 5 prerequisite ambiguity or source conflict produces per-course `REVIEW_REQUIRED` and top-level `REVIEW_REQUIRED`. No course is partially accepted, and the intent is excluded from normal validated demand. A separately suppressed review workload metric may count review-required intent owners without exposing courses or identities.

## 19. Constraints

Mock Registration V1 uses Morshidi safety bounds: at most 10 courses and at most `30.00` summed plan credits. These reuse existing computational bounds but are explicitly not official institutional registration limits. Exceeding either bound invalidates the whole submission; values are not clamped. Zero-credit courses count toward the course limit.

## 20. Offering boundary

Offering data is optional. Academically valid intent may be submitted when offerings are unavailable, with availability state `OFFERING_DATA_UNAVAILABLE`. If an exact verified/synthetic offering dataset is supplied, the result may report `MATCHING_OFFERING_FACT` or `NO_MATCHING_OFFERING_FACT`; the latter describes absence from the supplied version and is not a universal “not offered” claim.

## 21. Capacity boundary

Capacity is not required for intent validity. Missing capacity yields availability state `CAPACITY_DATA_UNAVAILABLE`, never zero. Capacity facts do not reserve or consume seats. Only verified-institutional or explicitly synthetic facts may be used by an optional descriptive aggregate comparison.

## 22. Validation result

Each course result contains course code, `VALID | INVALID | REVIEW_REQUIRED`, exact reason codes, Phase 5 decision/evidence reference, plan/group identity, credit hours, and optional offering/capacity availability—not raw history or grades. The top-level validation status is `VALID`, `INVALID`, or `REVIEW_REQUIRED`; invalid takes precedence over review when both exist.

## 23. No partial application/counting

Validation is atomic. If any course or intent-level field is invalid, nothing is accepted. If any course requires review and none is invalid, the whole intent requires review. Only a complete `VALID` current `SUBMITTED` revision enters normal demand. Withdrawn, expired, superseded, conflicted, invalid, and review-required records do not.

## 24. Idempotency

Logical idempotency key is the current-intent key plus revision. Canonical content fingerprint is SHA-256 over length-delimited normalized plan/version, period class/key/source version, lifecycle, revision, canonical course codes, intent source class, source version, and contract version. It excludes owner PII, names, grades, credentials, timestamps, and presentation data. The fingerprint supports idempotency/change detection and is not authentication or proof of authority.

## 25. Privacy

Intent data is sensitive academic-behavior data. Use minimum necessary fields, purpose-bound access, no raw grades/attempt payloads in aggregate output, and no default student-level institutional response. Logs must use safe IDs/codes rather than course-set payloads. Sensitive/demographic segmentation is forbidden in V1.

## 26. Transparency/consent

Before explicit submission, the future product must state that Mock Registration is non-binding, does not reserve or enroll, may be unavailable in actual offerings, and may contribute to privacy-preserving institutional planning aggregates. Intent must not be silently repurposed. Withdrawal removes the record from current-demand computation, subject to separately disclosed institutional retention policy.

## 27. Persistence future

P6.2 remains pure and adds no persistence. A later persistence slice must define owner RLS, exact plan/period/revision uniqueness, status, course set, fingerprint/idempotency, audit metadata, replacement/withdrawal behavior, retention/deletion, institutional aggregate access, concurrency, and reconciliation. Retain only what the approved purpose requires; production retention duration is institution/legal-policy configured, not invented here.

## 28. API future

Student submit/replace/withdraw and read-current endpoints plus institutional aggregate reads belong after the pure engine, provisionally P6.3. Transport must require explicit student action and ownership; institutional aggregate endpoints require a distinct authorized institutional role. Student bearer tokens cannot access institution-wide aggregates.

## 29. P6.2 contract

P6.2 implements only immutable models, canonicalization/fingerprint, finite validation, current-intent resolution, idempotency semantics, demand aggregation, coverage metadata, privacy suppression, optional supplied-fact offering/capacity comparison, deterministic provenance, tests, and implementation documentation. It adds no API, database, migration, frontend, SIS adapter, actual-registration comparison, forecast, bottleneck ranking, section estimate, faculty-workload inference, notification, or official transaction.
