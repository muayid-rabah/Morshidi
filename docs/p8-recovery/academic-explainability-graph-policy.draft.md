STATUS: RECONSTRUCTED DRAFT — NOT APPROVED

# P8 Academic Explainability Graph — Recovery Draft

## Verified existing requirements

- P8 names WC-007 as a typed directed acyclic graph connecting decisions, rules, factors, and policy passages (P8 umbrella policy §1).
- The capability roadmap expects material recommendations to link typed facts, constraints, versions, and readable reasoning; it identifies evidence completeness, redaction, and graph cycles as validation concerns.
- Existing deterministic engines and Slice 1 traces provide versioned facts, source/evidence references, scope, limitations, and replay metadata. They do not create a graph runtime.

## Requirements derived from existing implementation

The available conceptual relation is: `Decision → Rule/Factor → Course → Requirement → Evidence → Source`. `CanonicalLedgerEntry` provides decision/evidence/version provenance but has no graph node, edge, traversal, storage, or public projection type. Domain traces may be referenced via `domain_trace_reference` only.

## Proposed graph contract — requires approval

| Element | Draft fields / rule |
| --- | --- |
| Node | Stable node ID, closed node kind, tenant/scope classification, source version, provenance, redaction class, display-safe label/reference; never raw hidden reasoning. |
| Node kinds | `DECISION`, `RULE`, `FACTOR`, `COURSE`, `REQUIREMENT`, `EVIDENCE`, `SOURCE`, and optionally `LIMITATION` only after approval. |
| Edge | Stable edge ID; closed relation kind such as `EVALUATED_BY`, `CONSTRAINED_BY`, `SATISFIES`, `EVIDENCED_BY`, `SOURCED_FROM`, `SUPERSEDES`; directed from claim/decision to supporting or constraining fact. |
| Provenance | Each node/edge identifies originating deterministic engine, version, source/policy version, and evidence reference where applicable. |
| Cycle prevention | Graph builder rejects a new edge that makes a DAG cycle. Supersession is represented as a temporal reference outside causal traversal or a separately cycle-safe relation. |
| Scope validation | A child cannot widen parent university/student scope. Cross-tenant references fail closed. |
| Missing evidence | Render an explicit missing/unavailable evidence node or limitation; never invent an edge or source. |

## Security and privacy boundaries

- Student projection must expose only student-safe nodes/edges for the verified owner.
- Advisor projection requires the complete P7 predicate before loading an individual graph.
- Institutional analysts receive no individual graph; only future approved, suppression-safe aggregates may mention de-identified structural patterns.
- Graph expansion must not disclose inaccessible node existence through error distinctions or edge counts.

## Open contracts / requires human approval

- Definitive node/edge registries, identity algorithm, versioning/migration rules, maximum traversal/depth, caching, graph persistence, and exact redaction profiles.
- Whether recommendation explanation and policy-retrieval graph nodes share one graph namespace.

## Explicit non-goals

No graph database, graph API, UI visualization, graph persistence, automatic edge mining, or runtime graph builder is created. The graph must not substitute for deterministic eligibility/progress/planning engines.

## Acceptance criteria for later implementation

Approved type registry and access matrix; tests for determinism, cycle rejection, scope rejection, missing evidence, student/advisor projection, analyst denial, source provenance, and no hidden-reasoning fields.
