# Institutional AI Query Experience — Canonical Contract

Status: **APPROVED POLICY CONTRACT**

WC-039 is a constrained natural-language experience over a governed institutional
metric catalog. It is distinct from Advisor Copilot, student advisor features,
and the existing deterministic Institutional Intelligence endpoints.

## 1. Normative boundaries

- Natural language may map only to a finite, approved metric catalog with typed
  parameters and permitted aggregations. Unsupported requests abstain.
- The experience may call only approved server-side metric/service adapters. It
  must never emit, execute, or accept arbitrary SQL, table names, raw filters,
  debug exports, unrestricted database access, or browser-held service secrets.
- Each response identifies the metric definition/version, effective university
  and period scope, deterministic provenance, quality/suppression state, and
  limitations or uncertainty.
- University scope comes from active server-side institutional membership; client
  parameters cannot widen it or reveal unavailable tenants/records.
- Existing minimum-disclosure policy applies after the full filter. Suppressed
  results reveal no raw rows, bypass counts, individual identifiers, attempts,
  GPA, traces, scenarios, conversations, or low-cohort aggregates.
- AI may phrase governed metric output and cited policy evidence. It cannot
  manufacture values, infer individual records, mutate state, or decide academic
  legality.
- User/retrieved-content prompt injection cannot expand the metric allowlist,
  actor role, tenant scope, or response fields.

## 2. Owner-approved V1 runtime

WC-039 V1 is locally implemented over the existing Institutional Intelligence
service. Its static `WC039_METRIC_CATALOG_V1` contains exactly the 13 existing
`InstitutionalSignalId` values, with Arabic/English labels, units, one typed
university/period/plan/course scope, and suppression annotations. The question
is normalized and bounded to 300 characters. An authenticated active
`INSTITUTIONAL_ANALYST` membership is verified before one server-only OpenAI
interpretation call. The interpreter may select one catalog ID or abstain;
its structured result is untrusted and checked against the closed catalog.
There is no NL-to-SQL, model tool, arbitrary filter, batch, table metadata,
student drill-down, or model-produced metric value.

The existing deterministic service evaluates the authorized typed scope and
provides the sole metric result. WC-039 projects only the selected signal,
inherits whole-result suppression, and withholds suppressed values and unsafe
quality details. The final response contains a mechanically rendered answer,
metric/version/scope preview, quality state, source/policy provenance fields,
limitations, and a SHA-256 fingerprint over the governed metric, authorized
scope, and available versions—not raw question text or student data. Queries
are ephemeral: no conversation/query-history table, Decision Trace append,
or academic-state mutation. `INSTITUTIONAL_AD_HOC_QUERY` remains `NOT_LEDGERED`.
Missing provider configuration or malformed/provider-rejected interpretation
abstains safely. The focused institutional Arabic RTL page reuses the existing
session/proxy and backend analyst-role architecture.

Local Supabase tests verify role/tenant denial, below-threshold suppression,
absence of raw student fields, unchanged academic/registration/membership/
catalog/ledger snapshots, and no query-history table. This is synthetic/local
runtime evidence, **not representative institutional real-data validation**.

## 3. Remaining contracts — requires separate approval

- Representative real-data metric reconciliation, Arabic/English intent quality
  evaluation corpus, source-version authority, and institutional adoption.
- Repeated-query/differencing governance, operational rate/cost controls,
  retention/export rules, and any future approved saved-query workflow.
- Any expanded metrics, dimensions, authorized roles, or provider changes.

## 4. Non-goals and acceptance

V1 does not authorize NL-to-SQL, a database agent, unrestricted exports,
dashboards, predictive claims, or student-level institutional search. Local
runtime acceptance requires executable allowlist/injection, tenant, suppression,
abstention, deterministic parity, frontend, and no-write evidence. Full
institutional acceptance still requires representative real-data validation.
