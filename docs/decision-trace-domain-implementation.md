# Decision Trace Ledger Domain Core

## Scope
This corrective package restores the pure P8 Decision Trace Ledger domain core. It implements typed immutable trace contracts, deterministic local JSON canonicalization, SHA-256 integrity verification, immutable supersession, replay availability, and structural redaction metadata. It does not implement persistence, Supabase, RLS, HTTP APIs, retention jobs, exports, UI, Regulation RAG, Explainability Graph runtime, Change Impact runtime, or Institutional AI Query runtime.

## Package
`apps/api/app/decision_trace/` contains finite registries, immutable models, canonical hashing, validation/supersession, replay contracts, and public exports.

## Materiality
The closed classes are `LEDGER_REQUIRED`, `LEDGER_OPTIONAL`, `DOMAIN_TRACE_ONLY`, and `NOT_LEDGERED`. Unknown decision enum values fail closed.

## Envelope
`CanonicalLedgerEntry` retains decision identity, materiality, actor/scope, university isolation, conditional student identity, engine/policy/source versions, input/scenario references, status/outcome, typed evidence references, domain trace reference, provenance, timestamp, redaction profile, integrity/supersession/replay metadata, limitations, and schema/hash versions.

No chain-of-thought, reasoning token, scratchpad, raw prompt, raw completion, or hidden reasoning storage field exists.

## Hash contract
`HASH_CONTRACT_VERSION = "1.0"`. This is a local deterministic JSON contract and does not claim RFC 8785 conformance. JSON keys are sorted, compact separators are used, ASCII escaping is deterministic, hashing uses UTF-8, enums serialize by value, timestamps normalize to UTC, set-like tuples are normalized, and `integrity_hash` is excluded from its own payload. SHA-256 is integrity evidence only, not authorization or a digital signature.

## Validation
Validation requires nonblank identity and university scope, UTC-aware timestamps, correct materiality, non-empty source versions, valid SHA-256 shapes, student/period privacy invariants, authoritative-scenario separation, and no self-supersession. Authorization remains outside this pure package.

## Supersession
Corrections receive a new ledger identity, point to the prior entry via `supersedes_entry_id`, may link the prior integrity digest via `previous_entry_hash`, never mutate the previous object, and receive a fresh hash.

## Replay
`EXACT_REPLAY` fails closed when historical source, engine, or policy versions are unavailable. `CURRENT_RECOMPUTATION` is represented separately and never overwrites historical output. `NOT_REPLAYABLE` is explicit. The domain slice defines contracts only; persistence and engine orchestration remain deferred.

## Tests
`apps/api/tests/test_decision_trace.py` contains focused tests for immutability, finite registry behavior, deterministic normalization/hashing, tamper detection, supersession, scope invariants, replay availability and failure, structural no-CoT guarantees, and redaction projection.

## Deferred
Persistence, RLS, API/service, viewer authorization, retention enforcement, exports, policy retrieval, explainability graph runtime, change-impact runtime, and institutional AI query runtime remain future P8 work. WC-040 remains `PARTIALLY_ENABLED`.
