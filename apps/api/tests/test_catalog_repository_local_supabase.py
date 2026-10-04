"""Opt-in, read-only validation against the local Supabase catalog only."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.catalog.errors import TargetCourseNotFound, TargetCourseNotInStudyPlan
from app.catalog.supabase_repository import SupabaseAcademicCatalogRepository
from app.rules.evaluator import evaluate_can_take
from app.rules.models import AttemptOutcome, CanTakeRequest, Decision, StudentCourseAttempt

LOCAL_URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
LOCAL_SERVER_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
LOCAL_PLAN_ID = os.getenv("MORSHIDI_LOCAL_STUDY_PLAN_ID")

pytestmark = pytest.mark.skipif(
    not all((LOCAL_URL, LOCAL_SERVER_KEY, LOCAL_PLAN_ID)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values to run integration tests",
)


def local_load(target_course_code: str):
    async def operation():
        repository = SupabaseAcademicCatalogRepository(LOCAL_URL or "", LOCAL_SERVER_KEY or "")
        try:
            return await repository.load_target_rules(LOCAL_PLAN_ID or "", target_course_code)
        finally:
            await repository.close()

    return asyncio.run(operation())


def test_local_advisor_catalog_excludes_unnamed_referenced_only_prerequisites() -> None:
    async def operation():
        repository = SupabaseAcademicCatalogRepository(LOCAL_URL or "", LOCAL_SERVER_KEY or "")
        try:
            return await repository.load_advisor_course_catalog(LOCAL_PLAN_ID or "")
        finally:
            await repository.close()

    catalog = asyncio.run(operation())
    codes = {course.course_code for course in catalog}
    assert "1501112" in codes
    assert "0300103" not in codes


def test_local_catalog_maps_required_target_states() -> None:
    not_applicable = local_load("0200115").plan_courses[0]
    verified = local_load("1501112").plan_courses[0]
    unresolved = local_load("1505311").plan_courses[0]
    conflict = local_load("1505320").plan_courses[0]
    assert not_applicable.prerequisite_logic_status.value == "not_applicable"
    assert not_applicable.dependency_groups == ()
    assert verified.prerequisite_logic_status.value == "verified"
    assert verified.dependency_groups[0].option_course_codes == ("1501110",)
    assert unresolved.prerequisite_logic_status.value == "unresolved"
    assert unresolved.dependency_groups == ()
    assert conflict.prerequisite_logic_status.value == "source_conflict"
    assert conflict.dependency_groups == ()


def test_local_referenced_only_and_unknown_targets_are_distinct() -> None:
    with pytest.raises(TargetCourseNotInStudyPlan):
        local_load("0300103")
    with pytest.raises(TargetCourseNotFound):
        local_load("9999999")


def test_local_repository_catalog_drives_engine_without_translation() -> None:
    catalog = local_load("1501112")
    passed = evaluate_can_take(
        catalog,
        CanTakeRequest(
            LOCAL_PLAN_ID or "",
            "1501112",
            (StudentCourseAttempt("1501110", AttemptOutcome.PASSED),),
        ),
    )
    failed = evaluate_can_take(
        catalog,
        CanTakeRequest(
            LOCAL_PLAN_ID or "",
            "1501112",
            (StudentCourseAttempt("1501110", AttemptOutcome.FAILED),),
        ),
    )
    conflict = evaluate_can_take(
        local_load("1505320"),
        CanTakeRequest(LOCAL_PLAN_ID or "", "1505320", ()),
    )
    assert passed.decision is Decision.ELIGIBLE
    assert failed.decision is Decision.NOT_ELIGIBLE
    assert conflict.decision is Decision.REVIEW_REQUIRED
