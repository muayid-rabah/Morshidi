"""Opt-in local-only end-to-end checks for the FastAPI eligibility endpoint."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

PLAN_ID = os.getenv("MORSHIDI_LOCAL_STUDY_PLAN_ID")

pytestmark = pytest.mark.skipif(
    not all((
        PLAN_ID,
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SECRET_KEY"),
    )),
    reason="set local-only Supabase variables to run API end-to-end tests",
)


def request_body(target_course_code: str, attempts: list[dict[str, str]] | None = None) -> dict:
    return {
        "study_plan_id": PLAN_ID,
        "target_course_code": target_course_code,
        "attempts": attempts or [],
    }


def test_local_can_take_endpoint_against_accepted_catalog() -> None:
    with TestClient(app) as client:
        no_prerequisite = client.post(
            "/api/v1/eligibility/can-take",
            json=request_body("0200115"),
        )
        passed = client.post(
            "/api/v1/eligibility/can-take",
            json=request_body("1501112", [{"course_code": "1501110", "outcome": "PASSED"}]),
        )
        failed = client.post(
            "/api/v1/eligibility/can-take",
            json=request_body("1501112", [{"course_code": "1501110", "outcome": "FAILED"}]),
        )
        unresolved = client.post(
            "/api/v1/eligibility/can-take",
            json=request_body("1505311"),
        )
        conflict = client.post(
            "/api/v1/eligibility/can-take",
            json=request_body("1505320"),
        )
        referenced_only = client.post(
            "/api/v1/eligibility/can-take",
            json=request_body("0300103"),
        )
        unknown = client.post(
            "/api/v1/eligibility/can-take",
            json=request_body("9999999"),
        )

    assert (no_prerequisite.status_code, no_prerequisite.json()["decision"]) == (200, "ELIGIBLE")
    assert (passed.status_code, passed.json()["decision"]) == (200, "ELIGIBLE")
    assert (failed.status_code, failed.json()["decision"]) == (200, "NOT_ELIGIBLE")
    assert (unresolved.status_code, unresolved.json()["decision"]) == (200, "REVIEW_REQUIRED")
    assert (conflict.status_code, conflict.json()["decision"]) == (200, "REVIEW_REQUIRED")
    assert (referenced_only.status_code, referenced_only.json()["error_code"]) == (
        409,
        "TARGET_NOT_IN_STUDY_PLAN",
    )
    assert (unknown.status_code, unknown.json()["error_code"]) == (404, "TARGET_NOT_FOUND")
