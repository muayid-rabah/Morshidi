"""Eligibility graph derives only typed facts from the authoritative evaluator."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.explainability_graph import (
    EdgeRelation, GraphMode, GraphNodeType, build_eligibility_graph, validate_graph,
)
from app.explainability_graph.eligibility import GraphEdge, GraphLimitation
from app.rules.evaluator import evaluate_can_take
from app.rules.models import AttemptOutcome, Decision, DecisionReason, PrerequisiteLogicStatus
from tests.test_rules_evaluator import (
    PREREQUISITE, TARGET, attempt, catalog, decision, group, request, rule,
)


def result(*, groups=(group(1, PREREQUISITE),), status=PrerequisiteLogicStatus.VERIFIED,
           attempts=()):
    return decision(evaluate_can_take(catalog(rule(status=status, groups=groups)),
                                      request(attempts=attempts)))


def node(graph, identity):
    return next(item for item in graph.nodes if item.id == identity)


def test_no_prerequisites_eligible_is_positive_and_source_honest():
    graph = build_eligibility_graph(result(status=PrerequisiteLogicStatus.NOT_APPLICABLE,
                                           groups=()))
    assert graph.root_node_id == f"decision:{TARGET}"
    assert node(graph, graph.root_node_id).decision is Decision.ELIGIBLE
    assert node(graph, "reason:NO_PREREQUISITES").reason is DecisionReason.NO_PREREQUISITES
    assert not any(item.type is GraphNodeType.PREREQUISITE_GROUP for item in graph.nodes)
    assert graph.source_versions == () and graph.policy_versions == ()
    assert GraphLimitation.EXACT_SOURCE_VERSION_UNAVAILABLE in graph.limitations
    assert graph.subject_reference == TARGET and "student" not in graph.model_dump_json().lower()


def test_all_and_groups_satisfied_and_stable_order():
    groups = (group(2, "CS302"), group(1, "CS301"))
    evaluated = result(groups=groups, attempts=(attempt("CS301", AttemptOutcome.PASSED),
                                                 attempt("CS302", AttemptOutcome.PASSED)))
    first = build_eligibility_graph(evaluated)
    second = build_eligibility_graph(evaluated)
    assert first.model_dump(exclude={"generated_at"}) == second.model_dump(exclude={"generated_at"})
    assert {item.group_number for item in first.nodes if item.type is GraphNodeType.PREREQUISITE_GROUP} == {1, 2}
    assert all(edge.relation is EdgeRelation.SATISFIED_BY
               for edge in first.edges if edge.from_node_id.startswith("prereq-group:"))


def test_missing_and_satisfied_groups_preserve_separate_structure():
    evaluated = result(groups=(group(1, "CS301"), group(2, "CS302")),
                       attempts=(attempt("CS301", AttemptOutcome.PASSED),))
    graph = build_eligibility_graph(evaluated)
    assert node(graph, graph.root_node_id).decision is Decision.NOT_ELIGIBLE
    assert node(graph, f"prereq-group:{TARGET}:1").passed_option_course_codes == ("CS301",)
    assert node(graph, f"prereq-group:{TARGET}:2").non_passed_option_course_codes == ("CS302",)
    assert any(edge.relation is EdgeRelation.BLOCKED_BY and edge.to_node_id == f"prereq-group:{TARGET}:2"
               for edge in graph.edges)


def test_or_options_are_not_all_mandatory_and_courses_deduplicate():
    evaluated = result(groups=(group(1, "CS301", "CS302"), group(2, "CS301", "CS303")),
                       attempts=(attempt("CS301", AttemptOutcome.PASSED),))
    graph = build_eligibility_graph(evaluated)
    first = node(graph, f"prereq-group:{TARGET}:1")
    assert first.option_course_codes == ("CS301", "CS302")
    assert first.passed_option_course_codes == ("CS301",)
    assert first.non_passed_option_course_codes == ("CS302",)
    assert len([item for item in graph.nodes if item.id == "course:CS301"]) == 1
    assert not any(edge.relation is EdgeRelation.BLOCKED_BY and edge.to_node_id == "course:CS302"
                   for edge in graph.edges)


@pytest.mark.parametrize("status,reason,limitation", [
    (PrerequisiteLogicStatus.UNRESOLVED, DecisionReason.PREREQUISITE_LOGIC_UNRESOLVED,
     GraphLimitation.PREREQUISITE_LOGIC_UNRESOLVED),
    (PrerequisiteLogicStatus.SOURCE_CONFLICT, DecisionReason.PREREQUISITE_SOURCE_CONFLICT,
     GraphLimitation.PREREQUISITE_SOURCE_CONFLICT),
    (PrerequisiteLogicStatus.VERIFIED, DecisionReason.VERIFIED_PREREQUISITE_MODEL_INCOMPLETE,
     GraphLimitation.VERIFIED_MODEL_INCOMPLETE),
])
def test_review_required_retains_uncertainty(status, reason, limitation):
    graph = build_eligibility_graph(result(status=status, groups=()))
    assert node(graph, graph.root_node_id).decision is Decision.REVIEW_REQUIRED
    assert node(graph, f"reason:{reason.value}").reason is reason
    assert limitation in graph.limitations
    assert not any(item.type is GraphNodeType.PREREQUISITE_GROUP for item in graph.nodes)


def test_target_completed_and_in_progress_are_typed_existing_states():
    evaluated = result(status=PrerequisiteLogicStatus.NOT_APPLICABLE, groups=(),
                       attempts=(attempt(TARGET, AttemptOutcome.PASSED),
                                 attempt(TARGET, AttemptOutcome.IN_PROGRESS)))
    graph = build_eligibility_graph(evaluated)
    assert node(graph, f"state:{TARGET}:TARGET_COMPLETED").academic_state.value == "TARGET_COMPLETED"
    assert node(graph, f"state:{TARGET}:TARGET_IN_PROGRESS").academic_state.value == "TARGET_IN_PROGRESS"


def test_why_not_eligible_uses_only_actual_blockers():
    evaluated = result(groups=(group(1, "CS301"), group(2, "CS302")),
                       attempts=(attempt("CS301", AttemptOutcome.PASSED),))
    graph = build_eligibility_graph(evaluated, mode=GraphMode.WHY_NOT,
                                    target_decision=Decision.ELIGIBLE)
    assert graph.target_decision is Decision.ELIGIBLE
    assert not any(item.id == f"prereq-group:{TARGET}:1" for item in graph.nodes)
    assert node(graph, f"prereq-group:{TARGET}:2").non_passed_option_course_codes == ("CS302",)
    with pytest.raises(ValueError):
        build_eligibility_graph(evaluated, mode=GraphMode.WHY_NOT,
                                target_decision=Decision.REVIEW_REQUIRED)


def test_unknown_reason_invalid_edges_and_cycles_fail_closed():
    evaluated = result(status=PrerequisiteLogicStatus.NOT_APPLICABLE, groups=())
    with pytest.raises(ValueError):
        build_eligibility_graph(replace(evaluated, reasons=("NEW_REASON",)))
    graph = build_eligibility_graph(evaluated)
    with pytest.raises(ValueError):
        validate_graph(graph.model_copy(update={"edges": (*graph.edges,
            GraphEdge(from_node_id=graph.root_node_id, to_node_id="missing", relation=EdgeRelation.REFERENCES))}))
    with pytest.raises(ValueError):
        validate_graph(graph.model_copy(update={"edges": (*graph.edges,
            GraphEdge(from_node_id=f"course:{TARGET}", to_node_id=graph.root_node_id,
                      relation=EdgeRelation.REFERENCES))}))


def test_no_hidden_reasoning_or_student_ids_in_schema():
    graph = build_eligibility_graph(result())
    fields = set(type(graph).model_fields) | set(type(graph.nodes[0]).model_fields)
    assert fields.isdisjoint({"student_user_id", "university_id", "prompt", "completion",
                              "chain_of_thought", "scratchpad", "hidden_reasoning", "raw_prerequisite_text"})
    assert not any("11111111-" in item.id for item in graph.nodes)
