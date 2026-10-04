STATUS: RECONSTRUCTED DRAFT — NOT APPROVED

# P8 Institutional AI Query Experience — Recovery Draft

## Verified existing requirements

- P8 describes a constrained natural-language interface over a governed institutional metric catalog; arbitrary SQL and student-record exposure are prohibited (P8 umbrella policy §1).
- P6 institutional demand and P7 institutional intelligence are aggregate-first, tenant-scoped, and inherit whole-result minimum-disclosure suppression. Active exact-university institutional membership is a server-authoritative boundary.
- Institutional analyst role gives zero authority for individual student traces; advisor access is not analyst access.

## Requirements derived from existing implementation

Existing institutional intelligence exposes deterministic signals and decision traces, but there is no P8 natural-language query planner, metric registry for NL access, SQL executor, or P8 query tests. Existing aggregate suppression and membership services are reusable authority boundaries, not proof that a query experience exists.

## Proposed governed query boundary — requires approval

1. Natural language is translated only into a finite, approved institutional metric catalog with typed parameters and permitted aggregations. Unsupported requests abstain.
2. The planner may call only approved server-side metric/service adapters. It must never emit, execute, or accept arbitrary SQL, table names, raw filters, debug exports, or unrestricted database access.
3. Every response includes metric definition/version, applicable period/university scope, deterministic evidence/provenance, quality flags, suppression state, and limitations.
4. The authoritative university comes from active server-side membership; client parameters cannot widen it. The response must not disclose existence of unavailable tenants or records.
5. All aggregate results apply existing minimum-disclosure policy after the full query filter. Suppressed results expose no raw rows or bypass counts.
6. AI may phrase grounded metric output and cited policy evidence; it cannot manufacture metric values, decide student academic legality, or infer individual records.

## Security and privacy boundaries

- No individual student drill-down, identifier, attempt, GPA, trace, scenario, conversation, raw count, or unsuppressed low-cohort result.
- No direct database credentials, Data API endpoint, SQL string, or service role is exposed to the browser or model.
- Prompt injection in user or retrieved content cannot expand the metric allowlist, role, tenant, or response fields.

## Open contracts / requires human approval

- Approved metric catalog, allowed dimensions/periods, rate limits/query-cost controls, disclosure/differencing controls, audit retention, model/provider, Arabic query semantics, and authorized institutional roles beyond current analyst membership.

## Explicit non-goals

No NL-to-SQL, database agent, dashboard, query endpoint, unrestricted export, predictive demand claim, or student-level institutional search.

## Acceptance criteria for later implementation

Approved finite catalog and response schema; tests for allowlist rejection, SQL/prompt-injection rejection, analyst tenant binding, suppression, no individual fields, evidence grounding, missing-evidence abstention, and deterministic metric parity.
