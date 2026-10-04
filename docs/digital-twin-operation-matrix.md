# Digital Twin V1 Operation Matrix

Policy version: **1.0**. Operation IDs are stable and may not be reused with different semantics.

| Operation ID | Name | V1 status | Input | Validation | Effect | Engines recomputed | Authoritative state changed? | Modeled state changed? | External data required? | Reason codes | Failure behavior | Future dependency |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `TWIN_OP_MODEL_COURSE_COMPLETION` | Model course completion | `SUPPORTED_V1` | Exact course code | Same plan; known plan member; incomplete; not `IN_PROGRESS`; Phase 5 `ELIGIBLE`; no material conflict | Adds one dedicated `ModeledCourseCompletion`; no grade/term | Phase 5, Phase 6, structural P3 context, Phase 7, P4, Phase 8, Phase 9 | No | Yes | No | `TWIN_MODELED_COMPLETION_APPLIED` | Entire scenario `INVALID` for invalid target; `REVIEW_REQUIRED` for material rule ambiguity | None for pure V1 |
| `TWIN_OP_OMIT_NEXT_PLAN_COURSE` | Omit course from next modeled plan | `SUPPORTED_V1` | Exact plan target | P4 Delay target/context rules; not contradictory with completion | Delegates to P4 Delay Consequence; omission is not offering/failure/withdrawal | P4 delay; Phase 6/9 only through P4's existing composition paths | No | Yes, as delayed comparison | No | Existing twelve `DELAY_*` codes plus `TWIN_DELAY_COMPOSED` | Preserve P4 `INSUFFICIENT_DATA`/`REVIEW_REQUIRED`; invalid identity invalidates scenario | Live offerings only for real availability claims |
| `TWIN_OP_SET_PLANNING_CONSTRAINTS` | Set planner/path constraints | `SUPPORTED_V1` | Typed Phase 8/9 constraint bundle | Exact existing ranges and types; no clamping | Re-evaluates modeled planner/path under user preference bounds | Phase 8 and/or Phase 9 plus required upstream calls owned by those engines | No | Yes, result only | No | `TWIN_CONSTRAINTS_APPLIED` | `INVALID` with `TWIN_INVALID_CONSTRAINT` | Institutional limits remain separate |
| `TWIN_OP_PREFER_ELECTIVE_OPTION` | Prefer/select elective | `DEFERRED` | Course and elective group | No existing Phase 8/9 preference/pinning policy | None in V1; preference must never imply pass | None | No | No | Approved preference policy | `TWIN_OPERATION_DEFERRED` | Reject as unsupported | Goal/preference policy |
| `TWIN_OP_MODEL_COURSE_FAILURE` | Model failure | `DEFERRED` | Course, timing/attempt context | Timing, registration, repeat, and grade semantics unavailable | None | None | No | No | Official repeat/attempt policy | `TWIN_OPERATION_DEFERRED` | Reject as unsupported | Verified attempt/repeat policy |
| `TWIN_OP_MODEL_COURSE_WITHDRAWAL` | Model withdrawal | `DEFERRED` | Course, timing/attempt context | Timing and registration state unavailable | None | None | No | No | Official withdrawal policy | `TWIN_OPERATION_DEFERRED` | Reject as unsupported | Verified withdrawal policy |
| `TWIN_OP_ASSUME_IN_PROGRESS_OUTCOME` | Resolve current in-progress | `DEFERRED` | Active course and assumed outcome | Conflicts with conservative Phase 9 semantics | None | None | No | No | Explicit future policy | `TWIN_OPERATION_DEFERRED` | Reject as unsupported | Versioned assumption policy |
| `TWIN_OP_EXCLUDE_UNAVAILABLE_COURSE` | Model course unavailable | `DEFERRED` | Course and offering snapshot | No live offering authority | None; V1 omission cannot claim unavailability | None | No | No | WC-037 offering provider | `TWIN_OPERATION_DEFERRED` | Reject as unsupported | Authoritative dated offerings |
| `TWIN_OP_CHANGE_MAJOR` | Change major | `DEFERRED` | Target major/plan | No transfer recognition policy | None | None | No | No | WC-027/028/031 | `TWIN_OPERATION_DEFERRED` | Reject as unsupported | Transfer/equivalency rules |
| `TWIN_OP_CHANGE_PLAN_VERSION` | Change study-plan version | `DEFERRED` | Target version | No official transition/grandfathering policy | None | None | No | No | WC-026/028/029 | `TWIN_OPERATION_DEFERRED` | Reject as unsupported | Version-transition policy |
| `TWIN_OP_CREATE_EQUIVALENCY` | Create hypothetical equivalency | `FORBIDDEN` | Any mapping | V1 cannot create academic authority | None | None | No | No | Not applicable | `TWIN_OPERATION_FORBIDDEN` | Reject entire scenario | Only verified official equivalencies may be consumed |
| `TWIN_OP_SET_GRADE_OR_GPA` | Set grade/GPA | `FORBIDDEN` | Grade value | Grade invention/interpretation prohibited | None | None | No | No | Not applicable | `TWIN_OPERATION_FORBIDDEN` | Reject entire scenario | Separate governed grade policy cannot retroactively make invention valid |
| `TWIN_OP_MUTATE_AUTHORITATIVE_RECORD` | Add/update/delete official record | `FORBIDDEN` | Record mutation | Violates no-write boundary | None | None | No | No | Not applicable | `TWIN_OPERATION_FORBIDDEN` | Reject and expose no mutation channel | Authoritative SIS transactions remain outside Digital Twin |
| `TWIN_OP_FORCE_ELIGIBILITY` | Override academic rule | `FORBIDDEN` | Target/decision | Violates Phase 5 hard gate | None | None | No | No | Not applicable | `TWIN_OPERATION_FORBIDDEN` | Reject entire scenario | No future scenario policy may bypass official rules |
| `TWIN_OP_OFFICIAL_REGISTER` | Register/add/drop course | `FORBIDDEN` | Registration intent/action | Digital Twin has no transaction authority | None | None | No | No | Institutional registration API | `TWIN_OPERATION_FORBIDDEN` | Reject; no side effect | Separate explicitly authorized transaction capability |

## Completion-target validation outcomes

| Target | Phase 5 | Requirement-group state | Scenario result | Validation code | Application | Engine recomputation | Deltas | Authoritative state | Modeled state |
|---|---|---|---|---|---|---|---|---|---|
| Incomplete plan-listed elective | `ELIGIBLE` | Already satisfied under current Phase 6 semantics | `INVALID` | `TWIN_ELECTIVE_GROUP_ALREADY_SATISFIED` | None; operation rejected | None | None | Unchanged | Not applied |

This outcome is specific to `TWIN_OP_MODEL_COURSE_COMPLETION`. It does not change the Phase 5 eligibility result: academic prerequisite eligibility and bounded Digital Twin operation validity are separate decisions. It is deterministic rather than an academic-source ambiguity, so it does not produce `REVIEW_REQUIRED`.

## Operation-set rules

- Maximum operations: two—one structural operation and one constraint bundle.
- Completion and omission for the same or different targets cannot coexist in V1 because only one structural operation is allowed.
- Duplicate operations and multiple constraint bundles are invalid.
- Constraints validate first; the single structural operation applies second; engine recomputation follows the fixed graph. This is canonical processing, not arbitrary user-defined sequencing.
- Any invalid/forbidden operation invalidates the complete scenario. No partial application exists.
