# Morshidi — Academic Intelligence Operating System

Morshidi is engineering infrastructure for trusted academic decision support. Its
governing principle is **AI EXPLAINS — DETERMINISTIC RULES DECIDE**: academic
legality, progress, prerequisite satisfaction, planning constraints, and related
decisions come from explicit deterministic engines and governed data. AI-facing
components may explain supported results; they do not replace those decision
boundaries or an institution's official systems.

## Architecture

```text
Next.js frontend
  -> authenticated bearer request
FastAPI application and domain services
  -> deterministic academic engines / governed policy retrieval
Supabase Auth + PostgreSQL persistence
```

The frontend is a unified Arabic-first, RTL-capable Morshidi experience. Student
routes use the authenticated backend surface; server-side services use Supabase
Auth and PostgreSQL persistence without exposing service credentials to browsers.

## Repository structure

- `apps/web` — Next.js, TypeScript, authentication boundary, student experience
- `apps/api` — FastAPI routes, domain services, deterministic engines, and adapters
- `supabase` — forward-only PostgreSQL/Supabase migrations and local configuration
- `academic-data` — academic source dataset used by the project
- `docs` — normative policies, implementation records, validation evidence, and roadmap

## Current implementation status

| Capability | Status | Current boundary |
| --- | --- | --- |
| Catalog/Foundation | IMPLEMENTED | Versioned catalog and study-plan foundations. |
| Student Profile | IMPLEMENTED | Authenticated profile and course-attempt persistence. |
| Progress | IMPLEMENTED | Deterministic academic-progress evaluation. |
| Eligibility | IMPLEMENTED | Deterministic prerequisite and target-state decisions. |
| Recommendations | IMPLEMENTED | Deterministic ranked recommendations. |
| Semester Planner | IMPLEMENTED | Bounded deterministic plan options. |
| Degree Path | IMPLEMENTED | Deterministic modeled degree paths. |
| Mock Registration | IMPLEMENTED | Immutable, non-binding student intent; never official enrollment. |
| Advisor | IMPLEMENTED | Authenticated student-facing explanation service. |
| Advisor Copilot | IMPLEMENTED | Assignment-scoped, read-only deterministic tools. |
| Institutional Intelligence | IMPLEMENTED | Governed aggregate demand and intelligence surfaces. |
| Decision Trace | PARTIAL | Domain, persistence, evidence, replay, outbox, and processor boundaries exist; a student Decision History read surface is not implemented. |
| University Policy Retrieval | PARTIAL | Governed structured policy model, verified-only read surface, and citations exist; semantic RAG answers do not. |
| Policy Ingestion | IMPLEMENTED | Structured, atomic service-role ingestion of documents, versions, and passages. |
| Policy Frontend | PARTIAL | Authenticated student policy viewer is connected to the backend. |
| Decision History Frontend | PLANNED | Current page is explicitly an under-development shell. |
| Semantic Policy RAG | PLANNED | No embeddings, vector retrieval, document/PDF parser, or generated grounded answer pipeline. |
| Change Impact Engine | PLANNED | WC-046 analysis runtime is not implemented. |
| Academic Explainability Graph | PLANNED | WC-007 graph runtime is not implemented. |
| Institutional AI Query Experience | PLANNED | WC-039 governed natural-language metric-query runtime is not implemented. |

`IMPLEMENTED` means the repository contains the relevant runtime capability and
test coverage; it is not a claim of institutional adoption, production deployment,
or official university data authority. `PARTIAL` identifies a real implemented
slice with documented remaining boundaries.

## Local development

The backend needs Python 3.11 and the dependencies in
`apps/api/requirements.txt`.

```powershell
cd apps/api
.\.venv311\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

```powershell
cd apps/web
npm ci
npm run dev
```

Typical local endpoints are the frontend at `http://localhost:3000`, FastAPI at
`http://127.0.0.1:8000`, and API documentation at
`http://127.0.0.1:8000/docs`. Supabase local configuration and any secrets remain
environment-provided; never commit credentials.

## Verification baseline

The current audited backend baseline, executed from the repository root against
the configured Local Supabase environment, is **1,488 passed, 0 failed, 0
skipped** (two existing FastAPI/Starlette dependency deprecation warnings). Test
counts evolve; see current tests and validation records for later evidence.

## Deliberate boundaries

Morshidi is decision-support infrastructure, not an official registration,
enrollment, degree-clearance, or university source-of-truth system. Policy
retrieval remains governed and citation-bound: no silent source substitution,
no client-controlled tenant scope, and no AI authority over deterministic
academic computation.
