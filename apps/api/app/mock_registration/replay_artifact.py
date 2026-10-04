"""Version-one, private historical inputs for exact P6 submit validation replay.

Only fields read by the accepted P6 validator and its Phase 5 evaluator are
retained. Unused GPA, names, raw prerequisite prose and profile fields are not
part of this audit artifact. The V1 adapter is deliberately closed: changing
validation semantics requires a new engine version, not a registry overwrite.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.progress.models import (
    AcademicProgress, AcademicProgressCatalog, CourseProgress,
    CourseProgressState, ProgressPlanCourse, ProgressRequirementGroup,
    ProgressStudyPlan, RequirementGroupProgress, RequirementType,
)
from app.rules.models import (
    AttemptOutcome, CanTakeCatalog, CourseCatalogStatus, CourseIdentity,
    DependencyGroup, DependencyType, PlanCourseRule, PrerequisiteLogicStatus,
    StudentCourseAttempt,
)

from .models import (
    MockRegistrationContext, RegistrationIntent, TargetPeriod, ValidatedIntent,
    ValidationStatus,
)
from .validation import validate_registration_intent


REPLAY_CONTRACT_VERSION = "P6_REPLAY_ARTIFACT_V1"
REPLAY_ENGINE_ID = "P6_MOCK_REGISTRATION_VALIDATION"
REPLAY_ENGINE_VERSION = "1.0"
_INTENT = TypeAdapter(RegistrationIntent)
_PERIOD = TypeAdapter(TargetPeriod)
_OUTPUT = TypeAdapter(ValidatedIntent)
_PINNED_V1_SOURCES = {
    Path(__file__).with_name("validation.py"): "d4e73cc51dcf3b1cdce70ce1924cae89d9cb9680ccf7125823aa9a116e2b66cc",
    Path(__file__).with_name("fingerprint.py"): "7c4e43c6b2db9197f0d45bc42e4bddf5cd7022707b22659a96079f74df0cfa90",
    Path(__file__).with_name("canonicalization.py"): "92c769d693372d7996a5fbcec6e4dd913c9c260ef49daaf5263c24322756bbff",
    Path(__file__).with_name("models.py"): "0e42a6cce44610e07a0a029972ef174076b94440b0e7f4e8cde29166e521e177",
    Path(__file__).with_name("registries.py"): "c7c30b1dc2f1650fe07ec0346b40630173d1dd8efa98283fdd3023f104e04796",
    Path(__file__).parents[1] / "rules" / "evaluator.py": "54a330d16cc12a66bfb05d149e2ebcd30ea38d7e6e5cc5c747c2f99ea907f32f",
    Path(__file__).parents[1] / "rules" / "models.py": "ade6a482199d972db57aec6d919614132c9d31505bace243d47a3829246c09da",
    Path(__file__).parents[1] / "progress" / "models.py": "e207a51d267abe6158cbba46aaeb377d88acbdb7da3d6f49ba97c9b66c52b9a3",
}


class P6ReplayArtifactError(ValueError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class P6ReplayArtifactV1:
    replay_contract_version: str
    engine_id: str
    engine_version: str
    canonical_payload: str
    canonical_sha256: str
    source_versions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class P6ReplayVerification:
    status: str
    matched: bool
    reason_code: str | None
    historical_validation_status: str | None
    replayed_validation_status: str | None
    historical_reason_codes: tuple[str, ...]
    replayed_reason_codes: tuple[str, ...]
    historical_content_fingerprint: str | None
    replayed_content_fingerprint: str | None


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_p6_replay_artifact(
    intent: RegistrationIntent, context: MockRegistrationContext, result: ValidatedIntent,
) -> P6ReplayArtifactV1:
    _require_pinned_v1_engine()
    if intent.contract_version != REPLAY_ENGINE_VERSION or result.intent != intent:
        raise P6ReplayArtifactError("REPLAY_INPUT_MISMATCH")
    if result.status not in (ValidationStatus.VALID, ValidationStatus.REVIEW_REQUIRED):
        raise P6ReplayArtifactError("REPLAY_INPUT_MISMATCH")
    # The generated intent ID is deliberately omitted: P6 idempotent retries
    # generate a new one, while the immutable inserted revision supplies it.
    intent_data = _INTENT.dump_python(intent, mode="json")
    intent_data.pop("intent_id")
    value = {
        "contract": REPLAY_CONTRACT_VERSION,
        "engine_id": REPLAY_ENGINE_ID,
        "engine_version": REPLAY_ENGINE_VERSION,
        "intent": intent_data,
        "context": _minimal_context(context),
        "historical_output": _output_data(result),
    }
    canonical = _canonical(value)
    return P6ReplayArtifactV1(
        REPLAY_CONTRACT_VERSION, REPLAY_ENGINE_ID, REPLAY_ENGINE_VERSION,
        canonical, _hash(canonical), tuple(context.source_versions),
    )


def _output_data(result: ValidatedIntent) -> dict[str, Any]:
    data = _OUTPUT.dump_python(result, mode="json")
    data.pop("intent")
    return data


def _minimal_context(context: MockRegistrationContext) -> dict[str, Any]:
    eligibility = context.eligibility_catalog
    progress = context.progress_catalog
    current = context.current_progress
    return {
        "owner_scope_id": context.owner_scope_id,
        "university_id": context.university_id,
        "major_id": context.major_id,
        "study_plan_id": context.study_plan_id,
        "study_plan_version": context.study_plan_version,
        "allowed_target_period": _PERIOD.dump_python(context.allowed_target_period, mode="json"),
        "source_versions": list(context.source_versions),
        "engine_policy_versions": list(context.engine_policy_versions),
        "eligibility_catalog": {
            "study_plan_id": eligibility.study_plan_id,
            "courses": [c.course_code for c in eligibility.courses],
            "plan_courses": [{
                "course_code": c.course_code,
                "prerequisite_logic_status": c.prerequisite_logic_status.value,
                "dependency_groups": [{
                    "group_number": g.group_number,
                    "dependency_type": g.dependency_type.value,
                    "option_course_codes": list(g.option_course_codes),
                } for g in c.dependency_groups],
            } for c in eligibility.plan_courses],
        },
        "progress_catalog": {
            "study_plan_id": progress.study_plan.study_plan_id,
            "plan_courses": [{
                "course_code": c.course_code,
                "requirement_group_id": c.requirement_group_id,
                "credit_hours": str(c.credit_hours),
            } for c in progress.plan_courses],
            "requirement_groups": [{
                "group_id": g.group_id,
                "group_code": g.group_code,
                "requirement_type": g.requirement_type.value,
            } for g in progress.requirement_groups],
        },
        "current_progress": {
            "study_plan_id": current.study_plan_id,
            "courses": [{"course_code": c.course_code, "state": c.state.value}
                        for c in current.courses],
            "requirement_groups": [{"group_id": g.group_id, "is_satisfied": g.is_satisfied}
                                   for g in current.requirement_groups],
        },
        "student_attempts": [{"course_code": a.course_code, "outcome": a.outcome.value}
                             for a in context.student_attempts],
    }


def verify_p6_replay_artifact(artifact: P6ReplayArtifactV1) -> dict[str, Any]:
    if artifact.replay_contract_version != REPLAY_CONTRACT_VERSION:
        raise P6ReplayArtifactError("REPLAY_CONTRACT_UNAVAILABLE")
    if artifact.engine_id != REPLAY_ENGINE_ID:
        raise P6ReplayArtifactError("ENGINE_VERSION_UNAVAILABLE")
    if artifact.engine_version not in P6_REPLAY_ENGINE_REGISTRY:
        raise P6ReplayArtifactError("ENGINE_VERSION_UNAVAILABLE")
    try:
        payload = json.loads(artifact.canonical_payload)
        if _canonical(payload) != artifact.canonical_payload or _hash(artifact.canonical_payload) != artifact.canonical_sha256:
            raise P6ReplayArtifactError("REPLAY_ARTIFACT_INTEGRITY_FAILURE")
        if set(payload) != {"contract", "engine_id", "engine_version", "intent", "context", "historical_output"}:
            raise ValueError("artifact keys")
        if (payload["contract"], payload["engine_id"], payload["engine_version"]) != (
            artifact.replay_contract_version, artifact.engine_id, artifact.engine_version,
        ):
            raise ValueError("artifact metadata")
        if tuple(payload["context"]["source_versions"]) != artifact.source_versions:
            raise ValueError("source versions")
        return payload
    except (TypeError, KeyError, ValueError) as exc:
        if isinstance(exc, P6ReplayArtifactError):
            raise
        raise P6ReplayArtifactError("REPLAY_ARTIFACT_INTEGRITY_FAILURE") from exc


def reconstruct_p6_inputs(
    payload: dict[str, Any], *, persisted_intent_id: str,
) -> tuple[RegistrationIntent, MockRegistrationContext]:
    """Reconstruct exactly the V1 validator-accessed facts, never current state."""
    try:
        intent_data = dict(payload["intent"])
        intent_data["intent_id"] = persisted_intent_id
        intent = _INTENT.validate_python(intent_data)
        c = payload["context"]
        ec = c["eligibility_catalog"]
        pc = c["progress_catalog"]
        cp = c["current_progress"]
        zero = Decimal("0")
        eligibility = CanTakeCatalog(
            ec["study_plan_id"],
            tuple(PlanCourseRule(
                row["course_code"], PrerequisiteLogicStatus(row["prerequisite_logic_status"]),
                tuple(DependencyGroup(g["group_number"], DependencyType(g["dependency_type"]),
                                      tuple(g["option_course_codes"])) for g in row["dependency_groups"]),
            ) for row in ec["plan_courses"]),
            tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in ec["courses"]),
        )
        progress_catalog = AcademicProgressCatalog(
            ProgressStudyPlan(pc["study_plan_id"], zero),
            tuple(ProgressRequirementGroup(
                g["group_id"], pc["study_plan_id"], g["group_code"], "", None, "",
                RequirementType(g["requirement_type"]), zero, 0,
            ) for g in pc["requirement_groups"]),
            tuple(ProgressPlanCourse(
                "", pc["study_plan_id"], row["requirement_group_id"], row["course_code"],
                CourseCatalogStatus.KNOWN, Decimal(row["credit_hours"]), 0,
            ) for row in pc["plan_courses"]),
        )
        current = AcademicProgress(
            cp["study_plan_id"], zero, zero, zero, zero, 0, 0, False,
            tuple(RequirementGroupProgress(
                g["group_id"], "", "", None, "", RequirementType.REQUIRED,
                zero, zero, zero, zero, zero, zero, 0, 0, 0, 0, 0,
                g["is_satisfied"],
            ) for g in cp["requirement_groups"]),
            tuple(CourseProgress(row["course_code"], zero, "", "",
                                 CourseProgressState(row["state"])) for row in cp["courses"]),
            None, None, None,
        )
        context = MockRegistrationContext(
            c["owner_scope_id"], c["university_id"], c["major_id"], c["study_plan_id"],
            c["study_plan_version"], eligibility, progress_catalog, current,
            tuple(StudentCourseAttempt(a["course_code"], AttemptOutcome(a["outcome"]))
                  for a in c["student_attempts"]),
            tuple(c["source_versions"]), tuple(c["engine_policy_versions"]),
            _PERIOD.validate_python(c["allowed_target_period"]),
        )
        if intent.owner_scope_id != context.owner_scope_id or intent.target_period != context.allowed_target_period:
            raise ValueError("scope mismatch")
        return intent, context
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise P6ReplayArtifactError("REPLAY_ARTIFACT_MALFORMED") from exc


def _replay_v1(intent: RegistrationIntent, context: MockRegistrationContext) -> ValidatedIntent:
    # Pin to the accepted P6 1.0 validator. A later semantic change must add a
    # new registry entry and preserve this implementation, not replace it.
    _require_pinned_v1_engine()
    return validate_registration_intent(intent, context)


def _require_pinned_v1_engine() -> None:
    """A changed validator/dependency cannot silently impersonate historical 1.0."""
    try:
        for path, expected in _PINNED_V1_SOURCES.items():
            normalized = path.read_bytes().replace(b"\r\n", b"\n")
            if hashlib.sha256(normalized).hexdigest() != expected:
                raise P6ReplayArtifactError("ENGINE_VERSION_UNAVAILABLE")
    except OSError as exc:
        raise P6ReplayArtifactError("ENGINE_VERSION_UNAVAILABLE") from exc


P6_REPLAY_ENGINE_REGISTRY = {REPLAY_ENGINE_VERSION: _replay_v1}


def execute_p6_replay(
    artifact: P6ReplayArtifactV1, *, persisted_intent_id: str,
    persisted_status: ValidationStatus, persisted_reasons: tuple[str, ...],
    persisted_fingerprint: str, persisted_course_codes: tuple[str, ...],
) -> P6ReplayVerification:
    payload = verify_p6_replay_artifact(artifact)
    intent, context = reconstruct_p6_inputs(payload, persisted_intent_id=persisted_intent_id)
    historical = payload["historical_output"]
    try:
        historical_typed = _OUTPUT.validate_python({
            **historical, "intent": _INTENT.dump_python(intent, mode="json"),
        })
        if _output_data(historical_typed) != historical:
            raise P6ReplayArtifactError("REPLAY_ARTIFACT_MALFORMED")
        replayed = P6_REPLAY_ENGINE_REGISTRY[artifact.engine_version](intent, context)
        replayed_output = _output_data(replayed)
        original_matches_persistence = (
            historical["status"] == persisted_status.value
            and tuple(historical["reason_codes"]) == persisted_reasons
            and historical["content_fingerprint"] == persisted_fingerprint
            and tuple(historical["canonical_course_codes"]) == persisted_course_codes
        )
        matched = original_matches_persistence and replayed_output == historical
        return P6ReplayVerification(
            "MATCHED" if matched else "MISMATCH", matched, None if matched else "REPLAY_OUTPUT_MISMATCH",
            historical["status"], replayed.status.value,
            tuple(historical["reason_codes"]), tuple(code.value for code in replayed.reason_codes),
            historical["content_fingerprint"], replayed.content_fingerprint,
        )
    except P6ReplayArtifactError:
        raise
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise P6ReplayArtifactError("REPLAY_ARTIFACT_MALFORMED") from exc
