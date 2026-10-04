# Mock Registration and Institutional Demand V1 Test Matrix

Policy version: **1.0**. P6.1 defines **64** deterministic scenarios; it authorizes no test code.

| ID | Scenario | Required assertion |
|---|---|---|
| `P6-T01` | Eligible required course | Intent `VALID`; exact Phase 5 evidence retained. |
| `P6-T02` | Eligible elective with remaining need | Intent `VALID`; exact plan/group identity retained. |
| `P6-T03` | Eligible zero-credit required course | Valid; counts as selection/owner and adds zero declared credits. |
| `P6-T04` | Already passed target | Whole intent `INVALID` + `MOCK_REG_TARGET_ALREADY_COMPLETED`. |
| `P6-T05` | Current in-progress target | Whole intent `INVALID` + `MOCK_REG_TARGET_IN_PROGRESS`. |
| `P6-T06` | Failed history, currently eligible | Valid without special failure/retake inference. |
| `P6-T07` | Withdrawn history, currently eligible | Valid under current Phase 5 decision only. |
| `P6-T08` | Phase 5 not eligible | Whole intent invalid; no demand contribution. |
| `P6-T09` | Eligibility review required | Whole intent review-required; excluded from valid demand. |
| `P6-T10` | Source-conflict target | Review evidence preserved; no inferred result. |
| `P6-T11` | Unknown course | Invalid with exact unknown-course code. |
| `P6-T12` | Referenced-only course | Invalid target-not-plan-member; remains evidence only. |
| `P6-T13` | Satisfied elective group | Invalid with Mock Registration-specific elective-group code; Phase 5 unchanged. |
| `P6-T14` | Duplicate course input | Whole intent invalid; duplicates never inflate demand. |
| `P6-T15` | Same unique set reordered | Canonical courses/fingerprint/result identical. |
| `P6-T16` | Submitted empty intent | Invalid empty-course-set. |
| `P6-T17` | Explicit withdrawal empty set | Valid withdrawal lifecycle; no current demand. |
| `P6-T18` | Invalid university/major/plan | Rejected before course evaluation. |
| `P6-T19` | Wrong plan version | Rejected without transition inference. |
| `P6-T20` | Invalid/blank period | Rejected; no official term invented. |
| `P6-T21` | Declared planning period | Accepted but never labeled official. |
| `P6-T22` | Synthetic Sandbox period | Accepted with visible synthetic provenance. |
| `P6-T23` | Verified official period reference | Accepted only with provider/source version. |
| `P6-T24` | Course-count bound | 10 accepted; 11 rejected without truncation. |
| `P6-T25` | Credit safety bound | 30.00 accepted; above rejected without official-limit claim. |
| `P6-T26` | Same-set prerequisite chaining attempt | Each course validates against current state; no co-registration inference. |
| `P6-T27` | Missing offering data | Valid intent allowed with unavailable flag; no “not offered” claim. |
| `P6-T28` | Missing capacity data | Valid intent allowed; capacity unavailable rather than zero. |
| `P6-T29` | Matching synthetic offering | Exact-period match labeled synthetic. |
| `P6-T30` | No matching supplied offering fact | Exact dataset absence reported without universal unavailability claim. |
| `P6-T31` | Matching synthetic capacity | Optional descriptive comparison labeled synthetic. |
| `P6-T32` | One higher revision | Higher valid revision is current; lower is superseded. |
| `P6-T33` | Equal revision/equal fingerprint | Idempotent single logical intent. |
| `P6-T34` | Equal revision/different fingerprint | Revision conflict; both excluded. |
| `P6-T35` | Lower revision arrives later | Still superseded; no timestamp/row-order precedence. |
| `P6-T36` | Explicit expired period state | Intent excluded without wall-clock inference. |
| `P6-T37` | Multiple courses one owner | One cohort owner; one owner per selected course. |
| `P6-T38` | Same course multiple owners | Course metric equals distinct valid owners. |
| `P6-T39` | Same owner repeated course/revision rows | Owner/course counted once after resolution/idempotency. |
| `P6-T40` | Superseded historical submission | Historical selections do not inflate current aggregate. |
| `P6-T41` | Withdrawn current revision | Owner contributes no current demand. |
| `P6-T42` | Invalid intent among valid intents | Invalid record excluded atomically; no partial courses counted. |
| `P6-T43` | Review-required intent among valid intents | Excluded from valid demand; optional separate review owner metric. |
| `P6-T44` | Review metric disabled | No review count exposed or merged. |
| `P6-T45` | Review metric enabled | Distinct owners counted separately and suppression applied. |
| `P6-T46` | Total declared selections | Equals distinct current owner/course pairs. |
| `P6-T47` | Total declared credit load | Sums exact plan credits only; zero-credit adds zero. |
| `P6-T48` | Requirement-group owner count | One owner counted once per group despite multiple selected courses. |
| `P6-T49` | Plan owner count | One owner counted once for exact plan/version/period. |
| `P6-T50` | Two plans share course | By-plan views separate; university course view deduplicates owner/course. |
| `P6-T51` | Two universities | Inputs/results isolated; mixed call rejected. |
| `P6-T52` | Two target periods | Periods isolated; no implicit longitudinal result. |
| `P6-T53` | Known valid-intent denominator | Course share uses exact valid-active-owner count and explicit label. |
| `P6-T54` | Unknown population denominator | Population percentage omitted; unknown-coverage flag emitted. |
| `P6-T55` | Known partial adoption | Observed counts retained with partial-coverage metadata. |
| `P6-T56` | Privacy threshold passed | Aggregate metrics exposed in canonical order. |
| `P6-T57` | Privacy threshold suppressed | Status `SUPPRESSED`; all values including exact small count withheld. |
| `P6-T58` | Capacity gap positive/zero/negative | Exact arithmetic only; no shortage or section recommendation. |
| `P6-T59` | No valid active intents | `INSUFFICIENT_DATA`, not inferred zero institutional demand. |
| `P6-T60` | Aggregation input reordered | Byte-equivalent logical result and canonical metric order. |
| `P6-T61` | Aggregation limit exceeded | Entire evaluation rejected; no truncation/partial aggregate. |
| `P6-T62` | Aggregate privacy fields | No owner IDs, selections, grades, attempts, Advisor data, or Digital Twin data. |
| `P6-T63` | No automatic planner/recommendation intent | Copy requires explicit confirmation and revalidation; no submission side effect. |
| `P6-T64` | No official mutation/forecast/ranking | No SIS write, attempt/progress change, forecast, student score, or institutional action. |

## P6.2 regression gates

P6.2 must automate all 64 scenarios plus exact enum/count locks, property/permutation tests, fingerprint privacy, nested immutability, multi-plan/multi-university isolation, Phase 5/6 reuse, Digital Twin separation, planner/recommendation no-auto-intent, P3/P4/Advisor isolation, computational bounds, and complete Phase 5–P6/P3/P4/Advisor regressions.
