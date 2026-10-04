"""Focused P15.5 evidence, coverage, and eligibility isolation tests."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import re

from app.progress.engine import calculate_academic_progress
from app.progress.models import (AcademicProgressCatalog, ProgressPlanCourse,
                                 ProgressRequirementGroup, ProgressStudyPlan, RequirementType)
from app.recommendations.engine import recommend_courses
from app.rules.models import (AttemptOutcome, CanTakeCatalog, CourseCatalogStatus,
                              CourseIdentity, PlanCourseRule, PrerequisiteLogicStatus,
                              StudentCourseAttempt)
from app.student.models import (PerformanceProvenance, PerformanceVerificationState,
                                StudentAcademicState, StudentCourseAttemptRecord)
from app.student_intelligence.adaptive import (GradePolicy, WEIGHTS, build_adaptive_courses)

PLAN = "10000000-0000-0000-0000-000000000005"
INSTITUTION = "institution-fixture"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _snapshot(grade: Decimal | None, *, owner: str = "student-a", verified: bool = True,
              all_codes: tuple[str, ...] = ("1501110", "1501221", "1505311"),
              synthetic_scale: bool = True, fresh_until: datetime | None = NOW):
    group = ProgressRequirementGroup("group", PLAN, "MAJOR_REQUIRED", "Required", "Required",
                                     "major", RequirementType.REQUIRED, Decimal("132"), 1)
    progress_catalog = AcademicProgressCatalog(
        ProgressStudyPlan(PLAN, Decimal("132")), (group,),
        tuple(ProgressPlanCourse(f"pc-{code}", PLAN, "group", code,
                                 CourseCatalogStatus.KNOWN, Decimal("3"), index)
              for index, code in enumerate(all_codes)),
    )
    eligibility_catalog = CanTakeCatalog(
        PLAN, tuple(PlanCourseRule(code, (PrerequisiteLogicStatus.UNRESOLVED
                                         if code == "1505311" else PrerequisiteLogicStatus.NOT_APPLICABLE), (),
                                   credit_hours=Decimal("3")) for code in all_codes),
        tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in all_codes), True,
    )
    attempts = ((StudentCourseAttempt("1501110", AttemptOutcome.PASSED),)
                if "1501110" in all_codes else ())
    state = StudentAcademicState(owner, owner, PLAN, Decimal("3.5"), Decimal("4"),
                                 Decimal("99"), attempts, updated_at=NOW)
    records = ((StudentCourseAttemptRecord(
        "attempt-1", owner, "1501110", AttemptOutcome.PASSED, 1, None, None,
        None, "fixture", NOW, NOW, raw_numeric_grade=grade,
        performance_provenance=(PerformanceProvenance.OFFICIAL_VERIFIED if verified
                                else PerformanceProvenance.STUDENT_RECORD),
        performance_verification_state=(PerformanceVerificationState.VERIFIED if verified
                                        else PerformanceVerificationState.UNVERIFIED),
    ),) if attempts else ())
    progress = calculate_academic_progress(progress_catalog, attempts)
    recommendations = recommend_courses(progress_catalog, eligibility_catalog, attempts)
    policy = (GradePolicy(INSTITUTION, PLAN, "MODELED_GRADE_SCALE_V1", "SYNTHETIC_ONLY",
                          Decimal(0), Decimal(100)) if synthetic_scale else None)
    return build_adaptive_courses(state, INSTITUTION, progress_catalog, eligibility_catalog,
                                  progress, recommendations, records, generated_at=NOW,
                                  grade_policy=policy, source_fresh_until=fresh_until)


def test_verified_grades_change_student_difficulty_without_changing_general_model():
    strong = _snapshot(Decimal(95))
    weak = _snapshot(Decimal(52), owner="student-b")
    a = next(item for item in strong.courses if item.course_code == "1501221")
    b = next(item for item in weak.courses if item.course_code == "1501221")
    assert a.general == b.general
    assert a.personalized.score < b.personalized.score
    assert strong.profile.strong_courses == ("1501110",)
    assert weak.profile.weak_courses == ("1501110",)
    assert strong.profile.earned_completed_credits == Decimal("3")
    assert strong.profile.cumulative_gpa == Decimal("3.5")
    assert strong.profile.gpa_provenance == "REPORTED_NOT_RECALCULATED"
    assert strong.profile.grade_scale_version == "MODELED_GRADE_SCALE_V1"
    assert strong.profile.grade_scale_provenance == "SYNTHETIC_ONLY"


def test_unverified_grade_is_unknown_not_weak_and_ranked_courses_are_eligible_only():
    result = _snapshot(Decimal(42), verified=False)
    assert not result.profile.weak_courses
    assert not result.profile.skills
    assert all(item.personalized.confidence == "LOW" for item in result.courses)
    assert all(item.eligible and item.course_code != "1501110" for item in result.recommendations)
    assert sum(WEIGHTS.values()) == 100
    assert result == _snapshot(Decimal(42), verified=False)


def test_unknown_production_scale_excludes_grade_mastery_and_exposes_low_confidence():
    unknown = _snapshot(Decimal(95), synthetic_scale=False)
    assert unknown.profile.grade_scale_version is None
    assert unknown.profile.grade_scale_provenance == "UNVERIFIED_GRADE_SCALE"
    assert not unknown.profile.skills
    assert not unknown.profile.strong_courses
    for course in unknown.courses:
        assert course.personalized.confidence == "LOW"
        assert "UNVERIFIED_GRADE_SCALE" in course.personalized.reason_codes
        assert course.personalized.provenance == "MODELED_STRUCTURAL_FALLBACK_NO_GRADE_MASTERY"
    stale = _snapshot(Decimal(95), fresh_until=NOW - timedelta(days=1))
    assert stale.profile.freshness == "STALE_INPUT"
    assert all(course.personalized.confidence == "LOW" and "STALE_INPUT" in course.personalized.reason_codes
               for course in stale.courses)


def test_every_plan12_seed_course_receives_both_modeled_difficulties():
    seed = (Path(__file__).resolve().parents[3] / "supabase" / "migrations" /
            "20260916230222_seed_ai_plan12_courses.sql").read_text(encoding="utf-8")
    codes = tuple(dict.fromkeys(re.findall(r"(?m)^\s*\('([0-9]{7})',", seed)))
    assert codes
    result = _snapshot(None, all_codes=codes)
    assert {item.course_code for item in result.courses} == set(codes)
    assert all(0 <= item.general.score <= 100 and item.general.level and item.general.provenance
               and item.general.model_version and 0 <= item.personalized.score <= 100
               and item.personalized.level and item.personalized.confidence
               and item.personalized.provenance and item.personalized.model_version
               and item.personalized.reason_codes
               for item in result.courses)
    assert any(item.general.provenance == "MODELED_FALLBACK" for item in result.courses)
    added_code = "9999999"
    assert added_code not in codes
    extended = _snapshot(None, all_codes=(*codes, added_code))
    assert {item.course_code for item in extended.courses} == {*codes, added_code}
    assert next(item for item in extended.courses if item.course_code == added_code).skill_profile.provenance == "MODELED_FALLBACK"
