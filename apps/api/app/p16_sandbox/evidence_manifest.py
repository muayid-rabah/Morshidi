"""WC-050 Evidence Manifest & Proposal Compliance Verification.

Maintains verifiable, deterministic mapping of system capabilities, verification states,
and source file evidence without inventing unverified claims.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CapabilityEvidence:
    capability_id: str
    title: str
    status: str
    verification_method: str
    source_files: tuple[str, ...]
    notes: str


EVIDENCE_REGISTRY: tuple[CapabilityEvidence, ...] = (
    CapabilityEvidence(
        capability_id="WC-001",
        title="Deterministic Prerequisite Engine",
        status="SYNTHETIC_VERIFIED",
        verification_method="DETERMINISTIC_UNIT_TEST",
        source_files=("apps/api/app/rules/evaluator.py", "apps/api/app/rules/models.py"),
        notes="Evaluates eligibility deterministically using boolean expressions and catalog rules.",
    ),
    CapabilityEvidence(
        capability_id="WC-002",
        title="Degree Progress Engine",
        status="SYNTHETIC_VERIFIED",
        verification_method="DETERMINISTIC_UNIT_TEST",
        source_files=("apps/api/app/progress/engine.py", "apps/api/app/progress/models.py"),
        notes="Calculates degree completion credits, group requirements, and GPA without LLM invention.",
    ),
    CapabilityEvidence(
        capability_id="WC-010",
        title="Course Offerings Architecture",
        status="SYNTHETIC_VERIFIED",
        verification_method="CONTRACT_VERIFICATION",
        source_files=("apps/api/app/offerings/models.py", "apps/api/app/offerings/provider.py"),
        notes="Immutable period-scoped snapshot facts with capacity and schedule collision checks.",
    ),
    CapabilityEvidence(
        capability_id="WC-013",
        title="Multi-Tenant Institution Context",
        status="SYNTHETIC_VERIFIED",
        verification_method="TENANT_ISOLATION_TEST",
        source_files=("apps/api/app/institution_context/registry.py",),
        notes="Exact-tenant resolution; strict isolation preventing cross-tenant provider leakage.",
    ),
    CapabilityEvidence(
        capability_id="WC-015",
        title="P15 SIS Read Adapter Contract",
        status="SYNTHETIC_VERIFIED",
        verification_method="CONTRACT_VERIFICATION",
        source_files=("apps/api/app/p15_adapters/sis.py",),
        notes="Canonical student and academic record mapping with freshness and source evidence tracking.",
    ),
    CapabilityEvidence(
        capability_id="WC-050",
        title="Evidence Manifest & Contract Parity",
        status="IMPLEMENTED",
        verification_method="CONTRACT_VERIFICATION",
        source_files=("apps/api/app/p16_sandbox/evidence_manifest.py", "apps/api/app/p16_sandbox/drift.py"),
        notes="Tracks evidence states, parity with contributor portal, and zero credential leakage.",
    ),
    CapabilityEvidence(
        capability_id="WC-053",
        title="Observability, SLOs & Runbooks",
        status="IMPLEMENTED",
        verification_method="STRUCTURED_LOG_AUDIT",
        source_files=("apps/api/app/p16_sandbox/observability.py",),
        notes="Safe structured events, latency tracking, health status, and runbook mapping.",
    ),
)


def get_wc050_manifest() -> Mapping[str, Any]:
    """Return the structured WC-050 Evidence Manifest."""
    return {
        "manifest_version": "2026.10.02.v1",
        "institution_id": "morshidi-sandbox",
        "provenance": "MORSHIDI_EVIDENCE_REGISTRY",
        "capabilities_count": len(EVIDENCE_REGISTRY),
        "capabilities": [asdict(cap) for cap in EVIDENCE_REGISTRY],
    }
