"""Synthetic-only P11 domain, governance, and privacy regressions."""

import asyncio
from dataclasses import replace
from datetime import date
from time import perf_counter

import pytest

from app.offerings.fake_provider import FAKE_UNIVERSITY_ID
from app.p11_intelligence.engine import (
    CAUSAL_LIMITS, SyntheticRiskModel, UnavailableRiskModel, careers, cohort,
    compare_cohorts, drift, fingerprint, internships, risk, skills,
    synthetic_evaluation, workload,
)
from app.p11_intelligence.fake_provider import FAKE_PLAN_ID, FakeP11Provider
from app.p11_intelligence.models import CohortDefinition, WorkloadFact
from app.p11_intelligence.providers import UnavailableP11Provider


def load():
    async def _get():
        provider = FakeP11Provider()
        return (await provider.load_snapshot(FAKE_UNIVERSITY_ID, FAKE_PLAN_ID),
                await provider.load_facts(FAKE_UNIVERSITY_ID, FAKE_PLAN_ID),
                await provider.load_taxonomy(FAKE_UNIVERSITY_ID, FAKE_PLAN_ID),
                await provider.load_profiles(FAKE_UNIVERSITY_ID, FAKE_PLAN_ID),
                await provider.load_criteria(FAKE_UNIVERSITY_ID, FAKE_PLAN_ID))
    return asyncio.run(_get())


def definition(period="SYN-2026-FALL"):
    return CohortDefinition(FAKE_UNIVERSITY_ID, FAKE_PLAN_ID, "SYN-2025-FALL", period)


def test_history_is_reproducible_and_tenant_scoped():
    snapshot, *_ = load()
    assert snapshot == load()[0]
    assert snapshot.synthetic and snapshot.provenance == "FICTIONAL_SANDBOX_OUTCOMES"
    assert len(snapshot.records) == 12
    assert asyncio.run(FakeP11Provider().load_snapshot("foreign", FAKE_PLAN_ID)) is None
    assert asyncio.run(UnavailableP11Provider().load_snapshot(FAKE_UNIVERSITY_ID, FAKE_PLAN_ID)) is None


def test_cohort_aggregation_suppression_comparison_and_causal_limits():
    snapshot, *_ = load()
    current = cohort(snapshot, definition(), 3)
    prior = cohort(snapshot, definition("SYN-2025-FALL"), 3)
    assert current["status"] == "AVAILABLE" and current["size"] == 6
    assert current["metrics"]["completion_evidence_count"] == 6
    assert current["metrics"]["completion_distribution"] is None
    assert current["metrics"]["repeated_course_count"] is None
    assert current["fingerprint"] == cohort(snapshot, definition(), 3)["fingerprint"]
    assert compare_cohorts(current, prior)["status"] == "DESCRIPTIVE"
    assert "NOT_CAUSAL" in CAUSAL_LIMITS and "MAY_BE_CONFOUNDED" in CAUSAL_LIMITS
    small = cohort(snapshot, replace(definition(), minimum_level=3), 3)
    assert small["status"] == "UNAVAILABLE" and small["size"] is None and small["metrics"] is None
    one = cohort(replace(snapshot, records=(snapshot.records[-1],)), definition(), 3)
    assert one["status"] == "SUPPRESSED" and one["size"] is None and one["metrics"] is None
    duplicate = replace(snapshot, records=snapshot.records + (snapshot.records[-1],))
    assert cohort(duplicate, definition(), 3)["status"] == "UNAVAILABLE"
    assert "anonymous_id" not in str(current)
    with pytest.raises(ValueError):
        cohort(snapshot, replace(definition(), minimum_level=6, maximum_level=2), 3)
    with pytest.raises(ValueError):
        compare_cohorts(current, {**prior, "definition": {**prior["definition"], "university_id": "foreign"}})


def test_risk_governance_abstention_and_no_academic_decision():
    snapshot, *_ = load()
    when = "2026-10-01T00:00:00Z"
    output = SyntheticRiskModel().infer(snapshot.records[0], generated_at=when)
    assert output["signal"] in {"LOW_SIGNAL", "ELEVATED_SIGNAL"}
    assert output["model_id"] and output["model_version"] == "1.0"
    assert output["feature_contract_version"] and output["training_provenance"]
    assert output["intended_use"] and output["prohibited_use"]
    assert output["validation_status"] == "NOT_VALIDATED_FOR_REAL_STUDENTS"
    assert output["human_review_required"] and output["synthetic"]
    assert output["uncertainty"] and output["coverage"] and output["generated_at"] == when
    assert "eligibility" not in output and "decision" not in output
    assert risk(snapshot.records[0], model_version="invalid", generated_at=when)["signal"] == "ABSTAIN"
    assert risk(replace(snapshot.records[0], credit_load=None), generated_at=when)["signal"] == "ABSTAIN"
    assert UnavailableRiskModel().infer(snapshot.records[0], generated_at=when)["signal"] == "ABSTAIN"


def test_synthetic_validation_temporal_sparse_and_drift():
    snapshot, *_ = load()
    report = synthetic_evaluation(snapshot, generated_at="2026-10-01T00:00:00Z")
    assert report["label"] == "SYNTHETIC VALIDATION ONLY"
    assert report["temporal_split"] and report["training_count"] == report["holdout_count"] == 6
    assert report["calibration_status"].startswith("NOT_APPLICABLE")
    assert report["fairness_status"].startswith("NOT_EVALUATED")
    assert sum(report["counts"].values()) == 6
    changed = replace(snapshot, source_version="changed")
    assert drift(snapshot, changed)["status"] == "DRIFT_DETECTED"
    shifted = replace(snapshot, records=tuple(replace(row, completion_ratio=0.1) for row in snapshot.records))
    assert drift(snapshot, shifted)["completion_distribution_shifted"]
    assert drift(snapshot, snapshot)["status"] == "STABLE"
    sparse = replace(snapshot, records=(replace(snapshot.records[0], completion_ratio=None),))
    assert synthetic_evaluation(sparse, generated_at="now")["holdout_count"] == 1


def test_workload_range_unknown_and_no_eligibility_field():
    _, facts, *_ = load()
    estimate = workload(facts, ("CS101", "MATH101"))
    assert estimate["status"] == "RANGE"
    assert (estimate["low_hours_per_week"], estimate["high_hours_per_week"]) == (9, 15)
    assert estimate["synthetic"] and estimate["uncertainty"]
    assert "eligibility" not in estimate
    assert workload(facts, ("PHYS101",))["status"] == "UNKNOWN"
    assert workload(None, ("CS101",))["status"] == "UNKNOWN"
    assert workload((WorkloadFact("BAD", 3, 9, 2, 2, False),), ("BAD",))["status"] == "UNKNOWN"


def test_skill_states_provenance_version_and_no_mastery():
    _, _, taxonomy, *_ = load()
    graph = skills(taxonomy, ("CS101",), ("MATH101",), {"CS101": "2026-09-01"})
    states = {item["skill_id"]: item["state"] for item in graph["items"]}
    assert states == {"SYN-CODE": "EVIDENCED", "SYN-QUANT": "EXPOSED", "SYN-COMMS": "NOT_EVIDENCED"}
    assert graph["taxonomy_version"] == "p11-taxonomy-v1" and graph["synthetic"]
    assert graph["items"][0]["mapping_provenance"] == ["SYNTHETIC_MAPPING"]
    assert graph["items"][0]["evidence_dates"] == {"CS101": "2026-09-01"}
    assert "MASTERED" not in str(graph)
    assert skills(None, (), ())["status"] == "UNRESOLVED"
    mismatch = replace(taxonomy, mappings=(replace(taxonomy.mappings[0], version="wrong"),))
    assert skills(mismatch, (), ())["status"] == "UNRESOLVED"


def test_career_gaps_staleness_and_internship_states():
    _, _, taxonomy, profiles, criteria = load()
    graph = skills(taxonomy, ("CS101",), ("MATH101",))
    career = careers(profiles, graph, as_of=date(2026, 10, 1))[0]
    assert career["evidenced"] == ["SYN-CODE"] and career["exposed"] == ["SYN-QUANT"]
    assert career["gaps"] == [] and career["uncertainty"]
    assert "probability" not in career and "NO_EMPLOYMENT_PROBABILITY" in career["limitation"]
    assert careers(profiles, graph, as_of=date(2028, 1, 1))[0]["status"] == "UNRESOLVED"
    assert careers(profiles, graph, as_of=date(2028, 1, 1))[0]["evidenced"] == []
    assert careers((replace(profiles[0], taxonomy_version="wrong"),), graph, as_of=date(2026, 10, 1))[0]["status"] == "UNRESOLVED"
    assert internships(criteria, skills(taxonomy, ("CS101", "MATH101"), ()), as_of=date(2026, 10, 1))[0]["status"] == "READY"
    assert internships(criteria, skills(taxonomy, (), ()), as_of=date(2026, 10, 1))[0]["status"] == "GAP"
    unresolved = internships(criteria, graph, as_of=date(2026, 10, 1))[0]
    assert unresolved["status"] == "UNRESOLVED" and "PLACEMENT_ELIGIBILITY" in unresolved["limitation"]
    assert internships(criteria, graph, as_of=date(2028, 1, 1))[0]["status"] == "UNRESOLVED"
    assert internships(None, graph, as_of=date(2026, 10, 1)) == ()


def test_bounded_local_performance_contract():
    snapshot, facts, taxonomy, profiles, criteria = load()
    start = perf_counter()
    for _ in range(100):
        cohort(snapshot, definition(), 3)
        risk(snapshot.records[0], generated_at="fixed")
        workload(facts, ("CS101", "MATH101"))
        graph = skills(taxonomy, ("CS101",), ("MATH101",))
        careers(profiles, graph, as_of=date(2026, 10, 1))
        internships(criteria, graph, as_of=date(2026, 10, 1))
    assert perf_counter() - start < 2
    assert fingerprint(graph) == fingerprint(graph)
