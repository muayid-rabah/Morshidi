"""Pure, bounded synthetic P11 evaluations; never changes academic rules."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from hashlib import sha256
import json

from .models import (
    CareerProfile, CohortDefinition, HistoricalRecord, HistoricalSnapshot,
    InternshipCriteria, SkillTaxonomy, WorkloadFact,
)

CAUSAL_LIMITS = ("DESCRIPTIVE_ONLY", "NOT_CAUSAL", "MAY_BE_CONFOUNDED", "SYNTHETIC_VALIDATION_ONLY")
MODEL_ID = "p11-synthetic-rule-fixture"
MODEL_VERSION = "1.0"
FEATURE_VERSION = "synthetic-features-v1"


def fingerprint(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def cohort(snapshot: HistoricalSnapshot | None, definition: CohortDefinition, threshold: int) -> dict:
    if threshold < 2 or not 1 <= definition.minimum_level <= definition.maximum_level <= 8:
        raise ValueError("Invalid cohort definition or privacy threshold")
    if snapshot is None or len(snapshot.records) > 10_000 or (snapshot.university_id, snapshot.study_plan_id) != (definition.university_id, definition.study_plan_id):
        return {"status": "UNAVAILABLE", "definition": asdict(definition), "causal_limits": CAUSAL_LIMITS,
                "source_version": None, "fingerprint": None}
    rows = tuple(row for row in snapshot.records if row.entry_period == definition.entry_period
                 and row.period == definition.period and definition.minimum_level <= row.academic_level <= definition.maximum_level)
    base = {"definition": asdict(definition), "causal_limits": CAUSAL_LIMITS,
            "source_version": snapshot.source_version, "synthetic": snapshot.synthetic,
            "provenance": snapshot.provenance}
    if len({row.anonymous_id for row in rows}) != len(rows):
        return {**base, "status": "UNAVAILABLE", "size": None, "metrics": None,
                "fingerprint": None, "reason": "DUPLICATE_ANONYMOUS_RECORDS"}
    if not rows:
        return {**base, "status": "UNAVAILABLE", "size": None, "metrics": None,
                "fingerprint": None, "reason": "NO_COHORT_EVIDENCE"}
    if len(rows) < threshold:
        return {**base, "status": "SUPPRESSED", "size": None, "metrics": None,
                "fingerprint": fingerprint((definition, snapshot.source_version, "SUPPRESSED"))}
    known = tuple(row for row in rows if row.completion_ratio is not None)
    distribution = {bucket: sum(1 for row in known if (row.completion_ratio or 0) >= low and (row.completion_ratio or 0) < high)
                    for bucket, low, high in (("LOW", 0, .5), ("MID", .5, .75), ("HIGH", .75, 1.01))}
    # Suppress the entire distribution when any nonempty bucket is too small;
    # otherwise the published total could reveal a suppressed complement.
    if any(0 < value < threshold for value in distribution.values()):
        distribution = None
    repeated = sum(bool(row.repeated_courses) for row in rows)
    structural = sum(row.observed_structural_signal is True for row in rows)
    def safe_binary(count: int) -> int | None:
        return count if count == 0 or (count >= threshold and len(rows) - count >= threshold) else None
    metrics = {
        "completion_distribution": distribution,
        "repeated_course_count": safe_binary(repeated),
        "observed_structural_signal_count": safe_binary(structural),
        "mean_completion_ratio": round(sum(row.completion_ratio for row in known) / len(known), 3) if known else None,
        "completion_evidence_count": len(known),
        "credit_load_evidence_count": sum(row.credit_load is not None for row in rows),
    }
    return {**base, "status": "AVAILABLE", "size": len(rows), "metrics": metrics,
            "fingerprint": fingerprint((definition, snapshot.source_version, metrics))}


def compare_cohorts(first: dict, second: dict) -> dict:
    if first["status"] != "AVAILABLE" or second["status"] != "AVAILABLE":
        return {"status": "UNAVAILABLE", "causal_limits": CAUSAL_LIMITS, "difference": None}
    if first["definition"]["university_id"] != second["definition"]["university_id"]:
        raise ValueError("Cross-tenant cohort comparison is forbidden")
    first_mean = first["metrics"]["mean_completion_ratio"]
    second_mean = second["metrics"]["mean_completion_ratio"]
    return {"status": "DESCRIPTIVE", "causal_limits": CAUSAL_LIMITS,
            "difference": round(first_mean - second_mean, 3) if first_mean is not None and second_mean is not None else None}


def risk(record: HistoricalRecord | None, *, model_version: str = MODEL_VERSION, generated_at: str) -> dict:
    governance = {"model_id": MODEL_ID, "model_version": model_version,
                  "feature_contract_version": FEATURE_VERSION, "training_provenance": "FICTIONAL_RULE_FIXTURE_NO_TRAINING",
                  "intended_use": "SYNTHETIC_CONTRACT_TEST_ONLY",
                  "prohibited_use": "ACADEMIC_DECISIONS_OR_REAL_STUDENT_RISK",
                  "validation_status": "NOT_VALIDATED_FOR_REAL_STUDENTS", "synthetic": True,
                  "generated_at": generated_at, "human_review_required": True,
                  "review_action": "REQUEST_AUTHORIZED_HUMAN_REVIEW_NO_AUTOMATIC_ACTION"}
    if model_version != MODEL_VERSION or record is None:
        return {**governance, "signal": "ABSTAIN", "abstention": True,
                "reason": "MODEL_VERSION_INVALID" if model_version != MODEL_VERSION else "FEATURES_UNAVAILABLE",
                "coverage": "NONE", "uncertainty": "HIGH", "evidence": ()}
    features = (record.completion_ratio, record.credit_load, record.observed_structural_signal)
    coverage = sum(value is not None for value in features)
    if coverage < 3 or not 0 <= record.completion_ratio <= 1 or not 0 <= record.credit_load <= 30:
        return {**governance, "signal": "ABSTAIN", "abstention": True,
                "reason": "LOW_OR_INVALID_FEATURE_COVERAGE", "coverage": f"{coverage}/3",
                "uncertainty": "HIGH", "evidence": ()}
    elevated = record.completion_ratio < .6 or record.observed_structural_signal
    return {**governance, "signal": "ELEVATED_SIGNAL" if elevated else "LOW_SIGNAL",
            "abstention": False, "reason": "SYNTHETIC_RULE_ONLY", "coverage": "3/3",
            "uncertainty": "HIGH_SYNTHETIC_UNCALIBRATED",
            "evidence": ("COMPLETION_RATIO_BUCKET", "CREDIT_LOAD_COVERAGE", "STRUCTURAL_SIGNAL")}


class SyntheticRiskModel:
    """Local rule fixture. It was not trained or validated for people."""

    def infer(self, record: HistoricalRecord | None, *, generated_at: str) -> dict:
        return risk(record, generated_at=generated_at)


class UnavailableRiskModel:
    """Production boundary: never interpret absent validation as low risk."""

    def infer(self, record: HistoricalRecord | None, *, generated_at: str) -> dict:
        result = risk(None, generated_at=generated_at)
        return {**result, "synthetic": False, "reason": "VALIDATED_MODEL_UNAVAILABLE"}


def synthetic_evaluation(snapshot: HistoricalSnapshot, *, generated_at: str) -> dict:
    """Temporal split and classification counts are lab mechanics, not validity evidence."""
    ordered = sorted(snapshot.records, key=lambda row: (row.period, row.anonymous_id))
    cut = len(ordered) // 2
    train, holdout = ordered[:cut], ordered[cut:]
    counts = {"TP": 0, "TN": 0, "FP": 0, "FN": 0, "ABSTAIN": 0}
    for row in holdout:
        output = risk(row, generated_at=generated_at)
        if output["abstention"] or row.outcome is None:
            counts["ABSTAIN"] += 1
            continue
        actual = row.outcome in {"FAILED", "WITHDRAWN"}
        predicted = output["signal"] == "ELEVATED_SIGNAL"
        counts[("T" if actual == predicted else "F") + ("P" if predicted else "N")] += 1
    return {"label": "SYNTHETIC VALIDATION ONLY", "source_version": snapshot.source_version,
            "training_count": len(train), "holdout_count": len(holdout), "temporal_split": True,
            "counts": counts, "abstention_coverage": counts["ABSTAIN"],
            "fairness_status": "NOT_EVALUATED_NO_APPROVED_SUBGROUP_FEATURES",
            "calibration_status": "NOT_APPLICABLE_NO_PROBABILITY_OUTPUT"}


def drift(baseline: HistoricalSnapshot, candidate: HistoricalSnapshot) -> dict:
    if (baseline.university_id, baseline.study_plan_id) != (candidate.university_id, candidate.study_plan_id):
        raise ValueError("Drift scope mismatch")
    def average(rows: tuple[HistoricalRecord, ...]) -> float | None:
        values = [row.completion_ratio for row in rows if row.completion_ratio is not None]
        return sum(values) / len(values) if values else None
    left, right = average(baseline.records), average(candidate.records)
    changed = baseline.source_version != candidate.source_version
    shifted = left is not None and right is not None and abs(left - right) >= .2
    return {"status": "DRIFT_DETECTED" if changed or shifted else "STABLE",
            "source_version_changed": changed, "completion_distribution_shifted": shifted,
            "action": "HUMAN_REVIEW_NO_AUTOMATIC_RETRAINING"}


def workload(facts: tuple[WorkloadFact, ...] | None, course_codes: tuple[str, ...]) -> dict:
    by_code = {fact.course_code: fact for fact in facts or ()}
    selected = [by_code.get(code) for code in dict.fromkeys(course_codes)]
    known = [fact for fact in selected if fact and fact.observed_low_hours is not None and fact.observed_high_hours is not None
             and 0 <= fact.observed_low_hours <= fact.observed_high_hours <= 40]
    if not selected or len(known) != len(selected):
        return {"status": "UNKNOWN", "low_hours_per_week": None, "high_hours_per_week": None,
                "coverage": "LOW", "uncertainty": "HIGH", "source_version": "p11-synthetic-workload-v1" if facts else None,
                "assumptions": ("INCOMPLETE_SYNTHETIC_WORKLOAD_EVIDENCE",), "synthetic": bool(facts)}
    return {"status": "RANGE", "low_hours_per_week": sum(f.observed_low_hours for f in known),
            "high_hours_per_week": sum(f.observed_high_hours for f in known),
            "coverage": "HIGH", "uncertainty": "NOT_CALIBRATED_FOR_REAL_STUDENTS",
            "source_version": "p11-synthetic-workload-v1", "assumptions": ("WEEKLY_STUDY_HOURS_SYNTHETIC", "NOT_AN_ELIGIBILITY_RULE"),
            "synthetic": True}


def skills(taxonomy: SkillTaxonomy | None, passed: tuple[str, ...], in_progress: tuple[str, ...],
           evidence_dates: dict[str, str | None] | None = None) -> dict:
    skill_ids = {skill.skill_id for skill in taxonomy.skills} if taxonomy else set()
    if (taxonomy is None or len(taxonomy.skills) > 1_000 or len(taxonomy.mappings) > 5_000
            or any(mapping.version != taxonomy.version for mapping in taxonomy.mappings)
            or len(skill_ids) != len(taxonomy.skills)
            or any(mapping.skill_id not in skill_ids for mapping in taxonomy.mappings)):
        return {"status": "UNRESOLVED", "taxonomy_version": taxonomy.version if taxonomy else None, "items": (),
                "limitation": "TAXONOMY_UNAVAILABLE_OR_VERSION_MISMATCH"}
    items = []
    for skill in taxonomy.skills:
        mapped = [mapping for mapping in taxonomy.mappings if mapping.skill_id == skill.skill_id]
        completed = sorted({m.course_code for m in mapped if m.course_code in passed})
        exposure = sorted({m.course_code for m in mapped if m.course_code in in_progress})
        state = "EVIDENCED" if completed else "EXPOSED" if exposure else "NOT_EVIDENCED"
        items.append({"skill_id": skill.skill_id, "name_ar": skill.name_ar, "name_en": skill.name_en,
                      "state": state, "source_courses": completed or exposure,
                      "evidence_dates": {code: evidence_dates.get(code) for code in (completed or exposure)} if evidence_dates else {},
                      "mapping_provenance": sorted({m.provenance for m in mapped}),
                      "limitation": "COURSE_EVIDENCE_NOT_SKILL_MASTERY"})
    return {"status": "AVAILABLE", "taxonomy_version": taxonomy.version,
            "source_at": taxonomy.source_at.isoformat(), "synthetic": taxonomy.synthetic,
            "items": tuple(items), "limitation": "NO_MASTERY_ASSESSMENT"}


def careers(profiles: tuple[CareerProfile, ...] | None, graph: dict, *, as_of: date) -> tuple[dict, ...]:
    if graph["status"] != "AVAILABLE" or not profiles or len(profiles) > 100:
        return ()
    states = {item["skill_id"]: item["state"] for item in graph["items"]}
    results = []
    for profile in profiles:
        stale = (as_of - profile.source_at).days > 365
        mismatch = profile.taxonomy_version != graph["taxonomy_version"]
        unresolved = stale or mismatch
        results.append({"career_id": profile.career_id, "title_ar": profile.title_ar, "title_en": profile.title_en,
                        "status": "UNRESOLVED" if unresolved else "DESCRIPTIVE_ONLY",
                        "evidenced": [] if unresolved else sorted(s for s in profile.required_skill_ids if states.get(s) == "EVIDENCED"),
                        "exposed": [] if unresolved else sorted(s for s in profile.required_skill_ids if states.get(s) == "EXPOSED"),
                        "gaps": [] if unresolved else sorted(s for s in profile.required_skill_ids if states.get(s) == "NOT_EVIDENCED"),
                        "unresolved": sorted(profile.required_skill_ids) if unresolved else sorted(s for s in profile.required_skill_ids if s not in states),
                        "stale": stale, "source_at": profile.source_at.isoformat(),
                        "source_version": profile.source_version, "provenance": profile.provenance,
                        "synthetic": profile.synthetic, "uncertainty": "NOT_VALIDATED_FOR_CAREER_FIT",
                        "limitation": "NO_EMPLOYMENT_PROBABILITY_OR_PROMISE"})
    return tuple(results)


def internships(criteria: tuple[InternshipCriteria, ...] | None, graph: dict, *, as_of: date) -> tuple[dict, ...]:
    if not criteria or len(criteria) > 100:
        return ()
    states = {item["skill_id"]: item["state"] for item in graph.get("items", ())}
    results = []
    for program in criteria:
        unresolved = graph["status"] != "AVAILABLE" or program.taxonomy_version != graph["taxonomy_version"] or as_of > program.expires_at
        items = tuple({"criterion_id": c.criterion_id, "requirement_ar": c.requirement_ar,
                       "requirement_en": c.requirement_en, "skill_id": c.skill_id,
                       "status": "UNRESOLVED" if unresolved or c.skill_id not in states else
                                 "READY" if states[c.skill_id] == "EVIDENCED" else "GAP" if states[c.skill_id] == "NOT_EVIDENCED" else "UNRESOLVED",
                       "evidence": states.get(c.skill_id), "source_version": program.source_version}
                      for c in program.criteria)
        state = "UNRESOLVED" if unresolved or any(i["status"] == "UNRESOLVED" for i in items) else "GAP" if any(i["status"] == "GAP" for i in items) else "READY"
        results.append({"partner_id": program.partner_id, "title_ar": program.title_ar, "title_en": program.title_en,
                        "status": state, "criteria": items, "expires_at": program.expires_at.isoformat(),
                        "source_version": program.source_version, "provenance": program.provenance,
                        "synthetic": program.synthetic, "limitation": "MODELED_READINESS_NOT_PLACEMENT_ELIGIBILITY"})
    return tuple(results)
