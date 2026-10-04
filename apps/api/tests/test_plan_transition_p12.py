"""P12 local-only deterministic contracts; no database or synthetic tenant needed."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from app.plan_transition.engine import (TransitionIntegrityError, evaluate_transition,
                                        project_major_transfer)
from app.plan_transition.equivalency import decide_equivalency
from app.plan_transition.ingestion import (IngestionState, ModeledApproval,
                                           approve_local_version, publish_local_version,
                                           stage_structured_import)
from app.plan_transition.provider import IsolatedInMemoryPlanProvider
from app.plan_transition.publication import (ModeledVersionRegistry, ReconciliationStatus,
                                              reconcile_versions)
from app.plan_transition.models import (CompletedCourse, CourseIdentity, CreditStatus,
                                        EquivalencyRule, EquivalencyStatus,
                                        GrandfatheringAction, PlanCourse, PlanIdentity,
                                        PlanVersion, RequirementGroup, TransitionRule)

TODAY = date(2026, 10, 1)
SCOPE = "isolated-p12-test-institution"


def identity(version: str, major: str = "major-a") -> PlanIdentity:
    return PlanIdentity(SCOPE, "program-a", major, "plan-a", version,
                        date(2025, 1, 1), None, "isolated-test-v1")


def course(course_id: str, group: str = "core", code: str | None = None,
           prerequisites: tuple[str, ...] = ()) -> PlanCourse:
    return PlanCourse(CourseIdentity(SCOPE, course_id, code or course_id),
                      group, Decimal(3), prerequisites)


def plan(version: str, courses: tuple[PlanCourse, ...],
         major: str = "major-a", required: int = 6) -> PlanVersion:
    return PlanVersion(identity(version, major), (RequirementGroup("core", Decimal(required)),),
                       courses, "test-source-hash", "test-content-" + version + major,
                       "isolated-in-memory-test")


def attempt(plan_version: PlanVersion, item: PlanCourse) -> CompletedCourse:
    return CompletedCourse(item.identity, item.credits, plan_version.identity.key)


def rule(source: PlanVersion, target: PlanVersion, old: PlanCourse, new: PlanCourse,
         *, rule_id: str = "eq-1", status: str = "APPROVED",
         end: date | None = None) -> EquivalencyRule:
    return EquivalencyRule(rule_id, old.identity, new.identity,
                           source.identity.key, target.identity.key,
                           date(2025, 1, 1), end, "isolated-test-authority",
                           "v1", status, "isolated-test-rule")


def document() -> dict:
    return {"schema_version": "P12_PLAN_V1", "identity": {
        "institution_id": SCOPE, "program_id": "program-a", "major_id": "major-a",
        "plan_id": "plan-a", "version_id": "v1", "effective_from": "2025-01-01",
        "effective_to": None, "source_version": "local-test-v1"},
        "groups": [{"group_id": "core", "required_credits": "6"}],
        "courses": [{"course_id": "a", "code": "101", "group_id": "core", "credits": "3", "prerequisites": []},
                    {"course_id": "b", "code": "102", "group_id": "core", "credits": "3", "prerequisites": ["a"]}]}


def test_two_versions_and_plan_course_identity_do_not_collide():
    old, new = plan("v1", (course("a", code="101"),)), plan("v2", (course("b", code="101"),))
    assert old.identity.key != new.identity.key
    assert old.courses[0].identity.key != new.courses[0].identity.key
    result = evaluate_transition(old, new, (attempt(old, old.courses[0]),), (), (), TODAY)
    assert result.lines[0].status is CreditStatus.UNRESOLVED
    assert result.recognized_credits == 0


def test_shared_course_identity_keeps_plan_specific_credits_groups_and_prerequisites():
    shared = CourseIdentity(SCOPE, "shared-course-id", "CS101")
    old = PlanVersion(identity("v1"), (RequirementGroup("old-group", Decimal(3)),),
                      (PlanCourse(shared, "old-group", Decimal(3), ()),),
                      "source-a", "content-a", "isolated-test")
    new = PlanVersion(identity("v2"), (RequirementGroup("new-group", Decimal(4)),),
                      (PlanCourse(shared, "new-group", Decimal(4), ("other-course-id",)),
                       PlanCourse(CourseIdentity(SCOPE, "other-course-id", "CS100"),
                                  "new-group", Decimal(0))),
                      "source-b", "content-b", "isolated-test")
    assert old.courses[0].identity.key == new.courses[0].identity.key
    assert old.courses[0].credits == 3 and new.courses[0].credits == 4
    assert old.courses[0].group_id != new.courses[0].group_id
    assert old.courses[0].prerequisites != new.courses[0].prerequisites
    result = evaluate_transition(old, new, (attempt(old, old.courses[0]),), (), (), TODAY)
    assert result.recognized_credits == 3
    assert result.changed_prerequisites == ("shared-course-id",)


def test_exact_equivalency_is_scoped_and_does_not_chain():
    old = plan("v1", (course("a"),))
    new = plan("v2", (course("b"), course("c")))
    direct = rule(old, new, old.courses[0], new.courses[0])
    chained = rule(old, new, new.courses[0], new.courses[1], rule_id="eq-2")
    assert decide_equivalency(old.courses[0].identity, new.courses[0].identity,
                              old.identity, new.identity, TODAY, (direct,)).status is EquivalencyStatus.EQUIVALENT
    assert decide_equivalency(old.courses[0].identity, new.courses[1].identity,
                              old.identity, new.identity, TODAY, (direct, chained)).status is EquivalencyStatus.UNRESOLVED
    other = plan("v3", new.courses)
    assert decide_equivalency(old.courses[0].identity, new.courses[0].identity,
                              old.identity, other.identity, TODAY, (direct,)).status is EquivalencyStatus.NOT_APPLICABLE


def test_expiry_denial_draft_and_overlap_never_grant():
    old, new = plan("v1", (course("a"),)), plan("v2", (course("b"),))
    first = rule(old, new, old.courses[0], new.courses[0])
    kwargs = (old.courses[0].identity, new.courses[0].identity, old.identity, new.identity, TODAY)
    assert decide_equivalency(*kwargs, (rule(old, new, old.courses[0], new.courses[0], end=date(2025, 2, 1)),)).status is EquivalencyStatus.EXPIRED
    assert decide_equivalency(*kwargs, (rule(old, new, old.courses[0], new.courses[0], status="DENIED"),)).status is EquivalencyStatus.NOT_EQUIVALENT
    assert decide_equivalency(*kwargs, (rule(old, new, old.courses[0], new.courses[0], status="DRAFT"),)).status is EquivalencyStatus.UNRESOLVED
    assert decide_equivalency(*kwargs, (first, rule(old, new, old.courses[0], new.courses[0], rule_id="eq-2"))).status is EquivalencyStatus.CONFLICT


def test_conflicting_targets_and_cycles_are_not_granted():
    old = plan("v1", (course("a"), course("b")))
    new = plan("v2", (course("a"), course("b"), course("c")))
    first = rule(old, new, old.courses[0], new.courses[1])
    alternative = rule(old, new, old.courses[0], new.courses[2], rule_id="eq-2")
    decision = decide_equivalency(old.courses[0].identity, new.courses[1].identity,
                                  old.identity, new.identity, TODAY, (first, alternative))
    assert decision.status is EquivalencyStatus.CONFLICT
    reverse = rule(old, new, old.courses[1], new.courses[0], rule_id="eq-3")
    cycle = decide_equivalency(old.courses[0].identity, new.courses[1].identity,
                               old.identity, new.identity, TODAY, (first, reverse))
    assert cycle.status is EquivalencyStatus.CONFLICT


def test_transition_recognition_delta_and_no_write():
    old = plan("v1", (course("a"), course("removed")))
    new = plan("v2", (course("a"), course("new")))
    completed = (attempt(old, old.courses[0]),)
    before = (old, new, completed)
    result = evaluate_transition(old, new, completed, (), (), TODAY)
    assert (old, new, completed) == before
    assert result.recognized_credits == 3
    assert result.remaining_target_credits == 3
    assert result.new_requirements == ("new",)
    assert result.removed_requirements == ("removed",)
    assert CreditStatus.NEW_REQUIREMENT in {line.status for line in result.lines}
    assert CreditStatus.REMOVED_REQUIREMENT in {line.status for line in result.lines}
    assert result.fingerprint == evaluate_transition(old, new, completed, (), (), TODAY).fingerprint
    assert result.label == "MODELED_UNOFFICIAL_NO_WRITE"


def test_changed_group_and_prerequisite_constraints_are_visible():
    old = plan("v1", (course("a"), course("b", prerequisites=("a",))), required=6)
    new = plan("v2", (course("a"), course("b")), required=3)
    result = evaluate_transition(old, new, (attempt(old, old.courses[0]),), (), (), TODAY)
    assert result.changed_groups == ("core",)
    assert result.changed_prerequisites == ("b",)
    assert result.fingerprint != evaluate_transition(new, old, (), (), (), TODAY).fingerprint


def test_group_credit_cap_prevents_overstated_recognition():
    old = plan("v1", (course("a"), course("b")), required=6)
    new = plan("v2", (course("a"), course("b")), required=3)
    result = evaluate_transition(old, new, tuple(attempt(old, item) for item in old.courses), (), (), TODAY)
    assert result.recognized_credits == 3
    assert result.unresolved_credits == 3
    assert result.remaining_target_credits == 0


def test_equivalent_credit_requires_exact_rule_and_exposes_rule_id():
    old, new = plan("v1", (course("a"),)), plan("v2", (course("b"),))
    result = evaluate_transition(old, new, (attempt(old, old.courses[0]),),
                                 (rule(old, new, old.courses[0], new.courses[0]),), (), TODAY)
    assert result.lines[0].status is CreditStatus.EQUIVALENT
    assert result.lines[0].rule_ids == ("eq-1",)


def test_grandfathering_requires_explicit_rule_and_can_demand_review():
    old, new = plan("v1", (course("a", "old"),)), plan("v2", (course("a", "core"),))
    review = TransitionRule("tr-1", old.identity.key, new.identity.key, "core",
                            GrandfatheringAction.MANUAL_REVIEW_REQUIRED,
                            date(2025, 1, 1), None, "isolated-test-rule")
    result = evaluate_transition(old, new, (attempt(old, old.courses[0]),), (), (review,), TODAY)
    assert result.lines[0].status is CreditStatus.REVIEW_REQUIRED
    assert result.lines[0].rule_ids == ("tr-1",)


def test_cross_major_projection_is_no_write_and_institution_scoped():
    old = plan("v1", (course("a"),), major="major-a")
    new = plan("v1", (course("b"),), major="major-b")
    projection = project_major_transfer(old, new, (attempt(old, old.courses[0]),),
                                        (rule(old, new, old.courses[0], new.courses[0]),), (), TODAY)
    assert projection.recognized_credits == 3
    assert projection.target_plan_key[2] == "major-b"
    assert new.courses[0].identity.course_id == "b"
    with pytest.raises(TransitionIntegrityError):
        project_major_transfer(old, old, (), (), (), TODAY)


def test_rejects_foreign_attempt_and_cross_institution():
    old, new = plan("v1", (course("a"),)), plan("v2", (course("a"),))
    foreign_attempt = CompletedCourse(old.courses[0].identity, Decimal(3), identity("other").key)
    with pytest.raises(TransitionIntegrityError):
        evaluate_transition(old, new, (foreign_attempt,), (), (), TODAY)
    foreign = PlanVersion(PlanIdentity("other-university", "p", "m", "plan", "v",
                                       date(2025, 1, 1), None, "s"), (), (), "s", "c", "test")
    with pytest.raises(TransitionIntegrityError):
        evaluate_transition(old, foreign, (), (), (), TODAY)


def test_structured_import_preview_and_modeled_approval_only():
    preview = stage_structured_import(document(), source="isolated-test-input")
    assert preview.state is IngestionState.READY_FOR_REVIEW
    assert preview.course_count == 2 and preview.group_count == 1
    assert preview.prerequisite_edges == 1
    assert preview.plan is not None
    with pytest.raises(PermissionError):
        approve_local_version(preview, ModeledApproval("actor", "ANALYST", "test", TODAY))
    approved = approve_local_version(preview, ModeledApproval("actor", "MODELED_CURRICULUM_ADMIN", "test", TODAY))
    assert approved == preview.plan
    publication = publish_local_version(preview, ModeledApproval("actor", "MODELED_CURRICULUM_ADMIN", "test", TODAY))
    assert publication.state is IngestionState.PUBLISHED
    assert publication.plan == approved
    assert approved.content_fingerprint == stage_structured_import(document(), source="isolated-test-input").content_fingerprint


@pytest.mark.parametrize("change,expected", [
    (lambda d: d["courses"].append(deepcopy(d["courses"][0])), "Duplicate course identity"),
    (lambda d: d["courses"][1].update(prerequisites=["missing"]), "Prerequisite references nonexistent course"),
    (lambda d: d["courses"][0].update(prerequisites=["b"]), "Prerequisite cycle"),
    (lambda d: d["courses"][0].update(credits="-1"), "finite nonnegative"),
    (lambda d: d.update(groups=[]), "Missing requirement groups"),
    (lambda d: d["identity"].update(effective_to="2024-01-01"), "Conflicting effective dates"),
    (lambda d: d.update(schema_version="UNKNOWN"), "Unsupported schema version"),
])
def test_invalid_import_is_wholly_quarantined(change, expected):
    raw = document()
    change(raw)
    preview = stage_structured_import(raw, source="isolated-test-input")
    assert preview.state is IngestionState.QUARANTINED
    assert preview.plan is None
    assert any(expected in error for error in preview.errors)
    with pytest.raises(ValueError):
        approve_local_version(preview, ModeledApproval("actor", "MODELED_CURRICULUM_ADMIN", "test", TODAY))


def test_duplicate_version_and_changed_source_new_version():
    original = stage_structured_import(document(), source="isolated-test-input")
    assert original.plan_key is not None
    duplicate = stage_structured_import(document(), source="isolated-test-input",
                                        existing_keys=frozenset({original.plan_key}))
    assert duplicate.state is IngestionState.QUARANTINED
    changed = document()
    changed["identity"]["version_id"] = "v2"
    changed["courses"][1]["credits"] = "4"
    next_version = stage_structured_import(changed, source="isolated-test-input")
    assert next_version.plan_key != original.plan_key
    assert next_version.source_fingerprint != original.source_fingerprint


def test_content_addressed_publication_is_immutable_and_rollback_only_selects():
    approval = ModeledApproval("actor", "MODELED_CURRICULUM_ADMIN", "isolated-test", TODAY)
    first = stage_structured_import(document(), source="isolated-test-input")
    first_again = stage_structured_import(document(), source="isolated-test-input")
    assert first.content_fingerprint == first_again.content_fingerprint
    changed = document()
    changed["identity"]["version_id"] = "v2"
    changed["courses"][1]["credits"] = "4"
    second = stage_structured_import(changed, source="isolated-test-input")
    assert second.content_fingerprint != first.content_fingerprint
    v1 = publish_local_version(first, approval)
    v2 = publish_local_version(second, approval)
    registry = ModeledVersionRegistry().add(v1).add(v2)
    at_v2 = registry.activate(v2.plan.identity.key)
    rolled_back = at_v2.activate(v1.plan.identity.key)
    assert at_v2.active == v2 and rolled_back.active == v1
    assert rolled_back.publications == (v1, v2)
    assert registry.active is None
    with pytest.raises(FrozenInstanceError):
        v1.plan.courses[0].credits = Decimal(99)
    with pytest.raises(TypeError):
        v1.plan.courses[0] = course("tamper")
    with pytest.raises(ValueError):
        rolled_back.add(v1)


def test_version_reconciliation_lists_all_structural_deltas():
    first = plan("v1", (course("unchanged"), course("credit"),
                         course("group", "old"), course("prereq"), course("removed")))
    second = plan("v2", (course("unchanged"),
                          PlanCourse(course("credit").identity, "core", Decimal(4)),
                          course("group", "core"), course("prereq", prerequisites=("credit",)),
                          course("added")))
    result = reconcile_versions(first, second)
    changes = {row.course_id: set(row.changes) for row in result.lines}
    assert changes["unchanged"] == {ReconciliationStatus.UNCHANGED}
    assert changes["credit"] == {ReconciliationStatus.CHANGED_CREDITS}
    assert changes["group"] == {ReconciliationStatus.CHANGED_REQUIREMENT_GROUP}
    assert changes["prereq"] == {ReconciliationStatus.CHANGED_PREREQUISITE}
    assert changes["removed"] == {ReconciliationStatus.REMOVED_COURSE}
    assert changes["added"] == {ReconciliationStatus.ADDED_COURSE}


def test_overlapping_version_dates_and_duplicate_rules_quarantine():
    earlier = identity("v1")
    changed = document()
    changed["identity"]["version_id"] = "v2"
    overlap = stage_structured_import(changed, source="isolated-test-input",
                                      existing_versions=(earlier,))
    assert overlap.state is IngestionState.QUARANTINED
    assert any("Conflicting effective dates" in error for error in overlap.errors)
    record = {"rule_id": "r1", "authority": "isolated-test", "provenance": "test",
              "effective_from": "2025-01-01"}
    changed["equivalency_rules"] = [record, deepcopy(record)]
    duplicate = stage_structured_import(changed, source="isolated-test-input")
    assert duplicate.state is IngestionState.QUARANTINED
    assert "Duplicate equivalency rule" in duplicate.errors


@pytest.mark.anyio
async def test_provider_lookup_requires_entire_plan_version_key():
    first = plan("v1", (course("a"),))
    second = plan("v2", (course("a"),))
    provider = IsolatedInMemoryPlanProvider((first, second))
    assert await provider.load_version(first.identity.key) == first
    assert await provider.load_version(second.identity.key) == second
    assert await provider.load_version(identity("v1", "other-major").key) is None
    with pytest.raises(ValueError):
        IsolatedInMemoryPlanProvider((first, first))
