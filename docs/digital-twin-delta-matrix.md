# Digital Twin V1 Delta Matrix

Policy version: **1.0**. The registry contains exactly **16** delta types. Deltas compare preserved base values with modeled values; they do not overwrite either side.

| Delta type | Source engine | Meaning | Base value | Modeled value | Privacy | UI-safe wording | Limitations |
|---|---|---|---|---|---|---|---|
| `NEWLY_MODELED_ELIGIBLE` | Phase 5 | Target changes from non-eligible to eligible under modeled state | Exact base decision | Exact modeled decision | Course code and safe rule evidence only | “Becomes eligible in this modeled scenario.” | Not registration permission or offering evidence |
| `NO_LONGER_MODELED_ELIGIBLE` | Phase 5 | Eligible base target is not eligible in modeled state | Exact base decision | Exact modeled/review decision | Minimized dependency evidence | “Is no longer modeled eligible under this scenario.” | Review is not equivalent to ineligible |
| `NEWLY_MODELED_COMPLETED_REQUIREMENT` | Phase 6 | Requirement group changes to satisfied | Base group state | Modeled group state | Group code and aggregate credits | “This requirement becomes satisfied in the modeled state.” | Not official graduation clearance |
| `NO_LONGER_MODELED_SATISFIED_REQUIREMENT` | Phase 6 | A baseline-modeled satisfied group is unsatisfied on the compared branch | Base group state | Modeled group state | Group summary only | “This requirement is not satisfied in the compared modeled state.” | Normally arises in omission comparisons, never history rewrite |
| `COMPLETED_PLAN_CREDIT_DELTA` | Phase 6 | Difference in modeled completed plan credits | Decimal credits | Decimal credits | Aggregate only | “Modeled completed-plan credits change by Δ.” | Zero delta can still have structural effect |
| `REMAINING_PLAN_CREDIT_DELTA` | Phase 6 | Difference in modeled remaining plan credits | Decimal credits | Decimal credits | Aggregate only | “Modeled remaining-plan credits change by Δ.” | Derived plan value, not reported official credits |
| `RECOMMENDATION_MEMBERSHIP_CHANGE` | Phase 7/P4 | Candidate enters or leaves recommendation result | Stable code set | Stable code set | Course codes and safe reasons | “The modeled recommendation set changes.” | No offering/registration claim |
| `RECOMMENDATION_ORDER_CHANGE` | Phase 7/P4 | Relative order changes with retained ranks and trace | Base ranks | Modeled ranks | Safe categorical factor evidence | “The modeled ordering changes for these courses.” | No overall utility score; readiness must obey P4 |
| `MODELED_PLAN_CHANGE` | Phase 8 | Selected course set or permitted plan metric differs | Base plan option | Modeled plan option | Course codes and aggregates | “The modeled next registration set differs.” | Not an official schedule or registration |
| `MODELED_PATH_CHANGE` | Phase 9/P4 | Canonical path, termination, blocker, or equal-horizon progress differs | Base path facts | Modeled path facts | Minimized path facts | “The bounded modeled path differs.” | Non-global-optimal; no live offerings |
| `MODELED_REGISTRATION_SET_COUNT_DELTA` | Phase 9/P4 | Count difference when both paths are comparable and modeled-complete | Integer count | Integer count | Aggregate only | “The modeled path contains Δ more/fewer registration sets.” | Never translate to calendar semesters or graduation date |
| `NEWLY_MODELED_BLOCKED` | Phase 5/9/P4 | A verified modeled target/path becomes blocked | Base blocker set | Modeled blocker set | Safe codes/evidence | “A new modeled structural blocker appears.” | Structural, not predictive failure risk |
| `NEWLY_MODELED_UNLOCKED` | Phase 5/7/8/P4 | A verified target becomes newly eligible/unlocked | Base code set | Modeled code set | Course codes only where necessary | “These courses become structurally available in the model.” | Eligibility is not section availability |
| `STRUCTURAL_WARNING_CHANGE` | P3/P4 | Explanation-only structural warning set changes | Base warning codes | Modeled warning codes | No raw attempt/grade payload | “The modeled structural warnings differ.” | Not predictive risk; history-based signals are not regenerated from synthetic facts |
| `REVIEW_STATE_CHANGE` | Phase 5/P3/P4 | Review-required status appears/disappears for a facet | Base status/codes | Modeled status/codes | Safe review codes | “This modeled result requires academic review.” | Simulator never resolves the source conflict |
| `DELAY_CONSEQUENCE_CHANGE` | P4 Delay | Specialized delay result/facets differ | Base delay facts | Delayed scenario facts | P4 minimized evidence | “Omitting this course changes these modeled structural consequences.” | No real-term delay, offering, or graduation-date claim |

## Registry rules

Delta ordering follows the table. Each instance includes `delta_type`, `source_engine`, base and modeled references/values, affected stable identifiers, safe evidence references, source/policy versions, simulation provenance, and limitations. Unknown delta types are rejected. Presentation may localize wording but cannot derive new academic categories or a score.
