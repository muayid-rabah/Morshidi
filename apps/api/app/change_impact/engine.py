"""Pure, bounded projection of proposed changes over isolated academic snapshots.

The existing Phase 5/6 engines alone decide eligibility and progress. This
module neither edits a repository object nor computes a shadow academic rule.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.progress.engine import calculate_academic_progress
from app.progress.models import AcademicProgressCatalog
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    CanTakeCatalog, CanTakeDecision, CanTakeRequest, DependencyGroup,
    PrerequisiteLogicStatus, StudentCourseAttempt,
)

from .models import (
    AffectedFact, ChangeAuthority, ChangeDelta, ChangeImpactReport,
    CourseCreditHoursDelta, DecisionClass, ImpactComparison, ImpactLimitation,
    ImpactStatus, PolicyVersionDelta, PrerequisiteGroupDelta,
    RequirementGroupCreditDelta,
)


_PREREQ_DECISIONS = (
    DecisionClass.ELIGIBILITY, DecisionClass.RECOMMENDATIONS,
    DecisionClass.SEMESTER_PLANNER, DecisionClass.DEGREE_PATH,
)
_CREDIT_DECISIONS = (
    DecisionClass.PROGRESS, DecisionClass.RECOMMENDATIONS,
    DecisionClass.SEMESTER_PLANNER, DecisionClass.DEGREE_PATH,
)
CHANGE_FINGERPRINT_VERSION = "P13_TENANT_SCOPED_V2"


def fingerprint(delta: ChangeDelta, *, university_id: UUID) -> str:
    """Stable tenant-scoped semantic identity; no actor, student ID, or timestamp."""
    canonical = json.dumps({"schema": CHANGE_FINGERPRINT_VERSION,
                            "university_id": str(university_id),
                            "delta": delta.model_dump(mode="json", exclude={"provenance_reference"})}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_change_impact(
    delta: ChangeDelta, *, university_id: UUID,
    eligibility_catalog: CanTakeCatalog | None = None,
    progress_catalog: AcademicProgressCatalog | None = None,
    student_attempts: tuple[StudentCourseAttempt, ...] | None = None,
    reported_cumulative_gpa: Decimal | None = None,
    reported_gpa_scale: Decimal | None = None,
    reported_earned_credit_hours: Decimal | None = None,
    max_affected_courses: int = 100, max_depth: int = 20,
) -> ChangeImpactReport:
    if max_affected_courses < 1 or max_affected_courses > 100 or max_depth < 1 or max_depth > 20:
        raise ValueError("invalid impact fan-out bound")
    if not isinstance(university_id, UUID):
        raise ValueError("authorized university required")
    if isinstance(delta, PolicyVersionDelta):
        return _report(delta, university_id, ImpactStatus.REVIEW_REQUIRED,
                       facts=(AffectedFact(fact_type="POLICY_VERSION", reference=delta.document_code,
                                           before=delta.old_version, after=delta.new_version),),
                       decisions=(DecisionClass.POLICY_CONSULTATION,),
                       limitations=(ImpactLimitation.POLICY_CHANGE_NOT_MAPPED_TO_DETERMINISTIC_RULE,),
                       review=True)
    if isinstance(delta, PrerequisiteGroupDelta):
        return _prerequisite(delta, university_id, eligibility_catalog, student_attempts,
                             max_affected_courses, max_depth)
    if isinstance(delta, RequirementGroupCreditDelta):
        return _requirement(delta, university_id, progress_catalog, student_attempts,
                            reported_cumulative_gpa, reported_gpa_scale, reported_earned_credit_hours)
    if isinstance(delta, CourseCreditHoursDelta):
        return _course_credit(delta, university_id, progress_catalog, student_attempts,
                              reported_cumulative_gpa, reported_gpa_scale, reported_earned_credit_hours)
    raise ValueError("unsupported change delta")


def _prerequisite(
    delta: PrerequisiteGroupDelta, university_id: UUID, catalog: CanTakeCatalog | None,
    attempts: tuple[StudentCourseAttempt, ...] | None, max_nodes: int, max_depth: int,
) -> ChangeImpactReport:
    if catalog is None or catalog.study_plan_id != str(delta.study_plan_id):
        return _report(delta, university_id, ImpactStatus.UNKNOWN,
                       limitations=(ImpactLimitation.RECOMPUTATION_INPUT_UNAVAILABLE,), review=True)
    rules = {rule.course_code: rule for rule in catalog.plan_courses}
    target = rules.get(delta.target_course_code)
    if target is None:
        return _report(delta, university_id, ImpactStatus.UNKNOWN,
                       limitations=(ImpactLimitation.RECOMPUTATION_INPUT_UNAVAILABLE,), review=True)
    old_group = next((group for group in target.dependency_groups
                      if group.group_number == delta.group_number), None)
    if (target.prerequisite_logic_status is not PrerequisiteLogicStatus.VERIFIED
            or old_group is None or old_group.dependency_type is not delta.dependency_type
            or old_group.option_course_codes != delta.old_option_course_codes):
        return _report(delta, university_id, ImpactStatus.REVIEW_REQUIRED,
                       facts=(AffectedFact(fact_type="PREREQUISITE_GROUP",
                                           reference=f"{delta.target_course_code}:{delta.group_number}"),),
                       limitations=(ImpactLimitation.BASELINE_MISMATCH,), review=True)
    if any(code not in {course.course_code for course in catalog.courses}
           for code in delta.new_option_course_codes):
        return _report(delta, university_id, ImpactStatus.REVIEW_REQUIRED,
                       limitations=(ImpactLimitation.SOURCE_CONFLICT_OR_UNRESOLVED,), review=True)
    changed = delta.new_option_course_codes != delta.old_option_course_codes
    if not changed:
        return _report(delta, university_id, ImpactStatus.UNCHANGED)
    affected = _downstream(rules, delta.target_course_code, max_nodes, max_depth)
    if affected is None:
        return _report(delta, university_id, ImpactStatus.REVIEW_REQUIRED,
                       limitations=(ImpactLimitation.IMPACT_FANOUT_LIMIT_EXCEEDED,), review=True)
    proposed_group = replace(old_group, option_course_codes=delta.new_option_course_codes)
    proposed_target = replace(target, dependency_groups=tuple(
        proposed_group if group.group_number == delta.group_number else group
        for group in target.dependency_groups))
    proposed = replace(catalog, plan_courses=tuple(
        proposed_target if rule.course_code == delta.target_course_code else rule
        for rule in catalog.plan_courses))
    comparisons: list[ImpactComparison] = []
    limitations = [ImpactLimitation.SOURCE_VERSION_UNVERIFIED]
    if attempts is not None:
        for code in affected:
            request = CanTakeRequest(catalog.study_plan_id, code, attempts)
            before = evaluate_can_take(catalog, request)
            after = evaluate_can_take(proposed, request)
            if not isinstance(before, CanTakeDecision) or not isinstance(after, CanTakeDecision):
                limitations.append(ImpactLimitation.SOURCE_CONFLICT_OR_UNRESOLVED)
                continue
            if (before.decision.value == "REVIEW_REQUIRED" or after.decision.value == "REVIEW_REQUIRED"):
                limitations.append(ImpactLimitation.SOURCE_CONFLICT_OR_UNRESOLVED)
            comparisons.append(_comparison(DecisionClass.ELIGIBILITY, code,
                                           before.decision.value, after.decision.value))
    limitations.append(ImpactLimitation.RECOMPUTATION_INPUT_UNAVAILABLE)
    return _report(delta, university_id, ImpactStatus.CHANGED,
                   facts=(AffectedFact(fact_type="PREREQUISITE_GROUP",
                                       reference=f"{delta.target_course_code}:{delta.group_number}",
                                       before=",".join(delta.old_option_course_codes),
                                       after=",".join(delta.new_option_course_codes)),),
                   decisions=_PREREQ_DECISIONS, courses=affected,
                   comparisons=tuple(comparisons), limitations=tuple(limitations), review=True)


def _downstream(rules: dict, first: str, max_nodes: int, max_depth: int) -> tuple[str, ...] | None:
    reverse: dict[str, set[str]] = {}
    for rule in rules.values():
        for group in rule.dependency_groups:
            for option in group.option_course_codes:
                reverse.setdefault(option, set()).add(rule.course_code)
    queue = [(first, 0)]
    seen = {first}
    while queue:
        source, depth = queue.pop(0)
        downstream = sorted(reverse.get(source, ()))
        if downstream and depth >= max_depth:
            return None
        for target in downstream:
            if target not in seen:
                seen.add(target)
                if len(seen) > max_nodes:
                    return None
                queue.append((target, depth + 1))
    return tuple(sorted(seen))


def _requirement(
    delta: RequirementGroupCreditDelta, university_id: UUID,
    catalog: AcademicProgressCatalog | None, attempts: tuple[StudentCourseAttempt, ...] | None,
    gpa: Decimal | None, scale: Decimal | None, earned: Decimal | None,
) -> ChangeImpactReport:
    if catalog is None or catalog.study_plan.study_plan_id != str(delta.study_plan_id):
        return _report(delta, university_id, ImpactStatus.UNKNOWN,
                       limitations=(ImpactLimitation.RECOMPUTATION_INPUT_UNAVAILABLE,), review=True)
    group = next((item for item in catalog.requirement_groups
                  if item.group_code == delta.requirement_group_code), None)
    if group is None or group.required_credit_hours != delta.old_required_credits:
        return _report(delta, university_id, ImpactStatus.REVIEW_REQUIRED,
                       limitations=(ImpactLimitation.BASELINE_MISMATCH,), review=True)
    if delta.old_required_credits == delta.new_required_credits:
        return _report(delta, university_id, ImpactStatus.UNCHANGED)
    proposed_group = replace(group, required_credit_hours=delta.new_required_credits)
    proposed = replace(catalog, requirement_groups=tuple(
        proposed_group if item.group_id == group.group_id else item
        for item in catalog.requirement_groups))
    courses = tuple(sorted(item.course_code for item in catalog.plan_courses
                           if item.requirement_group_id == group.group_id))
    comparisons = _progress_comparisons(catalog, proposed, attempts, gpa, scale, earned,
                                        group.group_code)
    return _report(delta, university_id, ImpactStatus.CHANGED,
                   facts=(AffectedFact(fact_type="REQUIREMENT_GROUP_CREDITS", reference=group.group_code,
                                       before=str(delta.old_required_credits),
                                       after=str(delta.new_required_credits)),),
                   decisions=_CREDIT_DECISIONS, courses=courses, groups=(group.group_code,),
                   comparisons=comparisons,
                   limitations=(ImpactLimitation.SOURCE_VERSION_UNVERIFIED,
                                ImpactLimitation.RECOMPUTATION_INPUT_UNAVAILABLE), review=True)


def _course_credit(
    delta: CourseCreditHoursDelta, university_id: UUID,
    catalog: AcademicProgressCatalog | None, attempts: tuple[StudentCourseAttempt, ...] | None,
    gpa: Decimal | None, scale: Decimal | None, earned: Decimal | None,
) -> ChangeImpactReport:
    if catalog is None or catalog.study_plan.study_plan_id != str(delta.study_plan_id):
        return _report(delta, university_id, ImpactStatus.UNKNOWN,
                       limitations=(ImpactLimitation.RECOMPUTATION_INPUT_UNAVAILABLE,), review=True)
    course = next((item for item in catalog.plan_courses if item.course_code == delta.course_code), None)
    if course is None or course.credit_hours != delta.old_credit_hours:
        return _report(delta, university_id, ImpactStatus.REVIEW_REQUIRED,
                       limitations=(ImpactLimitation.BASELINE_MISMATCH,), review=True)
    if delta.old_credit_hours == delta.new_credit_hours:
        return _report(delta, university_id, ImpactStatus.UNCHANGED)
    proposed_course = replace(course, credit_hours=delta.new_credit_hours)
    proposed = replace(catalog, plan_courses=tuple(
        proposed_course if item.plan_course_id == course.plan_course_id else item
        for item in catalog.plan_courses))
    group = next(item.group_code for item in catalog.requirement_groups
                 if item.group_id == course.requirement_group_id)
    comparisons = _progress_comparisons(catalog, proposed, attempts, gpa, scale, earned, group)
    return _report(delta, university_id, ImpactStatus.CHANGED,
                   facts=(AffectedFact(fact_type="COURSE_CREDIT_HOURS", reference=course.course_code,
                                       before=str(delta.old_credit_hours),
                                       after=str(delta.new_credit_hours)),),
                   decisions=_CREDIT_DECISIONS, courses=(course.course_code,), groups=(group,),
                   comparisons=comparisons,
                   limitations=(ImpactLimitation.SOURCE_VERSION_UNVERIFIED,
                                ImpactLimitation.RECOMPUTATION_INPUT_UNAVAILABLE), review=True)


def _progress_comparisons(
    before_catalog: AcademicProgressCatalog, after_catalog: AcademicProgressCatalog,
    attempts: tuple[StudentCourseAttempt, ...] | None, gpa: Decimal | None,
    scale: Decimal | None, earned: Decimal | None, group_code: str,
) -> tuple[ImpactComparison, ...]:
    if attempts is None:
        return ()
    kwargs = dict(reported_cumulative_gpa=gpa, reported_gpa_scale=scale,
                  reported_earned_credit_hours=earned)
    before = calculate_academic_progress(before_catalog, attempts, **kwargs)
    after = calculate_academic_progress(after_catalog, attempts, **kwargs)
    before_group = next(item for item in before.requirement_groups if item.group_code == group_code)
    after_group = next(item for item in after.requirement_groups if item.group_code == group_code)
    return (
        _comparison(DecisionClass.PROGRESS, "completed_plan_credits",
                    str(before.completed_plan_credits), str(after.completed_plan_credits)),
        _comparison(DecisionClass.PROGRESS, "remaining_plan_credits",
                    str(before.remaining_plan_credits), str(after.remaining_plan_credits)),
        _comparison(DecisionClass.PROGRESS, f"group:{group_code}:remaining_credits",
                    str(before_group.remaining_required_credits),
                    str(after_group.remaining_required_credits)),
    )


def _comparison(decision: DecisionClass, reference: str, before: str, after: str) -> ImpactComparison:
    return ImpactComparison(decision_class=decision, reference=reference, before=before, after=after,
                            status=ImpactStatus.UNCHANGED if before == after else ImpactStatus.CHANGED)


def _report(
    delta: ChangeDelta, university_id: UUID, status: ImpactStatus, *,
    facts: tuple[AffectedFact, ...] = (), decisions: tuple[DecisionClass, ...] = (),
    courses: tuple[str, ...] = (), groups: tuple[str, ...] = (),
    comparisons: tuple[ImpactComparison, ...] = (),
    limitations: tuple[ImpactLimitation, ...] = (), review: bool = False,
) -> ChangeImpactReport:
    return ChangeImpactReport(
        change_id=fingerprint(delta, university_id=university_id), change_type=delta.change_type,
        change_authority=ChangeAuthority.PROPOSED_ANALYST_CHANGE,
        provenance_reference="sha256:" + hashlib.sha256(
            delta.provenance_reference.encode("utf-8")).hexdigest(),
        university_id=university_id,
        study_plan_id=getattr(delta, "study_plan_id", None), old_version=delta.old_version,
        new_version=delta.new_version, impact_status=status,
        affected_facts=facts, affected_decision_types=tuple(sorted(set(decisions))),
        structurally_affected_courses=tuple(sorted(set(courses))),
        affected_requirement_groups=tuple(sorted(set(groups))),
        comparisons=tuple(sorted(comparisons, key=lambda item: (item.decision_class, item.reference))),
        requires_human_review=review, limitations=tuple(sorted(set(limitations))),
        generated_at=datetime.now(timezone.utc),
    )
