# Mock Registration Concurrency Matrix

Policy version: **1.0**. `expected_current_revision` plus serialized compare-and-insert and database uniqueness form the V1 concurrency contract.

| Case | Client Expectation | Transaction Behavior | Winner / Stored State | API Result | Retry Rule |
|---|---|---|---|---|---|
| First submission | `expected_current_revision = null` | Serialize exact logical key; confirm none; assign revision 1 | One complete revision 1 | `201 Created` | Identical retry returns original 201/representation. |
| Normal next revision | Expected equals current `N` | Lock/serialize key; recheck; assign `N+1`; atomically insert | New immutable current candidate | `201 Created` | Safe identical replay. |
| Same revision, same fingerprint retry | Prior response uncertain | Unique key finds same fingerprint | Existing logical revision only | Original success representation; no duplicate | Retry is idempotent. |
| Same revision, different fingerprint | Content differs for occupied key/revision | Compare fingerprint; reject | Existing revision unchanged | `409 REVISION_CONFLICT` | Reload; submit new CAS command. |
| Stale expected revision | Expected `N`, server current differs | Reject before insert | No change | `409 REVISION_CONFLICT` | Read current, obtain user confirmation, retry. |
| Two concurrent writers | Both expect same `N` | Exact-key serialization/unique revision permits one `N+1` commit | First transaction winner only | Winner 201/202; loser 409 | Loser must not auto-merge. |
| Withdraw vs submit race | Both expect same current | Same CAS serialization | Exactly one next revision | Winner success; loser 409 | Reload; explicit student decision required. |
| Duplicate network request | Same command delivered twice | First commits; second matches key/fingerprint | One revision/header/course set | Same success representation | No separate idempotency key in V1. |
| Database unique conflict | Constraint races transaction | Repository classifies same fingerprint as replay, otherwise conflict | No duplicate/overwrite | Success replay or `409 PERSISTENCE_CONFLICT` | Never return 500 for expected concurrency. |
| Child insertion failure | Header or one child fails | Whole transaction rolls back | No header and no children | `503 PERSISTENCE_UNAVAILABLE` or safe mapped integrity error | Retry whole command only. |
| Academic state changes before commit | Validation version token differs at CAS | Abort transaction | No revision | `409 ACADEMIC_STATE_CHANGED` | Reload/revalidate and reconfirm. |
| REVIEW_REQUIRED concurrent retry | Same review content | Same immutable/CAS/idempotency behavior | One review-required revision | `202 REVIEW_REQUIRED` | Never enter valid demand. |

Timestamps, request arrival order outside the transaction, database row order, and client-proposed next revision never determine current state.

