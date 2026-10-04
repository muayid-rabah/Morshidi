"""A bounded, read-only projection of existing progress and eligibility decisions.

Structural dependencies are not a prediction of completion time. In particular,
an OR group never makes any one option an unavoidable critical course.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from app.advisor.models import ResolvedCourseReference
from app.catalog.errors import CatalogIntegrityError
from app.catalog.roadmap_metadata import RoadmapPlanMetadata
from app.degree_path.models import DegreePathResult
from app.progress.engine import calculate_academic_progress
from app.progress.models import AcademicProgressCatalog, CourseProgressState
from app.roadmap.critical_path import (
    CRITICAL_PATH_POLICY_VERSION, calculate_structural_critical_path,
)
from app.roadmap.fingerprint import ROADMAP_SNAPSHOT_VERSION, academic_input_fingerprint
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    CanTakeCatalog, CanTakeDecision, CanTakeRequest, Decision, DependencyType,
    PrerequisiteLogicStatus, StudentCourseAttempt,
)


class RoadmapState(str, Enum):
    COMPLETED = "COMPLETED"
    IN_PROGRESS = "IN_PROGRESS"
    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PLANNED = "PLANNED"


@dataclass(frozen=True)
class RoadmapEdge:
    prerequisite_code: str
    target_code: str
    dependency_type: DependencyType
    group_number: int
    option_count: int


@dataclass(frozen=True)
class RoadmapCourse:
    course_code: str
    name_ar: str
    name_en: str | None
    credit_hours: Decimal
    requirement_group_code: str
    state: RoadmapState
    reasons: tuple[str, ...]
    missing_prerequisite_groups: tuple[tuple[str, ...], ...]
    prerequisite_logic_status: str
    structural_criticality: bool
    structural_impact_count: int
    planned_semester: int | None = None
    planned_order: int | None = None
    critical_path: bool = False
    critical_path_reason: str | None = None
    critical_path_length: int = 0
    critical_path_downstream_codes: tuple[str, ...] = ()
    critical_path_evidence_chain: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModeledPlanOverlay:
    """Only a deterministic planning result may create this server-side input."""

    study_plan_id: str
    base_snapshot_fingerprint: str
    policy_version: str
    semesters: tuple[tuple[int, tuple[str, ...]], ...]


def overlay_from_degree_path(result: DegreePathResult, base_snapshot_fingerprint: str) -> ModeledPlanOverlay:
    if not result.study_plan_id or not base_snapshot_fingerprint or not result.degree_path_policy_version:
        raise CatalogIntegrityError("Modeled path provenance is incomplete")
    if result.paths and result.paths[0].rank != 1:
        raise CatalogIntegrityError("Modeled path is not the first ranked option")
    return ModeledPlanOverlay(
        result.study_plan_id, base_snapshot_fingerprint, result.degree_path_policy_version,
        tuple((entry.semester_index, tuple(course.course_code for course in entry.plan_option.courses))
              for entry in result.paths[0].semesters) if result.paths else (),
    )


@dataclass(frozen=True)
class AcademicRoadmap:
    study_plan_id: str
    plan_number: str | None
    effective_year: int | None
    plan_updated_at: str | None
    generated_at: datetime
    plan_total_required_credits: Decimal
    completed_plan_credits: Decimal
    in_progress_plan_credits: Decimal
    remaining_plan_credits: Decimal
    courses: tuple[RoadmapCourse, ...]
    edges: tuple[RoadmapEdge, ...]
    limitations: tuple[str, ...]
    snapshot_fingerprint: str | None = None
    snapshot_contract_version: str = ROADMAP_SNAPSHOT_VERSION
    critical_path_policy_version: str = CRITICAL_PATH_POLICY_VERSION
    modeling_status: str = "NOT_REQUESTED"
    modeled_plan_policy_version: str | None = None
    source_type: str | None = None
    source_retrieved_at: str | None = None
    source_content_hash: str | None = None
    source_snapshot_ref: str | None = None
    source_status: str | None = None


def build_roadmap(
    progress_catalog: AcademicProgressCatalog,
    eligibility_catalog: CanTakeCatalog,
    course_names: tuple[ResolvedCourseReference, ...],
    attempts: tuple[StudentCourseAttempt, ...],
    *,
    institution_id: str,
    plan_metadata: RoadmapPlanMetadata | None = None,
    modeled_overlay: ModeledPlanOverlay | None = None,
    generated_at: datetime | None = None,
) -> AcademicRoadmap:
    """Use the same pure engines as the student endpoints, without per-course I/O."""
    plan = progress_catalog.study_plan
    if eligibility_catalog.study_plan_id != plan.study_plan_id:
        raise CatalogIntegrityError("Roadmap catalog plan mismatch")
    if plan_metadata is not None and plan_metadata.study_plan_id != plan.study_plan_id:
        raise CatalogIntegrityError("Roadmap plan metadata mismatch")
    progress = calculate_academic_progress(progress_catalog, attempts)
    codes = {course.course_code for course in progress.courses}
    rules = {rule.course_code: rule for rule in eligibility_catalog.plan_courses}
    names = {course.course_code: course for course in course_names}
    if len(rules) != len(eligibility_catalog.plan_courses) or codes != set(rules) or codes != set(names):
        raise CatalogIntegrityError("Roadmap catalogs do not describe the same plan courses")
    fingerprint = academic_input_fingerprint(progress_catalog, eligibility_catalog, course_names, attempts,
                                             plan_metadata, institution_id=institution_id)
    planned: dict[str, tuple[int, int]] = {}
    if modeled_overlay is not None:
        if modeled_overlay.study_plan_id != plan.study_plan_id or modeled_overlay.base_snapshot_fingerprint != fingerprint:
            raise CatalogIntegrityError("Modeled path belongs to a stale or different academic snapshot")
        if not modeled_overlay.policy_version:
            raise CatalogIntegrityError("Modeled path policy version is missing")
        for semester, semester_codes in modeled_overlay.semesters:
            if isinstance(semester, bool) or not isinstance(semester, int) or semester < 1:
                raise CatalogIntegrityError("Modeled semester index is invalid")
            for order, code in enumerate(semester_codes, 1):
                if code not in codes or code in planned:
                    raise CatalogIntegrityError("Modeled path contains unknown or duplicate plan course")
                planned[code] = (semester, order)

    edges = tuple(
        RoadmapEdge(option, rule.course_code, group.dependency_type, group.group_number,
                    len(group.option_course_codes))
        for rule in eligibility_catalog.plan_courses
        if rule.prerequisite_logic_status is PrerequisiteLogicStatus.VERIFIED
        for group in rule.dependency_groups
        for option in group.option_course_codes
        if option in codes
    )
    # This is structural impact only: single-option prerequisites to unfinished
    # courses. It is not a guaranteed graduation critical path or time estimate.
    unfinished = {course.course_code for course in progress.courses
                  if course.state is not CourseProgressState.COMPLETED}
    unique_downstream = {
        code: {edge.target_code for edge in edges
               if edge.prerequisite_code == code and edge.dependency_type is DependencyType.PREREQUISITE
               and edge.option_count == 1 and edge.target_code in unfinished}
        for code in codes
    }
    critical_paths = calculate_structural_critical_path(progress_catalog, eligibility_catalog, progress)
    nodes = []
    for course in progress.courses:
        code = course.course_code
        result = evaluate_can_take(eligibility_catalog, CanTakeRequest(plan.study_plan_id, code, attempts))
        if not isinstance(result, CanTakeDecision):
            raise CatalogIntegrityError("Roadmap eligibility result is not a decision")
        if code in planned and (course.state in {CourseProgressState.COMPLETED, CourseProgressState.IN_PROGRESS}
                                or result.decision is Decision.REVIEW_REQUIRED):
            raise CatalogIntegrityError("Modeled path selects an unavailable academic course")
        if course.state is CourseProgressState.COMPLETED:
            state = RoadmapState.COMPLETED
        elif course.state is CourseProgressState.IN_PROGRESS:
            state = RoadmapState.IN_PROGRESS
        elif result.decision is Decision.REVIEW_REQUIRED:
            state = RoadmapState.REVIEW_REQUIRED
        elif code in planned:
            state = RoadmapState.PLANNED
        elif result.decision is Decision.ELIGIBLE:
            state = RoadmapState.ELIGIBLE
        elif result.decision is Decision.NOT_ELIGIBLE:
            state = RoadmapState.BLOCKED
        else:
            state = RoadmapState.REVIEW_REQUIRED
        nodes.append(RoadmapCourse(
            code, names[code].canonical_arabic_name, names[code].canonical_english_name,
            course.credit_hours, course.requirement_group_code, state,
            tuple(reason.value for reason in result.reasons),
            tuple(group.option_course_codes for group in result.missing_dependency_groups),
            result.prerequisite_logic_status.value, bool(unique_downstream[code]),
            len(unique_downstream[code]), planned[code][0] if state is RoadmapState.PLANNED else None,
            planned[code][1] if state is RoadmapState.PLANNED else None,
            critical_paths[code].is_critical if code in critical_paths else False,
            critical_paths[code].reason_code if code in critical_paths else None,
            critical_paths[code].chain_length if code in critical_paths else 0,
            critical_paths[code].downstream_required_codes if code in critical_paths else (),
            critical_paths[code].evidence_chain if code in critical_paths else (),
        ))
    return AcademicRoadmap(
        plan.study_plan_id, plan_metadata.plan_number if plan_metadata else None,
        plan_metadata.effective_year if plan_metadata else None,
        plan_metadata.updated_at if plan_metadata else None,
        generated_at or datetime.now(timezone.utc),
        progress.plan_total_required_credits, progress.completed_plan_credits,
        progress.in_progress_plan_credits, progress.remaining_plan_credits,
        tuple(nodes), edges,
        ("Eligibility covers verified prerequisites only; offerings and registration are not confirmed.",
         "Structural critical path is a required prerequisite chain, not a graduation delay prediction.",
         "This live projection is not an immutable or official academic record."),
        fingerprint, ROADMAP_SNAPSHOT_VERSION, CRITICAL_PATH_POLICY_VERSION,
        "MODELED_PATH" if planned else "NO_VALID_PATH" if modeled_overlay else "NOT_REQUESTED",
        modeled_overlay.policy_version if modeled_overlay else None,
        plan_metadata.source_type if plan_metadata else None,
        plan_metadata.source_retrieved_at if plan_metadata else None,
        plan_metadata.source_content_hash if plan_metadata else None,
        plan_metadata.source_snapshot_ref if plan_metadata else None,
        plan_metadata.source_status if plan_metadata else None,
    )
