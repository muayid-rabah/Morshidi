# Student Intelligence Engine — P3.2

## Purpose and claims

Policy 1.0 implements the 19 approved deterministic rules for PROP-011, PROP-012, PROP-013, PROP-014, and PROP-078. It intentionally does not close domain-level, predictive, UI, integration, or continuous-lifecycle claims.

## Architecture and shared contracts

`app.student_intelligence` is a pure package: immutable models, authority filtering, performance observations, strengths, difficulty, readiness, structural risk, predictive boundary, and one aggregate evaluator. It performs no I/O, persistence, HTTP, Supabase, LLM, clock, or random operation.

Every result carries policy version, exact capability/status, typed observations/signals, finite reason codes, minimal evidence, typed missing inputs, and limitations. Collections are sorted by stable identifiers. The evaluator consumes already-loaded attempt records, Phase 6 progress, dependency exposures, and an existing Phase 5 eligibility result; it does not recalculate those domains.

## Capability behavior

- Performance implements PERF-001–006: outcomes, repeats, sequence-backed recovery, repeated failures, requirement completion, and dependency exposure.
- Strength implements STRENGTH-001–002: required completion and verified recovery evidence.
- Difficulty implements DIFFICULTY-001–003 without severity, cause, or personal judgment.
- Readiness implements READINESS-001–005 as target-specific preparation evidence. Phase 5 remains authoritative and readiness never changes eligibility.
- Structural risk implements STRUCTURAL_RISK-001–003 as warnings, never predictions.
- Predictive risk always returns `BLOCKED_BY_EXTERNAL_DATA` with `NO_COHORT_DATA`; no model path exists.

## Safety boundaries

Raw grade values are never read by rules. Tests prove synthetic 85/59 and grade-point/letter changes cannot change any result or outcome. `UNVERIFIED`, `MODEL_OUTPUT`, and `DERIVED_DETERMINISTIC` attempts cannot drive conclusions. `STUDENT_RECORD` supports factual history only; verified official/manual-review evidence may support approved conclusions.

Recovery ordering requires supplied `attempt_sequence`; absent sequence never creates a temporal claim. Full history is retained. Required zero-credit courses participate through requirement semantics. Referenced-only courses contribute only when supplied as prerequisite evidence and never become plan progress dimensions. Review-required dependencies emit conservative review status without inferred relations.

## Persistence, service, API, and privacy decisions

Results are recomputed on demand and are not persisted; no migration or RLS change exists. P3.2 adds no repository-backed service and no API because no current consumer is authorized. Engine database reads are exactly zero; future orchestration must load student state, progress, and eligibility once and reuse them. Raw grades and source references are absent from outputs.

## Performance and dependencies

Evaluation is linear over attempts/progress/exposures plus stable sorting (`O(n log n)` worst case); there is no combinatorial search. Grade policy, canonical periods, taxonomy, and cohort/predictive data remain external dependencies.

## P4 entry conditions

P4 requires approval of P3.2 outputs, a versioned integration policy defining how (or whether) intelligence affects recommendations/plans, preserved Phase 5 hard gating, read-only API/privacy contracts, and full factor-isolation/regression tests. Predictive/domain/grade intelligence remains blocked independently.
