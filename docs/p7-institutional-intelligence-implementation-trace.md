# Phase P7.2 — Institutional Intelligence Implementation Trace

Trace version: **1.0**
Phase: **P7.2 — Institutional Intelligence Pure-Domain Engine**
Governing documents:
- `docs/institutional-intelligence-policy.md`
- `docs/institutional-capacity-pressure-policy.md`
- `docs/institutional-intelligence-signal-matrix.md`
- `docs/institutional-alert-matrix.md`
- `docs/institutional-intelligence-advisor-test-matrix.md`

---

## 1. Traceability Summary

All 55 test-matrix scenarios governing Phase P7.2 are fully implemented and verified in `apps/api/tests/test_institutional_intelligence.py`.

| Family | Matrix ID Range | Scenario Count | Pure-Domain Implementation Symbol | Test Function in `test_institutional_intelligence.py` | Status |
|---|---|---:|---|---|---|
| Demand & Capacity Pressure | `P7-TEST-CAP-001` .. `020` | 20 | `app.institutional_intelligence.capacity.evaluate_capacity_metrics` | `test_p7_test_cap_001` .. `020` | **VERIFIED** |
| Curricular Structure & Bottleneck | `P7-TEST-STR-001` .. `015` | 15 | `app.institutional_intelligence.structure.evaluate_structural_gateway` | `test_p7_test_str_001` .. `015` | **VERIFIED** |
| Privacy & Suppression Propagation | `P7-TEST-PRV-001` .. `012` | 12 | `app.institutional_intelligence.engine.evaluate_institutional_intelligence` | `test_p7_test_prv_001` .. `012` | **VERIFIED** |
| Institutional Alerts | `P7-TEST-ALT-001` .. `008` | 8 | `app.institutional_intelligence.alerts.evaluate_institutional_alerts` | `test_p7_test_alt_001` .. `008` | **VERIFIED** |
| **Total P7.2 Scenarios** | | **55** | | | **100% PASS** |

---

## 2. Demand & Capacity Pressure Trace (`P7-TEST-CAP-*`)

| Scenario ID | Test Name | Primary Implementation Symbol | Test Function | Result |
|---|---|---|---|---|
| `P7-TEST-CAP-001` | Verified offered course with missing capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_001_verified_offered_missing_capacity` | PASS |
| `P7-TEST-CAP-002` | Valid demand with verified capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_002_valid_demand_with_verified_capacity` | PASS |
| `P7-TEST-CAP-003` | Synthetic offered course with supplied capacity | `models.FactProvenance.SYNTHETIC_SANDBOX_FACT` | `test_p7_test_cap_003_synthetic_offered_with_supplied_capacity` | PASS |
| `P7-TEST-CAP-004` | Demand strictly less than capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_004_demand_strictly_less_than_capacity` | PASS |
| `P7-TEST-CAP-005` | Demand equal to capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_005_demand_equal_to_capacity` | PASS |
| `P7-TEST-CAP-006` | Demand exceeds capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_006_demand_exceeds_capacity` | PASS |
| `P7-TEST-CAP-007` | Verified zero capacity with positive demand | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_007_verified_zero_capacity_positive_demand` | PASS |
| `P7-TEST-CAP-008` | Zero demand with positive capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_008_zero_demand_with_positive_capacity` | PASS |
| `P7-TEST-CAP-009` | Verified not-offered course with missing capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_009_verified_not_offered_missing_capacity` | PASS |
| `P7-TEST-CAP-010` | Missing offering facts with missing capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_010_missing_offering_with_missing_capacity` | PASS |
| `P7-TEST-CAP-011` | Partial adoption coverage caveat | `engine.evaluate_institutional_intelligence` | `test_p7_test_cap_011_partial_adoption_coverage_caveat` | PASS |
| `P7-TEST-CAP-012` | Suppressed demand with missing capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_012_suppressed_demand_missing_capacity` | PASS |
| `P7-TEST-CAP-013` | Suppressed demand with positive capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_013_suppressed_demand_positive_capacity` | PASS |
| `P7-TEST-CAP-014` | Review-required intent owner volume | `engine.evaluate_institutional_intelligence` | `test_p7_test_cap_014_review_required_owner_volume` | PASS |
| `P7-TEST-CAP-015` | Zero-credit course demand & capacity | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_015_zero_credit_course_demand_and_capacity` | PASS |
| `P7-TEST-CAP-016` | Same course across two study plans | `engine.evaluate_institutional_intelligence` | `test_p7_test_cap_016_course_across_two_study_plans` | PASS |
| `P7-TEST-CAP-017` | Different target periods isolation | `engine.evaluate_institutional_intelligence` | `test_p7_test_cap_017_different_target_periods_isolation` | PASS |
| `P7-TEST-CAP-018` | Different universities isolation | `engine.evaluate_institutional_intelligence` | `test_p7_test_cap_018_different_universities_isolation` | PASS |
| `P7-TEST-CAP-019` | Capacity fact with study plan scope | `engine.evaluate_institutional_intelligence` | `test_p7_test_cap_019_capacity_fact_with_study_plan_scope` | PASS |
| `P7-TEST-CAP-020` | Empty demand population | `capacity.evaluate_capacity_metrics` | `test_p7_test_cap_020_empty_demand_population` | PASS |

---

## 3. Curricular Structure & Bottleneck Trace (`P7-TEST-STR-*`)

| Scenario ID | Test Name | Primary Implementation Symbol | Test Function | Result |
|---|---|---|---|---|
| `P7-TEST-STR-001` | Terminal elective course | `structure.evaluate_structural_gateway` | `test_p7_test_str_001_terminal_elective_course` | PASS |
| `P7-TEST-STR-002` | One downstream dependency | `structure.evaluate_structural_gateway` | `test_p7_test_str_002_one_downstream_dependency` | PASS |
| `P7-TEST-STR-003` | Required Supporting course with downstream dependency | `structure.evaluate_structural_gateway` | `test_p7_test_str_003_required_supporting_with_downstream` | PASS |
| `P7-TEST-STR-004` | Required Supporting course without downstream dependency | `structure.evaluate_structural_gateway` | `test_p7_test_str_004_required_supporting_without_downstream` | PASS |
| `P7-TEST-STR-005` | Deep transitive prerequisite chain | `structure.get_transitive_downstream_courses` | `test_p7_test_str_005_deep_transitive_prerequisite_chain` | PASS |
| `P7-TEST-STR-006` | Source conflict prerequisite | `structure.evaluate_structural_gateway` | `test_p7_test_str_006_source_conflict_prerequisite` | PASS |
| `P7-TEST-STR-007` | Required zero-credit course with downstream dependency | `structure.evaluate_structural_gateway` | `test_p7_test_str_007_zero_credit_course_with_downstream` | PASS |
| `P7-TEST-STR-008` | Required zero-credit course without downstream dependency | `structure.evaluate_structural_gateway` | `test_p7_test_str_008_zero_credit_course_without_downstream` | PASS |
| `P7-TEST-STR-009` | Structural status unchanged by demand suppression | `engine.evaluate_institutional_intelligence` | `test_p7_test_str_009_structural_status_immune_to_demand_suppression` | PASS |
| `P7-TEST-STR-010` | Structural status unchanged by missing capacity | `engine.evaluate_institutional_intelligence` | `test_p7_test_str_010_structural_status_immune_to_missing_capacity` | PASS |
| `P7-TEST-STR-011` | Elective course with downstream dependency | `structure.evaluate_structural_gateway` | `test_p7_test_str_011_elective_course_with_downstream_dependency` | PASS |
| `P7-TEST-STR-012` | Mandatory course with OR prerequisite alternative | `structure.compute_must_prerequisites` | `test_p7_test_str_012_mandatory_course_with_or_prerequisite_alternative` | PASS |
| `P7-TEST-STR-013` | Mandatory classification derived from plan semantics | `structure.is_course_individually_mandatory` | `test_p7_test_str_013_mandatory_classification_derived_from_plan_semantics` | PASS |
| `P7-TEST-STR-014` | Structural gateway with balanced capacity | `engine.evaluate_institutional_intelligence` | `test_p7_test_str_014_structural_gateway_with_balanced_capacity` | PASS |
| `P7-TEST-STR-015` | Multi-plan structural difference | `structure.evaluate_structural_gateway` | `test_p7_test_str_015_multi_plan_structural_difference` | PASS |
| — | Common-ancestor OR indispensable | `structure.compute_must_prerequisites` | `test_sound_boolean_common_ancestor_or_indispensable` | PASS |
| — | OR bypass non-indispensable | `structure.compute_must_prerequisites` | `test_sound_boolean_or_bypass_not_indispensable` | PASS |
| — | AND group indispensability | `structure.compute_must_prerequisites` | `test_sound_boolean_and_group_indispensability` | PASS |
| — | Elective gateway indispensability | `structure.evaluate_structural_gateway` | `test_elective_course_indispensable_to_mandatory_target_is_gateway` | PASS |
| — | Unrelated conflict localization | `structure.evaluate_structural_gateway` | `test_unrelated_prerequisite_source_conflict_does_not_poison_candidate` | PASS |
| — | Prerequisite cycle safety | `structure.detect_candidate_cycle` | `test_prerequisite_dependency_cycle_safety` | PASS |

---

## 4. Privacy & Suppression Propagation Trace (`P7-TEST-PRV-*`)

| Scenario ID | Test Name | Primary Implementation Symbol | Test Function | Result |
|---|---|---|---|---|
| `P7-TEST-PRV-001` | Demand below threshold $k$ | `engine.evaluate_institutional_intelligence` | `test_p7_test_prv_001_demand_below_threshold_suppressed` | PASS |
| `P7-TEST-PRV-002` | Suppression propagation to deficit | `capacity.evaluate_capacity_metrics` | `test_p7_test_prv_002_suppression_propagation_to_deficit` | PASS |
| `P7-TEST-PRV-003` | Suppression propagation to ratio | `capacity.evaluate_capacity_metrics` | `test_p7_test_prv_003_suppression_propagation_to_ratio` | PASS |
| `P7-TEST-PRV-004` | Suppression propagation to combined alert | `alerts.evaluate_institutional_alerts` | `test_p7_test_prv_004_suppression_propagation_to_combined_alert` | PASS |
| `P7-TEST-PRV-005` | Zero identity fields in schema | `models.InstitutionalIntelligenceResult` | `test_p7_test_prv_005_zero_identity_fields_in_schema` | PASS |
| `P7-TEST-PRV-006` | Review-required owner count suppression | `alerts.evaluate_institutional_alerts` | `test_p7_test_prv_006_review_required_owner_count_suppression` | PASS |
| `P7-TEST-PRV-007` | No raw bypass parameter | `models.InstitutionalIntelligenceInput` | `test_p7_test_prv_007_no_raw_bypass_parameter` | PASS |
| `P7-TEST-PRV-008` | Cross-filter subtraction mitigation | `engine.evaluate_institutional_intelligence` | `test_p7_test_prv_008_cross_filter_subtraction_mitigation` | PASS |
| `P7-TEST-PRV-009` | Multi-university tenant isolation | `engine.evaluate_institutional_intelligence` | `test_p7_test_prv_009_multi_university_tenant_isolation` | PASS |
| `P7-TEST-PRV-010` | Non-member user access | `models.InstitutionalIntelligenceResult` | `test_p7_test_prv_010_non_member_user_access_pure_domain_safety` | PASS |
| `P7-TEST-PRV-011` | Inactive analyst membership | `engine` | `test_p7_test_prv_011_inactive_analyst_membership_pure_domain_isolation` | PASS |
| `P7-TEST-PRV-012` | Minimum allowed threshold validation | `models.InstitutionalPrivacyConfiguration` | `test_p7_test_prv_012_minimum_allowed_threshold_validation` | PASS |

---

## 5. Institutional Alerts Trace (`P7-TEST-ALT-*`)

| Scenario ID | Test Name | Primary Implementation Symbol | Test Function | Result |
|---|---|---|---|---|
| `P7-TEST-ALT-001` | Capacity deficit present | `alerts.evaluate_institutional_alerts` | `test_p7_test_alt_001_capacity_deficit_detected` | PASS |
| `P7-TEST-ALT-002` | Zero capacity with demand | `alerts.evaluate_institutional_alerts` | `test_p7_test_alt_002_zero_capacity_with_demand` | PASS |
| `P7-TEST-ALT-003` | Structural bottleneck pressure | `alerts.evaluate_institutional_alerts` | `test_p7_test_alt_003_structural_bottleneck_pressure` | PASS |
| `P7-TEST-ALT-004` | Review volume present | `alerts.evaluate_institutional_alerts` | `test_p7_test_alt_004_review_volume_present` | PASS |
| `P7-TEST-ALT-005` | Verified offered course with missing capacity | `alerts.evaluate_institutional_alerts` | `test_p7_test_alt_005_verified_offered_with_missing_capacity` | PASS |
| `P7-TEST-ALT-006` | Missing offering with missing capacity | `alerts.evaluate_institutional_alerts` | `test_p7_test_alt_006_missing_offering_with_missing_capacity` | PASS |
| `P7-TEST-ALT-007` | Verified not-offered course with missing capacity | `alerts.evaluate_institutional_alerts` | `test_p7_test_alt_007_verified_not_offered_no_missing_capacity_alert` | PASS |
| `P7-TEST-ALT-008` | Suppressed count withholds alerts & zero side-effects | `alerts.evaluate_institutional_alerts` | `test_p7_test_alt_008_suppressed_count_withholds_alerts_and_zero_side_effects` | PASS |

---

## 6. Hardening & Edge-Case Trace (`P7.2.2 Hardening`)
## 6. Supplemental Implementation Tests (Hardening & Edge Cases)

| Scenario ID | Test Name | Primary Implementation Symbol | Test Function | Result |
|---|---|---|---|---|
| `P7-TEST-STR-016` | Conflict with verified OR bypass does not poison candidate | `structure.evaluate_structural_gateway` | `test_conflict_with_verified_or_bypass_does_not_poison_candidate` | PASS |
| `P7-TEST-STR-017` | Outcome-relevant conflict causes review required | `structure.evaluate_structural_gateway` | `test_outcome_relevant_conflict_causes_review_required` | PASS |
| `P7-TEST-STR-018` | Referenced-only course topology & mandatory role | `structure.evaluate_mandatory_role` & `structure.evaluate_structural_gateway` | `test_referenced_only_course_topology_and_mandatory_role` | PASS |
| `P7-TEST-STR-019` | Referenced-only course with source conflict | `structure.evaluate_structural_gateway` | `test_referenced_only_course_with_source_conflict` | PASS |
| `P7-TEST-DET-001` | Pure-domain deterministic reproducibility | `engine.evaluate_institutional_intelligence` | `test_deterministic_reproducibility` | PASS |
| `P7-TEST-DEM-001` | Missing demand metric evaluates to INSUFFICIENT_DATA | `engine.evaluate_institutional_intelligence` | `test_missing_demand_metric_evaluates_to_insufficient_data` | PASS |
| `P7-TEST-CAP-008` | Negative capacity fact validation | `models.CapacityFact` | `test_negative_capacity_fact_raises_value_error` | PASS |
These tests provide executable validation for boolean edge cases, provenance separation, and contract hardening without modifying the canonical 85-scenario acceptance matrix:

| Pytest Function Name | Scenario Description | Primary Implementation Symbol | Result |
|---|---|---|---|
| `test_conflict_with_verified_or_bypass_does_not_poison_candidate` | Conflict with verified OR bypass does not poison candidate | `structure.evaluate_structural_gateway` | PASS |
| `test_outcome_relevant_conflict_causes_review_required` | Outcome-relevant conflict causes review required | `structure.evaluate_structural_gateway` | PASS |
| `test_referenced_only_course_topology_and_mandatory_role` | Referenced-only course topology & mandatory role (`NOT_APPLICABLE`) | `structure.evaluate_mandatory_role` & `structure.evaluate_structural_gateway` | PASS |
| `test_referenced_only_course_with_source_conflict` | Referenced-only course with source conflict | `structure.evaluate_structural_gateway` | PASS |
| `test_deterministic_reproducibility` | Pure-domain deterministic reproducibility | `engine.evaluate_institutional_intelligence` | PASS |
| `test_missing_demand_metric_evaluates_to_insufficient_data` | Missing demand metric evaluates to INSUFFICIENT_DATA | `engine.evaluate_institutional_intelligence` | PASS |
| `test_negative_capacity_fact_raises_value_error` | Negative capacity fact validation | `models.CapacityFact` | PASS |
| `test_machine_enforced_signal_registry_lock` | Literal machine-enforced lock on 13 signal keys | `registries.InstitutionalSignalId` | PASS |
| `test_machine_enforced_alert_registry_lock` | Literal machine-enforced lock on 6 alert keys | `registries.InstitutionalAlertId` | PASS |
| `test_p6_metric_to_p7_signal_mapping_separation` | Strict separation of P6 metric keys and P7 signal IDs | `engine.evaluate_institutional_intelligence` | PASS |
| `test_cycle_localization_irrelevant_cycle_does_not_poison_candidate` | Irrelevant or bypassed cycle does not poison candidate | `structure.evaluate_structural_gateway` | PASS |
