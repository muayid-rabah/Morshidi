"""Closed, deterministic projections of Phase 7-9 result contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal

import pytest

from app.degree_path.models import PathStatus
from app.explainability_graph import (
    EdgeRelation, GraphMode, GraphNodeType, build_degree_path_graph,
    build_recommendation_graph, build_semester_planner_graph, validate_graph,
)
from tests.test_degree_path_api import _sample_degree_path_option, _sample_degree_path_result, _sample_modeled_semester
from tests.test_recommendation_api import FakeStudentServiceForRecommendations, _sample_candidate
from tests.test_semester_planner_api import FakeStudentServiceForPlanner, _sample_plan_option


def _recommendations():
    return asyncio.run(FakeStudentServiceForRecommendations().get_course_recommendations("owner"))


def _planner():
    return asyncio.run(FakeStudentServiceForPlanner().get_semester_plans(
        "owner", max_credit_hours=Decimal("15"), max_courses=5, max_options=3,
    ))


def _fact(node, key):
    return next((fact.value for fact in node.facts if fact.key.value == key), None)


def _sound(graph):
    validate_graph(graph)
    ids = [node.id for node in graph.nodes]
    assert ids == sorted(set(ids))
    assert all(edge.from_node_id in ids and edge.to_node_id in ids for edge in graph.edges)
    assert "11111111-1111-1111-1111-111111111111" not in graph.model_dump_json()
    assert not any(key in graph.model_dump_json().lower() for key in ("prompt", "chain_of_thought", "secret"))
    assert graph.source_versions == ()


def test_ranked_recommendations_have_typed_facts_group_state_reasons_unlock_and_version():
    graph = build_recommendation_graph(_recommendations())
    _sound(graph)
    ranked = [node for node in graph.nodes if node.type is GraphNodeType.RECOMMENDATION and _fact(node, "STATUS") == "RANKED"]
    assert len(ranked) == 5
    first = ranked[0]
    assert _fact(first, "RANK") == 1
    assert _fact(first, "EFFECTIVE_CREDIT_CONTRIBUTION") == Decimal("3")
    assert _fact(first, "GROUP_REMAINING_BEFORE") == Decimal("6")
    assert _fact(first, "GROUP_REMAINING_AFTER") == Decimal("3")
    assert _fact(first, "ELIGIBILITY_DECISION") == "ELIGIBLE"
    assert any(edge.from_node_id == first.id and edge.relation is EdgeRelation.CONTRIBUTES_TO for edge in graph.edges)
    assert any(edge.from_node_id == first.id and edge.relation is EdgeRelation.LEADS_TO for edge in graph.edges)
    assert graph.policy_versions == ("1.0",)
    assert any(node.type is GraphNodeType.POLICY_VERSION for node in graph.nodes)
    assert any(_fact(node, "STATUS") == "REVIEW_REQUIRED" for node in graph.nodes)
    assert any(_fact(node, "STATUS") == "EXCLUDED_IN_PROGRESS" for node in graph.nodes)


def test_recommendation_why_not_uses_known_review_or_in_progress_and_abstains_when_unknown():
    result = _recommendations()
    review = build_recommendation_graph(result, mode=GraphMode.WHY_NOT, course_code="1505311")
    assert any(_fact(node, "STATUS") == "REVIEW_REQUIRED" for node in review.nodes)
    progress = build_recommendation_graph(result, mode=GraphMode.WHY_NOT, course_code="1501221")
    assert any(_fact(node, "STATUS") == "EXCLUDED_IN_PROGRESS" for node in progress.nodes)
    unknown = build_recommendation_graph(result, mode=GraphMode.WHY_NOT, course_code="9999999")
    assert "WHY_NOT_EVIDENCE_UNAVAILABLE" in {item.value for item in unknown.limitations}
    assert unknown.subject_reference == "9999999"
    assert unknown.graph_id != build_recommendation_graph(
        result, mode=GraphMode.WHY_NOT, course_code="8888888"
    ).graph_id
    assert not any(_fact(node, "REASON_CODE") for node in unknown.nodes)
    _sound(unknown)


def test_recommendation_identity_and_order_are_stable_without_student_scope():
    result = _recommendations()
    first = build_recommendation_graph(result)
    second = build_recommendation_graph(result)
    assert first.graph_id == second.graph_id
    assert first.nodes == second.nodes and first.edges == second.edges


def test_elective_group_completion_prior_attempt_and_reason_are_exact():
    candidate = _sample_candidate(
        "1502222", req_type="elective", p4=1, previously_attempted=True,
    )
    graph = build_recommendation_graph(replace(_recommendations(), ranked_recommendations=(candidate,)))
    item = next(node for node in graph.nodes if node.id == "recommendation:1:1502222")
    assert _fact(item, "REQUIREMENT_TYPE") == "elective"
    assert _fact(item, "COMPLETES_REQUIREMENT_GROUP") is True
    assert _fact(item, "PREVIOUSLY_ATTEMPTED") is True
    assert any(edge.from_node_id == item.id and edge.relation is EdgeRelation.CONSTRAINED_BY for edge in graph.edges)
    assert any(edge.from_node_id == item.id and edge.relation is EdgeRelation.SUPPORTED_BY for edge in graph.edges)
    assert any(edge.from_node_id == item.id and edge.relation is EdgeRelation.LEADS_TO for edge in graph.edges)


def test_planner_multiple_options_constraints_selected_courses_and_review():
    result = replace(_planner(), plan_options=(_sample_plan_option(rank=1), _sample_plan_option(rank=2)))
    graph = build_semester_planner_graph(result)
    _sound(graph)
    assert len([n for n in graph.nodes if n.type is GraphNodeType.SEMESTER]) == 3
    assert any(_fact(n, "MAX_CREDIT_HOURS") == Decimal("15") for n in graph.nodes)
    assert any(_fact(n, "MAX_COURSES") == 5 for n in graph.nodes)
    assert any(edge.relation is EdgeRelation.SELECTED_IN for edge in graph.edges)
    assert any(_fact(n, "STATUS") == "REVIEW_REQUIRED" for n in graph.nodes)
    assert graph.policy_versions == ("1.0",)


def test_planner_empty_result_is_explicit_and_stable():
    graph = build_semester_planner_graph(replace(_planner(), plan_options=()))
    _sound(graph)
    assert not any(_fact(node, "RANK") for node in graph.nodes)
    assert any(node.type is GraphNodeType.CONSTRAINT for node in graph.nodes)


def test_planner_option_exact_group_unlock_reason_rank_and_constraint_links():
    option = replace(
        _sample_plan_option(rank=2), newly_satisfied_requirement_group_codes=("FACULTY_REQUIRED",),
        newly_satisfied_requirement_group_count=1,
    )
    graph = build_semester_planner_graph(replace(_planner(), plan_options=(option,)))
    item = next(node for node in graph.nodes if node.id == "semester-planner:option:2")
    assert _fact(item, "RANK") == 2
    assert _fact(item, "TOTAL_CREDIT_HOURS") == Decimal("15")
    assert _fact(item, "NEWLY_SATISFIED_GROUP_COUNT") == 1
    assert _fact(item, "NEWLY_ELIGIBLE_COUNT") == 1
    assert any(edge.from_node_id == item.id and edge.relation is EdgeRelation.CONSTRAINED_BY for edge in graph.edges)
    assert any(edge.from_node_id == item.id and edge.relation is EdgeRelation.CONTRIBUTES_TO for edge in graph.edges)
    assert any(edge.from_node_id == item.id and edge.relation is EdgeRelation.LEADS_TO for edge in graph.edges)
    assert any(edge.from_node_id == item.id and edge.relation is EdgeRelation.SUPPORTED_BY for edge in graph.edges)


@pytest.mark.parametrize("status", [
    PathStatus.MODELED_COMPLETE, PathStatus.HORIZON_REACHED,
    PathStatus.BLOCKED_BY_REVIEW_REQUIRED, PathStatus.BLOCKED_BY_CURRENT_IN_PROGRESS,
    PathStatus.NO_VALID_NEXT_PLAN,
])
def test_degree_path_status_constraints_semesters_and_no_historical_completion(status):
    semester1 = _sample_modeled_semester()
    semester2 = replace(_sample_modeled_semester(), semester_index=2)
    path = _sample_degree_path_option(status=status, semesters=(semester1, semester2), semester_count=2)
    graph = build_degree_path_graph(_sample_degree_path_result(paths=(path,)))
    _sound(graph)
    assert any(_fact(node, "STATUS") == status.value for node in graph.nodes)
    assert len([n for n in graph.nodes if n.type is GraphNodeType.SEMESTER]) == 2
    assert any(edge.relation is EdgeRelation.SELECTED_IN and edge.from_node_id == "degree-path:1" for edge in graph.edges)
    assert "MODELED_OUTCOME_NOT_HISTORICAL" in {item.value for item in graph.limitations}
    assert graph.policy_versions == ("1.0",)


def test_degree_path_identity_dedup_and_limits():
    result = _sample_degree_path_result(paths=(_sample_degree_path_option(rank=1), _sample_degree_path_option(rank=2)))
    first = build_degree_path_graph(result)
    second = build_degree_path_graph(result)
    assert first.graph_id == second.graph_id
    assert first.nodes == second.nodes and first.edges == second.edges
    _sound(first)


def test_degree_path_remaining_requirements_blockers_and_all_requested_constraints():
    path = replace(
        _sample_degree_path_option(status=PathStatus.BLOCKED_BY_REVIEW_REQUIRED),
        remaining_required_course_codes=("1509999",),
        unresolved_blocker_codes=("REVIEW_REQUIRED_BLOCKER",),
        final_remaining_plan_credits=Decimal("6"),
    )
    graph = build_degree_path_graph(_sample_degree_path_result(paths=(path,)))
    item = next(node for node in graph.nodes if node.id == "degree-path:1")
    assert _fact(item, "FINAL_REMAINING_CREDITS") == Decimal("6")
    assert any(edge.from_node_id == item.id and edge.relation is EdgeRelation.REFERENCES
               and edge.to_node_id == "course:1509999" for edge in graph.edges)
    assert any(edge.from_node_id == item.id and edge.relation is EdgeRelation.SUPPORTED_BY
               and edge.to_node_id == "blocker:REVIEW_REQUIRED_BLOCKER" for edge in graph.edges)
    constraints = {_fact(node, key) for key in ("MAX_CREDIT_HOURS", "MAX_COURSES", "MAX_SEMESTERS_AHEAD", "MAX_PATHS")
                   for node in graph.nodes if node.type is GraphNodeType.CONSTRAINT}
    assert {Decimal("15"), 5, 8, 3} <= constraints
    _sound(graph)
