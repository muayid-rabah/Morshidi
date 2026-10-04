"""Plan-wide Supabase catalog adapter tests."""

import asyncio
from typing import Any

import httpx
import pytest

from app.catalog.errors import CatalogIntegrityError, StudyPlanNotFound
from app.catalog.supabase_repository import SupabaseAcademicCatalogRepository
from app.progress.models import RequirementType

PLAN = "10000000-0000-0000-0000-000000000005"
GROUP = "10000000-0000-0000-0000-000000000011"


class ProgressFixture:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.rows: dict[str, list[dict[str, Any]]] = {
            "study_plans": [{"id": PLAN, "total_credit_hours": "132.00"}],
            "requirement_groups": [{
                "id": GROUP, "study_plan_id": PLAN, "group_code": "UNIVERSITY_REQUIRED",
                "name_ar": "جامعي", "name_en": None, "scope": "university",
                "requirement_type": "required", "required_credit_hours": "18.00",
                "display_order": 1,
            }],
            "study_plan_courses": [{
                "id": "20000000-0000-0000-0000-000000000001", "study_plan_id": PLAN,
                "requirement_group_id": GROUP, "credit_hours": "0.00", "display_order": 2,
                "courses": {"course_code": "0200115", "catalog_status": "known"},
            }],
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return httpx.Response(200, json=self.rows[request.url.path.rsplit("/", 1)[-1]])


def load(fixture: ProgressFixture):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fixture.handler)) as client:
            repository = SupabaseAcademicCatalogRepository("https://local.example", "server", client)
            return await repository.load_progress_catalog(PLAN)
    return asyncio.run(run())


def test_plan_wide_read_maps_explicit_progress_fields() -> None:
    fixture = ProgressFixture()
    catalog = load(fixture)
    assert catalog.study_plan.total_credit_hours == 132
    assert catalog.requirement_groups[0].requirement_type is RequirementType.REQUIRED
    assert catalog.plan_courses[0].course_code == "0200115"
    assert catalog.plan_courses[0].credit_hours == 0
    assert {request.method for request in fixture.calls} == {"GET"}
    assert all("*" not in request.url.params["select"] for request in fixture.calls)
    assert fixture.calls[1].url.params["order"] == "display_order.asc,group_code.asc"
    assert fixture.calls[2].url.params["order"] == "display_order.asc,id.asc"


def test_missing_plan_is_specific_not_found() -> None:
    fixture = ProgressFixture()
    fixture.rows["study_plans"] = []
    with pytest.raises(StudyPlanNotFound):
        load(fixture)
    assert len(fixture.calls) == 1


@pytest.mark.parametrize(
    ("resource", "field", "value"),
    [
        ("study_plans", "total_credit_hours", "not-a-number"),
        ("requirement_groups", "requirement_type", "invented"),
        ("study_plan_courses", "courses", None),
    ],
)
def test_invalid_persisted_progress_data_is_integrity_error(resource, field, value) -> None:
    fixture = ProgressFixture()
    fixture.rows[resource][0][field] = value
    with pytest.raises(CatalogIntegrityError):
        load(fixture)
