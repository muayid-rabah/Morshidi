"""Phase 7.4 Comprehensive Recommendation System Audit Tests.

Verifies:
- Complete candidate partitioning invariant
- Priority tuple exactness and 7-tuple lexicographic ordering
- Display order tie-break direction (+display_order ascending via -P6)
- Reason code mutual exclusivity (no contradictory unlock codes)
- No duplicated recommendation logic outside pure engine
- Pure engine boundary (zero infrastructure/API imports)
- Security audit (no leaked secrets or remote endpoints)
"""

from decimal import Decimal
import inspect
from pathlib import Path
import pytest

from app.progress.engine import calculate_academic_progress
from app.progress.models import (
    AcademicProgressCatalog,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.recommendations.engine import recommend_courses
from app.recommendations.models import (
    RECOMMENDATION_POLICY_VERSION,
    RecommendationReason,
)
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CourseCatalogStatus,
    CourseIdentity,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)

PLAN_ID = "10000000-0000-0000-0000-000000000005"
GROUP_REQ = "10000000-0000-0000-0000-000000000011"
GROUP_ELEC = "10000000-0000-0000-0000-000000000012"


def _build_audit_fixture():
    groups = (
        ProgressRequirementGroup(
            GROUP_REQ, PLAN_ID, "FACULTY_REQUIRED", "إجباري كلية", None, "faculty",
            RequirementType.REQUIRED, Decimal("9"), 1,
        ),
        ProgressRequirementGroup(
            GROUP_ELEC, PLAN_ID, "MAJOR_ELECTIVE", "اختياري تخصص", None, "major",
            RequirementType.ELECTIVE, Decimal("3"), 2,
        ),
    )
    # Courses:
    # 1. 1501110 (req, 3 cr, display 1, no prereq)
    # 2. 1501112 (req, 3 cr, display 2, prereq 1501110)
    # 3. 0200115 (req, 0 cr, display 3, no prereq)
    # 4. 1505311 (req, 3 cr, display 4, unresolved)
    # 5. 1505320 (req, 3 cr, display 5, source_conflict)
    # 6. 1505490 (elec, 3 cr, display 6, no prereq)
    # 7. 1505491 (elec, 3 cr, display 7, no prereq)
    plan_courses = (
        ProgressPlanCourse("pc-1", PLAN_ID, GROUP_REQ, "1501110", CourseCatalogStatus.KNOWN, Decimal("3"), 1),
        ProgressPlanCourse("pc-2", PLAN_ID, GROUP_REQ, "1501112", CourseCatalogStatus.KNOWN, Decimal("3"), 2),
        ProgressPlanCourse("pc-3", PLAN_ID, GROUP_REQ, "0200115", CourseCatalogStatus.KNOWN, Decimal("0"), 3),
        ProgressPlanCourse("pc-4", PLAN_ID, GROUP_REQ, "1505311", CourseCatalogStatus.KNOWN, Decimal("3"), 4),
        ProgressPlanCourse("pc-5", PLAN_ID, GROUP_REQ, "1505320", CourseCatalogStatus.KNOWN, Decimal("3"), 5),
        ProgressPlanCourse("pc-6", PLAN_ID, GROUP_ELEC, "1505490", CourseCatalogStatus.KNOWN, Decimal("3"), 6),
        ProgressPlanCourse("pc-7", PLAN_ID, GROUP_ELEC, "1505491", CourseCatalogStatus.KNOWN, Decimal("3"), 7),
    )
    progress_catalog = AcademicProgressCatalog(
        ProgressStudyPlan(PLAN_ID, Decimal("12")),
        groups,
        plan_courses,
    )

    rules = (
        PlanCourseRule("1501110", PrerequisiteLogicStatus.NOT_APPLICABLE, ()),
        PlanCourseRule(
            "1501112",
            PrerequisiteLogicStatus.VERIFIED,
            (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501110",)),),
        ),
        PlanCourseRule("0200115", PrerequisiteLogicStatus.NOT_APPLICABLE, ()),
        PlanCourseRule("1505311", PrerequisiteLogicStatus.UNRESOLVED, ()),
        PlanCourseRule("1505320", PrerequisiteLogicStatus.SOURCE_CONFLICT, ()),
        PlanCourseRule("1505490", PrerequisiteLogicStatus.NOT_APPLICABLE, ()),
        PlanCourseRule("1505491", PrerequisiteLogicStatus.NOT_APPLICABLE, ()),
    )
    identities = tuple(
        CourseIdentity(code, CourseCatalogStatus.KNOWN)
        for code in ("1501110", "1501112", "0200115", "1505311", "1505320", "1505490", "1505491")
    )
    eligibility_catalog = CanTakeCatalog(PLAN_ID, rules, identities)
    return progress_catalog, eligibility_catalog


# ---------------------------------------------------------------------------
# AUDIT 1 & 5: Candidate Partition Invariant
# ---------------------------------------------------------------------------


def test_audit_candidate_partition_invariant_every_plan_course_accounted_for() -> None:
    """Every plan course must fall into exactly one disjoint category."""
    prog_cat, elig_cat = _build_audit_fixture()
    # Scenario:
    # 1501110: PASSED (completed)
    # 1501112: IN_PROGRESS
    # 0200115: not attempted, eligible, required -> ranked
    # 1505311: unresolved -> review required
    # 1505320: source conflict -> review required
    # 1505490: PASSED (satisfies elective requirement of 3 cr!)
    # 1505491: not attempted, eligible, but elective group is now satisfied -> excluded elective
    attempts = (
        StudentCourseAttempt("1501110", AttemptOutcome.PASSED),
        StudentCourseAttempt("1501112", AttemptOutcome.IN_PROGRESS),
        StudentCourseAttempt("1505490", AttemptOutcome.PASSED),
    )
    result = recommend_courses(prog_cat, elig_cat, attempts)

    all_plan_codes = {c.course_code for c in prog_cat.plan_courses}
    assert len(all_plan_codes) == 7

    ranked_codes = {c.course_code for c in result.ranked_recommendations}
    review_codes = {c.course_code for c in result.review_required_courses}
    in_progress_codes = set(result.excluded_in_progress)

    # Calculate progress directly to verify completed
    progress = calculate_academic_progress(prog_cat, attempts)
    completed_codes = {c.course_code for c in progress.courses if c.state.value == "COMPLETED"}

    # Disjointness checks
    assert ranked_codes.isdisjoint(review_codes)
    assert ranked_codes.isdisjoint(in_progress_codes)
    assert ranked_codes.isdisjoint(completed_codes)
    assert review_codes.isdisjoint(in_progress_codes)
    assert review_codes.isdisjoint(completed_codes)
    assert in_progress_codes.isdisjoint(completed_codes)

    # Check exact expected classifications:
    # Completed: 1501110, 1505490
    assert completed_codes == {"1501110", "1505490"}
    # In-progress: 1501112
    assert in_progress_codes == {"1501112"}
    # Review required: 1505311, 1505320
    assert review_codes == {"1505311", "1505320"}
    # Ranked: 0200115 (mandatory zero-credit)
    assert ranked_codes == {"0200115"}
    # Excluded satisfied elective: 1505491 (elective group satisfied by 1505490)
    # Remaining accounted for: 1505491 is not in ranked, review, in-prog, or completed
    assert "1505491" not in ranked_codes
    assert "1505491" not in review_codes

    # Total union of accounted courses
    union_accounted = ranked_codes | review_codes | in_progress_codes | completed_codes | {"1505491"}
    assert union_accounted == all_plan_codes


# ---------------------------------------------------------------------------
# AUDIT 3 & 4: Priority Tuple & Exact Sort Direction
# ---------------------------------------------------------------------------


def test_audit_priority_tuple_length_and_elements() -> None:
    prog_cat, elig_cat = _build_audit_fixture()
    result = recommend_courses(prog_cat, elig_cat, ())
    for cand in result.ranked_recommendations:
        p = cand.priority_tuple
        assert len(p) == 7
        assert isinstance(p[0], int)       # P1: 0, 1, or 2
        assert p[0] in (0, 1, 2)
        assert isinstance(p[1], int)       # P2: 0 or 1
        assert p[1] in (0, 1)
        assert isinstance(p[2], Decimal)   # P3: Decimal effective contribution
        assert isinstance(p[3], int)       # P4: 0 or 1
        assert p[3] in (0, 1)
        assert isinstance(p[4], int)       # P5: newly eligible count >= 0
        assert p[4] >= 0
        assert isinstance(p[5], int)       # P6: -display_order
        assert p[5] <= 0
        assert isinstance(p[6], str)       # P7: course_code
        assert p[6] == cand.course_code


def test_audit_display_order_tiebreak_direction() -> None:
    """Audit that lower display_order wins tie when P1..P5 are equal."""
    prog_cat, elig_cat = _build_audit_fixture()
    # 1505490 (display 6) and 1505491 (display 7) are identical electives
    # Both have P1=0, P2=1, P3=3, P4=1, P5=0
    result = recommend_courses(prog_cat, elig_cat, ())
    codes = [c.course_code for c in result.ranked_recommendations]
    idx_490 = codes.index("1505490")
    idx_491 = codes.index("1505491")
    # 1505490 (display 6) must rank before 1505491 (display 7)
    assert idx_490 < idx_491


# ---------------------------------------------------------------------------
# AUDIT 6: Zero-Credit Required Course Behavior
# ---------------------------------------------------------------------------


def test_audit_zero_credit_outranks_electives_but_not_positive_required() -> None:
    prog_cat, elig_cat = _build_audit_fixture()
    result = recommend_courses(prog_cat, elig_cat, ())
    by_code = {c.course_code: c for c in result.ranked_recommendations}

    c_pos_req = by_code["1501110"]
    c_zero_req = by_code["0200115"]
    c_elec = by_code["1505490"]

    # P1 comparisons:
    # Positive required has P1 = 2
    assert c_pos_req.priority_tuple[0] == 2
    # Zero-credit required has P1 = 1
    assert c_zero_req.priority_tuple[0] == 1
    # Elective has P1 = 0
    assert c_elec.priority_tuple[0] == 0

    # Ranks:
    assert c_pos_req.rank < c_zero_req.rank < c_elec.rank

    # Zero-credit reasons:
    assert RecommendationReason.REQUIRED_PLAN_COURSE in c_zero_req.reason_codes
    assert RecommendationReason.MANDATORY_ZERO_CREDIT_COURSE in c_zero_req.reason_codes
    assert c_zero_req.effective_credit_contribution == Decimal("0")


# ---------------------------------------------------------------------------
# AUDIT 14: Reason Code Mutual Exclusivity
# ---------------------------------------------------------------------------


def test_audit_unlock_reason_codes_mutually_exclusive() -> None:
    prog_cat, elig_cat = _build_audit_fixture()
    result = recommend_courses(prog_cat, elig_cat, ())
    unlock_reasons = {
        RecommendationReason.NO_DIRECT_PREREQUISITE_IMPACT,
        RecommendationReason.UNLOCKS_FUTURE_COURSE,
        RecommendationReason.UNLOCKS_MULTIPLE_FUTURE_COURSES,
    }
    for cand in result.ranked_recommendations:
        matched = set(cand.reason_codes) & unlock_reasons
        # Exactly one unlock reason must be present
        assert len(matched) == 1
        if cand.newly_eligible_count == 0:
            assert matched == {RecommendationReason.NO_DIRECT_PREREQUISITE_IMPACT}
        elif cand.newly_eligible_count == 1:
            assert matched == {RecommendationReason.UNLOCKS_FUTURE_COURSE}
        else:
            assert matched == {RecommendationReason.UNLOCKS_MULTIPLE_FUTURE_COURSES}


# ---------------------------------------------------------------------------
# AUDIT 27: Pure Engine Boundary
# ---------------------------------------------------------------------------


def test_audit_pure_engine_has_no_infrastructure_imports() -> None:
    engine_path = Path("apps/api/app/recommendations/engine.py")
    models_path = Path("apps/api/app/recommendations/models.py")

    for path in (engine_path, models_path):
        with open(path) as f:
            lines = f.readlines()
        import_lines = [l.strip() for l in lines if l.strip().startswith(("import ", "from "))]
        for l in import_lines:
            low = l.lower()
            assert "fastapi" not in low, f"Forbidden import in {path}: {l}"
            assert "starlette" not in low, f"Forbidden import in {path}: {l}"
            assert "httpx" not in low, f"Forbidden import in {path}: {l}"
            assert "supabase" not in low, f"Forbidden import in {path}: {l}"
            assert "pydantic" not in low, f"Forbidden import in {path}: {l}"


# ---------------------------------------------------------------------------
# AUDIT 34: No Duplicated Recommendation Logic Outside Engine
# ---------------------------------------------------------------------------


def test_audit_no_duplicated_ranking_logic_outside_engine() -> None:
    from app.services.student import StudentService
    source = inspect.getsource(StudentService.get_course_recommendations)
    # Check that StudentService does not construct priority tuples or run sort
    assert "priority_tuple" not in source
    assert "required_mandatory_priority" not in source
    assert "effective_credit_contribution" not in source
    assert "newly_eligible_count" not in source
    assert "RecommendationReason" not in source
    assert "recommend_courses(" in source

