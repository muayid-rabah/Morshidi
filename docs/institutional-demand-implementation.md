# Institutional Demand V1 Implementation

## 1. Purpose

P6.2 computes privacy-minimized descriptions of current validated Mock Registration intent. It does not predict enrollment or recommend institutional action.

## 2. Architecture

`aggregation.py` validates a provider-neutral request and emits immutable typed output. `privacy.py` owns disclosure gating; `capacity.py` performs exact supplied-fact matching. No I/O occurs.

## 3. Aggregation input

`DemandAggregationInput` carries an exact scope/period, resolved records, normalized plan-course facts, disclosure configuration, positive deployment limits, optional coverage/offering/capacity facts, review-metric choice, and source versions.

## 4. Current valid intent filtering

Normal metrics include only `CURRENT + VALID + SUBMITTED` records. Invalid, review-required, withdrawn, expired, superseded, and conflicted records never contribute.

## 5. Metric registry

The closed `DemandMetricId` enum implements exactly the nine P6.1 metric IDs. Views repeat registered metrics with typed dimensions; they are not hidden metric types.

## 6. Unique-owner semantics

Sets enforce at most one owner/course/period contribution after deterministic resolution and idempotent duplicate handling.

## 7. Course demand

Plan views group exact plan/version. University-period global views deduplicate owner/course pairs across included plans. Both retain exact course identity and expose no owner lists.

## 8. Requirement-group demand

Exact normalized mappings count one owner once per plan/version/group even when multiple selected courses map to that group.

## 9. Plan demand

One owner counts once per exact university/major/plan/version/period regardless of selected-course count.

## 10. Credit-load metric

`TOTAL_DECLARED_CREDIT_LOAD` sums exact normalized plan credits. Zero-credit selections add zero. The total is declared intent, not enrolled or attempted workload.

## 11. Denominators

Course share divides course owners only by unsuppressed valid-active intent owners in the same scope/period. It is never labeled a population or eligible-student share.

## 12. Coverage

Output states observed-intents-only, optional exact population denominator, and ratio only for a nonzero authoritative denominator. Unknown and partial adoption remain explicit flags/reasons.

## 13. Privacy suppression

The caller supplies a versioned integer threshold of at least two. A nonzero contributing population below it yields whole-result `SUPPRESSED`; all metric values, small count, category membership, coverage counts, offerings, and capacity arithmetic are absent.

## 14. Review-demand metric

When explicitly enabled, distinct current review-required owners are counted only by `REVIEW_REQUIRED_INTENT_OWNER_COUNT`, excluded from normal demand, and governed by the same whole-result suppression.

## 15. Offering facts

No dataset yields `OFFERING_DATA_UNAVAILABLE`. An explicitly supplied exact dataset yields `MATCHING_OFFERING_FACT` or `NO_MATCHING_OFFERING_FACT`; absence from that dataset is not a universal availability claim.

## 16. Capacity facts

Capacity is optional, nonnegative, exact-scope/period/course supplied data with verified or synthetic provenance. Missing/mismatched data never becomes zero.

## 17. Capacity-gap arithmetic

`DECLARED_DEMAND_MINUS_CAPACITY` is emitted only for an exact fact and equals course intent owners minus known capacity. Negative, zero, and positive values carry no shortage, section, staffing, or action label.

## 18. Provenance

Intent provenance remains `DECLARED_STUDENT_INTENT`, `SYNTHETIC_SANDBOX_INTENT`, or `INSTITUTIONAL_IMPORT`. Fact provenance separately remains verified, synthetic, or unavailable. Versions are canonicalized.

## 19. Data-quality flags

Output uses exactly seven finite factual flags: complete input, partial coverage, unknown coverage, missing offerings, missing capacity, privacy suppression, and excluded review intents. No score exists.

## 20. Multi-plan

Broader university scope may include multiple explicit plans. Plan/group/credit semantics remain plan-scoped while global course demand deduplicates owner/course pairs.

## 21. Multi-university isolation

One result contains exactly one university. Any intent, catalog, period, offering, or capacity fact crossing that boundary rejects the entire call.

## 22. Period isolation

One exact target period is required; mixed-period input rejects atomically. No trend or longitudinal combination is performed.

## 23. Determinism

Canonical registry/dimension ordering and set-based deduplication make results independent of record, catalog, dictionary, and set order.

## 24. Performance

Processing is bounded and linear/set-based over supplied records, selections, and facts. Positive deployment `max_intents` and `max_catalog_courses` are mandatory; overflow rejects rather than truncates.

## 25. Limitations

Adoption may be partial; intent may change; facts may be missing/synthetic; broad repeated-query subtraction risk needs later controls. There is no forecast, confidence score, bottleneck rank, section estimate, faculty workload, or actual-registration comparison.

## 26. Future institutional API/adapters

Later work requires authorized institutional roles, permitted scopes, query auditing/rate controls, complementary suppression, real provider adapters, retention/audit, and aggregate UI. No such boundary is part of P6.2.
