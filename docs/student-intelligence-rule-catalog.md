# Student Intelligence V1 Rule Catalog

Policy version: 1.0. Conditions are conceptual only; no implementation is authorized.

| Rule ID | Capability | Rule name | Inputs / authority | Condition | Output / reason | Evidence | Missing behavior | PROP |
|---|---|---|---|---|---|---|---|---|
| PERF-001 | Performance | Attempt outcome distribution | Explicit outcomes; non-UNVERIFIED | Any attempts | factual counts / `PERF_OUTCOME_DISTRIBUTION` | ATTEMPT_OUTCOME | NO_ATTEMPT_HISTORY | 007,078 |
| PERF-002 | Performance | Repeat history | course attempts | same course has >1 attempts | factual repeat count / `PERF_REPEAT_HISTORY` | COURSE_ATTEMPT | NO_ATTEMPT_HISTORY | 007,078 |
| PERF-003 | Performance | Fail-to-pass recovery | course attempts | FAILED precedes PASSED in recorded history, no temporal claim | recovery observation / `PERF_FAIL_PASS_RECOVERY` | COURSE_ATTEMPT | NO_ATTEMPT_HISTORY | 007,078 |
| PERF-004 | Performance | Repeated failure history | course attempts | >=2 FAILED for same course | factual pattern / `PERF_REPEATED_FAILURE` | ATTEMPT_OUTCOME | NO_ATTEMPT_HISTORY | 007,078 |
| PERF-005 | Performance | Requirement completion | progress | modeled group/course state | factual completion / `PERF_REQUIREMENT_COMPLETION` | REQUIREMENT_PROGRESS | INSUFFICIENT_DATA | 078 |
| PERF-006 | Performance | Dependency exposure | eligibility/progress | modeled required course blocked | factual exposure / `PERF_DEPENDENCY_EXPOSURE` | ELIGIBILITY_RESULT | REVIEW_REQUIRED | 078 |
| STRENGTH-001 | Strength | Successful required completion | modeled progress | required completion evidence exists | evidence observation / `STRENGTH_REQUIRED_COMPLETION` | REQUIREMENT_PROGRESS | INSUFFICIENT_DATA | 011 |
| STRENGTH-002 | Strength | Recovery evidence | PERF-003 | recovery exists | evidence observation / `STRENGTH_RECOVERY_EVIDENCE` | COURSE_ATTEMPT | INSUFFICIENT_DATA | 011 |
| DIFFICULTY-001 | Difficulty | Repeated course failure | PERF-004 | repeated failures | signal / `DIFFICULTY_REPEATED_FAILURE` | ATTEMPT_OUTCOME | INSUFFICIENT_DATA | 012 |
| DIFFICULTY-002 | Difficulty | Repeated required withdrawal | attempts + plan membership | >=2 withdrawals in required course | signal / `DIFFICULTY_REPEATED_WITHDRAWAL` | COURSE_ATTEMPT | INSUFFICIENT_DATA | 012 |
| DIFFICULTY-003 | Difficulty | Required bottleneck | verified eligibility | required course structurally blocked | signal / `DIFFICULTY_REQUIRED_BOTTLENECK` | ELIGIBILITY_RESULT | REVIEW_REQUIRED | 012 |
| READINESS-001 | Readiness | Preparation evidence | verified target eligibility/history | eligible and passed prerequisite evidence | PREPARATION_EVIDENCE_AVAILABLE / `READINESS_PREREQUISITES_COMPLETED` | ELIGIBILITY_RESULT | REVIEW_REQUIRED | 014 |
| READINESS-002 | Readiness | Caution evidence | target prerequisite history | eligible with failed/repeated prerequisite history | CAUTION_EVIDENCE_AVAILABLE / `READINESS_PREREQUISITE_DIFFICULTY` | COURSE_ATTEMPT | INSUFFICIENT_DATA | 014 |
| READINESS-003 | Readiness | In-progress context | target prerequisite history | prerequisite IN_PROGRESS | CAUTION_EVIDENCE_AVAILABLE / `READINESS_PREREQUISITE_IN_PROGRESS` | ATTEMPT_OUTCOME | INSUFFICIENT_DATA | 014 |
| READINESS-004 | Readiness | No target prerequisite | verified rule | eligible course has no prerequisites | NOT_APPLICABLE / `READINESS_NO_PREREQUISITES` | COURSE_DEPENDENCY | REVIEW_REQUIRED | 014 |
| READINESS-005 | Readiness | Ambiguous target rule | Phase 5 status | unresolved/source conflict | REVIEW_REQUIRED / `READINESS_RULE_REVIEW_REQUIRED` | ELIGIBILITY_RESULT | REVIEW_REQUIRED | 014 |
| STRUCTURAL_RISK-001 | Structural risk | Mandatory repeated failure | DIFFICULTY-001 + required membership | repeated failure required course | warning / `STRUCTURAL_RISK_REQUIRED_REPEAT_FAILURE` | COURSE_ATTEMPT | INSUFFICIENT_DATA | 013 |
| STRUCTURAL_RISK-002 | Structural risk | Required bottleneck | DIFFICULTY-003 | blocked required course | warning / `STRUCTURAL_RISK_REQUIRED_BOTTLENECK` | ELIGIBILITY_RESULT | REVIEW_REQUIRED | 013 |
| STRUCTURAL_RISK-003 | Structural risk | Concentrated blockage | verified dependency graph | one prerequisite blocks multiple required courses | warning / `STRUCTURAL_RISK_CONCENTRATED_DEPENDENCY` | COURSE_DEPENDENCY | REVIEW_REQUIRED | 013 |

No V1 domain-strength, grade-interpretation, trend, GPA, predictive-risk, cohort, personality, or overall-score rule exists.
