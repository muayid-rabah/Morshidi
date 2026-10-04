"""Pure, read-only DAG projection of a Phase 5 eligibility decision.

Only typed evidence already present in CanTakeDecision is used. No raw
prerequisite prose, student identifier, LLM content, or inferred source citation
can enter this graph.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.rules.models import (
    CanTakeDecision, Decision, DecisionReason, DependencyType,
    PrerequisiteLogicStatus,
)


class GraphMode(str, Enum):
    WHY = "why"
    WHY_NOT = "why_not"


class GraphNodeType(str, Enum):
    DECISION = "DECISION"
    COURSE = "COURSE"
    REASON = "REASON"
    PREREQUISITE_GROUP = "PREREQUISITE_GROUP"
    ACADEMIC_STATE = "ACADEMIC_STATE"
    LIMITATION = "LIMITATION"
    RECOMMENDATION = "RECOMMENDATION"
    CONSTRAINT = "CONSTRAINT"
    REQUIREMENT_GROUP = "REQUIREMENT_GROUP"
    SEMESTER = "SEMESTER"
    DEGREE_PATH = "DEGREE_PATH"
    POLICY_VERSION = "POLICY_VERSION"


class EdgeRelation(str, Enum):
    DECIDED_BY = "DECIDED_BY"
    REFERENCES = "REFERENCES"
    SUPPORTED_BY = "SUPPORTED_BY"
    SATISFIED_BY = "SATISFIED_BY"
    BLOCKED_BY = "BLOCKED_BY"
    LIMITED_BY = "LIMITED_BY"
    CONTRIBUTES_TO = "CONTRIBUTES_TO"
    CONSTRAINED_BY = "CONSTRAINED_BY"
    SELECTED_IN = "SELECTED_IN"
    LEADS_TO = "LEADS_TO"
    VERSIONED_BY = "VERSIONED_BY"
    RANKED_AS = "RANKED_AS"


class AcademicState(str, Enum):
    PASSED = "PASSED"
    NOT_PASSED = "NOT_PASSED"
    TARGET_COMPLETED = "TARGET_COMPLETED"
    TARGET_IN_PROGRESS = "TARGET_IN_PROGRESS"


class GraphLimitation(str, Enum):
    CURRENT_STORED_STATE = "CURRENT_STORED_STATE"
    NOT_OFFICIAL_REGISTRATION = "NOT_OFFICIAL_REGISTRATION"
    EXACT_SOURCE_VERSION_UNAVAILABLE = "EXACT_SOURCE_VERSION_UNAVAILABLE"
    PREREQUISITE_LOGIC_UNRESOLVED = "PREREQUISITE_LOGIC_UNRESOLVED"
    PREREQUISITE_SOURCE_CONFLICT = "PREREQUISITE_SOURCE_CONFLICT"
    VERIFIED_MODEL_INCOMPLETE = "VERIFIED_MODEL_INCOMPLETE"
    SOURCE_DOCUMENT_VERSION_UNAVAILABLE = "SOURCE_DOCUMENT_VERSION_UNAVAILABLE"
    WHY_NOT_EVIDENCE_UNAVAILABLE = "WHY_NOT_EVIDENCE_UNAVAILABLE"
    MODELED_OUTCOME_NOT_HISTORICAL = "MODELED_OUTCOME_NOT_HISTORICAL"


class GraphFactKey(str, Enum):
    RANK = "RANK"
    STATUS = "STATUS"
    REASON_CODE = "REASON_CODE"
    REQUIREMENT_TYPE = "REQUIREMENT_TYPE"
    COURSE_STATE = "COURSE_STATE"
    ELIGIBILITY_DECISION = "ELIGIBILITY_DECISION"
    CREDIT_HOURS = "CREDIT_HOURS"
    EFFECTIVE_CREDIT_CONTRIBUTION = "EFFECTIVE_CREDIT_CONTRIBUTION"
    GROUP_REMAINING_BEFORE = "GROUP_REMAINING_BEFORE"
    GROUP_REMAINING_AFTER = "GROUP_REMAINING_AFTER"
    COMPLETES_REQUIREMENT_GROUP = "COMPLETES_REQUIREMENT_GROUP"
    NEWLY_ELIGIBLE_COUNT = "NEWLY_ELIGIBLE_COUNT"
    PREVIOUSLY_ATTEMPTED = "PREVIOUSLY_ATTEMPTED"
    MAX_CREDIT_HOURS = "MAX_CREDIT_HOURS"
    MAX_COURSES = "MAX_COURSES"
    MAX_OPTIONS = "MAX_OPTIONS"
    MAX_SEMESTERS_AHEAD = "MAX_SEMESTERS_AHEAD"
    MAX_PATHS = "MAX_PATHS"
    TOTAL_CREDIT_HOURS = "TOTAL_CREDIT_HOURS"
    TOTAL_COURSES = "TOTAL_COURSES"
    MANDATORY_COURSE_COUNT = "MANDATORY_COURSE_COUNT"
    COMPLETED_PLAN_CREDIT_DELTA = "COMPLETED_PLAN_CREDIT_DELTA"
    NEWLY_SATISFIED_GROUP_COUNT = "NEWLY_SATISFIED_GROUP_COUNT"
    RECOMMENDATION_RANK_SUM = "RECOMMENDATION_RANK_SUM"
    SEMESTER_INDEX = "SEMESTER_INDEX"
    SEMESTER_COUNT = "SEMESTER_COUNT"
    TOTAL_PLANNED_COURSES = "TOTAL_PLANNED_COURSES"
    TOTAL_PLANNED_CREDITS = "TOTAL_PLANNED_CREDITS"
    FINAL_COMPLETED_CREDITS = "FINAL_COMPLETED_CREDITS"
    FINAL_REMAINING_CREDITS = "FINAL_REMAINING_CREDITS"
    AGGREGATE_SEMESTER_RANK_SUM = "AGGREGATE_SEMESTER_RANK_SUM"
    BLOCKER_CODE = "BLOCKER_CODE"
    POLICY_VERSION = "POLICY_VERSION"


class GraphFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: GraphFactKey
    value: str | int | bool | Decimal


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    type: GraphNodeType
    decision: Decision | None = None
    reason: DecisionReason | None = None
    course_code: str | None = None
    reference_code: str | None = None
    group_number: int | None = None
    dependency_type: DependencyType | None = None
    option_course_codes: tuple[str, ...] = ()
    passed_option_course_codes: tuple[str, ...] = ()
    non_passed_option_course_codes: tuple[str, ...] = ()
    academic_state: AcademicState | None = None
    limitation: GraphLimitation | None = None
    facts: tuple[GraphFact, ...] = ()


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    from_node_id: str
    to_node_id: str
    relation: EdgeRelation


class ExplainabilityGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    graph_id: str
    subject_type: str
    subject_reference: str
    root_node_id: str
    mode: GraphMode
    target_decision: Decision | None
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    generated_at: datetime
    policy_versions: tuple[str, ...]
    source_versions: tuple[str, ...]
    limitations: tuple[GraphLimitation, ...]


_COURSE_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")
_MAX_NODES = 5000
_MAX_EDGES = 10000
_EDGE_TYPES = {
    EdgeRelation.DECIDED_BY: {(GraphNodeType.DECISION, GraphNodeType.REASON)},
    EdgeRelation.REFERENCES: {
        (GraphNodeType.DECISION, GraphNodeType.COURSE),
        (GraphNodeType.PREREQUISITE_GROUP, GraphNodeType.COURSE),
        (GraphNodeType.RECOMMENDATION, GraphNodeType.COURSE),
        (GraphNodeType.SEMESTER, GraphNodeType.COURSE),
        (GraphNodeType.DEGREE_PATH, GraphNodeType.COURSE),
        (GraphNodeType.REASON, GraphNodeType.COURSE),
    },
    EdgeRelation.SUPPORTED_BY: {
        (GraphNodeType.REASON, GraphNodeType.PREREQUISITE_GROUP),
        (GraphNodeType.DECISION, GraphNodeType.PREREQUISITE_GROUP),
        (GraphNodeType.COURSE, GraphNodeType.ACADEMIC_STATE),
        (GraphNodeType.REASON, GraphNodeType.ACADEMIC_STATE),
        (GraphNodeType.RECOMMENDATION, GraphNodeType.ACADEMIC_STATE),
        (GraphNodeType.RECOMMENDATION, GraphNodeType.REASON),
        (GraphNodeType.SEMESTER, GraphNodeType.REASON),
        (GraphNodeType.DEGREE_PATH, GraphNodeType.REASON),
    },
    EdgeRelation.SATISFIED_BY: {(GraphNodeType.PREREQUISITE_GROUP, GraphNodeType.COURSE)},
    EdgeRelation.BLOCKED_BY: {
        (GraphNodeType.REASON, GraphNodeType.PREREQUISITE_GROUP),
        (GraphNodeType.PREREQUISITE_GROUP, GraphNodeType.COURSE),
    },
    EdgeRelation.LIMITED_BY: {(GraphNodeType.DECISION, GraphNodeType.LIMITATION)},
    EdgeRelation.CONTRIBUTES_TO: {
        (GraphNodeType.RECOMMENDATION, GraphNodeType.REQUIREMENT_GROUP),
        (GraphNodeType.SEMESTER, GraphNodeType.REQUIREMENT_GROUP),
        (GraphNodeType.DEGREE_PATH, GraphNodeType.REQUIREMENT_GROUP),
    },
    EdgeRelation.CONSTRAINED_BY: {
        (GraphNodeType.RECOMMENDATION, GraphNodeType.CONSTRAINT),
        (GraphNodeType.SEMESTER, GraphNodeType.CONSTRAINT),
        (GraphNodeType.DEGREE_PATH, GraphNodeType.CONSTRAINT),
    },
    EdgeRelation.SELECTED_IN: {
        (GraphNodeType.SEMESTER, GraphNodeType.COURSE),
        (GraphNodeType.DEGREE_PATH, GraphNodeType.SEMESTER),
    },
    EdgeRelation.LEADS_TO: {
        (GraphNodeType.RECOMMENDATION, GraphNodeType.COURSE),
        (GraphNodeType.SEMESTER, GraphNodeType.COURSE),
    },
    EdgeRelation.VERSIONED_BY: {
        (GraphNodeType.RECOMMENDATION, GraphNodeType.POLICY_VERSION),
        (GraphNodeType.SEMESTER, GraphNodeType.POLICY_VERSION),
        (GraphNodeType.DEGREE_PATH, GraphNodeType.POLICY_VERSION),
    },
    EdgeRelation.RANKED_AS: {
        (GraphNodeType.RECOMMENDATION, GraphNodeType.RECOMMENDATION),
        (GraphNodeType.SEMESTER, GraphNodeType.SEMESTER),
        (GraphNodeType.DEGREE_PATH, GraphNodeType.DEGREE_PATH),
    },
}
_EDGE_TYPES[EdgeRelation.LIMITED_BY].update({
    (GraphNodeType.RECOMMENDATION, GraphNodeType.LIMITATION),
    (GraphNodeType.SEMESTER, GraphNodeType.LIMITATION),
    (GraphNodeType.DEGREE_PATH, GraphNodeType.LIMITATION),
})
_REVIEW_LIMITATION = {
    DecisionReason.PREREQUISITE_LOGIC_UNRESOLVED: GraphLimitation.PREREQUISITE_LOGIC_UNRESOLVED,
    DecisionReason.PREREQUISITE_SOURCE_CONFLICT: GraphLimitation.PREREQUISITE_SOURCE_CONFLICT,
    DecisionReason.VERIFIED_PREREQUISITE_MODEL_INCOMPLETE: GraphLimitation.VERIFIED_MODEL_INCOMPLETE,
}


def build_eligibility_graph(
    result: CanTakeDecision, *, mode: GraphMode = GraphMode.WHY,
    target_decision: Decision | None = None,
) -> ExplainabilityGraph:
    """Project one authoritative decision without rerunning or changing it."""
    if not isinstance(result, CanTakeDecision) or result.kind != "decision":
        raise ValueError("an authoritative eligibility decision is required")
    if not isinstance(result.decision, Decision) or not isinstance(mode, GraphMode):
        raise ValueError("unsupported graph decision or mode")
    if mode is GraphMode.WHY and target_decision is not None:
        raise ValueError("WHY does not accept an alternative target")
    if mode is GraphMode.WHY_NOT and (
        target_decision is not Decision.ELIGIBLE or result.decision is Decision.ELIGIBLE
    ):
        raise ValueError("WHY_NOT supports only an existing blocker of ELIGIBLE")
    code = _safe_code(result.target_course_code)
    if result.decision is Decision.REVIEW_REQUIRED and not result.review_reasons:
        raise ValueError("review decision requires an approved review reason")
    if result.decision is Decision.NOT_ELIGIBLE and not result.missing_dependency_groups:
        raise ValueError("not-eligible decision requires an existing missing group")
    if any(not isinstance(reason, DecisionReason) for reason in (*result.reasons, *result.review_reasons)):
        raise ValueError("unknown reason is not graphable")

    nodes: dict[str, GraphNode] = {}
    edges: set[tuple[str, str, EdgeRelation]] = set()

    def add(node: GraphNode) -> None:
        existing = nodes.get(node.id)
        if existing is not None and existing != node:
            raise ValueError("conflicting graph node identity")
        nodes[node.id] = node

    def link(source: str, target: str, relation: EdgeRelation) -> None:
        edges.add((source, target, relation))

    root = f"decision:{code}"
    target_course = f"course:{code}"
    add(GraphNode(id=root, type=GraphNodeType.DECISION, decision=result.decision))
    add(GraphNode(id=target_course, type=GraphNodeType.COURSE, course_code=code))
    link(root, target_course, EdgeRelation.REFERENCES)

    reasons = tuple(dict.fromkeys(result.reasons))
    if mode is GraphMode.WHY_NOT:
        reasons = tuple(reason for reason in reasons if reason in {
            DecisionReason.MISSING_PREREQUISITE_GROUP,
            DecisionReason.PREREQUISITE_LOGIC_UNRESOLVED,
            DecisionReason.PREREQUISITE_SOURCE_CONFLICT,
            DecisionReason.VERIFIED_PREREQUISITE_MODEL_INCOMPLETE,
        })
        if not reasons:
            raise ValueError("no existing blocker supports WHY_NOT")

    for reason in reasons:
        reason_id = f"reason:{reason.value}"
        add(GraphNode(id=reason_id, type=GraphNodeType.REASON, reason=reason))
        link(root, reason_id, EdgeRelation.DECIDED_BY)

    groups = (
        tuple(result.missing_dependency_groups)
        if mode is GraphMode.WHY_NOT else
        tuple(result.satisfied_dependency_groups) + tuple(result.missing_dependency_groups)
    )
    numbers: set[int] = set()
    for group in sorted(groups, key=lambda item: item.group_number):
        if group.group_number <= 0 or group.group_number in numbers:
            raise ValueError("invalid prerequisite group identity")
        numbers.add(group.group_number)
        if group.dependency_type is not DependencyType.PREREQUISITE:
            raise ValueError("only evaluated prerequisite groups are graphable")
        options = tuple(sorted(set(_safe_code(item) for item in group.option_course_codes)))
        passed = tuple(sorted(set(_safe_code(item) for item in group.passed_option_course_codes)))
        not_passed = tuple(sorted(set(_safe_code(item) for item in group.non_passed_option_course_codes)))
        if not options or set(passed) | set(not_passed) != set(options) or set(passed) & set(not_passed):
            raise ValueError("prerequisite evidence is inconsistent")
        is_missing = group in result.missing_dependency_groups
        if is_missing == bool(passed):
            raise ValueError("group satisfaction contradicts engine evidence")
        group_id = f"prereq-group:{code}:{group.group_number}"
        add(GraphNode(
            id=group_id, type=GraphNodeType.PREREQUISITE_GROUP,
            group_number=group.group_number, dependency_type=group.dependency_type,
            option_course_codes=options, passed_option_course_codes=passed,
            non_passed_option_course_codes=not_passed,
        ))
        cause = (DecisionReason.MISSING_PREREQUISITE_GROUP if is_missing
                 else DecisionReason.PREREQUISITES_SATISFIED)
        if cause in reasons:
            link(f"reason:{cause.value}", group_id,
                 EdgeRelation.BLOCKED_BY if is_missing else EdgeRelation.SUPPORTED_BY)
        elif not is_missing and result.decision is Decision.NOT_ELIGIBLE:
            # An otherwise satisfied AND group is evidence, not the blocker.
            link(root, group_id, EdgeRelation.SUPPORTED_BY)
        else:
            raise ValueError("group has no matching authoritative reason")
        for option in options:
            course_id = f"course:{option}"
            add(GraphNode(id=course_id, type=GraphNodeType.COURSE, course_code=option))
            state = AcademicState.PASSED if option in passed else AcademicState.NOT_PASSED
            state_id = f"state:{option}:{state.value}"
            add(GraphNode(id=state_id, type=GraphNodeType.ACADEMIC_STATE,
                          course_code=option, academic_state=state))
            link(group_id, course_id,
                 EdgeRelation.SATISFIED_BY if option in passed else
                 EdgeRelation.BLOCKED_BY if is_missing else EdgeRelation.REFERENCES)
            link(course_id, state_id, EdgeRelation.SUPPORTED_BY)

    if mode is GraphMode.WHY:
        for reason, active, state in (
            (DecisionReason.TARGET_ALREADY_COMPLETED, result.target_attempt_state.has_passed_target,
             AcademicState.TARGET_COMPLETED),
            (DecisionReason.TARGET_CURRENTLY_ENROLLED, result.target_attempt_state.has_in_progress_target,
             AcademicState.TARGET_IN_PROGRESS),
        ):
            if active and reason in reasons:
                state_id = f"state:{code}:{state.value}"
                add(GraphNode(id=state_id, type=GraphNodeType.ACADEMIC_STATE,
                              course_code=code, academic_state=state))
                link(f"reason:{reason.value}", state_id, EdgeRelation.SUPPORTED_BY)

    limitations = [GraphLimitation.CURRENT_STORED_STATE,
                   GraphLimitation.NOT_OFFICIAL_REGISTRATION,
                   GraphLimitation.EXACT_SOURCE_VERSION_UNAVAILABLE]
    for reason in reasons:
        if reason in _REVIEW_LIMITATION:
            limitations.append(_REVIEW_LIMITATION[reason])
    for limitation in limitations:
        limitation_id = f"limitation:{limitation.value}"
        add(GraphNode(id=limitation_id, type=GraphNodeType.LIMITATION,
                      limitation=limitation))
        link(root, limitation_id, EdgeRelation.LIMITED_BY)

    graph = ExplainabilityGraph(
        graph_id=f"eligibility:{code}:{result.decision.value}:{mode.value}",
        subject_type="ELIGIBILITY", subject_reference=code, root_node_id=root,
        mode=mode, target_decision=target_decision,
        nodes=tuple(nodes[key] for key in sorted(nodes)),
        edges=tuple(GraphEdge(from_node_id=source, to_node_id=target, relation=relation)
                    for source, target, relation in sorted(edges)),
        generated_at=datetime.now(timezone.utc), policy_versions=(), source_versions=(),
        limitations=tuple(sorted(set(limitations))),
    )
    validate_graph(graph)
    return graph


def validate_graph(graph: ExplainabilityGraph) -> None:
    """Fail closed on dangling edges, duplicate IDs, excess size, or a DAG cycle."""
    if len(graph.nodes) > _MAX_NODES or len(graph.edges) > _MAX_EDGES:
        raise ValueError("graph exceeds the bounded V1 projection")
    by_id = {node.id: node for node in graph.nodes}
    ids = set(by_id)
    if (len(ids) != len(graph.nodes) or graph.root_node_id not in ids
            or by_id[graph.root_node_id].type not in {
                GraphNodeType.DECISION, GraphNodeType.RECOMMENDATION,
                GraphNodeType.SEMESTER, GraphNodeType.DEGREE_PATH,
            }):
        raise ValueError("graph node identities are invalid")
    if len({(edge.from_node_id, edge.to_node_id, edge.relation) for edge in graph.edges}) != len(graph.edges):
        raise ValueError("duplicate graph edge")
    adjacency = {node_id: set() for node_id in ids}
    for edge in graph.edges:
        if edge.from_node_id not in ids or edge.to_node_id not in ids:
            raise ValueError("graph edge references a missing node")
        if (by_id[edge.from_node_id].type, by_id[edge.to_node_id].type) not in _EDGE_TYPES[edge.relation]:
            raise ValueError("graph edge violates the closed relation registry")
        adjacency[edge.from_node_id].add(edge.to_node_id)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError("graph contains a directed cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in adjacency[node_id]:
            visit(child)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in ids:
        visit(node_id)


def _safe_code(value: str) -> str:
    if not isinstance(value, str) or _COURSE_CODE.fullmatch(value) is None:
        raise ValueError("unsafe course code in eligibility evidence")
    return value
