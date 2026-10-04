"""Read-only projections of authoritative recommendation and planning results.

No academic rule is evaluated here. Only closed, already-computed fields enter
the graph; source-document citations and historical completion are not inferred.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from app.degree_path.models import DegreePathResult
from app.planner.models import SemesterPlannerResult
from app.recommendations.models import RecommendationResult

from .eligibility import (
    EdgeRelation, ExplainabilityGraph, GraphEdge, GraphFact, GraphFactKey,
    GraphLimitation, GraphMode, GraphNode, GraphNodeType, validate_graph,
)


_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")


def _token(value: str) -> str:
    if not isinstance(value, str) or _TOKEN.fullmatch(value) is None:
        raise ValueError("unsafe graph evidence identifier")
    return value


def _fact(key: GraphFactKey, value: str | int | bool | Decimal | Enum) -> GraphFact:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, str):
        value = _token(value)
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("non-finite graph fact")
    return GraphFact(key=key, value=value)


class _Builder:
    def __init__(self, subject: str, root: GraphNode, *, mode: GraphMode = GraphMode.WHY,
                 subject_reference: str = "current") -> None:
        self.subject = subject
        self.subject_reference = _token(subject_reference)
        self.root = root.id
        self.mode = mode
        self.nodes: dict[str, GraphNode] = {}
        self.edges: set[tuple[str, str, EdgeRelation]] = set()
        self.add(root)

    def add(self, node: GraphNode) -> str:
        if node.id in self.nodes and self.nodes[node.id] != node:
            raise ValueError("conflicting graph node identity")
        self.nodes[node.id] = node
        return node.id

    def link(self, source: str, target: str, relation: EdgeRelation) -> None:
        self.edges.add((source, target, relation))

    def version(self, parent: str, version: str, engine: str) -> None:
        safe_version = _token(version)
        ident = self.add(GraphNode(
            id=f"policy-version:{engine}:{safe_version}", type=GraphNodeType.POLICY_VERSION,
            facts=(_fact(GraphFactKey.POLICY_VERSION, safe_version),),
        ))
        self.link(parent, ident, EdgeRelation.VERSIONED_BY)

    def constraint(self, parent: str, name: GraphFactKey, value: str | int | Decimal | None) -> None:
        if value is None:
            return
        ident = self.add(GraphNode(
            id=f"constraint:{name.value.lower()}:{value}", type=GraphNodeType.CONSTRAINT,
            facts=(_fact(name, value),),
        ))
        self.link(parent, ident, EdgeRelation.CONSTRAINED_BY)

    def course(self, code: str) -> str:
        code = _token(code)
        return self.add(GraphNode(id=f"course:{code}", type=GraphNodeType.COURSE, course_code=code))

    def group(self, code: str) -> str:
        code = _token(code)
        return self.add(GraphNode(id=f"requirement-group:{code}", type=GraphNodeType.REQUIREMENT_GROUP,
                                  reference_code=code))

    def reason(self, parent: str, code: Enum) -> None:
        value = _token(code.value)
        ident = self.add(GraphNode(id=f"reason:{value}", type=GraphNodeType.REASON,
                                  facts=(_fact(GraphFactKey.REASON_CODE, value),)))
        self.link(parent, ident, EdgeRelation.SUPPORTED_BY)

    def limitation(self, value: GraphLimitation) -> None:
        ident = self.add(GraphNode(id=f"limitation:{value.value}", type=GraphNodeType.LIMITATION,
                                  limitation=value))
        self.link(self.root, ident, EdgeRelation.LIMITED_BY)

    def finish(self, version: str, limitations: tuple[GraphLimitation, ...]) -> ExplainabilityGraph:
        for limitation in limitations:
            self.limitation(limitation)
        nodes = tuple(self.nodes[key] for key in sorted(self.nodes))
        edges = tuple(GraphEdge(from_node_id=a, to_node_id=b, relation=r)
                      for a, b, r in sorted(self.edges))
        identity = json.dumps({
            "subject": self.subject, "reference": self.subject_reference, "mode": self.mode.value,
            "nodes": [node.model_dump(mode="json") for node in nodes],
            "edges": [edge.model_dump(mode="json") for edge in edges],
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        graph = ExplainabilityGraph(
            graph_id=f"{self.subject.lower()}:{self.mode.value}:{digest}",
            subject_type=self.subject, subject_reference=self.subject_reference,
            root_node_id=self.root, mode=self.mode, target_decision=None,
            nodes=nodes, edges=edges, generated_at=datetime.now(timezone.utc),
            policy_versions=(_token(version),), source_versions=(),
            limitations=tuple(sorted(set(limitations))),
        )
        validate_graph(graph)
        return graph


_SOURCE_LIMIT = GraphLimitation.SOURCE_DOCUMENT_VERSION_UNAVAILABLE
_MODELED_LIMITS = (_SOURCE_LIMIT, GraphLimitation.NOT_OFFICIAL_REGISTRATION,
                   GraphLimitation.MODELED_OUTCOME_NOT_HISTORICAL)


def build_recommendation_graph(
    result: RecommendationResult, *, mode: GraphMode = GraphMode.WHY,
    course_code: str | None = None,
) -> ExplainabilityGraph:
    if not isinstance(result, RecommendationResult) or not isinstance(mode, GraphMode):
        raise ValueError("authoritative recommendation result required")
    if mode is GraphMode.WHY and course_code is not None:
        raise ValueError("WHY does not accept a target course")
    if mode is GraphMode.WHY_NOT and course_code is None:
        raise ValueError("WHY_NOT requires a target course")
    target = _token(course_code) if course_code is not None else None
    builder = _Builder("COURSE_RECOMMENDATIONS", GraphNode(
        id="recommendations:result", type=GraphNodeType.RECOMMENDATION,
        facts=(_fact(GraphFactKey.STATUS, "AUTHORITATIVE_RESULT"),),
    ), mode=mode, subject_reference=target or "current")
    builder.version(builder.root, result.recommendation_policy_version, "recommendations")
    if mode is GraphMode.WHY:
        candidates = result.ranked_recommendations
        reviews = result.review_required_courses
        in_progress = result.excluded_in_progress
    else:
        candidates = tuple(item for item in result.ranked_recommendations if item.course_code == target)
        reviews = tuple(item for item in result.review_required_courses if item.course_code == target)
        in_progress = tuple(code for code in result.excluded_in_progress if code == target)
        if candidates:
            raise ValueError("target is already ranked")
    for candidate in candidates:
        code = _token(candidate.course_code)
        if candidate.eligibility_decision != "ELIGIBLE":
            raise ValueError("ranked recommendation is not eligible")
        ident = builder.add(GraphNode(
            id=f"recommendation:{candidate.rank}:{code}", type=GraphNodeType.RECOMMENDATION,
            facts=(
                _fact(GraphFactKey.RANK, candidate.rank),
                _fact(GraphFactKey.STATUS, "RANKED"),
                _fact(GraphFactKey.REQUIREMENT_TYPE, candidate.requirement_type),
                _fact(GraphFactKey.ELIGIBILITY_DECISION, candidate.eligibility_decision),
                _fact(GraphFactKey.CREDIT_HOURS, candidate.credit_hours),
                _fact(GraphFactKey.EFFECTIVE_CREDIT_CONTRIBUTION, candidate.effective_credit_contribution),
                _fact(GraphFactKey.GROUP_REMAINING_BEFORE, candidate.group_remaining_credits_before),
                _fact(GraphFactKey.GROUP_REMAINING_AFTER, candidate.group_remaining_credits_after),
                _fact(GraphFactKey.COMPLETES_REQUIREMENT_GROUP, candidate.completes_requirement_group),
                _fact(GraphFactKey.NEWLY_ELIGIBLE_COUNT, candidate.newly_eligible_count),
                _fact(GraphFactKey.PREVIOUSLY_ATTEMPTED, candidate.previously_attempted),
            ),
        ))
        builder.link(builder.root, ident, EdgeRelation.RANKED_AS)
        builder.link(ident, builder.course(code), EdgeRelation.REFERENCES)
        builder.constraint(ident, GraphFactKey.ELIGIBILITY_DECISION, candidate.eligibility_decision)
        group = builder.group(candidate.requirement_group_code)
        builder.link(ident, group, EdgeRelation.CONTRIBUTES_TO)
        state = builder.add(GraphNode(id=f"state:{code}:{_token(candidate.course_state)}",
                                      type=GraphNodeType.ACADEMIC_STATE, course_code=code,
                                      facts=(_fact(GraphFactKey.COURSE_STATE, candidate.course_state),)))
        builder.link(ident, state, EdgeRelation.SUPPORTED_BY)
        builder.version(ident, result.recommendation_policy_version, "recommendations")
        for reason in candidate.reason_codes:
            builder.reason(ident, reason)
        for unlocked in candidate.newly_eligible_course_codes:
            builder.link(ident, builder.course(unlocked), EdgeRelation.LEADS_TO)
    for review in reviews:
        code = _token(review.course_code)
        ident = builder.add(GraphNode(
            id=f"recommendation:review:{code}", type=GraphNodeType.RECOMMENDATION,
            facts=(_fact(GraphFactKey.STATUS, "REVIEW_REQUIRED"),
                   _fact(GraphFactKey.REASON_CODE, review.review_reason),
                   _fact(GraphFactKey.REQUIREMENT_TYPE, review.requirement_type),
                   _fact(GraphFactKey.PREVIOUSLY_ATTEMPTED, review.previously_attempted)),
        ))
        builder.link(builder.root, ident, EdgeRelation.RANKED_AS)
        builder.link(ident, builder.course(code), EdgeRelation.REFERENCES)
        builder.link(ident, builder.group(review.requirement_group_code), EdgeRelation.CONTRIBUTES_TO)
        builder.version(ident, result.recommendation_policy_version, "recommendations")
    for code in in_progress:
        code = _token(code)
        ident = builder.add(GraphNode(id=f"recommendation:in-progress:{code}",
                                      type=GraphNodeType.RECOMMENDATION,
                                      facts=(_fact(GraphFactKey.STATUS, "EXCLUDED_IN_PROGRESS"),)))
        builder.link(builder.root, ident, EdgeRelation.RANKED_AS)
        builder.link(ident, builder.course(code), EdgeRelation.REFERENCES)
    limits = [_SOURCE_LIMIT, GraphLimitation.CURRENT_STORED_STATE]
    if mode is GraphMode.WHY_NOT and not (candidates or reviews or in_progress):
        limits.append(GraphLimitation.WHY_NOT_EVIDENCE_UNAVAILABLE)
    return builder.finish(result.recommendation_policy_version, tuple(limits))


def _semester_option(builder: _Builder, option, *, parent: str, prefix: str,
                     version: str, engine: str = "semester-planner") -> str:
    ident = builder.add(GraphNode(
        id=f"{prefix}:option:{option.rank}", type=GraphNodeType.SEMESTER,
        facts=(
            _fact(GraphFactKey.RANK, option.rank),
            _fact(GraphFactKey.TOTAL_CREDIT_HOURS, option.total_credit_hours),
            _fact(GraphFactKey.TOTAL_COURSES, option.total_courses),
            _fact(GraphFactKey.MANDATORY_COURSE_COUNT, option.mandatory_course_count),
            _fact(GraphFactKey.COMPLETED_PLAN_CREDIT_DELTA, option.completed_plan_credit_delta),
            _fact(GraphFactKey.NEWLY_SATISFIED_GROUP_COUNT, option.newly_satisfied_requirement_group_count),
            _fact(GraphFactKey.NEWLY_ELIGIBLE_COUNT, option.newly_eligible_count),
            _fact(GraphFactKey.RECOMMENDATION_RANK_SUM, option.recommendation_rank_sum),
        ),
    ))
    builder.link(parent, ident, EdgeRelation.RANKED_AS if parent == builder.root else EdgeRelation.SELECTED_IN)
    builder.version(ident, version, engine)
    for entry in option.courses:
        builder.link(ident, builder.course(entry.course_code), EdgeRelation.SELECTED_IN)
    for code in option.newly_satisfied_requirement_group_codes:
        builder.link(ident, builder.group(code), EdgeRelation.CONTRIBUTES_TO)
    for code in option.newly_eligible_course_codes:
        builder.link(ident, builder.course(code), EdgeRelation.LEADS_TO)
    for reason in option.reason_codes:
        builder.reason(ident, reason)
    return ident


def build_semester_planner_graph(result: SemesterPlannerResult) -> ExplainabilityGraph:
    if not isinstance(result, SemesterPlannerResult):
        raise ValueError("authoritative semester planner result required")
    builder = _Builder("SEMESTER_PLANNER", GraphNode(
        id="semester-planner:result", type=GraphNodeType.SEMESTER,
        facts=(_fact(GraphFactKey.STATUS, "MODELED_RESULT"),),
    ))
    builder.version(builder.root, result.semester_planner_policy_version, "semester-planner")
    constraints = result.constraints
    for key, value in (
        (GraphFactKey.MAX_CREDIT_HOURS, constraints.max_credit_hours),
        (GraphFactKey.MAX_COURSES, constraints.max_courses),
        (GraphFactKey.MAX_OPTIONS, constraints.max_options),
    ):
        builder.constraint(builder.root, key, value)
    for option in result.plan_options:
        option_id = _semester_option(builder, option, parent=builder.root, prefix="semester-planner",
                                     version=result.semester_planner_policy_version)
        for key, value in (
            (GraphFactKey.MAX_CREDIT_HOURS, constraints.max_credit_hours),
            (GraphFactKey.MAX_COURSES, constraints.max_courses),
            (GraphFactKey.MAX_OPTIONS, constraints.max_options),
        ):
            builder.constraint(option_id, key, value)
    for code in result.review_required_courses:
        ident = builder.add(GraphNode(id=f"semester-planner:review:{_token(code)}",
                                      type=GraphNodeType.REASON,
                                      facts=(_fact(GraphFactKey.STATUS, "REVIEW_REQUIRED"),)))
        builder.link(builder.root, ident, EdgeRelation.SUPPORTED_BY)
        builder.link(ident, builder.course(code), EdgeRelation.REFERENCES)
    return builder.finish(result.semester_planner_policy_version, _MODELED_LIMITS)


def build_degree_path_graph(result: DegreePathResult) -> ExplainabilityGraph:
    if not isinstance(result, DegreePathResult):
        raise ValueError("authoritative degree path result required")
    builder = _Builder("DEGREE_PATH", GraphNode(
        id="degree-path:result", type=GraphNodeType.DEGREE_PATH,
        facts=(_fact(GraphFactKey.STATUS, "MODELED_RESULT"),),
    ))
    builder.version(builder.root, result.degree_path_policy_version, "degree-path")
    constraints = result.constraints
    for key, value in (
        (GraphFactKey.MAX_CREDIT_HOURS, constraints.max_credit_hours_per_semester),
        (GraphFactKey.MAX_COURSES, constraints.max_courses_per_semester),
        (GraphFactKey.MAX_SEMESTERS_AHEAD, constraints.max_semesters_ahead),
        (GraphFactKey.MAX_PATHS, constraints.max_paths),
    ):
        builder.constraint(builder.root, key, value)
    for path in result.paths:
        ident = builder.add(GraphNode(
            id=f"degree-path:{path.rank}", type=GraphNodeType.DEGREE_PATH,
            facts=(
                _fact(GraphFactKey.RANK, path.rank),
                _fact(GraphFactKey.STATUS, path.status),
                _fact(GraphFactKey.SEMESTER_COUNT, path.semester_count),
                _fact(GraphFactKey.TOTAL_PLANNED_COURSES, path.total_planned_courses),
                _fact(GraphFactKey.TOTAL_PLANNED_CREDITS, path.total_planned_credits),
                _fact(GraphFactKey.COMPLETED_PLAN_CREDIT_DELTA, path.completed_plan_credit_delta),
                _fact(GraphFactKey.FINAL_COMPLETED_CREDITS, path.final_completed_plan_credits),
                _fact(GraphFactKey.FINAL_REMAINING_CREDITS, path.final_remaining_plan_credits),
                _fact(GraphFactKey.NEWLY_SATISFIED_GROUP_COUNT, path.newly_satisfied_requirement_group_count),
                _fact(GraphFactKey.AGGREGATE_SEMESTER_RANK_SUM, path.aggregate_semester_rank_sum),
            ),
        ))
        builder.link(builder.root, ident, EdgeRelation.RANKED_AS)
        builder.version(ident, result.degree_path_policy_version, "degree-path")
        for key, value in (
            (GraphFactKey.MAX_CREDIT_HOURS, constraints.max_credit_hours_per_semester),
            (GraphFactKey.MAX_COURSES, constraints.max_courses_per_semester),
            (GraphFactKey.MAX_SEMESTERS_AHEAD, constraints.max_semesters_ahead),
        ):
            builder.constraint(ident, key, value)
        for semester in path.semesters:
            sem_id = _semester_option(builder, semester.plan_option, parent=ident,
                                      prefix=f"degree-path:{path.rank}:semester:{semester.semester_index}",
                                      version=result.degree_path_policy_version, engine="degree-path")
            # The semester is modeled; its resulting deltas are not historical attempts.
            sem_node = builder.nodes[sem_id]
            builder.nodes[sem_id] = sem_node.model_copy(update={"facts": sem_node.facts + (
                _fact(GraphFactKey.SEMESTER_INDEX, semester.semester_index),
                _fact(GraphFactKey.FINAL_COMPLETED_CREDITS, semester.completed_plan_credits_after),
                _fact(GraphFactKey.FINAL_REMAINING_CREDITS, semester.remaining_plan_credits_after),
            )})
        for code in path.newly_satisfied_requirement_group_codes:
            builder.link(ident, builder.group(code), EdgeRelation.CONTRIBUTES_TO)
        for code in path.remaining_required_course_codes:
            builder.link(ident, builder.course(code), EdgeRelation.REFERENCES)
        for code in path.unresolved_blocker_codes:
            blocker = builder.add(GraphNode(id=f"blocker:{_token(code)}", type=GraphNodeType.REASON,
                                            facts=(_fact(GraphFactKey.BLOCKER_CODE, code),)))
            builder.link(ident, blocker, EdgeRelation.SUPPORTED_BY)
        for reason in path.reason_codes:
            builder.reason(ident, reason)
    return builder.finish(result.degree_path_policy_version, _MODELED_LIMITS)
