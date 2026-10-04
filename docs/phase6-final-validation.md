# Phase 6 final validation

## 1. Scope

Phase 6.6 audited the complete Student Academic Foundation from verified
Supabase Auth identity through profile/attempt persistence, profile-backed
eligibility, and deterministic academic progress. The audit added acceptance
coverage and fixed one request-validation defect. It added no recommendation,
ranking, planning, transcript import, GPA calculation, equivalency inference,
frontend, AI, or remote operation.

## 2. Components audited

- Auth verification and application configuration
- Student profile and attempt schema, triggers, grants, and RLS
- Student and catalog Data API repositories
- Phase 5 prerequisite evaluator and eligibility service
- Academic progress models and pure engine
- Student orchestration service, HTTP routes, schemas, and exception mappings
- Normal, repository, API, pure-engine, and local integration tests
- Phase 6 and supporting Phase 2/4/5 documentation

The boundaries remain coherent: Auth verifies identity; repositories own
persistence; the student service orchestrates; rules and progress engines are
pure; routes map HTTP only.

## 3. Auth findings

Every `/api/v1/me/*` operation depends on `get_current_user`. Bearer tokens are
verified by local Supabase Auth at `/auth/v1/user`; no local JWT decoding or
user-controlled identity claim is used. Auth user IDs are parsed and rendered
as canonical UUID text. Missing, malformed, invalid, timed-out, and malformed
Auth responses map to 401 without returning credentials.

The server credential remains a `SecretStr`, is used only by server-side Auth
and Data API clients, and is absent from application logging and error bodies.
No application logger or credential/debug print exists.

## 4. Ownership findings

The database enforces one profile per Auth user. Self-service request schemas
do not contain `owner_user_id`. Profile reads, updates, and deletes filter on
the verified owner. Attempt creation first resolves that owner's profile;
attempt updates/deletes filter by both the owner's profile ID and attempt ID.
A foreign attempt is returned as missing rather than disclosing existence.

The API does not expose profile IDs as mutation selectors. `study_plan_id` is
accepted only on profile creation and is absent from the update contract.
Deleting a profile cascades its attempts while catalog FKs remain restrictive.

## 5. Database findings

`supabase db reset --local --no-seed` rebuilt the database from zero and
successfully applied all five existing migrations in order. The local database
linter reported no schema errors.

Canonical post-reset counts:

| Invariant | Result |
| --- | ---: |
| Plan 12 total credits | 132 |
| Requirement groups | 6 |
| Study-plan courses | 68 |
| Courses | 74 |
| Known courses | 68 |
| Referenced-only courses | 6 |
| Dependency groups/options | 32 / 32 |
| Equivalencies | 0 |
| Prerequisite statuses | 30 not-applicable, 32 verified, 4 unresolved, 2 source-conflict |

The audit and E2E did not mutate these canonical facts.

## 6. Attempt-history findings

The persisted enum is exactly `PASSED`, `FAILED`, `IN_PROGRESS`, and
`WITHDRAWN`. Repeat rows are allowed and retained; deterministic reads order by
`created_at`, then ID. Raw grade text is evidence only. Course identity is not
part of the update contract. Course codes remain exact strings, including
leading zeroes, and no unknown course is created.

Course resolution follows owner -> profile -> plan -> university -> exact
course code. Same-university known and referenced-only courses are accepted;
unknown and cross-university courses have distinct failures. No fuzzy, name,
normalized, equivalency, or substitution matching exists.

## 7. Eligibility findings

Persisted attempts map losslessly to the unchanged Phase 5
`StudentCourseAttempt` contract. Real local scenarios passed:

- `1501110 PASSED` -> `1501112 ELIGIBLE`
- `1501110 FAILED` or no attempt -> `NOT_ELIGIBLE`
- failed then passed, passed then failed -> `ELIGIBLE`
- `1505311` and `1505320` -> `REVIEW_REQUIRED`
- `0200115` -> `ELIGIBLE`
- target `0300103` -> target-not-in-plan
- unknown target -> target-not-found

Unresolved and source-conflict rules remain unresolved/conflicted. Raw
prerequisite text is preserved as evidence and never parsed. Infrastructure
failures remain errors rather than academic `REVIEW_REQUIRED` decisions.

## 8. Progress findings

Course-state priority remains any pass, then any in-progress, then
failed/withdrawn history, then no attempt. The output states are `COMPLETED`,
`IN_PROGRESS`, `ATTEMPTED_NOT_COMPLETED`, and `NOT_ATTEMPTED`. Mixed histories,
repeat passes, row-order changes, and no-attempt cases pass pure tests.

Completed credit counts each plan course once. Failed/withdrawn attempts earn
nothing; in-progress credits remain separate. Referenced-only history outside
the selected plan does not enter the plan universe. Group credits and overall
credits are capped, and remaining credits cannot be negative.

## 9. Required/elective accounting

Required groups need both the persisted credit target and every listed course.
Elective groups need only their persisted credit target. Excess elective
completion remains visible as completed listed credits but is capped when
credited toward the requirement. Real Plan 12 data verifies University
Elective as 9 required from 33 listed credits and Major Elective as 9 required
from 39 listed credits.

## 10. Zero-credit behavior

`0200115` and `1509999` both appear in progress with zero credits and belong to
required groups. Each still participates in mandatory-course completion. A
required group whose positive-credit target is met remains unsatisfied while
its zero-credit required course is incomplete.

## 11. Reported vs derived facts

Reported GPA, GPA scale, and earned credits are stored and passed through
unchanged. They never drive outcome, eligibility, or plan-credit derivation.
Derived course states, group satisfaction, completed plan credits, and
remaining credits do not overwrite reported values and are not required to
match them.

## 12. API contract and HTTP findings

Profile CRUD, attempt CRUD, profile-backed eligibility, and academic progress
remain authenticated self-service contracts. The legacy request-backed
eligibility endpoint remains separate. Profile-backed eligibility accepts no
history or plan input; progress accepts no owner, plan, or attempt input.

Mappings remain intentional: auth 401; missing resources 404; duplicate
profile, target-outside-plan, and cross-university conflicts 409; invalid
request values 422; integrity 500; transport/configuration 503; academic
decisions 200.

One defect was found: whitespace-only optional term/raw-grade text passed
Pydantic, failed the database nonblank constraint, and surfaced as 503. The
request models now reject empty/whitespace-only optional attempt text as 422.
Create and update regressions cover both fields and both blank forms. No schema
change was needed.

## 13. RLS findings

Both student tables have RLS enabled and exactly eight accepted ownership
policies. `authenticated` has the intended eight table privileges across the
two tables; `anon` has none. Policies use `auth.uid()` ownership predicates,
including `USING` and `WITH CHECK` for updates.

The local E2E proved User A can read their profile/history, User B sees no User
A profile or attempt and cannot update the attempt, and anon cannot access
student tables. API-level User B operations return not-found.

## 14. Consolidated local E2E

The clean-database E2E created and authenticated User A, created/read a Plan 12
profile, stored failed then passed `1501110`, observed `NOT_ELIGIBLE` then
`ELIGIBLE`, stored exact referenced-only `0300103`, confirmed it contributes no
plan credit, confirmed repeats count once, updated reported facts, and observed
them unchanged in progress. It created User B and verified API and direct-RLS
isolation, deleted the mistaken failure, deleted User A's profile, verified the
attempt cascade, and deleted both Auth users.

## 15. Determinism

Repeated identical local eligibility and progress calls returned equal JSON.
Pure engines have no clock, randomness, network, framework, or AI dependency.
Repositories specify stable ordering, and the progress engine applies explicit
persisted-order and identity/code tie-breakers.

## 16. OpenAPI

`/docs` and `/openapi.json` respond successfully. OpenAPI contains all student
operations, bearer security, strict textual course codes, exact attempt and
progress enums, nested progress schemas, and a parameter-free progress
operation. No self-service request schema contains `owner_user_id`.

## 17. Security and duplication audit

The tracked tree contains no `.env`, private key, hardcoded real token, or
hardcoded server secret. The `.env.example` contains empty placeholders only.
Searches found no token/header logging or debug prints. Tests use synthetic
fixtures or process-local credentials obtained from local CLI status.

Prerequisite satisfaction has one implementation in the rules evaluator;
course-state collapsing and credit capping have one implementation in the
progress engine; exact course resolution has one implementation in the student
repository. Ownership is intentionally enforced in both repository filters and
RLS as defense in depth, not duplicated academic logic.

Current Supabase guidance was reviewed. It confirms that grants determine
object reachability while RLS determines row visibility. No relevant current
breaking change required a Phase 6 code or migration change.

## 18. Test and tooling results

- Focused Phase 6 audit suite before the fix: 77 passed.
- Focused fix regression suite: 62 passed.
- Consolidated local E2E: passed.
- Normal isolated suite: 180 passed, 8 local-only tests skipped.
- Full suite with all local integrations enabled: 188 passed.
- Database lint: no schema errors.
- Python compilation: included in final validation and passed.
- OpenAPI assertions: passed.
- `git diff --check`: included in final validation and passed.

Only upstream deprecation warnings from the FastAPI/Starlette test stack and a
non-functional pytest cache warning appeared; no test or lint failure remains.

## 19. Clean database replay and cleanup

The full migration chain replayed without seed.sql or remote access. Before the
E2E, Auth users, profiles, and attempts were zero. Test cleanup is verified
again after all local runs; no audit-created user data remains. Canonical
catalog data is retained.

## 20. Known limitations

- No official GPA calculation engine
- No transfer-credit, equivalency, or substitution model
- No full institutional registration-permission engine
- Unresolved prerequisites remain unresolved
- Source conflicts remain conflicts
- Derived academic progress is not official graduation clearance
- Reported earned credits may differ from derived plan credits
- No recommendations, ranking, semester planning, graduation prediction, or AI

## 21. Final acceptance checklist

- [x] Clean migration replay and database lint
- [x] Canonical catalog invariants unchanged
- [x] Auth boundary and normalized verified identity
- [x] Profile and attempt ownership, CRUD, and cascade
- [x] Exact course resolution and repeated-attempt preservation
- [x] Phase 5 compatibility and raw-prerequisite safety
- [x] Progress states, caps, required/elective behavior, and zero-credit rules
- [x] Reported/derived separation
- [x] Eight RLS policies and owner/User B/anon behavior
- [x] Consolidated authenticated local E2E and determinism
- [x] OpenAPI and HTTP mapping
- [x] Security and duplicated-logic searches
- [x] Normal and all-local test suites
- [x] No temporary data, remote access, schema migration, commit, or push

Phase 6 is accepted as a coherent Student Academic Foundation. This conclusion
does not authorize or begin Phase 7.
