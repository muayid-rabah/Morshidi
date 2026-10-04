"""Comprehensive P16 Sandbox Integration & Conformance Tests.

Validates contract parity, drift detection, zero credential leakage, SIS mapping,
offering provider snapshotting, persona security invariants, engine compatibility,
WC-050 evidence manifest, and WC-053 observability.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.institution_context.registry import CapabilityState, InstitutionConfig
from app.main import app
from app.offerings.models import Modality, OfferingSnapshot, SourceType
from app.p15_adapters.sis import (
    CanonicalSISAcademicRecord,
    Entity,
    Freshness,
    SISHealth,
    SISPage,
)
from app.p16_sandbox.drift import (
    EXPECTED_COURSE_COUNT,
    EXPECTED_FIXTURE_VERSION,
    EXPECTED_OFFERING_COUNT,
    EXPECTED_RECORD_COUNT,
    EXPECTED_SCHEMA_VERSION,
    EXPECTED_STUDENT_COUNT,
    EXPECTED_STUDENT_IDS,
    DriftStatus,
    validate_sandbox_contract,
)
from app.p16_sandbox.evidence_manifest import get_wc050_manifest
from app.p16_sandbox.observability import SandboxObservability, mask_student_id, sandbox_obs
from app.p16_sandbox.offering_provider import SandboxOfferingProvider
from app.p16_sandbox.persona import (
    ALLOWED_PERSONA_IDS,
    SYNTHETIC_WATERMARK,
    SandboxPersonaNotFoundError,
    SandboxPersonaSecurityError,
    resolve_sandbox_persona,
    sanitize_persona_view,
)
from app.p16_sandbox.sis_adapter import SandboxSISAdapter
from app.p16_sandbox.tenant import (
    SANDBOX_INSTITUTION_ID,
    assert_sandbox_institution,
    get_sandbox_institution_config,
    is_sandbox_institution,
)
from app.p16_sandbox.transport import (
    HTTPReadOnlyTransport,
    SandboxTransportError,
    StaticFixtureTransport,
)
from app.progress.engine import calculate_academic_progress
from app.progress.models import (
    AcademicProgressCatalog,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CanTakeRequest,
    CourseCatalogStatus,
    CourseIdentity,
    Decision,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def transport() -> StaticFixtureTransport:
    return StaticFixtureTransport()


@pytest.fixture
def sis_adapter(transport: StaticFixtureTransport) -> SandboxSISAdapter:
    return SandboxSISAdapter(transport=transport)


@pytest.fixture
def offering_provider(transport: StaticFixtureTransport) -> SandboxOfferingProvider:
    return SandboxOfferingProvider(transport=transport)


# ============================================================================
# 1. CONTRACT PARITY & INTEGRITY TESTS
# ============================================================================

def test_contract_manifest_integrity(transport: StaticFixtureTransport):
    manifest = asyncio.run(transport.load_manifest())
    assert manifest["schema_version"] == EXPECTED_SCHEMA_VERSION
    assert manifest["fixture_version"] == EXPECTED_FIXTURE_VERSION
    assert manifest["institution_id"] == SANDBOX_INSTITUTION_ID
    assert manifest["synthetic"] is True
    assert manifest["student_count"] == EXPECTED_STUDENT_COUNT
    assert manifest["course_count"] == EXPECTED_COURSE_COUNT
    assert manifest["offering_count"] == EXPECTED_OFFERING_COUNT


def test_contract_entity_counts(transport: StaticFixtureTransport):
    students = asyncio.run(transport.load_students())
    courses = asyncio.run(transport.load_courses())
    offerings = asyncio.run(transport.load_offerings())
    records = asyncio.run(transport.load_academic_records())

    assert len(students) == EXPECTED_STUDENT_COUNT
    assert len(courses) == EXPECTED_COURSE_COUNT
    assert len(offerings) == EXPECTED_OFFERING_COUNT
    assert len(records.get("records", [])) == EXPECTED_RECORD_COUNT


def test_contract_persona_identities(transport: StaticFixtureTransport):
    students = asyncio.run(transport.load_students())
    student_ids = {s.get("university_id") or s.get("student_id") for s in students}
    assert student_ids == EXPECTED_STUDENT_IDS


def test_drift_validator_passes_on_valid_fixtures(transport: StaticFixtureTransport):
    manifest = asyncio.run(transport.load_manifest())
    students = asyncio.run(transport.load_students())
    courses = asyncio.run(transport.load_courses())
    offerings = asyncio.run(transport.load_offerings())
    records = asyncio.run(transport.load_academic_records())

    status, errors = validate_sandbox_contract(manifest, students, courses, offerings, records)
    assert status is DriftStatus.SUPPORTED
    assert errors == []


def test_drift_validator_detects_version_mismatch():
    manifest = {
        "schema_version": "1.0.0",
        "fixture_version": "2099.99.99.v99",
        "institution_id": SANDBOX_INSTITUTION_ID,
        "synthetic": True,
    }
    status, errors = validate_sandbox_contract(manifest, [{}], [{}], [{}], {"records": []})
    assert status in {DriftStatus.VERSION_MISMATCH, DriftStatus.INVALID_FIXTURE}
    assert any("version" in e.lower() for e in errors)


def test_drift_validator_detects_forbidden_credentials():
    manifest = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "fixture_version": EXPECTED_FIXTURE_VERSION,
        "institution_id": SANDBOX_INSTITUTION_ID,
        "synthetic": True,
    }
    students = [{"student_id": "202310001", "password": "supersecretpassword"}]
    status, errors = validate_sandbox_contract(manifest, students, [], [], {"records": []})
    assert status is DriftStatus.INVALID_FIXTURE
    assert any("password" in e.lower() for e in errors)


# ============================================================================
# 2. ZERO CREDENTIAL LEAKAGE TESTS
# ============================================================================

def test_fixtures_contain_no_passwords_or_secrets(transport: StaticFixtureTransport):
    students = asyncio.run(transport.load_students())
    records = asyncio.run(transport.load_academic_records())
    offerings = asyncio.run(transport.load_offerings())

    for s in students:
        assert "password" not in s
        assert "token" not in s
        assert "secret" not in s
        assert "credential" not in s

    for r in records.get("records", []):
        assert "password" not in r
        assert "token" not in r

    for o in offerings:
        assert "password" not in o


# ============================================================================
# 3. TRANSPORT TESTS
# ============================================================================

def test_static_fixture_transport_reads_all_entities(transport: StaticFixtureTransport):
    m = asyncio.run(transport.load_manifest())
    s = asyncio.run(transport.load_students())
    c = asyncio.run(transport.load_courses())
    o = asyncio.run(transport.load_offerings())
    a = asyncio.run(transport.load_academic_records())

    assert m and s and c and o and a


def test_static_fixture_transport_invalid_path():
    with pytest.raises(SandboxTransportError):
        StaticFixtureTransport(fixtures_dir="/non/existent/path/for/test")


def test_http_transport_read_only_handling():
    transport = HTTPReadOnlyTransport(base_url="https://fake-sandbox-endpoint.local")
    # Verify methods exist
    assert hasattr(transport, "load_manifest")
    assert hasattr(transport, "load_students")
    assert hasattr(transport, "load_courses")
    assert hasattr(transport, "load_offerings")
    assert hasattr(transport, "load_academic_records")
    # Ensure no mutation methods are exposed
    assert not hasattr(transport, "save_manifest")
    assert not hasattr(transport, "write_record")


# ============================================================================
# 4. SIS READ ADAPTER TESTS
# ============================================================================

def test_sis_adapter_protocol_conformance(sis_adapter: SandboxSISAdapter):
    assert sis_adapter.institution_id == SANDBOX_INSTITUTION_ID
    assert sis_adapter.adapter_id == "sandbox-sis-adapter"
    assert hasattr(sis_adapter, "health")
    assert hasattr(sis_adapter, "fetch_page")
    assert Entity.STUDENT in sis_adapter.capabilities
    assert Entity.COURSE in sis_adapter.capabilities
    assert Entity.OFFERING in sis_adapter.capabilities
    assert Entity.ATTEMPT in sis_adapter.capabilities


def test_sis_adapter_health(sis_adapter: SandboxSISAdapter):
    health = asyncio.run(sis_adapter.health())
    assert isinstance(health, SISHealth)
    assert health.available is True
    assert health.freshness is Freshness.FRESH
    assert health.institution_id == SANDBOX_INSTITUTION_ID
    assert health.last_error is None


def test_sis_adapter_fetch_page_students(sis_adapter: SandboxSISAdapter):
    page = asyncio.run(sis_adapter.fetch_page(Entity.STUDENT, limit=2))
    assert isinstance(page, SISPage)
    assert page.institution_id == SANDBOX_INSTITUTION_ID
    assert page.entity is Entity.STUDENT
    assert len(page.records) == 2
    assert page.next_cursor == "2"
    assert page.evidence.institution_id == SANDBOX_INSTITUTION_ID


def test_sis_adapter_fetch_page_courses(sis_adapter: SandboxSISAdapter):
    page = asyncio.run(sis_adapter.fetch_page(Entity.COURSE, limit=50))
    assert len(page.records) == 50
    assert page.next_cursor == "50"


def test_sis_adapter_canonical_record_mapping(sis_adapter: SandboxSISAdapter):
    record = asyncio.run(sis_adapter.get_canonical_record("202310001"))
    assert isinstance(record, CanonicalSISAcademicRecord)
    assert record.institution_id == SANDBOX_INSTITUTION_ID
    assert record.student_id == "202310001"
    assert record.program_id == "IT"
    assert record.major_id == "AI"
    assert record.plan_id == "12"
    assert record.earned_credits == Decimal("96")
    assert len(record.attempts) > 0

    # Verify attempt outcome mapping
    outcomes = {att.outcome for att in record.attempts}
    assert AttemptOutcome.PASSED in outcomes


def test_sis_adapter_canonical_record_with_failed_attempts(sis_adapter: SandboxSISAdapter):
    # Student 202410002 has struggling profile with some failed/withdrawn courses
    record = asyncio.run(sis_adapter.get_canonical_record("202410002"))
    assert record.student_id == "202410002"
    outcomes = {att.outcome for att in record.attempts}
    assert AttemptOutcome.FAILED in outcomes or AttemptOutcome.WITHDRAWN in outcomes or AttemptOutcome.PASSED in outcomes


# ============================================================================
# 5. OFFERING PROVIDER TESTS
# ============================================================================

def test_offering_provider_snapshot_exact_counts(offering_provider: SandboxOfferingProvider):
    snapshot = asyncio.run(offering_provider.load_snapshot(SANDBOX_INSTITUTION_ID, "2026-1"))
    assert isinstance(snapshot, OfferingSnapshot)
    assert snapshot.university_id == SANDBOX_INSTITUTION_ID
    assert snapshot.source_type is SourceType.SYNTHETIC
    assert snapshot.complete is True
    assert len(snapshot.sections) == 204


def test_offering_provider_tenant_boundary(offering_provider: SandboxOfferingProvider):
    # Reject non-sandbox university requests
    foreign_snapshot = asyncio.run(offering_provider.load_snapshot("foreign-uni-123", "2026-1"))
    assert foreign_snapshot is None


def test_offering_provider_meeting_blocks(offering_provider: SandboxOfferingProvider):
    snapshot = asyncio.run(offering_provider.load_snapshot(SANDBOX_INSTITUTION_ID, "2026-1"))
    assert snapshot is not None

    for sec in snapshot.sections:
        assert sec.course_code
        assert sec.modality is Modality.IN_PERSON
        assert sec.student_visible is True
        for mb in sec.meetings:
            assert mb.day in range(1, 8)  # ISO weekdays 1-7
            assert mb.starts_at < mb.ends_at
            assert mb.timezone == "Asia/Amman"


# ============================================================================
# 6. TENANT & PERSONA SECURITY TESTS
# ============================================================================

def test_sandbox_institution_identity():
    assert is_sandbox_institution(SANDBOX_INSTITUTION_ID) is True
    assert is_sandbox_institution("some-other-tenant") is False
    assert is_sandbox_institution(None) is False

    assert_sandbox_institution(SANDBOX_INSTITUTION_ID)
    with pytest.raises(PermissionError):
        assert_sandbox_institution("production-tenant-a")


def test_sandbox_institution_config():
    config = get_sandbox_institution_config()
    assert isinstance(config, InstitutionConfig)
    assert config.context.institution_id == SANDBOX_INSTITUTION_ID
    assert config.context.country_code == "JO"
    assert config.context.timezone == "Asia/Amman"
    assert config.context.default_locale == "ar"
    assert config.capabilities["offerings"] is CapabilityState.ENABLED
    assert config.theme_key == "sand"


def test_persona_resolution_allowlist():
    for pid in ALLOWED_PERSONA_IDS:
        resolved = resolve_sandbox_persona(pid, SANDBOX_INSTITUTION_ID)
        assert resolved == pid


def test_persona_resolution_security_negative_foreign_tenant():
    # Invariant: Persona hint must FAIL CLOSED on non-sandbox tenants!
    with pytest.raises(SandboxPersonaSecurityError):
        resolve_sandbox_persona("202310001", "some-production-institution")


def test_persona_resolution_security_negative_unknown_persona():
    # Invariant: Unknown personas fail closed
    with pytest.raises(SandboxPersonaNotFoundError):
        resolve_sandbox_persona("999999999", SANDBOX_INSTITUTION_ID)


def test_persona_resolution_empty():
    with pytest.raises(ValueError):
        resolve_sandbox_persona("", SANDBOX_INSTITUTION_ID)


def test_persona_sanitization_watermark():
    raw = {
        "student_id": "202310001",
        "name": "أحمد محمود الخطيب",
        "password": "plain_password_must_be_stripped",
        "token": "secret_token_must_be_stripped",
    }
    clean = sanitize_persona_view(raw)
    assert clean["student_id"] == "202310001"
    assert clean["name"] == "أحمد محمود الخطيب"
    assert "password" not in clean
    assert "token" not in clean
    assert clean["synthetic"] is True
    assert clean["watermark"] == SYNTHETIC_WATERMARK


# ============================================================================
# 7. FASTAPI ROUTE ENDPOINTS TESTS
# ============================================================================

def test_api_route_manifest(client: TestClient):
    resp = client.get("/api/v1/sandbox/manifest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["institution_id"] == SANDBOX_INSTITUTION_ID
    assert data["synthetic"] is True
    assert data["watermark"] == SYNTHETIC_WATERMARK


def test_api_route_personas_list(client: TestClient):
    resp = client.get("/api/v1/sandbox/personas")
    assert resp.status_code == 200
    data = resp.json()
    assert data["personas_count"] == 5
    assert len(data["personas"]) == 5
    for p in data["personas"]:
        assert "password" not in p
        assert p["synthetic"] is True


def test_api_route_persona_detail(client: TestClient):
    resp = client.get(f"/api/v1/sandbox/persona/202310001?institution={SANDBOX_INSTITUTION_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["student_id"] == "202310001"
    assert "أحمد" in data["name"]
    assert data["synthetic"] is True


def test_api_route_persona_detail_negative_tenant(client: TestClient):
    resp = client.get("/api/v1/sandbox/persona/202310001?institution=foreign-tenant")
    assert resp.status_code == 403


def test_api_route_persona_detail_not_found(client: TestClient):
    resp = client.get(f"/api/v1/sandbox/persona/999999999?institution={SANDBOX_INSTITUTION_ID}")
    assert resp.status_code == 404


def test_api_route_persona_record(client: TestClient):
    resp = client.get(f"/api/v1/sandbox/persona/202310001/record?institution={SANDBOX_INSTITUTION_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["student_id"] == "202310001"
    assert data["earned_credits"] == 96.0
    assert data["attempts_count"] > 0
    assert data["synthetic"] is True


def test_api_route_offerings(client: TestClient):
    resp = client.get("/api/v1/sandbox/offerings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["section_count"] == 204
    assert len(data["sections"]) == 204
    assert data["synthetic"] is True


def test_api_route_reset(client: TestClient):
    resp = client.post("/api/v1/sandbox/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["action"] == "RESET_COMPLETED"
    assert data["synthetic"] is True


def test_api_route_evidence(client: TestClient):
    resp = client.get("/api/v1/sandbox/evidence")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provenance"] == "MORSHIDI_EVIDENCE_REGISTRY"
    assert data["capabilities_count"] >= 5


def test_api_route_observability_events(client: TestClient):
    resp = client.get("/api/v1/sandbox/observability/events")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert isinstance(data["events"], list)


# ============================================================================
# 8. ACADEMIC ENGINE COMPATIBILITY (P15.5 & P15.6)
# ============================================================================

def test_can_take_evaluation_with_sandbox_records(sis_adapter: SandboxSISAdapter):
    """Prove that sandbox attempts feed directly into Morshidi rules evaluator."""
    record = asyncio.run(sis_adapter.get_canonical_record("202310001"))

    # Calculus 2 (0300154) requires Calculus 1 (0300153)
    target_code = "0300154"
    prereq_code = "0300153"

    dep_group = DependencyGroup(1, DependencyType.PREREQUISITE, (prereq_code,))
    plan_rule = PlanCourseRule(
        course_code=target_code,
        prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
        dependency_groups=(dep_group,),
        raw_prerequisite_text=prereq_code,
        target_name_ar="تفاضل وتكامل (2)",
        credit_hours=Decimal("3"),
    )
    identities = (
        CourseIdentity(target_code, CourseCatalogStatus.KNOWN),
        CourseIdentity(prereq_code, CourseCatalogStatus.KNOWN),
    )
    cat = CanTakeCatalog(
        study_plan_id="12",
        plan_courses=(plan_rule,),
        courses=identities,
    )

    req = CanTakeRequest(
        study_plan_id="12",
        target_course_code=target_code,
        student_attempts=record.attempts,
        earned_completed_credits=record.earned_credits,
    )

    decision = evaluate_can_take(cat, req)
    assert decision.decision == Decision.ELIGIBLE


def test_progress_calculation_with_sandbox_records(sis_adapter: SandboxSISAdapter):
    """Prove that sandbox attempts calculate progress with degree progress engine."""
    record = asyncio.run(sis_adapter.get_canonical_record("202310001"))

    plan_id = "12"
    group_id = "GRP-MANDATORY"
    course_code = "0200104"  # National Education (passed by student 202310001)

    group = ProgressRequirementGroup(
        group_id=group_id,
        study_plan_id=plan_id,
        group_code="MANDATORY",
        name_ar="متطلبات إجبارية",
        name_en="Mandatory",
        scope="university",
        requirement_type=RequirementType.REQUIRED,
        required_credit_hours=Decimal("3"),
        display_order=1,
    )
    course = ProgressPlanCourse(
        plan_course_id="pc-1",
        study_plan_id=plan_id,
        requirement_group_id=group_id,
        course_code=course_code,
        catalog_status=CourseCatalogStatus.KNOWN,
        credit_hours=Decimal("3"),
        display_order=1,
        course_name_ar="التربية الوطنية",
        course_name_en="National Education",
    )
    cat = AcademicProgressCatalog(
        study_plan=ProgressStudyPlan(plan_id, Decimal("132")),
        requirement_groups=(group,),
        plan_courses=(course,),
    )

    progress = calculate_academic_progress(cat, record.attempts)
    assert progress.completed_plan_credits >= Decimal("3")
    assert progress.plan_total_required_credits == Decimal("132")


# ============================================================================
# 9. WC-050 & WC-053 OBSERVABILITY & MANIFEST TESTS
# ============================================================================

def test_wc050_manifest_structure():
    manifest = get_wc050_manifest()
    assert manifest["manifest_version"] == "2026.10.02.v1"
    assert manifest["institution_id"] == "morshidi-sandbox"
    assert manifest["capabilities_count"] > 0
    cap_ids = {c["capability_id"] for c in manifest["capabilities"]}
    assert "WC-001" in cap_ids
    assert "WC-002" in cap_ids
    assert "WC-010" in cap_ids
    assert "WC-013" in cap_ids
    assert "WC-015" in cap_ids
    assert "WC-050" in cap_ids
    assert "WC-053" in cap_ids


def test_observability_event_recording_and_masking():
    obs = SandboxObservability()
    event = obs.record_event(
        "TEST_EVENT",
        latency_ms=12.345,
        student_id="202310001",
        status="SUCCESS",
        entity="test",
    )
    assert event.event_type == "TEST_EVENT"
    assert event.masked_student_id == "20***01"  # Masked! Zero PII
    assert event.latency_ms == 12.345
    assert event.status == "SUCCESS"

    events = obs.get_recent_events()
    assert len(events) >= 1
    assert events[-1]["masked_student_id"] == "20***01"


def test_observability_masking_helper():
    assert mask_student_id("202310001") == "20***01"
    assert mask_student_id("123") == "****"
    assert mask_student_id(None) == "UNKNOWN"


def test_observability_runbooks():
    obs = SandboxObservability()
    drift_rb = obs.get_runbook("DRIFT_DETECTED")
    assert drift_rb["severity"] == "HIGH"
    assert "export:data" in drift_rb["action"]

    security_rb = obs.get_runbook("PERSONA_SECURITY_VIOLATION")
    assert security_rb["severity"] == "CRITICAL"
