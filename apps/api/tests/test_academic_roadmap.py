"""Synthetic deterministic P9 roadmap cases; no production identities or data."""

import asyncio
from types import SimpleNamespace
from datetime import datetime, timezone
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.advisor.models import ResolvedCourseReference
from app.catalog.errors import CatalogIntegrityError
from app.catalog.roadmap_metadata import RoadmapPlanMetadata
from app.progress.models import (
    AcademicProgressCatalog, ProgressPlanCourse, ProgressRequirementGroup,
    ProgressStudyPlan, RequirementType,
)
from app.roadmap.engine import ModeledPlanOverlay, RoadmapState, build_roadmap
from app.roadmap.fingerprint import academic_input_fingerprint
from app.roadmap.report import build_report_snapshot
from app.rules.models import (
    AttemptOutcome, CanTakeCatalog, CourseCatalogStatus, CourseIdentity,
    DependencyGroup, DependencyType, PlanCourseRule, PrerequisiteLogicStatus,
    StudentCourseAttempt,
)
from app.services.student import StudentService
from app.student.models import StudentAcademicState


PLAN = "sandbox-plan-v1"
INSTITUTION = "isolated-roadmap-institution"
CODES = ("DONE", "CURRENT", "OPEN", "LOCKED", "REVIEW", "LATER")


def catalogs():
    progress = AcademicProgressCatalog(
        ProgressStudyPlan(PLAN, Decimal("18")),
        (ProgressRequirementGroup("group", PLAN, "CORE", "متطلبات", "Core", "major", RequirementType.REQUIRED, Decimal("18"), 1),),
        tuple(ProgressPlanCourse(code, PLAN, "group", code, CourseCatalogStatus.KNOWN, Decimal("3"), index)
              for index, code in enumerate(CODES)),
    )
    rules = CanTakeCatalog(
        PLAN,
        tuple(PlanCourseRule(
            code,
            PrerequisiteLogicStatus.UNRESOLVED if code == "REVIEW" else
            PrerequisiteLogicStatus.VERIFIED if code in {"LOCKED", "LATER"} else
            PrerequisiteLogicStatus.NOT_APPLICABLE,
            (DependencyGroup(1, DependencyType.PREREQUISITE, ("CURRENT",)),) if code == "LOCKED" else
            (DependencyGroup(1, DependencyType.PREREQUISITE, ("LOCKED",)),) if code == "LATER" else (),
        ) for code in CODES),
        tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in CODES),
    )
    names = tuple(ResolvedCourseReference(code, f"مادة {code}", f"Course {code}") for code in CODES)
    attempts = (StudentCourseAttempt("DONE", AttemptOutcome.PASSED),
                StudentCourseAttempt("CURRENT", AttemptOutcome.IN_PROGRESS))
    return progress, rules, names, attempts


def test_synthetic_roadmap_states_evidence_and_provenance():
    inputs = catalogs()
    metadata = RoadmapPlanMetadata(PLAN, "sandbox-1", 2026, "2026-09-30T00:00:00Z")
    fingerprint = academic_input_fingerprint(*inputs, metadata, institution_id=INSTITUTION)
    result = build_roadmap(*inputs, institution_id=INSTITUTION, plan_metadata=metadata,
                           modeled_overlay=ModeledPlanOverlay(PLAN, fingerprint, "test-policy-v1", ((2, ("LATER",)),)),
                           generated_at=datetime(2026, 9, 30, tzinfo=timezone.utc))
    nodes = {node.course_code: node for node in result.courses}
    assert {code: node.state for code, node in nodes.items()} == {
        "DONE": RoadmapState.COMPLETED, "CURRENT": RoadmapState.IN_PROGRESS,
        "OPEN": RoadmapState.ELIGIBLE, "LOCKED": RoadmapState.BLOCKED,
        "REVIEW": RoadmapState.REVIEW_REQUIRED, "LATER": RoadmapState.PLANNED,
    }
    assert nodes["LOCKED"].missing_prerequisite_groups == (("CURRENT",),)
    assert nodes["CURRENT"].structural_criticality
    assert nodes["CURRENT"].structural_impact_count == 1
    assert nodes["LATER"].planned_semester == 2
    assert nodes["LATER"].planned_order == 1
    assert result.modeling_status == "MODELED_PATH"
    assert result.snapshot_fingerprint == fingerprint
    assert result.plan_number == "sandbox-1" and result.effective_year == 2026
    assert result.completed_plan_credits == Decimal("3")
    assert len(result.edges) == 2


def test_overlay_rejects_stale_snapshot_and_unavailable_courses():
    inputs = catalogs()
    fingerprint = academic_input_fingerprint(*inputs, None, institution_id=INSTITUTION)
    with pytest.raises(CatalogIntegrityError, match="stale"):
        build_roadmap(*inputs, institution_id=INSTITUTION, modeled_overlay=ModeledPlanOverlay(PLAN, "old", "v1", ((1, ("LATER",)),)))
    with pytest.raises(CatalogIntegrityError, match="unavailable"):
        build_roadmap(*inputs, institution_id=INSTITUTION, modeled_overlay=ModeledPlanOverlay(PLAN, fingerprint, "v1", ((1, ("DONE",)),)))
    without = build_roadmap(*inputs, institution_id=INSTITUTION)
    assert without.modeling_status == "NOT_REQUESTED"
    assert all(node.state is not RoadmapState.PLANNED for node in without.courses)


def test_report_snapshot_is_immutable_reproducible_and_version_sensitive():
    progress, rules, names, attempts = catalogs()
    metadata = RoadmapPlanMetadata(PLAN, "v1", 2026, "2026-09-30T00:00:00Z")
    first = build_report_snapshot(build_roadmap(progress, rules, names, attempts, institution_id=INSTITUTION, plan_metadata=metadata,
                                                 generated_at=datetime(2026, 9, 30, tzinfo=timezone.utc)))
    second = build_report_snapshot(build_roadmap(progress, rules, names, attempts, institution_id=INSTITUTION, plan_metadata=metadata,
                                                  generated_at=datetime(2026, 10, 1, tzinfo=timezone.utc)))
    assert first.content_fingerprint == second.content_fingerprint
    assert first.courses == second.courses
    assert first.generated_at != second.generated_at
    changed_state = build_report_snapshot(build_roadmap(progress, rules, names, (), institution_id=INSTITUTION, plan_metadata=metadata))
    changed_version = build_report_snapshot(build_roadmap(
        progress, rules, names, attempts, institution_id=INSTITUTION,
        plan_metadata=RoadmapPlanMetadata(PLAN, "v2", 2026, "2026-09-30T00:00:00Z")))
    assert len({first.content_fingerprint, changed_state.content_fingerprint,
                changed_version.content_fingerprint}) == 3
    assert first.modeled_state_marker == "MODELED_UNOFFICIAL"
    assert first.report_schema_version and first.snapshot_fingerprint
    with pytest.raises(FrozenInstanceError):
        first.plan_number = "mutated"


def test_cross_plan_catalogs_fail_closed():
    progress, rules, names, attempts = catalogs()
    with pytest.raises(CatalogIntegrityError):
        build_roadmap(progress, CanTakeCatalog("foreign-plan", rules.plan_courses, rules.courses), names, attempts, institution_id=INSTITUTION)


def test_missing_names_fail_closed_and_or_group_is_not_critical():
    progress, rules, names, attempts = catalogs()
    with pytest.raises(CatalogIntegrityError):
        build_roadmap(progress, rules, names[:-1], attempts, institution_id=INSTITUTION)
    other_rules = tuple(
        PlanCourseRule(rule.course_code, rule.prerequisite_logic_status,
                       (DependencyGroup(1, DependencyType.PREREQUISITE, ("CURRENT", "DONE")),)
                       if rule.course_code == "LOCKED" else rule.dependency_groups)
        for rule in rules.plan_courses
    )
    result = build_roadmap(progress, CanTakeCatalog(PLAN, other_rules, rules.courses), names, attempts, institution_id=INSTITUTION)
    assert not next(node for node in result.courses if node.course_code == "CURRENT").structural_criticality


def test_critical_path_is_repeatable_and_excludes_or_and_disconnected():
    progress, rules, names, attempts = catalogs()
    first = build_roadmap(progress, rules, names, attempts, institution_id=INSTITUTION)
    second = build_roadmap(progress, rules, names, attempts, institution_id=INSTITUTION)
    assert first.courses == second.courses
    nodes = {node.course_code: node for node in first.courses}
    assert {code for code, node in nodes.items() if node.critical_path} == {"CURRENT", "LOCKED", "LATER"}
    assert nodes["CURRENT"].critical_path_length == 2
    assert nodes["CURRENT"].critical_path_downstream_codes == ("LATER", "LOCKED")
    assert nodes["LATER"].critical_path_evidence_chain == ("CURRENT", "LOCKED", "LATER")
    assert nodes["OPEN"].critical_path is False
    assert nodes["DONE"].critical_path is False
    other_rules = tuple(PlanCourseRule(
        rule.course_code, rule.prerequisite_logic_status,
        (DependencyGroup(1, DependencyType.PREREQUISITE, ("CURRENT", "OPEN")),)
        if rule.course_code == "LOCKED" else rule.dependency_groups,
    ) for rule in rules.plan_courses)
    branched = build_roadmap(progress, CanTakeCatalog(PLAN, other_rules, rules.courses), names, attempts, institution_id=INSTITUTION)
    branched_nodes = {node.course_code: node for node in branched.courses}
    assert not branched_nodes["CURRENT"].critical_path
    assert branched_nodes["LOCKED"].critical_path
    assert all("graduation date" not in note.lower() for note in branched.limitations)


def test_elective_courses_are_not_marked_structural_critical_path():
    progress, rules, names, attempts = catalogs()
    elective = ProgressRequirementGroup(
        "elective", PLAN, "ELEC", "اختياري", "Elective", "elective",
        RequirementType.ELECTIVE, Decimal("0"), 2,
    )
    courses = tuple(
        ProgressPlanCourse(course.plan_course_id, course.study_plan_id,
                           "elective" if course.course_code in {"LOCKED", "LATER"} else course.requirement_group_id,
                           course.course_code, course.catalog_status, course.credit_hours, course.display_order)
        for course in progress.plan_courses
    )
    revised = AcademicProgressCatalog(progress.study_plan, progress.requirement_groups + (elective,), courses)
    result = build_roadmap(revised, rules, names, attempts, institution_id=INSTITUTION)
    assert not any(node.critical_path for node in result.courses)


def test_service_reads_only_owner_and_batch_catalogs_once():
    progress, rules, names, attempts = catalogs()
    calls = []

    class StudentRepository:
        async def load_student_academic_state(self, owner):
            calls.append(("owner", owner))
            return StudentAcademicState("synthetic-profile", owner, PLAN, None, None, None, attempts)
        async def resolve_student_university_id(self, owner):
            calls.append(("institution", owner)); return INSTITUTION

    class CatalogRepository:
        async def load_progress_catalog(self, plan):
            calls.append(("progress", plan)); return progress
        async def load_plan_eligibility_catalog(self, plan):
            calls.append(("eligibility", plan)); return rules
        async def load_advisor_course_catalog(self, plan):
            calls.append(("names", plan)); return names
        async def load_roadmap_plan_metadata(self, plan):
            calls.append(("metadata", plan)); return RoadmapPlanMetadata(PLAN, "sandbox-1", 2026, "2026-09-30T00:00:00Z")

    result = asyncio.run(StudentService(StudentRepository(), None, CatalogRepository()).get_academic_roadmap("owner-a"))
    assert len(result.courses) == 6
    assert set(calls[:2]) == {("owner", "owner-a"), ("institution", "owner-a")}
    assert calls[2:] == [("progress", PLAN), ("eligibility", PLAN),
                         ("names", PLAN), ("metadata", PLAN)]


def test_modeled_service_uses_owner_institution_for_overlay_fingerprint():
    progress, rules, names, attempts = catalogs()
    state = StudentAcademicState("profile", "owner-a", PLAN, None, None, None, attempts)
    metadata = RoadmapPlanMetadata(PLAN, "sandbox-1", 2026, "2026-09-30T00:00:00Z")

    class StudentRepository:
        async def resolve_student_university_id(self, owner):
            assert owner == "owner-a"
            return INSTITUTION

    class CatalogRepository:
        async def load_advisor_course_catalog(self, plan):
            assert plan == PLAN
            return names
        async def load_roadmap_plan_metadata(self, plan):
            assert plan == PLAN
            return metadata

    service = StudentService(StudentRepository(), None, CatalogRepository())

    async def fake_degree_paths(owner, *, snapshot_callback, **_kwargs):
        assert owner == "owner-a"
        await snapshot_callback(state, progress, rules)
        return SimpleNamespace(study_plan_id=PLAN, degree_path_policy_version="v1", paths=())

    service.get_degree_paths = fake_degree_paths
    result = asyncio.run(service.get_modeled_roadmap("owner-a", max_credit_hours_per_semester=Decimal(6)))
    assert result.snapshot_fingerprint == academic_input_fingerprint(
        progress, rules, names, attempts, metadata, institution_id=INSTITUTION)


@pytest.mark.parametrize("attempts,expected_done,expected_current", [
    ((), RoadmapState.ELIGIBLE, RoadmapState.ELIGIBLE),
    ((StudentCourseAttempt("DONE", AttemptOutcome.FAILED),), RoadmapState.ELIGIBLE, RoadmapState.ELIGIBLE),
    ((StudentCourseAttempt("DONE", AttemptOutcome.FAILED),
      StudentCourseAttempt("DONE", AttemptOutcome.PASSED)), RoadmapState.COMPLETED, RoadmapState.ELIGIBLE),
    (tuple(StudentCourseAttempt(code, AttemptOutcome.PASSED) for code in CODES[:-1]),
     RoadmapState.COMPLETED, RoadmapState.COMPLETED),
])
def test_synthetic_new_repeat_and_near_complete_profiles(attempts, expected_done, expected_current):
    progress, rules, names, _ = catalogs()
    result = build_roadmap(progress, rules, names, attempts, institution_id=INSTITUTION)
    states = {node.course_code: node.state for node in result.courses}
    assert states["DONE"] is expected_done
    assert states["CURRENT"] is expected_current


def test_seventy_five_course_synthetic_catalog_is_bounded_and_complete():
    count = 75
    codes = tuple(f"SYN{i:03}" for i in range(count))
    progress = AcademicProgressCatalog(
        ProgressStudyPlan(PLAN, Decimal("225")),
        (ProgressRequirementGroup("g", PLAN, "CORE", "تجريبي", "Synthetic", "major", RequirementType.REQUIRED, Decimal("225"), 1),),
        tuple(ProgressPlanCourse(code, PLAN, "g", code, CourseCatalogStatus.KNOWN, Decimal("3"), i)
              for i, code in enumerate(codes)),
    )
    rules = CanTakeCatalog(PLAN,
        tuple(PlanCourseRule(code, PrerequisiteLogicStatus.NOT_APPLICABLE) for code in codes),
        tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in codes))
    names = tuple(ResolvedCourseReference(code, f"مادة {code}", code) for code in codes)
    result = build_roadmap(progress, rules, names, (), institution_id=INSTITUTION)
    assert len(result.courses) == count
    assert all(node.state is RoadmapState.ELIGIBLE for node in result.courses)
