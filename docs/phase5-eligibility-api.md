# Phase 5.4 Eligibility API Decision Record

## Temporary study-plan selector

`POST /api/v1/eligibility/can-take` accepts `study_plan_id` as a UUID.

The accepted schema does not currently provide a safe public natural key for a
study plan: university, faculty, and major names/codes are not both required
and uniquely constrained. A plan is uniquely identified only by the internal
`major_id`, `plan_number`, and `effective_year` combination. Exposing an
unverified combination of mutable display names would be less safe than the
existing UUID contract. A future phase should add or approve a stable public
plan selector before browser-facing product work relies on this endpoint.

## Boundary and errors

The API only validates transport structure and orchestrates the catalog
repository with the pure evaluator. It never parses `raw_prerequisite_text` or
infers equivalencies.

| Condition | HTTP status | `error_code` |
| --- | ---: | --- |
| Study plan absent | 404 | `STUDY_PLAN_NOT_FOUND` |
| Target absent from its university catalog | 404 | `TARGET_NOT_FOUND` |
| Target exists but is not in the selected plan | 409 | `TARGET_NOT_IN_STUDY_PLAN` |
| Catalog persistence inconsistency | 500 | `CATALOG_INTEGRITY_ERROR` |
| Catalog Data API failure | 503 | `CATALOG_TRANSPORT_ERROR` |
| Server-side catalog configuration missing | 503 | `CATALOG_CONFIGURATION_ERROR` |

`ELIGIBLE`, `NOT_ELIGIBLE`, and `REVIEW_REQUIRED` remain successful `200`
academic decisions, never infrastructure errors.
