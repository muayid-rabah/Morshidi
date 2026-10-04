# Institutional Demand Privacy and Suppression Policy

Policy version: **1.0**

## 1. Aggregate-first access

Institutional Demand V1 is aggregate-first. Its normal result contains typed scope, period, metrics, suppression metadata, coverage, quality flags, provenance, versions, and limitations. It never returns a collection of intent records.

## 2. Student-level prohibition

Institutional results exclude owner/student IDs, names, emails, phone numbers, individual course sets, raw attempts, grades, GPA, Advisor conversations, Digital Twin scenarios, recommendations, protected attributes, credentials, and source documents. A future advisor drill-down is a separate purpose, authorization, consent, and audit contract.

## 3. Minimum disclosure configuration

Every aggregation request supplies a versioned `minimum_disclosure_group_size` policy value. It must be an integer at least `2`. P6 does not declare a universal legal threshold. Production value and permissible scope design require institutional privacy/legal governance. Sandbox University may use `3` only as a visibly synthetic test default; it is not a legal or production recommendation.

## 4. Suppression semantics

Before metric calculation is exposed, count distinct owners contributing to the requested result class in the exact scope/period. Zero valid current owners with no separately requested review workload returns `INSUFFICIENT_DATA`. A nonzero contributing population below the configured threshold returns `SUPPRESSED`, reason `DEMAND_PRIVACY_SUPPRESSED`, and quality flag `SUPPRESSED_FOR_PRIVACY`.

Suppression withholds:

- the exact below-threshold population count;
- every course, group, plan, share, credit, review, offering, and capacity metric value;
- course membership and small-category identities when their presence would reveal a selection;
- capacity-gap arithmetic.

Suppressed values are absent, never `0`, rounded, bucketed, or estimated. The result may retain only safe scope/period references, contract/policy versions, threshold policy reference, suppressed metric IDs, provenance class, and generic limitations.

## 5. Small-group handling

No exception exists for zero-credit courses, review workload, synthetic capacity comparison, or administrator convenience. If a broader authorized scope passes the threshold it may be queried directly; V1 does not automatically broaden a scope or combine periods to escape suppression.

## 6. Coverage limitations

Passing the disclosure threshold says nothing about adoption coverage or representativeness. Results separately state `OBSERVED_INTENTS_ONLY`, known/unknown population denominator, and partial/unknown coverage flags. Suppression and coverage are orthogonal.

## 7. Synthetic Sandbox default

Sandbox outputs use synthetic owner identifiers and `SYNTHETIC_SANDBOX_INTENT` provenance. The default threshold `3` exists only for deterministic demonstrations and tests. UI and documentation must label it synthetic/non-legal and must not imply formal compliance.

## 8. Future institutional/legal configuration

Before production, an institution must approve threshold, allowed scope dimensions, query-rate controls, complementary suppression, release review, retention, audit, and incident response. This policy makes no claim of compliance with any specific law or regulation.

## 9. Subtraction-risk limitation

V1 accepts one exact authorized scope per result and does not expose owner lists or arbitrary demographic slices. These controls reduce but do not eliminate differencing/subtraction risk across repeated overlapping queries. Production aggregate APIs therefore require later query auditing, rate controls, permitted-dimension governance, complementary suppression, and possibly noise/bucketing policy before broad analyst access.

## 10. Role boundary

- `STUDENT`: may create/read/withdraw only owned intent through a future owner-authorized service; cannot read institutional aggregates merely by being a student.
- `AUTHORIZED_INSTITUTIONAL_ANALYST`: may read only suppressed aggregate results for authorized university, purpose, scope, and periods; no individual selections.
- `AUTHORIZED_ADVISOR`: receives no aggregate or cross-student drill-down authority by default; any case-level access requires separate policy and purpose.

P6.1 implements none of these roles. A future API must enforce them independently of scenario or intent identifiers.

## 11. Retention and withdrawal

Current-demand computation retains only the latest resolved current record needed for the approved purpose. A withdrawal stops current contribution immediately. Historical revisions and audit events, if later persisted, use a separately approved minimum/institution-configured retention schedule and are excluded from current aggregates. Withdrawal does not promise immediate erasure where an approved legal/audit obligation exists; that behavior must be disclosed by the institution.

## 12. Transparency

Before submission, students must receive clear notice that intent is non-binding and may contribute to privacy-preserving institutional planning aggregates. The notice identifies purpose, data classes, current-versus-historical handling, withdrawal effect, synthetic/real source context, and where institutional retention/privacy terms can be found. No silent secondary use is allowed.
