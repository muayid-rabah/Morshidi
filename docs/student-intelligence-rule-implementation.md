# Student Intelligence Rule Implementation Traceability

Policy version: 1.0. All 19 catalog rules are implemented and tested in `test_student_intelligence.py`.

| Rule | Module/function | Reason code | Evidence | Status |
|---|---|---|---|---|
| PERF-001 | observations/evaluate_performance | PERF_OUTCOME_DISTRIBUTION | ATTEMPT_OUTCOME | IMPLEMENTED |
| PERF-002 | observations/evaluate_performance | PERF_REPEAT_HISTORY | COURSE_ATTEMPT | IMPLEMENTED |
| PERF-003 | observations/evaluate_performance | PERF_FAIL_PASS_RECOVERY | COURSE_ATTEMPT | IMPLEMENTED |
| PERF-004 | observations/evaluate_performance | PERF_REPEATED_FAILURE | ATTEMPT_OUTCOME | IMPLEMENTED |
| PERF-005 | observations/evaluate_performance | PERF_REQUIREMENT_COMPLETION | REQUIREMENT_PROGRESS | IMPLEMENTED |
| PERF-006 | observations/evaluate_performance | PERF_DEPENDENCY_EXPOSURE | ELIGIBILITY_RESULT | IMPLEMENTED |
| STRENGTH-001 | strengths/evaluate_strengths | STRENGTH_REQUIRED_COMPLETION | REQUIREMENT_PROGRESS | IMPLEMENTED |
| STRENGTH-002 | strengths/evaluate_strengths | STRENGTH_RECOVERY_EVIDENCE | COURSE_ATTEMPT | IMPLEMENTED |
| DIFFICULTY-001 | difficulty/evaluate_difficulty | DIFFICULTY_REPEATED_FAILURE | ATTEMPT_OUTCOME | IMPLEMENTED |
| DIFFICULTY-002 | difficulty/evaluate_difficulty | DIFFICULTY_REPEATED_WITHDRAWAL | COURSE_ATTEMPT | IMPLEMENTED |
| DIFFICULTY-003 | difficulty/evaluate_difficulty | DIFFICULTY_REQUIRED_BOTTLENECK | ELIGIBILITY_RESULT | IMPLEMENTED |
| READINESS-001 | readiness/evaluate_readiness | READINESS_PREREQUISITES_COMPLETED | ELIGIBILITY_RESULT | IMPLEMENTED |
| READINESS-002 | readiness/evaluate_readiness | READINESS_PREREQUISITE_DIFFICULTY | COURSE_ATTEMPT | IMPLEMENTED |
| READINESS-003 | readiness/evaluate_readiness | READINESS_PREREQUISITE_IN_PROGRESS | ATTEMPT_OUTCOME | IMPLEMENTED |
| READINESS-004 | readiness/evaluate_readiness | READINESS_NO_PREREQUISITES | COURSE_DEPENDENCY | IMPLEMENTED |
| READINESS-005 | readiness/evaluate_readiness | READINESS_RULE_REVIEW_REQUIRED | ELIGIBILITY_RESULT | IMPLEMENTED |
| STRUCTURAL_RISK-001 | structural_risk/evaluate_structural_risk | STRUCTURAL_RISK_REQUIRED_REPEAT_FAILURE | COURSE_ATTEMPT | IMPLEMENTED |
| STRUCTURAL_RISK-002 | structural_risk/evaluate_structural_risk | STRUCTURAL_RISK_REQUIRED_BOTTLENECK | ELIGIBILITY_RESULT | IMPLEMENTED |
| STRUCTURAL_RISK-003 | structural_risk/evaluate_structural_risk | STRUCTURAL_RISK_CONCENTRATED_DEPENDENCY | COURSE_DEPENDENCY | IMPLEMENTED |

Focused coverage includes positive/negative/abstention paths, all repeated-attempt cases, all readiness matrix states, provenance, grade invariance, source conflicts, zero-credit, referenced-only, predictive blocking, deterministic input permutations, and empty/partial data.
