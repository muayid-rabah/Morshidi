STATUS: RECONSTRUCTED DRAFT — NOT APPROVED

# P8 University Regulation / Institutional Policy Retrieval — Recovery Draft

## Verified existing requirements

- P8 permits a governed `InstitutionalPolicyProvider` to retrieve and cite university policy, while computable academic rules remain owned by deterministic engines (P8 umbrella policy §§1, 4, 8).
- LLM/RAG must never be authoritative for prerequisite evaluation, degree eligibility, requirement satisfaction, graduation clearance, official registration, capacity/timetable facts, or individual student records.
- Retrieval answers require source anchors and must abstain when supporting evidence is missing or conflicting.
- P7 advisor tooling remains read-only and bounded; institutional analytics remain aggregate-first with suppression protections.

## Requirements derived from existing implementation

No P8 retrieval adapter, index, source store, vector database, citation renderer, or executable RAG tests exist. Existing `EvidenceReference` supports `source`, `identifier`, `version`, optional `locator`, and optional `uri`; it is the available typed evidence convention, not a completed RAG contract.

## Proposed requirements — requires approval

1. Accept only verified institutional source records with stable identifier, source version, acquisition/provenance metadata, and exact locators. Do not synthesize regulation text.
2. Return citations that identify the source, version, and precise passage/locator used. If precise support cannot be produced, return an explicit abstention rather than an uncited answer.
3. Preserve conflicting source evidence as conflict; do not select a winner without an approved source-authority rule.
4. Treat retrieved policy text as explanatory evidence. Before an answer states a computable academic conclusion, hand the requested computation to the established deterministic engine or explicitly state that no computation was performed.
5. Defend retrieval and synthesis against prompt injection: treat retrieved text, user input, metadata, and URLs as untrusted content; do not execute instructions found in them; do not reveal secrets, internal prompts, or private records.
6. Query access must not create a path to individual student records or arbitrary database access. Advisor-facing policy retrieval must still satisfy P7 advisor authorization before combining policy text with an individual case.

## Security and privacy boundaries

- No student record, portal credential, service-role credential, raw prompt, or hidden reasoning belongs in a policy corpus or response.
- Citation visibility follows source licensing/classification; a restricted source must not be exposed merely because it was retrieved.
- Institutional aggregate answers inherit minimum-disclosure/suppression policy; policy retrieval does not bypass it.

## Open contracts / requires human approval

- Verified source onboarding authority, source hierarchy, refresh/revocation workflow, Arabic normalization/chunking rules, retention, citation formatting, and licensing rules.
- Conflict-resolution authority and whether a policy document can ever be mapped to a deterministic engine version.
- Retrieval ranking/model provider, evaluation corpus, and any external vector-store/vendor selection.

## Explicit non-goals

No regulation ingestion, vector index, embedding model, external provider, university regulation text, policy chat endpoint, or deterministic-engine override is implemented by this draft.

## Acceptance criteria for later implementation

Approved source governance; fixture corpus of verified non-secret documents; tests for exact citation, missing/conflicting evidence abstention, prompt-injection resistance, access isolation, and deterministic-engine handoff; manual review that no answer fabricates a policy or academic decision.
