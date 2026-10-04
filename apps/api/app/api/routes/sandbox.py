"""Morshidi Sandbox University API endpoints.

Exposes read-only synthetic contracts, persona views, offerings, evidence manifests,
and isolated demo session reset.
CRITICAL INVARIANT: Persona hint is purely a demo navigation hint, never authentication.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.p16_sandbox.drift import validate_sandbox_contract
from app.p16_sandbox.evidence_manifest import get_wc050_manifest
from app.p16_sandbox.observability import sandbox_obs
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
from app.p16_sandbox.tenant import SANDBOX_INSTITUTION_ID, assert_sandbox_institution

router = APIRouter(prefix="/api/v1/sandbox", tags=["sandbox"])


def _get_sis_adapter(request: Request) -> SandboxSISAdapter:
    adapter = getattr(request.app.state, "sandbox_sis_adapter", None)
    if adapter is None:
        adapter = SandboxSISAdapter()
    return adapter


def _get_offering_provider(request: Request) -> SandboxOfferingProvider:
    provider = getattr(request.app.state, "sandbox_offering_provider", None)
    if provider is None:
        provider = SandboxOfferingProvider()
    return provider


@router.get("/manifest")
async def get_manifest(request: Request, response: Response) -> dict[str, Any]:
    """Retrieve the versioned Sandbox manifest."""
    start = time.perf_counter()
    adapter = _get_sis_adapter(request)
    manifest = await adapter.transport.load_manifest()

    response.headers["Cache-Control"] = "no-cache"
    latency = (time.perf_counter() - start) * 1000
    sandbox_obs.record_event("SANDBOX_READ", latency_ms=latency, entity="manifest")

    return {
        **manifest,
        "synthetic": True,
        "watermark": SYNTHETIC_WATERMARK,
    }


@router.get("/personas")
async def get_personas(request: Request, response: Response) -> dict[str, Any]:
    """List the 5 authorized synthetic student personas."""
    start = time.perf_counter()
    adapter = _get_sis_adapter(request)
    raw_students = await adapter.transport.load_students()

    personas = [
        sanitize_persona_view(s)
        for s in raw_students
        if (s.get("student_id") in ALLOWED_PERSONA_IDS or s.get("university_id") in ALLOWED_PERSONA_IDS)
    ]

    response.headers["Cache-Control"] = "no-cache"
    latency = (time.perf_counter() - start) * 1000
    sandbox_obs.record_event("SANDBOX_READ", latency_ms=latency, entity="personas")

    return {
        "institution_id": SANDBOX_INSTITUTION_ID,
        "personas_count": len(personas),
        "personas": personas,
        "synthetic": True,
        "watermark": SYNTHETIC_WATERMARK,
    }


@router.get("/persona/{student_id}")
async def get_persona_detail(
    student_id: str,
    request: Request,
    response: Response,
    institution: str = Query(default=SANDBOX_INSTITUTION_ID),
) -> dict[str, Any]:
    """Fetch sanitized profile for a specific synthetic persona."""
    start = time.perf_counter()
    try:
        resolved_id = resolve_sandbox_persona(student_id, institution)
    except SandboxPersonaSecurityError as exc:
        sandbox_obs.record_event(
            "PERSONA_SECURITY_VIOLATION",
            latency_ms=0,
            status="ERROR",
            student_id=student_id,
            error_code="FORBIDDEN_INSTITUTION",
            institution_id=institution,
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (SandboxPersonaNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="SANDBOX_PERSONA_NOT_FOUND") from exc

    adapter = _get_sis_adapter(request)
    profile = await adapter.get_student_profile(resolved_id)
    if not profile:
        raise HTTPException(status_code=404, detail="SANDBOX_PERSONA_NOT_FOUND")

    response.headers["Cache-Control"] = "no-cache"
    latency = (time.perf_counter() - start) * 1000
    sandbox_obs.record_event("PERSONA_RESOLVE", latency_ms=latency, student_id=resolved_id)

    return sanitize_persona_view(profile)


@router.get("/persona/{student_id}/record")
async def get_persona_academic_record(
    student_id: str,
    request: Request,
    response: Response,
    institution: str = Query(default=SANDBOX_INSTITUTION_ID),
) -> dict[str, Any]:
    """Fetch canonical academic record for a synthetic persona."""
    start = time.perf_counter()
    try:
        resolved_id = resolve_sandbox_persona(student_id, institution)
    except SandboxPersonaSecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (SandboxPersonaNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="SANDBOX_PERSONA_NOT_FOUND") from exc

    adapter = _get_sis_adapter(request)
    try:
        record = await adapter.get_canonical_record(resolved_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="ACADEMIC_RECORD_NOT_FOUND") from exc

    response.headers["Cache-Control"] = "no-cache"
    latency = (time.perf_counter() - start) * 1000
    sandbox_obs.record_event("SANDBOX_READ", latency_ms=latency, student_id=resolved_id, entity="record")

    return {
        "institution_id": record.institution_id,
        "student_id": record.student_id,
        "program_id": record.program_id,
        "major_id": record.major_id,
        "plan_id": record.plan_id,
        "plan_version_id": record.plan_version_id,
        "earned_credits": float(record.earned_credits),
        "attempts_count": len(record.attempts),
        "attempts": [
            {"course_code": att.course_code, "outcome": att.outcome.value}
            for att in record.attempts
        ],
        "enrolled_course_codes": list(record.enrolled_course_codes),
        "synthetic": True,
        "watermark": SYNTHETIC_WATERMARK,
    }


@router.get("/offerings")
async def get_offerings(request: Request, response: Response) -> dict[str, Any]:
    """Load canonical course offerings (204 sections) snapshot."""
    start = time.perf_counter()
    provider = _get_offering_provider(request)
    snapshot = await provider.load_snapshot(SANDBOX_INSTITUTION_ID, "2026-1")

    if not snapshot:
        raise HTTPException(status_code=503, detail="OFFERINGS_UNAVAILABLE")

    response.headers["Cache-Control"] = "no-cache"
    latency = (time.perf_counter() - start) * 1000
    sandbox_obs.record_event("SANDBOX_READ", latency_ms=latency, entity="offerings")

    return {
        "university_id": snapshot.university_id,
        "period_key": snapshot.period_key,
        "section_count": len(snapshot.sections),
        "source_version": snapshot.source_version,
        "source_type": snapshot.source_type.value,
        "sections": [
            {
                "section_id": s.section_id,
                "course_code": s.course_code,
                "status": s.status,
                "modality": s.modality.value,
                "campus": s.campus,
                "location": s.location,
                "capacity": s.capacity,
                "enrolled": s.enrolled,
                "available": s.available,
                "meetings": [
                    {
                        "day": m.day,
                        "starts_at": m.starts_at.isoformat(),
                        "ends_at": m.ends_at.isoformat(),
                        "timezone": m.timezone,
                    }
                    for m in s.meetings
                ],
            }
            for s in snapshot.sections
        ],
        "synthetic": True,
        "watermark": SYNTHETIC_WATERMARK,
    }


@router.post("/reset")
async def reset_sandbox_session(response: Response) -> dict[str, Any]:
    """Reset sandbox demo state. Zero writes to production infrastructure."""
    start = time.perf_counter()
    latency = (time.perf_counter() - start) * 1000
    sandbox_obs.record_event("SANDBOX_RESET", latency_ms=latency)

    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "SUCCESS",
        "action": "RESET_COMPLETED",
        "message": "تم إعادة ضبط البيئة التجريبية بنجاح",
        "message_en": "Sandbox environment reset successfully.",
        "institution_id": SANDBOX_INSTITUTION_ID,
        "synthetic": True,
        "watermark": SYNTHETIC_WATERMARK,
    }


@router.get("/evidence")
async def get_evidence(response: Response) -> dict[str, Any]:
    """Retrieve the WC-050 Evidence Manifest."""
    response.headers["Cache-Control"] = "no-cache"
    return dict(get_wc050_manifest())


@router.get("/observability/events")
async def get_observability_events(limit: int = 50) -> dict[str, Any]:
    """Retrieve safe recent telemetry events (zero student credentials/PII)."""
    return {
        "institution_id": SANDBOX_INSTITUTION_ID,
        "events": sandbox_obs.get_recent_events(limit=limit),
    }
