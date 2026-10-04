# P6 Mock Registration and Demand Implementation Trace

Contract version: **1.0**. Result: **PASS**. This trace maps the closed P6.1 contract to `app.mock_registration` and `test_mock_registration.py`.

## Contract-clause trace

| P6.1 clause | Implementation | Automated evidence | Result |
|---|---|---|---|
| Intent identity, ownership, period, lifecycle | `models.py`; `validation.validate_registration_intent` | `test_period_plan_revision_and_lifecycle_validation`; `test_withdrawal_and_expiry_are_explicit_and_do_not_use_time` | PASS |
| Canonical course set and bounds | `canonicalization.py`; `validation.py` | `test_course_identity_duplicate_and_empty_validation`; `test_intent_bounds_are_atomic_and_not_clamped` | PASS |
| Phase 5/6 reuse and atomic precedence | `validation._validate_course` | Phase 5/6, completed/in-progress, elective, history, and review tests | PASS |
| Fingerprint/idempotency | `fingerprint.py`; `resolution.py` | `test_fingerprint_is_canonical_private_and_decision_sensitive`; resolution test | PASS |
| Latest-valid revision resolution | `resolution.resolve_current_intents` | `test_latest_revision_idempotency_conflict_and_row_order_determinism` | PASS |
| Descriptive demand and all views | `aggregation.aggregate_institutional_demand` | aggregate, multi-course, group, plan, share, ordering tests | PASS |
| Coverage and finite quality | `aggregation.py`; `registries.py` | coverage and registry-lock tests | PASS |
| Whole-result privacy | `privacy.py`; suppression branches in `aggregation.py` | privacy suppression and aggregate-field tests | PASS |
| Optional offerings/capacity | `capacity.py`; metric construction | offering/capacity tests | PASS |
| University/period/scope/limit isolation | `aggregation._validate_input` | hard rejection and provider-neutral tests | PASS |
| No automatic conversion, mutation, I/O, prediction, or action | pure package boundary | isolation/source scan and immutability tests | PASS |

## All 30 reason codes

All values are members of the closed `ReasonCode` enum; the focused registry test locks the count at 30.

| Code | Implementation point | Test evidence | Result |
|---|---|---|---|
| `MOCK_REG_UNKNOWN_COURSE` | `validation._validate_course` | identity parameterization | PASS |
| `MOCK_REG_TARGET_NOT_PLAN_MEMBER` | `validation._validate_course` | referenced-only case | PASS |
| `MOCK_REG_TARGET_ALREADY_COMPLETED` | `validation._validate_course` | protected-state parameterization | PASS |
| `MOCK_REG_TARGET_IN_PROGRESS` | `validation._validate_course` | protected-state parameterization | PASS |
| `MOCK_REG_TARGET_NOT_ELIGIBLE` | `validation._validate_course` | Phase 5 blocked test | PASS |
| `MOCK_REG_ELIGIBILITY_REVIEW_REQUIRED` | `validation._validate_course` | source-conflict/review test | PASS |
| `MOCK_REG_ELECTIVE_GROUP_ALREADY_SATISFIED` | `validation._validate_course` | satisfied-elective test | PASS |
| `MOCK_REG_DUPLICATE_COURSE` | `duplicate_course_codes`; validation | duplicate test | PASS |
| `MOCK_REG_EMPTY_COURSE_SET` | intent validation | empty test | PASS |
| `MOCK_REG_INVALID_PLAN_IDENTITY` | intent validation | identity test | PASS |
| `MOCK_REG_INVALID_PLAN_VERSION` | intent validation | version test | PASS |
| `MOCK_REG_INVALID_TARGET_PERIOD` | `_valid_period` | period test | PASS |
| `MOCK_REG_INVALID_REVISION` | intent validation | revision test | PASS |
| `MOCK_REG_INVALID_LIFECYCLE` | intent validation | lifecycle test | PASS |
| `MOCK_REG_COURSE_LIMIT_EXCEEDED` | intent validation | bounds test | PASS |
| `MOCK_REG_CREDIT_LIMIT_EXCEEDED` | intent validation | bounds test | PASS |
| `MOCK_REG_REQUIRED_CONTEXT_MISSING` | intent/context validation | context identity tests | PASS |
| `MOCK_REG_REVISION_SUPERSEDED` | resolver | revision test | PASS |
| `MOCK_REG_REVISION_CONFLICT` | resolver | conflict test | PASS |
| `MOCK_REG_WITHDRAWN_INTENT` | resolver | withdrawal test | PASS |
| `MOCK_REG_EXPIRED_INTENT` | resolver | expiry test | PASS |
| `DEMAND_PRIVACY_SUPPRESSED` | aggregator privacy branch | suppression test | PASS |
| `DEMAND_NO_VALID_ACTIVE_INTENTS` | empty branch | empty-demand test | PASS |
| `DEMAND_UNKNOWN_POPULATION_COVERAGE` | coverage branch | coverage test | PASS |
| `DEMAND_PARTIAL_INTENT_COVERAGE` | coverage branch | coverage test | PASS |
| `DEMAND_OFFERING_DATA_UNAVAILABLE` | optional-fact branch | offering test | PASS |
| `DEMAND_CAPACITY_DATA_UNAVAILABLE` | optional-fact branch | capacity test | PASS |
| `DEMAND_REVIEW_INTENTS_EXCLUDED` | review filter | exclusion test | PASS |
| `DEMAND_SCOPE_MISMATCH` | `_validate_input` | scope/period test | PASS |
| `DEMAND_LIMIT_EXCEEDED` | `_validate_input` | limit test | PASS |

## Metric, status, quality, lifecycle, period, and provenance registries

| Registry | Exact values | Implementation/test | Result |
|---|---|---|---|
| 9 metrics | `VALID_ACTIVE_INTENT_OWNER_COUNT`; `COURSE_INTENT_OWNER_COUNT`; `COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS`; `TOTAL_DECLARED_COURSE_SELECTION_COUNT`; `TOTAL_DECLARED_CREDIT_LOAD`; `REQUIREMENT_GROUP_INTENT_OWNER_COUNT`; `PLAN_INTENT_OWNER_COUNT`; `REVIEW_REQUIRED_INTENT_OWNER_COUNT`; `DECLARED_DEMAND_MINUS_CAPACITY` | `DemandMetricId`, `METRIC_REGISTRY`, aggregate/capacity/review tests | PASS |
| 4 statuses | `AVAILABLE`; `PARTIAL`; `SUPPRESSED`; `INSUFFICIENT_DATA` | `DemandStatus`, availability/coverage/privacy/empty tests | PASS |
| 7 quality flags | `COMPLETE_DECLARED_INTENT_INPUT_SET`; `PARTIAL_INTENT_COVERAGE`; `UNKNOWN_POPULATION_COVERAGE`; `MISSING_OFFERING_DATA`; `MISSING_CAPACITY_DATA`; `SUPPRESSED_FOR_PRIVACY`; `REVIEW_REQUIRED_INTENTS_EXCLUDED` | `DataQualityFlag`, registry and branch tests | PASS |
| Lifecycle | `SUBMITTED`; `WITHDRAWN`; `EXPIRED` | `IntentLifecycle`, lifecycle/resolution tests | PASS |
| Period class | `DECLARED_PLANNING_PERIOD`; `OFFICIAL_PERIOD_REFERENCE`; `SYNTHETIC_SANDBOX_PERIOD` | `TargetPeriodClass`, period validation tests | PASS |
| Intent provenance | `DECLARED_STUDENT_INTENT`; `SYNTHETIC_SANDBOX_INTENT`; `INSTITUTIONAL_IMPORT` | `IntentProvenance`, registry and aggregate tests | PASS |
| Fact provenance | `VERIFIED_INSTITUTIONAL_FACT`; `SYNTHETIC_SANDBOX_FACT`; `UNAVAILABLE` | `FactProvenance`, offering/capacity tests | PASS |

## All 64 committed scenarios

Each stable ID is present in `SCENARIO_TEST_MAPPING`; the named focused test families exercise the behavior rather than a transport or persistence substitute.

| IDs | Automated test family | Result |
|---|---|---|
| `P6-T01`–`P6-T03` | valid required/elective/zero-credit test | PASS |
| `P6-T04`–`P6-T05` | completed/in-progress protected-state test | PASS |
| `P6-T06`–`P6-T07` | failed/withdrawn history test | PASS |
| `P6-T08`–`P6-T10` | Phase 5 blocked/review/source-conflict test | PASS |
| `P6-T11`–`P6-T16` | exact identity, referenced-only, elective, duplicate, ordering, empty tests | PASS |
| `P6-T17` | withdrawal/expiry test | PASS |
| `P6-T18`–`P6-T23` | plan/version/period/lifecycle validation test and enum locks | PASS |
| `P6-T24`–`P6-T25` | course/credit bounds test | PASS |
| `P6-T26` | Phase 5 test plus no same-intent state mutation assertion | PASS |
| `P6-T27`–`P6-T31` | offering/capacity supplied-fact tests | PASS |
| `P6-T32`–`P6-T35` | revision, idempotency, conflict, ordering test | PASS |
| `P6-T36` | explicit expiry test | PASS |
| `P6-T37`–`P6-T39` | owner/course deduplication and idempotency tests | PASS |
| `P6-T40`–`P6-T45` | superseded/withdrawn/invalid/review filtering and review-metric tests | PASS |
| `P6-T46`–`P6-T49` | selection, credit, group, plan aggregate test | PASS |
| `P6-T50` | plan-scoped and global course implementation plus deterministic aggregate tests | PASS |
| `P6-T51`–`P6-T52` | university/period hard-partition test | PASS |
| `P6-T53`–`P6-T55` | denominator and coverage test | PASS |
| `P6-T56`–`P6-T57` | disclosure pass/suppression tests | PASS |
| `P6-T58` | positive/zero/negative capacity arithmetic test | PASS |
| `P6-T59` | no-valid-intent test | PASS |
| `P6-T60` | reordered aggregate equivalence test | PASS |
| `P6-T61` | configured-limit rejection test | PASS |
| `P6-T62` | aggregate result-field privacy scan | PASS |
| `P6-T63` | no cross-package conversion/source dependency test | PASS |
| `P6-T64` | immutability and forbidden dependency/action scan | PASS |

## Required cross-cutting cases

- Privacy suppression: whole output and all nine IDs are withheld; exact counts, identities, category membership, offerings, and gap arithmetic are absent.
- Fingerprint/idempotency: reordered courses match; course, plan-version, period, lifecycle/revision/source changes remain decision-relevant; owner/intent identity does not authenticate content.
- Revision resolution: higher valid revision wins, duplicate fingerprints collapse logically, conflicts exclude all tied candidates, withdrawal and explicit expiry remove current demand.
- Cross-plan: plan/group/credit dimensions stay separate; university-period course view deduplicates owner/course pairs.
- Cross-university and cross-period: the whole request rejects on any mismatch.
- Offering/capacity: only exact supplied facts match; missing remains unavailable; capacity arithmetic is descriptive and never ranked or converted to sections/staffing.
