# Academic Digital Twin and What-If V1 Test Matrix

Policy version: **1.0**. P5.1 defines tests only; no test code is authorized.

| ID | Scenario | Required assertion |
|---|---|---|
| `TWIN-T01` | Empty/no-attempt state | Valid authoritative snapshot; deterministic outputs; no invented history. |
| `TWIN-T02` | Hypothetical pass required course | Dedicated modeled completion; base unchanged; Phase 5/6 downstream recomputed. |
| `TWIN-T03` | Hypothetical pass elective with remaining need | Elective cap respected; completion affects only modeled state. |
| `TWIN-T04` | Pass already completed course | Scenario `INVALID`; no duplicate completion or delta. |
| `TWIN-T05` | Pass unknown course | `INVALID` + `TWIN_UNKNOWN_COURSE`. |
| `TWIN-T06` | Zero-credit pass | Requirement/dependency delta may occur with zero credit delta. |
| `TWIN-T07` | Referenced-only completion target | `INVALID` + target-not-plan-member; no progress dimension created. |
| `TWIN-T08` | Source-conflict target | Scenario `REVIEW_REQUIRED`; modeled completion is not applied and no relation is inferred. |
| `TWIN-T09` | Unresolved material dependency | Affected facet/scenario `REVIEW_REQUIRED`; independent facts retained. |
| `TWIN-T10` | Current `IN_PROGRESS` completion target | `INVALID`; authoritative in-progress remains unchanged. |
| `TWIN-T11` | Failed history plus modeled pass | Failures retained as authoritative; modeled pass separate; no recovery/strength evidence created. |
| `TWIN-T12` | Delay direct dependency | Existing P4 direct-impact result/codes reproduced. |
| `TWIN-T13` | Delay transitive dependency | Existing cycle-safe canonical depth/path reproduced. |
| `TWIN-T14` | Delay OR alternative | Satisfied alternative prevents false direct impact. |
| `TWIN-T15` | Delay elective substitute | Existing eligible substitute preserves requirement progress. |
| `TWIN-T16` | Constraint 12 → 15 credits | Phase 8/9 rerun within exact bounds; result labeled user preference. |
| `TWIN-T17` | Invalid constraint | Entire scenario `INVALID`; value not clamped. |
| `TWIN-T18` | Baseline vs scenario identical | Empty delta tuple and explicit factual equality; no score/winner. |
| `TWIN-T19` | Baseline vs scenario changed | Closed deltas contain exact base/modeled values and owning engines. |
| `TWIN-T20` | Scenario A vs scenario B | Same-base/version pair compares deterministically in caller order. |
| `TWIN-T21` | Cross-base scenario comparison | Comparison rejected even for the same student/plan. |
| `TWIN-T22` | Raw grade unchanged | Raw values are neither read nor emitted; base payload remains equal. |
| `TWIN-T23` | Predictive risk requested | Remains `BLOCKED_BY_EXTERNAL_DATA`; no probability or score. |
| `TWIN-T24` | Modeled path changes | Exact Phase 9/P4 safe metrics and non-predictive wording returned. |
| `TWIN-T25` | Modeled path unchanged | Explicit unchanged delta; no hidden “better” conclusion. |
| `TWIN-T26` | Determinism | Five identical evaluations are byte-equivalent. |
| `TWIN-T27` | Input reorder | Reordered attempts/catalog/evidence/operations yield canonical identical output. |
| `TWIN-T28` | Authoritative-state immutability | Deep equality and object-level mutation guards pass before/after every engine. |
| `TWIN-T29` | Operation conflict | Completion plus omission is rejected atomically. |
| `TWIN-T30` | Duplicate operation | Duplicate completion/constraint operation rejected. |
| `TWIN-T31` | Too many structural operations | Scenario rejected; no arbitrary sequencing. |
| `TWIN-T32` | Stale base state | Fingerprint mismatch returns `STALE_BASE_STATE`; no silent rebasing. |
| `TWIN-T33` | Fingerprint privacy | Digest source excludes PII/raw grades and is stable under irrelevant field changes. |
| `TWIN-T34` | Multi-plan fixture | Same contract works on two plans; no identifier/cache/result leakage. |
| `TWIN-T35` | Sandbox provider fixture | Synthetic provenance is visible; domain behavior matches real-provider contract. |
| `TWIN-T36` | Plan identity mismatch | Scenario rejected before engine invocation. |
| `TWIN-T37` | Zero operations | Scenario invalid; baseline retrieval is not a What-If operation. |
| `TWIN-T38` | One structural + constraint bundle | Canonical order validates constraints, applies structural overlay, then recomputes. |
| `TWIN-T39` | Current `IN_PROGRESS` downstream | No assumed pass; path remains conservatively blocked where applicable. |
| `TWIN-T40` | History-based readiness | Modeled pass never becomes preparation/recovery evidence; affected readiness factor abstains. |
| `TWIN-T41` | P4 hard-gate invariance | No intelligence factor makes a non-eligible course eligible. |
| `TWIN-T42` | Delay context missing Phase 9 | Structural delay succeeds; path comparison explicitly unavailable. |
| `TWIN-T43` | Equivalency operation | Hypothetical equivalency is forbidden; no name/code inference. |
| `TWIN-T44` | Course availability wording | Omission never claims course is or is not offered. |
| `TWIN-T45` | Graduation wording | Registration-set count never becomes a graduation/calendar promise. |
| `TWIN-T46` | Authorization | Foreign student base/scenario reference rejected before evaluation/comparison. |
| `TWIN-T47` | Privacy output | No raw grade, PII, credential, prompt, source payload, or protected attribute. |
| `TWIN-T48` | Computational bounds | Operation, comparison, Phase 8, and Phase 9 limits enforced. |
| `TWIN-T49` | No writes | No repository/database/cache/API/LLM call or persisted scenario side effect. |
| `TWIN-T50` | Engine reuse/purity | No duplicated prerequisite, progress, ranking, planner, path, P3, or delay logic. |
| `TWIN-T51` | Pass eligible, incomplete elective whose requirement group is already satisfied | Scenario `INVALID` + `TWIN_ELECTIVE_GROUP_ALREADY_SATISFIED`; operation rejected; no modeled completion, engine recomputation, or delta; authoritative state unchanged; Phase 5 eligibility unchanged. |

## Required regression gates for P5.2

P5.2 must add focused contract/golden tests, the full matrix above, Phase 5–9/P3/P4 regressions, mutation/purity scans, deterministic permutation tests, and performance tests bounded by the inherited Phase 8/9 limits. It must demonstrate identical behavior on normalized Sandbox University and multi-plan fixtures without Plan 12 hardcoding.
