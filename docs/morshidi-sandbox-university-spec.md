# Morshidi Sandbox University Specification

## Purpose and identity

Morshidi Sandbox University (MSU) is a fictional, isolated institution for deterministic product demonstration and evaluation. It must never use a real university's name, logo, policy text, identifiers, credentials, or student records. Every screen and export displays a persistent **Synthetic demonstration data** label.

## Dataset

The sandbox contains two fictional versioned study plans, prerequisite/corequisite graphs, credit and residency rules, course equivalencies, a synthetic academic calendar, offerings, sections, capacities, timetables, locations, and a cited synthetic policy corpus. Pseudonymous students cover clean progress, repeated course, missing prerequisite, transfer credit, plan transition, bottleneck, delayed critical path, overload, near-graduation, and unresolved-data cases.

Generation is seed-driven and reproducible. Each record includes `source_id`, `source_version`, `retrieved_at`, `verification_state`, and `synthetic=true`. Expected decisions and traces are checked into test fixtures. No generated name, email, identifier, or transcript may be derived from production data.

## Provider suite

The sandbox implements `StudentRecordProvider`, `CourseOfferingProvider`, `HistoricalOutcomeProvider`, `IdentityProvider`, `AcademicCalendarProvider`, and `InstitutionalPolicyProvider` from the external adapter strategy. It supports normal, stale, unavailable, incomplete, duplicated, and conflicting-source fixtures so the UI can demonstrate safe degradation rather than only happy paths.

## Roles and isolation

Fixed local identities represent student, advisor, curriculum analyst, and sandbox administrator roles. Authentication is test-only; authorization remains production-shaped. Student ownership, advisor scope, aggregate institution views, and audit events are enforced. Sandbox tenants, keys, storage, and logs are isolated from production, with no network route or import path to production records.

## Required demonstration journeys

1. Build and inspect an Academic Digital Twin.
2. Compare what-if scenarios without mutating the record.
3. Explain a delay consequence and graduation-audit result.
4. Create mock-registration intent and aggregate synthetic demand.
5. Review an advisor recommendation, override, and queue item.
6. Inspect bottleneck, capacity, data-quality, and curriculum views.
7. Retrieve a cited synthetic policy and distinguish it from a deterministic rule.
8. Show Arabic RTL, accessibility, modeled report, privacy control, and decision trace behavior.
9. Demonstrate stale/unavailable providers and honest uncertainty.

## Reset, privacy, and evidence controls

The sandbox resets to a known seed, expires mutable scenarios, and produces no production analytics. Screenshots and exports retain the synthetic watermark. Telemetry contains only sandbox identifiers and redacted events. Evaluation reports distinguish task/usability evidence from model-validity or institutional-readiness evidence.

## Acceptance criteria

The sandbox is complete when fixtures reproduce identically, provider contract suites pass, all journeys are automated, accessibility and Arabic RTL checks pass, failure states are demonstrated, reset succeeds, synthetic provenance cannot be removed, and an isolation test proves no production endpoint or credential is reachable. A sandbox pass does not satisfy the Real Student Pilot gate.
