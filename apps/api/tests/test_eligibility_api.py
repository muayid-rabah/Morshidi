"""HTTP contract tests for the deterministic CAN TAKE endpoint."""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.routes.eligibility import get_eligibility_service
from app.catalog.errors import (
    CatalogIntegrityError,
    CatalogTransportError,
    StudyPlanNotFound,
    TargetCourseNotFound,
    TargetCourseNotInStudyPlan,
)
from app.main import app
from app.rules.models import (
    CanTakeCatalog,
    CourseCatalogStatus,
    CourseIdentity,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
)
from app.services.eligibility import EligibilityService

PLAN_ID = "10000000-0000-0000-0000-000000000005"
ENDPOINT = "/api/v1/eligibility/can-take"


class FakeRepository:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[tuple[object, str]] = []

    async def load_target_rules(self, study_plan_id, target_course_code: str):
        self.calls.append((study_plan_id, target_course_code))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def catalog(
    *,
    target_code: str = "1501112",
    status: PrerequisiteLogicStatus = PrerequisiteLogicStatus.VERIFIED,
    groups: tuple[DependencyGroup, ...] | None = None,
    raw_text: str | None = None,
) -> CanTakeCatalog:
    if groups is None:
        groups = (
            (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501110",)),)
            if status is PrerequisiteLogicStatus.VERIFIED
            else ()
        )
    codes = {target_code}
    for group in groups:
        codes.update(group.option_course_codes)
    return CanTakeCatalog(
        study_plan_id=PLAN_ID,
        plan_courses=(PlanCourseRule(target_code, status, groups, raw_text),),
        courses=tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in sorted(codes)),
    )


@pytest.fixture
def api_client() -> Iterator[tuple[TestClient, FakeRepository]]:
    repository = FakeRepository(catalog())
    app.dependency_overrides[get_eligibility_service] = lambda: EligibilityService(repository)
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def request_body(target: str = "1501112", attempts: list[dict[str, str]] | None = None) -> dict:
    return {"study_plan_id": PLAN_ID, "target_course_code": target, "attempts": attempts or []}


def replace_repository(repository: FakeRepository) -> None:
    app.dependency_overrides[get_eligibility_service] = lambda: EligibilityService(repository)


def test_not_applicable_is_successful_eligible(api_client) -> None:
    client, _ = api_client
    replace_repository(FakeRepository(catalog(target_code="0200115", status=PrerequisiteLogicStatus.NOT_APPLICABLE)))
    response = client.post(ENDPOINT, json=request_body("0200115"))
    assert response.status_code == 200
    assert response.json()["decision"] == "ELIGIBLE"
    assert response.json()["reasons"] == ["NO_PREREQUISITES"]


@pytest.mark.parametrize(
    ("attempts", "decision"),
    [
        ([{"course_code": "1501110", "outcome": "PASSED"}], "ELIGIBLE"),
        ([{"course_code": "1501110", "outcome": "FAILED"}], "NOT_ELIGIBLE"),
        ([], "NOT_ELIGIBLE"),
        ([{"course_code": "1501110", "outcome": "IN_PROGRESS"}], "NOT_ELIGIBLE"),
        ([{"course_code": "1501110", "outcome": "WITHDRAWN"}], "NOT_ELIGIBLE"),
        (
            [
                {"course_code": "1501110", "outcome": "FAILED"},
                {"course_code": "1501110", "outcome": "PASSED"},
            ],
            "ELIGIBLE",
        ),
    ],
)
def test_verified_prerequisite_outcomes_are_pure_engine_decisions(api_client, attempts, decision) -> None:
    client, _ = api_client
    response = client.post(ENDPOINT, json=request_body(attempts=attempts))
    assert response.status_code == 200
    assert response.json()["decision"] == decision


@pytest.mark.parametrize(
    ("target_code", "status", "reason"),
    [
        ("1505311", PrerequisiteLogicStatus.UNRESOLVED, "PREREQUISITE_LOGIC_UNRESOLVED"),
        ("1505320", PrerequisiteLogicStatus.SOURCE_CONFLICT, "PREREQUISITE_SOURCE_CONFLICT"),
    ],
)
def test_non_executable_catalog_statuses_are_successful_review_responses(
    api_client,
    target_code,
    status,
    reason,
) -> None:
    client, _ = api_client
    replace_repository(FakeRepository(catalog(target_code=target_code, status=status, raw_text="official raw text")))
    response = client.post(ENDPOINT, json=request_body(target_code))
    assert response.status_code == 200
    assert response.json()["decision"] == "REVIEW_REQUIRED"
    assert response.json()["reasons"] == [reason]


def test_target_attempt_facts_are_exposed_without_changing_decision(api_client) -> None:
    client, _ = api_client
    response = client.post(
        ENDPOINT,
        json=request_body(attempts=[{"course_code": "1501112", "outcome": "PASSED"}]),
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "NOT_ELIGIBLE"
    assert response.json()["target_attempt_state"] == {
        "has_passed_target": True,
        "has_in_progress_target": False,
    }


def test_target_in_progress_fact_is_exposed(api_client) -> None:
    client, _ = api_client
    response = client.post(
        ENDPOINT,
        json=request_body(attempts=[{"course_code": "1501112", "outcome": "IN_PROGRESS"}]),
    )
    assert response.json()["target_attempt_state"]["has_in_progress_target"] is True


def test_leading_zero_target_code_survives_unchanged(api_client) -> None:
    client, repository = api_client
    replace_repository(FakeRepository(catalog(target_code="0200115", status=PrerequisiteLogicStatus.NOT_APPLICABLE)))
    response = client.post(ENDPOINT, json=request_body("0200115"))
    assert response.json()["target_course_code"] == "0200115"
    assert repository.calls == []


def test_numeric_course_code_is_rejected(api_client) -> None:
    client, _ = api_client
    response = client.post(ENDPOINT, json={**request_body(), "target_course_code": 200115})
    assert response.status_code == 422


def test_invalid_attempt_outcome_and_missing_target_are_validation_errors(api_client) -> None:
    client, _ = api_client
    invalid_outcome = client.post(
        ENDPOINT,
        json=request_body(attempts=[{"course_code": "1501110", "outcome": "UNKNOWN"}]),
    )
    missing_target = client.post(ENDPOINT, json={"study_plan_id": PLAN_ID, "attempts": []})
    assert invalid_outcome.status_code == 422
    assert missing_target.status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code", "error_code"),
    [
        (StudyPlanNotFound("missing"), 404, "STUDY_PLAN_NOT_FOUND"),
        (TargetCourseNotFound("missing"), 404, "TARGET_NOT_FOUND"),
        (TargetCourseNotInStudyPlan("not member"), 409, "TARGET_NOT_IN_STUDY_PLAN"),
        (CatalogIntegrityError("corrupt"), 500, "CATALOG_INTEGRITY_ERROR"),
        (CatalogTransportError("GET", "courses", status_code=503), 503, "CATALOG_TRANSPORT_ERROR"),
    ],
)
def test_repository_errors_have_intentional_safe_http_mapping(
    api_client,
    error,
    status_code,
    error_code,
) -> None:
    client, _ = api_client
    replace_repository(FakeRepository(error))
    response = client.post(ENDPOINT, json=request_body())
    assert response.status_code == status_code
    assert response.json() == {"kind": "error", "error_code": error_code, "detail": response.json()["detail"]}
    assert "test-server-key" not in response.text


def test_repository_receives_exact_code_and_api_uses_engine_result(api_client) -> None:
    client, repository = api_client
    response = client.post(
        ENDPOINT,
        json=request_body("1501112", [{"course_code": "1501110", "outcome": "PASSED"}]),
    )
    assert response.json()["decision"] == "ELIGIBLE"
    assert repository.calls == [(UUID(PLAN_ID), "1501112")]


def test_duplicate_and_unrelated_attempts_are_deterministic(api_client) -> None:
    client, _ = api_client
    first = client.post(
        ENDPOINT,
        json=request_body(
            attempts=[
                {"course_code": "9999999", "outcome": "PASSED"},
                {"course_code": "1501110", "outcome": "PASSED"},
                {"course_code": "1501110", "outcome": "PASSED"},
            ]
        ),
    )
    second = client.post(
        ENDPOINT,
        json=request_body(attempts=[{"course_code": "1501110", "outcome": "PASSED"}]),
    )
    assert first.json()["decision"] == second.json()["decision"] == "ELIGIBLE"


def test_api_does_not_parse_raw_text_or_infer_equivalencies(api_client) -> None:
    client, _ = api_client
    replace_repository(
        FakeRepository(
            catalog(
                target_code="1505320",
                status=PrerequisiteLogicStatus.SOURCE_CONFLICT,
                raw_text="0300103,1505311",
            )
        )
    )
    response = client.post(ENDPOINT, json=request_body("1505320"))
    source = inspect.getsource(__import__("app.api.routes.eligibility", fromlist=["*"]))
    assert response.json()["decision"] == "REVIEW_REQUIRED"
    assert ".split(" not in source
    assert "equivalen" not in source.lower()


def test_openapi_documents_post_request_and_domain_enums(api_client) -> None:
    client, _ = api_client
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][ENDPOINT]["post"]
    assert "requestBody" in operation
    assert "CanTakeRequestBody" in schema["components"]["schemas"]
    assert schema["components"]["schemas"]["Decision"]["enum"] == [
        "ELIGIBLE",
        "NOT_ELIGIBLE",
        "REVIEW_REQUIRED",
    ]
    assert schema["components"]["schemas"]["AttemptOutcome"]["enum"] == [
        "PASSED",
        "FAILED",
        "IN_PROGRESS",
        "WITHDRAWN",
    ]


def test_endpoint_requires_no_network_when_repository_is_mocked(api_client) -> None:
    client, _ = api_client
    assert client.post(ENDPOINT, json=request_body()).status_code == 200


def test_unconfigured_real_repository_fails_safely(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_secret_key", None)
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        response = client.post(ENDPOINT, json=request_body())
    assert response.status_code == 503
    assert response.json()["error_code"] == "CATALOG_CONFIGURATION_ERROR"


def test_lifespan_closes_its_shared_http_client() -> None:
    with TestClient(app):
        assert app.state.catalog_http_client.is_closed is False
    assert app.state.catalog_http_client.is_closed is True
