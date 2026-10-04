"""Tiny two-institution provider matrix; no seed, users, or database writes."""

import asyncio
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.api.routes.institution_context import router as institution_context_router
from app.core.auth import CurrentUser, get_current_user

from app.institution_context import (CapabilityState, InstitutionProviderRegistry,
                                     ProviderBinding)
from app.institutional_policy.enums import (GroundingStatus, PolicyAuthorityLevel,
                                            PolicyCategory)
from app.institutional_policy.models import (CitationAnchor, PolicyDocument,
                                             PolicyDocumentVersion, PolicyPassage,
                                             PolicyRetrievalQuery)
from app.institutional_policy.provider import InMemoryInstitutionalPolicyProvider
from app.offerings.logic import capacity_state
from app.offerings.models import (CapacityState, Modality, OfferingSection,
                                  OfferingSnapshot, SourceType)
from app.offerings.simulation import fingerprint as offering_fingerprint
from app.p11_intelligence.engine import cohort
from app.p11_intelligence.models import (CohortDefinition, HistoricalRecord,
                                         HistoricalSnapshot)
from app.plan_transition.ingestion import IngestionState, LocalPublication
from app.plan_transition.models import (CourseIdentity, PlanCourse, PlanIdentity,
                                        PlanVersion, RequirementGroup)
from app.plan_transition.provider import ApprovedLocalModelingProvider

from tests.test_institution_context_p13 import A, B, config

DATE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


class TenantPolicy:
    def __init__(self, institution_id: str, label: str):
        self.institution_id = institution_id
        self._provider = InMemoryInstitutionalPolicyProvider()
        self._provider.add_document(PolicyDocument(
            "shared-document", institution_id, f"Policy {label}", "POL-1",
            PolicyAuthorityLevel.UNIVERSITY_COUNCIL, PolicyCategory.ACADEMIC_BYLAWS,
            DATE_TIME, "en"))
        content = f"registration window {label}"
        self._provider.add_version(PolicyDocumentVersion(
            "shared-version", "shared-document", "v1", DATE_TIME,
            sha256(content.encode()).hexdigest()))
        self._provider.add_passage(PolicyPassage(
            "shared-passage", "shared-document", "v1", institution_id,
            CitationAnchor("shared-anchor", "shared-document", "v1", "article 1"),
            content, sha256(content.encode()).hexdigest()))

    async def retrieve_passages(self, query: PolicyRetrievalQuery):
        if query.university_id != self.institution_id:
            return None
        return await self._provider.retrieve_passages(query)


class TenantOfferings:
    def __init__(self, institution_id: str, seats: int):
        self.institution_id = institution_id
        self._snapshot = OfferingSnapshot(
            institution_id, "2026-FALL", "same-snapshot", "v1", SourceType.SYNTHETIC,
            DATE_TIME, datetime(2027, 1, 1, tzinfo=timezone.utc), True,
            (OfferingSection("same-section", "CS101", "OPEN" if seats else "FULL",
                             Modality.IN_PERSON, None, None, (), 2, 2 - seats,
                             seats, 0, "P13_SYNTHETIC", True),), "P13_SYNTHETIC")

    async def load_snapshot(self, university_id: str, period_key: str):
        return self._snapshot if (university_id, period_key) == \
            (self.institution_id, "2026-FALL") else None


class TenantHistorical:
    def __init__(self, institution_id: str, ratio: float):
        self.institution_id = institution_id
        records = tuple(HistoricalRecord(
            f"anonymous-{index}", "2026-FALL", "2026-FALL", 1,
            ("CS101",), (), ratio, 3, False, "PASSED") for index in range(2))
        self._snapshot = HistoricalSnapshot(institution_id, "PLAN-2026", "v1",
                                            DATE_TIME, "P13_SYNTHETIC", True, records)

    async def load_snapshot(self, university_id: str, study_plan_id: str):
        return self._snapshot if (university_id, study_plan_id) == \
            (self.institution_id, "PLAN-2026") else None


class TenantPlans:
    def __init__(self, institution_id: str, label: str):
        self.institution_id = institution_id
        plans = []
        for version in ("v1", "v2"):
            identity = PlanIdentity(institution_id, "program", "major", "PLAN-2026",
                                    version, date(2026, 1, 1), None, "v1")
            course = PlanCourse(CourseIdentity(institution_id, "CS101", "CS101"),
                                "core", Decimal(3))
            plans.append(PlanVersion(identity, (RequirementGroup("core", Decimal(3)),),
                                     (course,), "source-" + label,
                                     "content-" + label + version, "P13_SYNTHETIC"))
        publications = tuple(LocalPublication(IngestionState.PUBLISHED, plan,
                                              "p13-local", date(2026, 1, 1), "P13_SYNTHETIC")
                             for plan in plans)
        self._provider = ApprovedLocalModelingProvider(
            publications, {(institution_id, "PLAN-2026"): plans[0].identity.key},
            {plans[0].identity.key: (plans[1].identity.key,)})

    async def source_for(self, institution_id: str, study_plan_id: str):
        return await self._provider.source_for(institution_id, study_plan_id)

    async def allowed_targets(self, source: PlanIdentity):
        return await self._provider.allowed_targets(source)


def _registry(*, failing_a: bool = False) -> InstitutionProviderRegistry:
    configs = []
    adapters = {}
    for institution_id, key, seats, ratio in ((A, "a", 1, .5), (B, "b", 0, .8)):
        bindings = {kind: ProviderBinding(key + "-" + kind, institution_id)
                    for kind in ("catalog", "policy", "offerings", "historical", "transition")}
        base = config(institution_id, key=key)
        configs.append(replace(base, capabilities={
            "academic_roadmap": CapabilityState.ENABLED,
            "policy_rag": CapabilityState.ENABLED,
            "offerings": CapabilityState.ENABLED,
            "career_intelligence": CapabilityState.UNAVAILABLE,
            "plan_transition": CapabilityState.MODELED_ONLY,
        }, provider_bindings=bindings))
        plans = TenantPlans(institution_id, key)
        offering = TenantOfferings(institution_id, seats)
        if failing_a and institution_id == A:
            async def unavailable(_university_id: str, _period_key: str):
                raise RuntimeError("P13 local A-provider outage")
            offering.load_snapshot = unavailable
        for kind, adapter in (("catalog", plans), ("transition", plans),
                              ("policy", TenantPolicy(institution_id, key)),
                              ("offerings", offering),
                              ("historical", TenantHistorical(institution_id, ratio))):
            adapters[(institution_id, bindings[kind].provider_key)] = adapter
    return InstitutionProviderRegistry(tuple(configs), adapters)


def test_provider_matrix_a_b_a_and_no_cross_tenant_fallback():
    registry = _registry()

    async def collect(tenant: str):
        bundle = registry.resolve(tenant)
        plans = bundle.require("catalog")
        source = await plans.source_for(tenant, "PLAN-2026")
        target = (await bundle.require("transition").allowed_targets(source.identity))[0]
        policy = await bundle.require("policy").retrieve_passages(
            PolicyRetrievalQuery("registration", tenant))
        offering = await bundle.require("offerings").load_snapshot(tenant, "2026-FALL")
        historical = await bundle.require("historical").load_snapshot(tenant, "PLAN-2026")
        cohort_view = cohort(historical, CohortDefinition(tenant, "PLAN-2026",
                                                         "2026-FALL", "2026-FALL"), 2)
        assert policy.grounding_status is GroundingStatus.GROUNDED
        return (source.identity.key, target.identity.key, source.content_fingerprint,
                policy.passages[0].content, policy.citations[0].title,
                offering_fingerprint(offering), capacity_state(offering.sections[0]),
                cohort_view["metrics"]["mean_completion_ratio"], cohort_view["fingerprint"])

    a, b, again = (asyncio.run(collect(tenant)) for tenant in (A, B, A))
    assert a == again
    assert a[0][3:] == b[0][3:] == ("PLAN-2026", "v1")
    assert a[1][3:] == b[1][3:] == ("PLAN-2026", "v2")
    assert a[0][0] == A and b[0][0] == B
    assert a[2] != b[2] and a[3] != b[3] and a[4] != b[4]
    assert a[5] != b[5] and a[6] is CapacityState.KNOWN_OPEN
    assert b[6] is CapacityState.KNOWN_FULL
    assert a[7] != b[7] and a[8] != b[8]
    a_plan = registry.resolve(A).require("catalog")
    assert asyncio.run(a_plan.source_for(B, "PLAN-2026")) is None
    a_offer = registry.resolve(A).require("offerings")
    assert asyncio.run(a_offer.load_snapshot(B, "2026-FALL")) is None
    a_policy = registry.resolve(A).require("policy")
    assert asyncio.run(a_policy.retrieve_passages(PolicyRetrievalQuery("registration", B))) is None
    a_history = registry.resolve(A).require("historical")
    assert asyncio.run(a_history.load_snapshot(B, "PLAN-2026")) is None


def test_local_fastapi_registry_composition_auth_scope_capability_and_failure_isolation():
    local_app = FastAPI()
    local_app.include_router(institution_context_router)
    local_app.state.institution_registry = _registry(failing_a=True)
    actor = {"user": "owner-a"}

    class OwnerService:
        async def resolve_student_university_id(self, owner: str) -> str:
            return {"owner-a": A, "owner-b": B}[owner]

    local_app.state.student_service = OwnerService()
    local_app.dependency_overrides[get_current_user] = lambda: CurrentUser(actor["user"])

    @local_app.get("/local/offering")
    async def local_offering(request: Request, user: CurrentUser = Depends(get_current_user)):
        institution_id = await request.app.state.student_service.resolve_student_university_id(user.user_id)
        bundle = request.app.state.institution_registry.resolve(institution_id)
        try:
            snapshot = await bundle.require("offerings").load_snapshot(institution_id, "2026-FALL")
        except RuntimeError:
            raise HTTPException(503, "PROVIDER_UNAVAILABLE") from None
        if snapshot is None or snapshot.university_id != institution_id:
            raise HTTPException(503, "PROVIDER_UNAVAILABLE")
        return {"institution_id": institution_id, "fingerprint": offering_fingerprint(snapshot)}

    with TestClient(local_app) as client:
        a_context = client.get("/api/v1/me/institution-context", params={"institution_id": B})
        assert a_context.status_code == 200 and a_context.json()["institution_id"] == A
        assert a_context.json()["capabilities"]["academic_roadmap"] == "ENABLED"
        assert set(a_context.json()) == {"institution_id", "display_name", "default_locale",
                                         "supported_locales", "theme_key", "capabilities",
                                         "config_version", "config_fingerprint"}
        assert not any(marker in a_context.text.lower() for marker in
                       ("provider_key", "secret", "service_role", "oauth", "sis_password",
                        "database_url", "internal_endpoint"))
        assert client.request("GET", "/api/v1/me/institution-context",
                              json={"institution_id": B}).json()["institution_id"] == A
        assert client.get("/local/offering", params={"institution_id": B}).status_code == 503
        actor["user"] = "owner-b"
        b_context = client.get("/api/v1/me/institution-context")
        assert b_context.status_code == 200 and b_context.json()["institution_id"] == B
        b_offering = client.get("/local/offering")
        assert b_offering.status_code == 200 and b_offering.json()["institution_id"] == B
        actor["user"] = "owner-a"
        assert client.get("/local/offering").status_code == 503
        actor["user"] = "owner-b"
        assert client.get("/local/offering").json() == b_offering.json()
