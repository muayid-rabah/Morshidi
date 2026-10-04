STATUS: RECONSTRUCTED DRAFT — NOT APPROVED

# P8.1 Recovery Source Traceability Map

## Method

This map distinguishes evidence already present in the repository from draft proposals. Empty canonical companion files are evidence of a documentation gap, not evidence of their alleged original contents.

| Reconstructed contract | Exact source / location | Implementation or test evidence | Classification |
| --- | --- | --- | --- |
| P8 no-write, engine precedence, role redaction | `docs/p8-grounded-knowledge-decision-trace-policy.md`, §§1, 2, 4–8 | No P8 runtime service | VERIFIED policy umbrella |
| Ledger envelope / fields | `apps/api/app/decision_trace/models.py`, `CanonicalLedgerEntry`, `EvidenceReference` | `tests/test_decision_trace.py` 001, 020–024, 036–040 | VERIFIED Slice 1 |
| Materiality registry | `decision_trace/registries.py`, `DecisionType`, `MaterialityClass`, `DECISION_MATERIALITY_REGISTRY` | Tests 003–008 | VERIFIED Slice 1 |
| Canonical JSON and SHA-256 | `decision_trace/canonical.py`, `canonical_ledger_payload`, `calculate_integrity_hash`, `verify_integrity_hash` | Tests 009–014, 028, 039 | VERIFIED Slice 1 |
| Scope validation / supersession/redaction | `decision_trace/validation.py`, `validate_entry`, `create_superseding_entry`, `project_trace_metadata` | Tests 015–027, 040 | VERIFIED Slice 1 |
| Replay modes | `decision_trace/replay.py`, `check_exact_replay_availability`, `evaluate_replay_comparison` | Tests 029–035 | VERIFIED Slice 1 |
| Slice 1 non-goals | `docs/decision-trace-domain-implementation.md`, Scope/Deferred | No persistence imports/routes | VERIFIED deferral |
| Advisor authorization predicate | `docs/advisor-authorization-persistence.md`, §2; `apps/api/app/advisor_service/authorization.py`, `authorize_advisor_for_student` | `tests/test_advisor_authorization.py` and migration static tests | VERIFIED P7 contract/implementation |
| Advisor assignment storage | `supabase/migrations/20260923150000_add_advisor_authorization_persistence.sql` | Full root suite passes; local DB security still skipped | VERIFIED schema text; NOT VERIFIED runtime RLS |
| RLS/grant distinction and owner/analyst boundaries | `docs/mock-registration-rls-access-matrix.md`, introductory paragraph and matrix | Existing P6 local tests skipped here | VERIFIED policy precedent |
| Append-only/RPC precedent | `docs/mock-registration-threat-model.md`, direct update/delete/RPC threats; `supabase/migrations/20260922134625...sql`, `persist_mock_registration_revision`, RLS/grant section | Existing mock-registration local tests skipped here | VERIFIED P6 precedent, not P8 implementation |
| Institutional aggregate/suppression boundary | `docs/mock-registration-persistence-policy.md`; `docs/institutional-intelligence-policy.md`; P8 umbrella §6 | P6/P7 suites and skipped local integration files | VERIFIED boundary; P8 query runtime absent |
| Advisor copilot non-mutating boundary | `docs/advisor-copilot-policy.md`; capability matrix P7.5 evidence | `apps/api/app/advisor_copilot/`, tests | VERIFIED P7 boundary |
| Explainability capability direction | `docs/morshidi-world-class-capability-matrix.md`, WC-007 and WC-040 rows | No graph package/test | VERIFIED roadmap intent; DRAFT contract details |
| Regulation RAG / query / impact direction | P8 umbrella §§1, 7–9; capability matrix WC-038, WC-039, WC-046 | No runtime packages/tests | VERIFIED roadmap intent; DRAFT contract details |

## Explicit contradictions and gaps

1. The umbrella policy says companion contracts and a 54-scenario matrix exist, but six canonical files are zero-byte. Their detailed original requirements cannot be recovered from Git history and are **OPEN CONTRACT / REQUIRES HUMAN APPROVAL**.
2. P8 umbrella policy labels P8.1 “APPROVED POLICY CONTRACT,” while its listed companion evidence is absent. This recovery therefore keeps P8.1 **PARTIAL / AWAITING HUMAN APPROVAL** rather than treating it as complete.
3. Slice 1 implements a pure, local canonical hash contract but no persistence/RLS/RPC. Any draft persistence statement is proposed; SHA-256 does not grant access or sign data.
4. Existing P6/P7 migrations are security precedents, not authorization to copy their SQL, table names, grants, or policies into P8 without review.
5. Existing test suite passes from repository root with 13 local-Supabase skips; it does not validate P8 Slice 2 database security because no P8 Slice 2 files/tests exist.

## Open contracts requiring human approval

- Source authority, ingestion, retention, and conflict resolution for university regulations.
- Ledger persistence schema/RPC/access policy, event selection, evidence retention, and exact replay artifact retention.
- Graph type registry/identity/projection and change-impact affected-population semantics.
- Institutional metric catalog, permitted roles/dimensions, disclosure/differencing controls, and AI query evaluation policy.
