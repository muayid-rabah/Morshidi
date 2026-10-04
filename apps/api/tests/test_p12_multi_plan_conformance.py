"""Two concurrent in-memory plan versions through existing deterministic engines."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.advisor.models import ResolvedCourseReference
from app.catalog.roadmap_metadata import RoadmapPlanMetadata
from app.degree_path.engine import plan_degree_paths
from app.degree_path.models import DegreePathConstraints, DegreePathIntegrityError
from app.plan_transition.context import PlanVersionContext
from app.plan_transition.models import PlanIdentity
from app.planner.engine import plan_semester
from app.planner.models import PlannerConstraints, PlannerIntegrityError
from app.progress.engine import calculate_academic_progress
from app.progress.models import (AcademicProgressCatalog, ProgressPlanCourse,
                                 ProgressRequirementGroup, ProgressStudyPlan,
                                 RequirementType)
from app.recommendations.engine import recommend_courses
from app.roadmap.engine import build_roadmap
from app.roadmap.report import build_report_snapshot
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (AttemptOutcome, CanTakeCatalog, CanTakeRequest,
                              CourseCatalogStatus, CourseIdentity, Decision,
                              DependencyGroup, DependencyType, PlanCourseRule,
                              PrerequisiteLogicStatus, StudentCourseAttempt)


def fixture(version: str):
    """Same codes and row labels, changed credits and prerequisite graph."""
    plan_id = "isolated-plan-version-" + version
    context = PlanVersionContext(
        PlanIdentity("isolated-inst", "program", "major", "logical-plan", plan_id,
                     date(2025, 1, 1), None, "isolated-source"), plan_id)
    credits = Decimal(3 if version == "v1" else 4)
    group_id = "core-v1" if version == "v1" else "elective-v2"
    group = ProgressRequirementGroup(group_id, plan_id, "CORE", "Core", "Core",
                                     "major", RequirementType.REQUIRED, credits * 2, 1)
    progress = AcademicProgressCatalog(
        ProgressStudyPlan(plan_id, credits * 2), (group,),
        tuple(ProgressPlanCourse("shared-row-" + code, plan_id, group.group_id, code,
                                 CourseCatalogStatus.KNOWN, credits, index)
              for index, code in enumerate(("A101", "B101"))))
    prerequisite = (DependencyGroup(1, DependencyType.PREREQUISITE, ("A101",)),)
    rules = CanTakeCatalog(plan_id,
                           (PlanCourseRule("A101", PrerequisiteLogicStatus.NOT_APPLICABLE),
                            PlanCourseRule("B101", PrerequisiteLogicStatus.VERIFIED, prerequisite)
                            if version == "v1" else
                            PlanCourseRule("B101", PrerequisiteLogicStatus.NOT_APPLICABLE)),
                           (CourseIdentity("A101", CourseCatalogStatus.KNOWN),
                            CourseIdentity("B101", CourseCatalogStatus.KNOWN)))
    names = (ResolvedCourseReference("A101", "A", "A"),
             ResolvedCourseReference("B101", "B", "B"))
    metadata = RoadmapPlanMetadata(plan_id, "logical-plan-" + version, 2025,
                                   "2025-01-01T00:00:00Z")
    context.validate_scoped_inputs(progress, rules, metadata)
    return context, progress, rules, names, metadata


def snapshot(item):
    context, progress, rules, names, metadata = item
    attempts: tuple[StudentCourseAttempt, ...] = ()
    eligibility = evaluate_can_take(rules, CanTakeRequest(context.study_plan_version_row_id,
                                                           "B101", attempts))
    derived = calculate_academic_progress(progress, attempts)
    recommendation = recommend_courses(progress, rules, attempts)
    roadmap = build_roadmap(progress, rules, names, attempts, institution_id=context.identity.institution_id, plan_metadata=metadata,
                            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    report = build_report_snapshot(roadmap)
    planner = plan_semester(progress, rules, attempts, recommendation,
                            PlannerConstraints(Decimal(4), max_courses=1, max_options=2))
    degree = plan_degree_paths(progress, rules, attempts,
                               DegreePathConstraints(Decimal(4), max_courses_per_semester=1,
                                                     max_semesters_ahead=1, max_paths=1))
    return eligibility, derived, recommendation, roadmap, report, planner, degree


def test_two_versions_alternate_without_rule_cache_or_result_leakage():
    first, second = fixture("v1"), fixture("v2")
    a = snapshot(first)
    b = snapshot(second)
    again = snapshot(first)
    assert a == again
    assert a[0].decision is Decision.NOT_ELIGIBLE
    assert b[0].decision is Decision.ELIGIBLE
    assert a[0].study_plan_id != b[0].study_plan_id
    assert a[1].plan_total_required_credits == 6 and b[1].plan_total_required_credits == 8
    assert first[1].requirement_groups[0].group_id != second[1].requirement_groups[0].group_id
    assert a[2].study_plan_id != b[2].study_plan_id
    assert {item.course_code for item in a[2].ranked_recommendations} == {"A101"}
    assert {item.course_code for item in b[2].ranked_recommendations} == {"A101", "B101"}
    assert len(a[3].edges) == 1 and len(b[3].edges) == 0
    assert a[3].snapshot_fingerprint != b[3].snapshot_fingerprint
    assert a[4].content_fingerprint != b[4].content_fingerprint
    assert a[4].study_plan_id != b[4].study_plan_id
    assert a[5].study_plan_id != b[5].study_plan_id
    assert a[6].study_plan_id != b[6].study_plan_id
    assert first[0].cache_key != second[0].cache_key


def test_mixed_plan_inputs_fail_at_context_planner_and_degree_boundaries():
    first, second = fixture("v1"), fixture("v2")
    with pytest.raises(ValueError, match="scope mismatch"):
        first[0].validate_scoped_inputs(first[1], second[2], first[4])
    recommendations = recommend_courses(first[1], first[2], ())
    with pytest.raises(PlannerIntegrityError):
        plan_semester(first[1], second[2], (), recommendations, PlannerConstraints(Decimal(4)))
    with pytest.raises(DegreePathIntegrityError):
        plan_degree_paths(first[1], second[2], (), DegreePathConstraints(Decimal(4)))
