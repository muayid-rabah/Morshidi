"""Versioned load-profile coverage and explicit semester-balance relaxation."""

from decimal import Decimal
from pathlib import Path
import re

from app.planner.engine import plan_semester
from app.planner.learning_profile import (MAX_MEMORIZATION_HEAVY,
                                          resolve_learning_profile)
from app.planner.models import PlannerConstraints
from app.progress.models import (AcademicProgressCatalog, ProgressPlanCourse,
                                 ProgressRequirementGroup, ProgressStudyPlan, RequirementType)
from app.recommendations.engine import recommend_courses
from app.rules.models import (CanTakeCatalog, CourseCatalogStatus, CourseIdentity,
                              PlanCourseRule, PrerequisiteLogicStatus)

PLAN = "10000000-0000-0000-0000-000000000005"
HEAVY = ("0200104", "0200110", "0200111")


def _case(codes, *, accept=False):
    group = ProgressRequirementGroup("g", PLAN, "CORE", "Core", None, "core",
                                     RequirementType.REQUIRED, Decimal(len(codes) * 3), 1)
    progress = AcademicProgressCatalog(ProgressStudyPlan(PLAN, Decimal(len(codes) * 3)), (group,),
        tuple(ProgressPlanCourse(f"pc-{code}", PLAN, "g", code,
              CourseCatalogStatus.KNOWN, Decimal(3), n,
              course_name_ar="مادة ذات حمل حفظ", course_name_en="Memory-heavy course") for n, code in enumerate(codes)))
    eligible = CanTakeCatalog(PLAN, tuple(PlanCourseRule(code,
        PrerequisiteLogicStatus.NOT_APPLICABLE) for code in codes),
        tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in codes))
    recs = recommend_courses(progress, eligible, ())
    profiles = {code: resolve_learning_profile(code, plan_id=PLAN) for code in codes}
    return plan_semester(progress, eligible, (), recs,
        PlannerConstraints(Decimal(9), max_options=3), learning_profiles=profiles,
        accept_heavy_balance=accept)


def test_every_plan12_seed_code_has_versioned_profile_and_fallback():
    seed = (Path(__file__).resolve().parents[3] / "supabase" / "migrations" /
            "20260916230222_seed_ai_plan12_courses.sql").read_text(encoding="utf-8")
    codes = set(re.findall(r"(?m)^\s*\('([0-9]{7})',", seed))
    assert len(codes) == 68
    profiles = {code: resolve_learning_profile(code, plan_id=PLAN) for code in codes}
    assert len(profiles) == len(codes)
    assert all(item.provenance and item.version and item.primary_type for item in profiles.values())
    assert MAX_MEMORIZATION_HEAVY == 2
    assert resolve_learning_profile("9999999", plan_id=PLAN).provenance == "MODELED_FALLBACK"


def test_balanced_alternative_beats_three_heavy_without_sacrificing_credits():
    result = _case((*HEAVY, "1501111"))
    assert not result.balance_relaxation_required
    assert result.plan_options[0].total_credit_hours == 9
    assert result.plan_options[0].memorization_heavy_count <= 2
    assert "1501111" in {c.course_code for c in result.plan_options[0].courses}


def test_unavoidable_heavy_full_load_requires_explicit_approval():
    default = _case(HEAVY)
    assert default.balance_relaxation_required
    assert all(option.memorization_heavy_count <= 2 for option in default.plan_options)
    accepted = _case(HEAVY, accept=True)
    assert accepted.plan_options[0].total_credit_hours == 9
    assert accepted.plan_options[0].memorization_heavy_count == 3
    assert accepted.plan_options[0].balance_warning.startswith("BALANCE_CONSTRAINT_RELAXATION_REQUIRED:")
    assert "0200111" in accepted.plan_options[0].balance_warning
    assert "مادة ذات حمل حفظ (0200111)" in accepted.plan_options[0].balance_warning
    assert accepted == _case(HEAVY, accept=True)
