# Institutional Demand Policy

Policy version: **1.0**

Phase: **P6.1 — policy and contracts only**

## 1. Purpose

Institutional Demand V1 deterministically describes current validated Mock Registration intent within one authorized academic scope and declared target period. It supplies privacy-minimized signals for human planning. It is not enrollment, a forecast, a capacity decision, or an automated institutional recommendation.

## 2. Traceability

Direct contract targets are WC-009 and WC-008. WC-010, WC-011, and WC-015 are enabled but remain separately gated. Proposal relationships are `DIRECT_P6` PROP-050, `ENABLED_BY_P6` PROP-032, PROP-033, PROP-066, and PROP-088, and `LATER_DEPENDENCY` PROP-073, PROP-074, PROP-078, PROP-089, PROP-090, PROP-091, and PROP-098. No status changes arise from policy documentation.

## 3. Demand Signal definition

A `DEMAND_SIGNAL` is a descriptive aggregate derived from currently valid student registration intents. It answers only what students currently declared within the supplied scope. It must never be labeled actual enrollment, guaranteed demand, future enrollment, predicted registration, or forecast demand.

## 4. Non-goals

V1 does not predict registration, estimate probability, rank courses as bottlenecks, recommend opening/closing sections, estimate sections, assign rooms/instructors, infer faculty workload, rank students, expose student selections, perform causal analysis, combine periods as trends, or mutate institutional systems.

## 5. Input contract

`DemandAggregationInput` contains:

```text
contract_version
aggregation_scope
target_period
validated_intent_records[]
normalized_plan_course_catalog
optional population_denominator
optional offering_facts[]
optional capacity_facts[]
privacy_configuration
aggregation_limits
source_versions[]
```

The input is provider-neutral and contains no database model. Intents must already carry course-level and top-level validation. Catalog data supplies canonical course, plan, requirement-group, credit, and source identity. Optional facts must be explicitly verified-institutional or synthetic.

`DemandAggregationResult` contains contract/status, exact scope and period, optional disclosed population/coverage values, ordered course/plan/group metrics, suppressed metric IDs, offering/capacity states, data-quality flags, reason codes, provenance, source versions, and limitations. Status is exactly `AVAILABLE`, `PARTIAL`, `SUPPRESSED`, or `INSUFFICIENT_DATA`. `PARTIAL` means adoption/population coverage is known incomplete or unknown; missing optional offering/capacity facts alone do not invalidate otherwise available descriptive demand. No free-form analytics blob is allowed.

`AggregationLimits` requires positive configured `max_intents` and `max_catalog_courses`. Input beyond either bound is rejected atomically with `DEMAND_LIMIT_EXCEEDED`; it is never truncated. P6.1 deliberately sets no arbitrary deployment-scale maximum. The fixed per-intent limits remain 10 courses and `30.00` declared credits.

## 6. Active-intent resolution

Resolve exact current-intent keys using `LATEST_VALID_INTENT_WINS`: greatest positive revision wins; equal fingerprint is idempotent; equal revision/different fingerprint conflicts; lower revisions are superseded. Only current, valid, submitted, non-expired records enter normal demand. Withdrawn current revisions yield no current intent. Review-required records may enter only the distinct review-workload metric. Resolution is independent of timestamps and row order.

## 7. Aggregation scope

V1 requires one exact university/provider, target period, and explicit academic scope. Supported scope dimensions are university, major, study plan, plan version, and target period. A broader university scope may contain multiple plans only when each record retains exact plan/version identity. Campus, college, department, demographics, and arbitrary cohorts are excluded unless later authoritative contracts add them.

## 8. Course demand

For every canonical course in scope, `COURSE_INTENT_OWNER_COUNT` counts distinct current valid owners selecting it. A course metric may also carry canonical plan/group context, course credit, offering-fact state, optional capacity comparison, and share of valid-intent owners. It contains no owner list. Zero count is emitted only for a known course inside an unsuppressed complete requested metric set—not for missing or suppressed facts.

## 9. Program/plan demand

`PLAN_INTENT_OWNER_COUNT` counts distinct owners with a current valid intent for an exact plan/version/period. An owner contributes once to the cohort owner count regardless of number of selected courses. Multiple active-major semantics for one owner are deferred; V1 input must provide one authoritative active plan per current-intent key.

## 10. Requirement-group demand

`REQUIREMENT_GROUP_INTENT_OWNER_COUNT` counts distinct owners whose current valid intent contains at least one course mapped by the supplied normalized catalog to the exact requirement group. Categories such as major required or major elective come only from canonical requirement-group facts and are never inferred from names.

## 11. Zero-credit

Zero-credit selections count in course-selection, course-owner, plan-owner, and requirement-group-owner metrics. They contribute exactly zero to `TOTAL_DECLARED_CREDIT_LOAD`.

## 12. Cross-plan behavior

The same canonical course may have two views:

- `COURSE_BY_PLAN_DEMAND`: distinct owners within exact plan/version.
- `COURSE_GLOBAL_DEMAND`: distinct owners within one university/period across included plans.

The global view deduplicates owner/course pairs across plans. Requirement-group and credit semantics remain plan-scoped. Cross-university aggregation is forbidden.

## 13. Denominators

`COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS` uses the exact unsuppressed `VALID_ACTIVE_INTENT_OWNER_COUNT` for the selected scope/period. It must be labeled a share of participating valid-intent owners, not of all students or eligible students. An eligible-population share is deferred unless an authorized exact eligible population denominator and derivation contract are supplied. Unknown denominators produce no percentage and never become zero.

## 14. Coverage

Observed counts can be exact for the supplied active intents while population adoption is partial or unknown. Output states `VALID_ACTIVE_INTENT_OWNER_COUNT`, optional authoritative `KNOWN_POPULATION_DENOMINATOR`, and `POPULATION_COVERAGE_RATIO` only when that denominator is exact and nonzero. Otherwise quality includes `UNKNOWN_POPULATION_COVERAGE` or `PARTIAL_INTENT_COVERAGE`, and wording is `OBSERVED_INTENTS_ONLY`.

## 15. Privacy suppression

Every request supplies `minimum_disclosure_group_size`. Production values are institution/privacy-policy configured; P6 defines no legal threshold. Sandbox fixtures may use default `3`, explicitly synthetic and non-legal. The threshold must be an integer of at least `2`.

If there are no valid current intents (and no separately requested review workload population), status is `INSUFFICIENT_DATA`. If the relevant nonzero contributing owner population is below the threshold, status is `SUPPRESSED`. Counts, shares, credit totals, group metrics, course metrics, review counts, capacity gaps, and the exact small population count are withheld—not returned as zero. Only safe scope, period, status, threshold policy reference, suppressed metric IDs, provenance, quality flag, and limitations remain. V1 accepts one exact scope per call and does not provide neighboring-difference tooling; subtraction-risk resistance beyond this restriction remains a limitation.

## 16. Provenance

Demand provenance classes are `DECLARED_STUDENT_INTENT`, `SYNTHETIC_SANDBOX_INTENT`, and `INSTITUTIONAL_IMPORT`. Student-declared intent is not an institutional fact. Institutional facts use the separate hierarchy `VERIFIED_INSTITUTIONAL_FACT`, `SYNTHETIC_SANDBOX_FACT`, or `UNAVAILABLE`. Output records source/policy/catalog versions and never upgrades synthetic data to institutional truth.

## 17. Data quality

The finite flags are:

- `COMPLETE_DECLARED_INTENT_INPUT_SET`
- `PARTIAL_INTENT_COVERAGE`
- `UNKNOWN_POPULATION_COVERAGE`
- `MISSING_OFFERING_DATA`
- `MISSING_CAPACITY_DATA`
- `SUPPRESSED_FOR_PRIVACY`
- `REVIEW_REQUIRED_INTENTS_EXCLUDED`

Flags are factual and independently combinable. There is no confidence score.

## 18. Missing offerings

Demand counts remain available when offering data is absent; offering state is `OFFERING_DATA_UNAVAILABLE`, not “not offered.” With a complete exact-period supplied dataset, per-course state may be `MATCHING_OFFERING_FACT` or `NO_MATCHING_OFFERING_FACT`. The latter means absent only from that versioned dataset.

## 19. Missing capacity

Demand counts remain available when capacity is absent. Known capacity and declared gap are unavailable, not zero. Capacity absence does not change intent validity or normal demand counts.

## 20. Capacity comparison

V1 optionally computes `DECLARED_DEMAND_MINUS_CAPACITY = COURSE_INTENT_OWNER_COUNT - known_capacity` only when an exact verified-institutional or synthetic capacity fact matches university, course, period, and scope. Negative, zero, and positive results are descriptive arithmetic. They do not claim shortage, availability, seat reservation, enrollment, or a need to open sections.

## 21. No forecasting

V1 may say “47 current valid intents include course X.” It may not say “47 students will register,” attach a probability, forecast confidence, predicted enrollment, trend projection, or ML inference. Longitudinal demand and actual-intent conversion analysis are deferred.

## 22. No individual ranking

No result ranks or scores a student by importance, priority, risk, merit, or seat entitlement. No individual intent or identity is returned. Review workload, when enabled, is an aggregate owner count subject to the same suppression.

## 23. Sandbox compatibility

Morshidi Sandbox University may supply synthetic students, plans, periods, intents, offerings, capacity, and sections. Every input/output carries synthetic provenance and must not imply a real institution, real student, legal threshold, or production capacity fact.

## 24. Multi-university isolation

All inputs, intent keys, catalog facts, provider facts, scopes, fingerprints, and outputs carry normalized university/provider identity. One result contains exactly one university. Sandbox and real data never mix. Cross-institution totals are outside V1.

## 25. Determinism

Intent resolution, owner/course deduplication, metric ordering, scope ordering, suppression, quality flags, and output are independent of input row order, set order, dictionary insertion order, current time, randomness, and database behavior. Canonical order is metric-registry order, then university, plan version, plan, requirement group, and course identifiers.

## 26. Institutional authorization future

P6.1/P6.2 implement no auth. Future demand reads require an explicit `AUTHORIZED_INSTITUTIONAL_ANALYST` role limited to authorized university/scope. `STUDENT` may access only owned intent; `AUTHORIZED_ADVISOR` student drill-down requires a separate purpose/consent contract and receives no institutional aggregate authority by implication.

## 27. Limitations

Intent adoption may be incomplete; declared intent can change; offerings/capacity may be absent or synthetic; no actual enrollment comparison exists; suppression cannot alone prevent every multi-query subtraction attack; multi-major, equivalency, trends, forecasting, bottleneck labels, section estimation, faculty workload, and automated decisions are deferred.

## 28. P6.2 contract

Implement, in order: (1) immutable enums/models and registries; (2) canonical intent normalization and fingerprint; (3) Phase 5/6-backed atomic validation; (4) revision/idempotency/current-intent resolution; (5) period/university/plan isolation; (6) owner/course/group/plan metric aggregation; (7) denominator and coverage metadata; (8) whole-result suppression; (9) optional supplied offering/capacity comparison; (10) canonical result/provenance; (11) the complete test matrix and prior regressions; (12) implementation documentation. P6.2 is pure/domain-only with no I/O.
