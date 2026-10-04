# Morshidi Engineering Instructions

## Required start-of-session discipline

1. Read `docs/CODEX_PROGRESS.md` before starting work, then verify its claims against the actual filesystem and Git state.
2. Inspect `git status --short`, the relevant source files, existing architecture, policy documents, migrations, and tests before changing behavior.
3. Do not rebuild an existing feature until its implementation, contracts, and boundaries are understood.
4. Follow the official roadmap. Do not silently expand scope; implement the smallest coherent slice.
5. Update `docs/CODEX_PROGRESS.md` continuously with date, phase/slice, objective, starting SHA, files changed, real file sizes, implementation details, test commands/results, security checks, remaining problems, acceptance status, and the exact next starting point.

## Architectural and security invariants

**AI EXPLAINS — DETERMINISTIC RULES DECIDE.**

- LLMs and RAG may explain, summarize, retrieve governed evidence, and cite sources. They must never independently determine academic eligibility, prerequisite satisfaction, progress, graduation, semester validity, or degree-path correctness.
- Preserve authentication, authorization, tenant isolation, student ownership, and advisor-assignment boundaries. Do not weaken them for convenience.
- Never expose credentials, tokens, secrets, private student data, chain-of-thought, or hidden reasoning.
- Treat database/RLS/RPC security as unverified until it passes real local database integration tests. Mocked tests alone are insufficient.

## Verification and delivery rules

- Add meaningful focused and regression tests for every implementation slice.
- Record actual test outcomes, including failures, skips, and blockers. Never fabricate implementation or test evidence.
- Verify every important created or modified file from disk: existence, nonzero byte size where expected, diff, and applicable tests.
- Do not modify production resources or apply migrations to production during local validation.
- Never automatically stage, commit, push, merge, or create a pull request. Human approval is required before each of those actions.
- Preserve existing work and nested instructions. In particular, read and obey `apps/web/AGENTS.md` before frontend changes.
