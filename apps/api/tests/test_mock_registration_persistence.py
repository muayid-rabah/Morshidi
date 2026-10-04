"""Focused unit tests for the P6.4 typed persistence adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from app.mock_registration.models import (
    IntentLifecycle,
    IntentProvenance,
    ValidationStatus,
)
from app.mock_registration.registries import ReasonCode
from app.mock_registration_persistence.errors import (
    MockRegistrationPersistenceError,
    PersistenceFailureCode,
)
from app.mock_registration_persistence.models import (
    PersistRevisionCommand,
    PersistenceResultKind,
)
from app.mock_registration_persistence.repository import (
    SupabaseMockRegistrationRepository,
)

OWNER = UUID("00000000-0000-0000-0000-000000000001")
UNIVERSITY = UUID("00000000-0000-0000-0000-000000000002")
MAJOR = UUID("00000000-0000-0000-0000-000000000003")
PLAN = UUID("00000000-0000-0000-0000-000000000004")
PERIOD = UUID("00000000-0000-0000-0000-000000000005")
COURSE = UUID("00000000-0000-0000-0000-000000000006")
INTENT = UUID("00000000-0000-0000-0000-000000000007")
REVISION = UUID("00000000-0000-0000-0000-000000000008")


def _command() -> PersistRevisionCommand:
    return PersistRevisionCommand(
        intent_id=INTENT,
        owner_user_id=OWNER,
        university_id=UNIVERSITY,
        major_id=MAJOR,
        study_plan_id=PLAN,
        study_plan_version="plan-12:v1",
        target_period_id=PERIOD,
        expected_current_revision=None,
        lifecycle_status=IntentLifecycle.SUBMITTED,
        validation_status=ValidationStatus.VALID,
        content_fingerprint="a" * 64,
        intent_provenance=IntentProvenance.DECLARED_STUDENT_INTENT,
        intent_source_version="intent:v1",
        validation_reason_codes=(),
        catalog_source_versions=("catalog:v1",),
        prerequisite_source_versions=("prerequisites:v1",),
        progress_state_version="progress:v1",
        progress_state_reference=None,
        phase5_policy_version="phase5:v1",
        phase6_policy_version="phase6:v1",
        p6_contract_version="1.0",
        target_period_source_version="period:v1",
        transparency_notice_version="notice:v1",
        actor_class="STUDENT_AUTHENTICATED",
        course_ids=(COURSE,),
        course_codes=("1501110",),
    )


def test_persist_revision_uses_atomic_rpc_and_maps_typed_result() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.path == "/rest/v1/rpc/persist_mock_registration_revision"
        assert request.headers["authorization"] == "Bearer server-secret"
        body = __import__("json").loads(request.content)
        assert body["p_owner_user_id"] == str(OWNER)
        assert body["p_expected_current_revision"] is None
        assert body["p_course_codes"] == ["1501110"]
        assert body["p_validation_reason_codes"] == []
        return httpx.Response(
            200,
            json=[{
                "result_kind": "INSERTED",
                "persisted_revision_id": str(REVISION),
                "persisted_revision": 1,
                "persisted_fingerprint": "a" * 64,
            }],
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            repository = SupabaseMockRegistrationRepository(
                "https://example.supabase.co", "server-secret", client
            )
            result = await repository.persist_revision(_command())
            assert result.kind is PersistenceResultKind.INSERTED
            assert result.revision_id == REVISION
            assert result.revision == 1
            assert result.content_fingerprint == "a" * 64

    asyncio.run(run())
    assert len(seen) == 1


@pytest.mark.parametrize(
    ("database_code", "expected"),
    [
        ("23503", PersistenceFailureCode.PERSISTENCE_CONFLICT),
        ("23505", PersistenceFailureCode.PERSISTENCE_CONFLICT),
        ("23514", PersistenceFailureCode.PERSISTENCE_CONFLICT),
        ("42501", PersistenceFailureCode.PERSISTENCE_UNAVAILABLE),
    ],
)
def test_database_failures_map_without_exposing_raw_details(database_code, expected) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "code": database_code,
                "message": "secret constraint and database detail",
                "details": "raw postgres detail",
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            repository = SupabaseMockRegistrationRepository(
                "https://example.supabase.co", "server-secret", client
            )
            with pytest.raises(MockRegistrationPersistenceError) as caught:
                await repository.persist_revision(_command())
            assert caught.value.code is expected
            assert "secret constraint" not in str(caught.value)
            assert "postgres" not in str(caught.value).lower()

    asyncio.run(run())


def test_review_reason_codes_remain_typed_at_repository_boundary() -> None:
    review = _command()
    review = PersistRevisionCommand(
        **{
            **review.__dict__,
            "validation_status": ValidationStatus.REVIEW_REQUIRED,
            "validation_reason_codes": (
                ReasonCode.MOCK_REG_ELIGIBILITY_REVIEW_REQUIRED,
            ),
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert body["p_validation_status"] == "REVIEW_REQUIRED"
        assert body["p_validation_reason_codes"] == [
            "MOCK_REG_ELIGIBILITY_REVIEW_REQUIRED"
        ]
        return httpx.Response(
            200,
            json=[{
                "result_kind": "IDEMPOTENT_REPLAY",
                "persisted_revision_id": str(REVISION),
                "persisted_revision": 1,
                "persisted_fingerprint": "a" * 64,
            }],
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            repository = SupabaseMockRegistrationRepository("https://local.test", "server", client)
            result = await repository.persist_revision(review)
            assert result.kind is PersistenceResultKind.IDEMPOTENT_REPLAY

    asyncio.run(run())


def test_persistence_package_has_no_api_or_academic_decision_logic() -> None:
    package = Path(__file__).parents[1] / "app" / "mock_registration_persistence"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    for forbidden in (
        "fastapi",
        "apirouter",
        "evaluate_can_take",
        "calculate_academic_progress",
        "aggregate_institutional_demand",
        "validate_registration_intent",
        "openai",
        "register_course",
        "reserve_seat",
    ):
        assert forbidden not in source.lower()
