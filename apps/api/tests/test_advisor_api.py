"""HTTP contract tests for the authenticated read-only advisor endpoint."""

from __future__ import annotations

import inspect
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.advisor import (
    AdvisorIntent,
    ClarificationReason,
    ClarificationRequest,
    CourseResolution,
    EntityResolutionStatus,
    NormalizedAdvisorRequest,
    ProviderFailure,
    ProviderFailureType,
    ResolvedCourseReference,
    orchestrate_advisor_request,
    ExplanationStatus,
    ExplanationLanguage,
)
from app.advisor.orchestrator import AdvisorContext
from app.api.routes.advisor import get_advisor_service
from app.api.schemas.advisor import ADVISOR_MESSAGE_MAX_LENGTH
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.services.advisor import AdvisorProviderError, AdvisorServiceResult
from app.student.errors import StudentProfileNotFound
from app.planner.models import PlannerConstraints
from app.degree_path.models import DegreePathConstraints
from tests.test_advisor_orchestrator import _context


OWNER = "11111111-1111-1111-1111-111111111111"
ENDPOINT = "/api/v1/me/advisor"


class FakeAdvisorService:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    async def advise_with_explanation(self, owner: str, message: str):  # type: ignore[no-untyped-def]
        self.calls.append((owner, message))
        if isinstance(self.result, Exception):
            raise self.result
        if isinstance(self.result, AdvisorServiceResult):
            return self.result
        return AdvisorServiceResult(
            self.result,
            None,
            ExplanationStatus.UNAVAILABLE,
            None,
        )


def _general_result():  # type: ignore[no-untyped-def]
    return orchestrate_advisor_request(
        NormalizedAdvisorRequest("شو يعني prerequisite؟", AdvisorIntent.GENERAL_ACADEMIC_INFORMATION),
        AdvisorContext(),
    )


def _clarification_result():  # type: ignore[no-untyped-def]
    clarification = ClarificationRequest(
        ClarificationReason.AMBIGUOUS_INTENT,
        "advisor.clarify.ambiguous_intent",
    )
    return orchestrate_advisor_request(
        NormalizedAdvisorRequest(
            "وضح سؤالك",
            AdvisorIntent.CLARIFICATION_REQUIRED,
            clarification_request=clarification,
        ),
        AdvisorContext(),
    )


def _eligibility_result(code: str = "0300153"):  # type: ignore[no-untyped-def]
    course = ResolvedCourseReference(code, f"المساق {code}", f"Course {code}")
    return orchestrate_advisor_request(
        NormalizedAdvisorRequest(
            f"هل أستطيع أخذ {code}؟",
            AdvisorIntent.COURSE_ELIGIBILITY,
            course_resolution=CourseResolution(
                EntityResolutionStatus.RESOLVED,
                resolved_course=course,
            ),
        ),
        _context(),
    )


@pytest.fixture
def api() -> Iterator[tuple[TestClient, FakeAdvisorService]]:
    service = FakeAdvisorService(_general_result())
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    app.dependency_overrides[get_advisor_service] = lambda: service
    with TestClient(app) as client:
        yield client, service
    app.dependency_overrides.clear()


def test_01_endpoint_exists_and_accepts_post(api) -> None:
    response = api[0].post(ENDPOINT, json={"message": "شو يعني prerequisite؟"})
    assert response.status_code == 200


def test_02_endpoint_is_post_only(api) -> None:
    assert api[0].get(ENDPOINT).status_code == 405
    assert set(app.openapi()["paths"][ENDPOINT]) == {"post"}


def test_03_authentication_is_required() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        assert client.post(ENDPOINT, json={"message": "وضعي"}).status_code == 401


def test_04_valid_message_is_trimmed_and_owner_comes_from_auth(api) -> None:
    response = api[0].post(ENDPOINT, json={"message": "  وضعي الأكاديمي  "})
    assert response.status_code == 200
    assert api[1].calls == [(OWNER, "وضعي الأكاديمي")]


@pytest.mark.parametrize("message", ("", " ", "\n\t"))
def test_05_blank_message_is_rejected(api, message: str) -> None:
    assert api[0].post(ENDPOINT, json={"message": message}).status_code == 422


def test_06_null_message_is_rejected(api) -> None:
    assert api[0].post(ENDPOINT, json={"message": None}).status_code == 422


def test_07_overlong_message_is_rejected(api) -> None:
    body = {"message": "x" * (ADVISOR_MESSAGE_MAX_LENGTH + 1)}
    assert api[0].post(ENDPOINT, json=body).status_code == 422


@pytest.mark.parametrize(
    "field",
    (
        "owner_user_id",
        "student_id",
        "study_plan_id",
        "attempts",
        "gpa",
        "provider",
        "model",
        "temperature",
        "system_prompt",
        "api_key",
        "beam_width",
        "candidate_window",
    ),
)
def test_08_12_every_extra_control_field_is_forbidden(api, field: str) -> None:
    response = api[0].post(ENDPOINT, json={"message": "وضعي", field: "attacker"})
    assert response.status_code == 422
    assert api[1].calls == []


def test_13_deterministic_authority_returns_200(api) -> None:
    api[1].result = _eligibility_result()
    response = api[0].post(ENDPOINT, json={"message": "هل أستطيع أخذ 0300153؟"})
    assert response.status_code == 200
    assert response.json()["answer_authority"] == "DETERMINISTIC"
    assert response.json()["result"]["kind"] == "eligibility"


def test_14_review_required_returns_200_with_distinction(api) -> None:
    api[1].result = _eligibility_result("1505320")
    response = api[0].post(ENDPOINT, json={"message": "هل أستطيع أخذ 1505320؟"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer_authority"] == "REVIEW_REQUIRED"
    assert body["result"]["prerequisite_logic_status"] == "source_conflict"
    assert "PREREQUISITE_SOURCE_CONFLICT" in body["result"]["review_reasons"]


def test_15_general_information_returns_200(api) -> None:
    response = api[0].post(ENDPOINT, json={"message": "شو يعني prerequisite؟"})
    assert response.status_code == 200
    assert response.json()["answer_authority"] == "GENERAL_INFORMATION"
    assert response.json()["result"] is None


def test_16_clarification_returns_200(api) -> None:
    api[1].result = _clarification_result()
    response = api[0].post(ENDPOINT, json={"message": "وضح سؤالك"})
    assert response.status_code == 200
    assert response.json()["answer_authority"] == "INSUFFICIENT_CONTEXT"
    assert response.json()["clarification"]["reason"] == "AMBIGUOUS_INTENT"


@pytest.mark.parametrize(
    ("failure_type", "status_code", "error_code"),
    (
        (ProviderFailureType.PROVIDER_UNAVAILABLE, 503, "ADVISOR_PROVIDER_UNAVAILABLE"),
        (ProviderFailureType.TIMEOUT, 503, "ADVISOR_PROVIDER_TIMEOUT"),
        (ProviderFailureType.MALFORMED_STRUCTURED_OUTPUT, 502, "ADVISOR_PROVIDER_RESPONSE_INVALID"),
        (ProviderFailureType.SCHEMA_MISMATCH, 502, "ADVISOR_PROVIDER_RESPONSE_INVALID"),
    ),
)
def test_17_19_provider_failures_have_safe_http_mapping(
    api,
    failure_type: ProviderFailureType,
    status_code: int,
    error_code: str,
) -> None:
    api[1].result = AdvisorProviderError(ProviderFailure(failure_type, "secret-free.key"))
    response = api[0].post(ENDPOINT, json={"message": "وضعي"})
    assert response.status_code == status_code
    assert response.json()["error_code"] == error_code
    assert "secret-free.key" not in response.text


def test_20_profile_not_found_uses_established_404(api) -> None:
    api[1].result = StudentProfileNotFound("private repository detail")
    response = api[0].post(ENDPOINT, json={"message": "وضعي"})
    assert response.status_code == 404
    assert response.json()["error_code"] == "STUDENT_RESOURCE_NOT_FOUND"
    assert "private repository detail" not in response.text


@pytest.mark.parametrize(
    "forbidden",
    (
        "bearer",
        "authorization",
        "api_key",
        "provider_credentials",
        "raw_prompt",
        "raw_provider_response",
        "chain_of_thought",
        "owner_user_id",
    ),
)
def test_21_25_response_excludes_secrets_prompts_and_identity(api, forbidden: str) -> None:
    response = api[0].post(
        ENDPOINT,
        headers={"Authorization": "Bearer test-secret-token"},
        json={"message": "شو يعني prerequisite؟"},
    )
    assert forbidden not in response.text.casefold()
    assert "test-secret-token" not in response.text


def test_26_openapi_documents_request_response_and_bearer_security(api) -> None:
    schema = api[0].get("/openapi.json").json()
    operation = schema["paths"][ENDPOINT]["post"]
    assert operation["security"] == [{"HTTPBearer": []}]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/AdvisorRequest"
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/AdvisorResponse"
    )


def test_27_openapi_request_forbids_additional_properties(api) -> None:
    request_schema = api[0].get("/openapi.json").json()["components"]["schemas"]["AdvisorRequest"]
    assert request_schema["additionalProperties"] is False


def test_28_openapi_request_has_exact_message_field(api) -> None:
    request_schema = api[0].get("/openapi.json").json()["components"]["schemas"]["AdvisorRequest"]
    assert set(request_schema["properties"]) == {"message"}
    assert request_schema["required"] == ["message"]
    assert request_schema["properties"]["message"]["maxLength"] == 4000


def test_29_response_has_minimized_safe_trace(api) -> None:
    api[1].result = _eligibility_result("1505320")
    trace = api[0].post(ENDPOINT, json={"message": "1505320"}).json()["trace"]
    assert set(trace) == {
        "authoritative_sources",
        "course_codes",
        "decision_references",
        "policy_versions",
        "option_references",
    }


def test_30_route_introduces_no_academic_mutation_action() -> None:
    source = inspect.getsource(__import__("app.api.routes.advisor", fromlist=["*"]))
    for operation in ("create_attempt", "update_attempt", "delete_attempt", "register_course"):
        assert operation not in source


def test_31_response_preserves_canonical_course_identity(api) -> None:
    api[1].result = _eligibility_result("0300153")
    resolved = api[0].post(ENDPOINT, json={"message": "0300153"}).json()["course_resolution"]
    assert resolved["resolved_course"] == {
        "course_code": "0300153",
        "canonical_arabic_name": "المساق 0300153",
        "canonical_english_name": "Course 0300153",
    }


def test_32_response_preserves_policy_versions(api) -> None:
    body = api[0].post(ENDPOINT, json={"message": "general"}).json()
    assert body["policy_version"] == "1.0"
    assert body["trace"]["policy_versions"] == [{"source": "AI_ADVISOR", "version": "1.0"}]


@pytest.mark.parametrize(
    ("intent", "kind"),
    (
        (AdvisorIntent.ACADEMIC_STATUS, "progress"),
        (AdvisorIntent.COURSE_RECOMMENDATIONS, "recommendations"),
        (AdvisorIntent.SEMESTER_PLANNING, "semester_plans"),
        (AdvisorIntent.DEGREE_PATH_MODELING, "degree_paths"),
        (AdvisorIntent.COURSE_INFORMATION, "course_information"),
    ),
)
def test_33_all_authoritative_payload_families_serialize(api, intent: AdvisorIntent, kind: str) -> None:
    context = _context()
    kwargs: dict[str, object] = {}
    if intent is AdvisorIntent.SEMESTER_PLANNING:
        kwargs["planning_constraints"] = PlannerConstraints(max_credit_hours=15)
    elif intent is AdvisorIntent.DEGREE_PATH_MODELING:
        kwargs["planning_constraints"] = DegreePathConstraints(max_credit_hours_per_semester=15)
    elif intent is AdvisorIntent.COURSE_INFORMATION:
        kwargs["course_resolution"] = CourseResolution(
            EntityResolutionStatus.RESOLVED,
            resolved_course=ResolvedCourseReference("1505311", "تعلم الآلة", "Machine Learning"),
        )
    request = NormalizedAdvisorRequest("advisor request", intent, **kwargs)  # type: ignore[arg-type]
    api[1].result = orchestrate_advisor_request(request, context)
    response = api[0].post(ENDPOINT, json={"message": "advisor request"})
    assert response.status_code == 200
    assert response.json()["result"]["kind"] == kind


def test_34_response_includes_typed_explanation_fields(api) -> None:
    api[1].result = AdvisorServiceResult(
        _general_result(),
        "شرح عام فقط.",
        ExplanationStatus.GENERATED,
        ExplanationLanguage.ARABIC,
    )
    body = api[0].post(ENDPOINT, json={"message": "اشرح"}).json()
    assert body["explanation"] == "شرح عام فقط."
    assert body["explanation_status"] == "GENERATED"
    assert body["explanation_language"] == "ar"


def test_35_explanation_unavailable_keeps_structured_response_200(api) -> None:
    api[1].result = AdvisorServiceResult(
        _eligibility_result(),
        None,
        ExplanationStatus.UNAVAILABLE,
        None,
    )
    response = api[0].post(ENDPOINT, json={"message": "0300153"})
    assert response.status_code == 200
    assert response.json()["result"]["kind"] == "eligibility"
    assert response.json()["explanation"] is None


def test_36_openapi_exposes_explanation_but_no_provider_controls(api) -> None:
    schema = api[0].get("/openapi.json").json()["components"]["schemas"]["AdvisorResponse"]
    assert {"explanation", "explanation_status", "explanation_language"}.issubset(
        schema["properties"]
    )
    serialized = str(schema).casefold()
    for forbidden in ("api_key", "provider", "model", "prompt", "request_id", "usage"):
        assert forbidden not in serialized
