"""Privacy-minimized deterministic base-state fingerprinting."""

from __future__ import annotations

import hashlib
import json

from app.academic_digital_twin.models import AuthoritativeAcademicSnapshot


def calculate_base_state_fingerprint(snapshot: AuthoritativeAcademicSnapshot) -> str:
    """Hash only decision-relevant normalized state with canonical ordering."""
    payload = {
        "plan": [
            snapshot.plan_identity.university_id,
            snapshot.plan_identity.major_id,
            snapshot.plan_identity.study_plan_id,
            snapshot.plan_identity.plan_version,
        ],
        "attempts": sorted(
            [
                item.course_code,
                item.outcome.value,
                item.attempt_sequence,
                item.provenance,
                item.verification_state,
            ]
            for item in snapshot.attempts
        ),
        "eligibility_rules": sorted(
            [
                rule.course_code,
                rule.prerequisite_logic_status.value,
                sorted(
                    [
                        group.group_number,
                        group.dependency_type.value,
                        sorted(group.option_course_codes),
                    ]
                    for group in rule.dependency_groups
                ),
            ]
            for rule in snapshot.eligibility_catalog.plan_courses
        ),
        "course_catalog": sorted(
            [course.course_code, course.catalog_status.value]
            for course in snapshot.eligibility_catalog.courses
        ),
        "requirements": sorted(
            [
                group.group_id,
                group.group_code,
                group.scope,
                group.requirement_type.value,
                str(group.required_credit_hours),
                group.display_order,
            ]
            for group in snapshot.progress_catalog.requirement_groups
        ),
        "plan_courses": sorted(
            [
                course.plan_course_id,
                course.requirement_group_id,
                course.course_code,
                course.catalog_status.value,
                str(course.credit_hours),
                course.display_order,
            ]
            for course in snapshot.progress_catalog.plan_courses
        ),
        "plan_total_credits": str(snapshot.progress_catalog.study_plan.total_credit_hours),
        "planner_constraints": [
            str(snapshot.baseline_planner_constraints.max_credit_hours),
            snapshot.baseline_planner_constraints.max_courses,
            snapshot.baseline_planner_constraints.max_options,
        ],
        "path_constraints": [
            str(snapshot.baseline_path_constraints.max_credit_hours_per_semester),
            snapshot.baseline_path_constraints.max_courses_per_semester,
            snapshot.baseline_path_constraints.max_semesters_ahead,
            snapshot.baseline_path_constraints.max_paths,
        ],
        "source_versions": sorted(snapshot.source_versions),
        "engine_policy_versions": sorted(snapshot.engine_policy_versions),
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

