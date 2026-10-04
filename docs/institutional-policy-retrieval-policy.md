# University Regulation RAG / Policy Retrieval — Approved Canonical Contract

Status: **APPROVED POLICY CONTRACT**

This approved canonical contract recovers the P8 policy-retrieval boundary. It
does not certify an institution's policy corpus, source approval, deployment, or
generated-answer workflow.

## 1. Governing authority

**AI EXPLAINS — DETERMINISTIC RULES DECIDE.** University Regulation RAG / Policy
Retrieval may retrieve, summarize, and cite governed regulatory text. It must
never independently decide prerequisite satisfaction, eligibility, academic
progress, degree/graduation completion, semester validity, degree-path validity,
official registration, capacity/timetable facts, or individual standing.

When a request is computable by an established deterministic engine, retrieval
must hand it off or state that no computation was performed. Policy text is
explanatory evidence, not a substitute authority.

## 2. Normative source and response rules

- Sources have a stable document identity, version, admission state, provenance,
  and exact passage locator. No regulation text or citation may be synthesized.
- Only verified/effective source material may support a student-facing governed
  response. Unverified, pending, superseded, withdrawn, unavailable, missing, or
  conflicting evidence must produce a visible limitation or abstention, not a
  silent substitution.
- A cited result identifies the document, version, and exact passage/locator.
  Citation fidelity is required even where a rendered response is concise.
- Conflicting verified evidence remains a disclosed conflict until an approved
  source-authority rule resolves it.
- Retrieved text, user input, metadata, and URLs are untrusted content. They
  cannot issue instructions, expand tool access, disclose secrets, or change
  deterministic/authorization authority.
- Retrieval is tenant-scoped. Client input cannot widen university scope or
  become a route to arbitrary database access or individual academic records.
- Combining policy evidence with an individual advisor case requires the existing
  P7 advisor authorization predicate before student data is loaded.

## 3. Current implementation status

**PARTIAL.** The repository contains a typed policy domain, source-admission
states, document/version/passage and citation-anchor models, deterministic
computation classifier handoff, Supabase/PostgreSQL persistence, atomic
structured service-role ingestion, verified-only student-policy read endpoints,
lexical and semantic retrieval, deterministic hybrid fusion, and a bounded
grounded-answer endpoint and frontend. The answer path abstains without verified
evidence, accepts only retrieved passage IDs from the provider, and constructs
citations from server-side retrieval rows.

The implementation does not establish that a particular university has supplied
or verified production policy content. Production currently has no verified
institutional corpus. Document/PDF parsing, institutional source onboarding,
human conflict adjudication, and acceptance of the complete P8 exit gate remain
outside this bounded runtime slice.

## 4. Privacy and disclosure

Policy retrieval must not return credentials, raw prompts, hidden reasoning,
student records, or source content that the caller may not view. Restricted
source visibility follows an approved classification/licensing policy. Aggregate
institutional use retains existing minimum-disclosure and suppression controls.

## 5. Open contracts — requires human approval

- Verified source onboarding authority, source hierarchy, refresh/revocation,
  retention, licensing, and source classification.
- Arabic normalization/chunking and citation-rendering rules.
- Conflict-resolution authority and mapping between policy versions and
  deterministic engine versions.
- Evaluation corpus, retrieval ranking, model/provider, and any vector-store or
  embedding adoption.
- Generated-answer review and audit governance beyond the bounded V1 UX.

## 6. Non-goals and acceptance

This contract does not authorize an LLM to decide academic outcomes, an
unrestricted policy chat endpoint, or an official university data claim. The
bounded V1 answer endpoint and server-only provider described above do not
constitute institutional approval. Completion requires approved source
governance and tests for exact
citations, missing/conflicting evidence abstention, prompt-injection resistance,
tenant/access isolation, and deterministic-engine handoff.
