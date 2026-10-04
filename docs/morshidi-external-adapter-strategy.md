# Morshidi External Adapter Strategy

## Contract rule

Morshidi domain and decision services consume stable provider interfaces, never vendor payloads. Synthetic, CSV, and institutional adapters must return the same normalized records with source identity, retrieval time, academic period, source version, and verification state. Unknown values remain unknown; adapters do not infer institutional facts.

| Provider | Purpose | Synthetic implementation | CSV/file implementation | Institutional implementation | Authority and security boundary |
|---|---|---|---|---|---|
| `StudentRecordProvider` | Courses, attempts, grades, standing, program association | Deterministic pseudonymous fixtures | Validated import with quarantine and row-level diagnostics | SIS/student-record API | SIS is authoritative; owner/role scope, encryption, audit, minimum fields |
| `CourseOfferingProvider` | Sections, terms, capacity, modality, location, timetable | Seeded offerings and capacity scenarios | Term-scoped controlled import | Registration/scheduling API | Offering system is authoritative; freshness and reconciliation are mandatory |
| `HistoricalOutcomeProvider` | Aggregated outcomes for workload and predictive validation | Clearly synthetic cohorts | De-identified governed extracts | Warehouse/research data service | Not authoritative for individuals; purpose limitation, suppression, bias review |
| `IdentityProvider` | Authentication and institutional roles | Local test identities with fixed roles | Not permitted for identity assertion | OIDC/SAML university SSO | IdP authenticates; Morshidi authorizes; no role trust without mapped claims |
| `AcademicCalendarProvider` | Terms, deadlines, holidays, milestones | Fictional calendar | Versioned calendar import | Registrar/calendar API | Registrar source is authoritative; timezone and version required |
| `InstitutionalPolicyProvider` | Regulations, policies, handbooks, effective dates | Synthetic cited corpus | Signed/versioned document ingestion | Governed document repository/API | Retrieval supports explanation; deterministic rules require separately approved encoding |

## Adapter conformance

Every adapter must pass the same contract suite: schema validation, stable identifiers, provenance completeness, version replay, pagination, timeout behavior, partial failure, duplicate handling, freshness, authorization, redaction, and deterministic fixture tests. Vendor-specific fields remain inside the adapter.

CSV ingestion is staged: upload, parse, validate, quarantine invalid rows, preview, approve, publish a version, and retain an audit manifest. It never writes around domain constraints. Synthetic adapters use fixed seeds and visible `synthetic` provenance, and can be reset without affecting non-sandbox data.

## Integration maturity

1. In-memory deterministic fixtures prove domain behavior.
2. Sandbox providers prove full workflows and failure states.
3. Controlled CSV adapters prove mapping and data-quality operations.
4. Read-only institutional adapters prove identity, freshness, and reconciliation.
5. Transactional adapters, if later authorized, add explicit confirmation, idempotency, audit, rollback/reconciliation, and operational ownership.

No adapter is production-ready solely because a synthetic or CSV implementation passes. Real SIS and SSO delivery remains an institutional dependency, and historical-data features remain unvalidated until representative governed datasets pass their stated evaluation gates.
