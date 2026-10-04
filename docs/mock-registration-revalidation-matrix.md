# Mock Registration Revalidation Matrix

This policy matrix defines how a persisted immutable mock-registration revision is evaluated against current authoritative facts. Revalidation never edits history, never treats elapsed wall-clock time as expiry authority, and never adds a metric to the P6.2 nine-metric registry.

| Case | Stored history changed? | Current demand eligible? | Revalidation required? | Result state / quality flag | Student action required? | Institutional aggregate behavior |
|---|---|---|---|---|---|---|
| No academic change | No | Yes, when the stored revision was `VALID` and the period remains eligible | Yes before aggregation; cached freshness is not assumed | `CURRENT_VALID`; freshness `COMPLETE` | No | Include through the ordinary P6.2 aggregation and suppression pipeline |
| Student passes an intended course | No | No for that revision | Yes | `CURRENT_INVALID` with the existing already-completed domain reason; freshness `COMPLETE` | Submit a new revision if the student still wishes to express intent for other courses | Exclude the revision from valid demand; do not rewrite or subtract from history |
| Student starts an intended course | No | No for that revision | Yes | `CURRENT_INVALID` with the existing in-progress domain reason; freshness `COMPLETE` | Submit a new revision if needed | Exclude the revision from valid demand |
| Prerequisite source changes | No | Only if revalidation against the new authoritative source still returns `VALID` | Yes | Current P6.1 validation status and reasons; freshness `COMPLETE`, or `STALE_REQUIRES_REVALIDATION` if the source is unavailable | Act only if the current result is not valid | Include only a newly `VALID` result; otherwise exclude, with review handling below |
| Study-plan version changes | No | No until validated against the current applicable plan scope | Yes | `STALE_REQUIRES_REVALIDATION` or current `INVALID`; freshness reflects completion | Submit a new revision under the current plan/version | Exclude the stale revision; never silently remap its courses |
| Target period closes | No | No | Yes, using explicit provider/institution period state | `EXPIRED`; freshness `COMPLETE` | Choose an eligible target period and submit a new revision | Exclude from current demand while retaining historical evidence |
| Validation policy version changes | No | Only if the current policy revalidation returns `VALID` | Yes | Current P6.1 result; freshness `COMPLETE`, or `STALE_REQUIRES_REVALIDATION` when evaluation cannot complete | Act only when the current result requires correction/review | Include only current-valid demand; retain the submitted policy version as history |
| Course removed from plan | No | No | Yes | `CURRENT_INVALID` with existing plan-scope reason, or stale if authoritative plan data is unavailable | Submit a new revision with current plan-scoped courses | Exclude from demand; no automatic substitution |
| Authoritative source conflict introduced | No | No as valid demand | Yes | `REVIEW_REQUIRED`; freshness `COMPLETE` | Review the ambiguity and submit a later revision when resolvable | Exclude from normal valid-demand metrics; it may affect only the already-defined P6.2 review metric |
| Authoritative source conflict resolved | No | Yes only if the fresh domain result is `VALID` | Yes | Current P6.1 result; freshness `COMPLETE` | None when valid; otherwise follow returned domain reasons | Include only when valid; otherwise apply invalid/review behavior |

## Revalidation contract

- Trigger revalidation before every institutional aggregation when academic state, study-plan/source version, validation-policy version, or explicit target-period state may have changed.
- Derive current eligibility from the immutable revision plus current authoritative inputs. The stored submission-time status remains evidence of what was accepted at submission.
- When an authoritative dependency cannot be loaded or evaluated, return `STALE_REQUIRES_REVALIDATION`, set aggregate freshness to `INCOMPLETE`, set `stale_records_excluded` to `true`, and exclude the affected record.
- Freshness metadata is service metadata, not a tenth institutional metric. The API does not expose the number or identity of excluded students.
