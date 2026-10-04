"""Tiny two-institution contract fixtures; no live SIS, IdP, or database."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.institution_context.registry import (PROVIDER_KINDS, InstitutionConfig,
    InstitutionContext, InstitutionProviderRegistry, ProviderBinding)
from app.p15_adapters.federation import (
    AccountLink, AccountLinks, AuditCode, AuthAuditEvent, ChallengeStore,
    FederationConfig, FederationDenied,
    FederationFailure, LocalSession, LocalSessionStore, ProtocolKind, Role,
    RoleRule, UniversityIdentityProvider, VerifiedAssertion, map_candidate_role,
    normalize_identity, validate_oidc_assertion,
)
from app.p15_adapters.sis import (
    Entity, Failure, Freshness, IdentifierMapping, IdentifierRegistry,
    Reconciliation, SISFailure, SISHealth, SISPage, SourceEvidence,
    SISReadAdapter, decision_ready, map_academic_record, read_pages,
    reconcile, stage_curriculum, validate_offering_snapshot,
)
from app.offerings.models import OfferingSnapshot, SourceType
from app.plan_transition.ingestion import IngestionState

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def evidence(tenant="A", fresh=True):
    return SourceEvidence(tenant, "test-adapter", "v1", "m1", NOW,
                          NOW, NOW + timedelta(minutes=1) if fresh else NOW - timedelta(seconds=1))


class ReadAdapter:
    def __init__(self, tenant="A", *, next_cursor=None, delay=0):
        self.institution_id = tenant
        self.adapter_id = "test-adapter"
        self.capabilities = frozenset({Entity.STUDENT})
        self.next_cursor = next_cursor
        self.delay = delay
        self.calls = 0

    async def health(self):
        return SISHealth(self.institution_id, self.adapter_id, True, NOW, "m1",
                         self.capabilities, None, Freshness.FRESH)

    async def fetch_page(self, entity, *, cursor, limit):
        import asyncio
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return SISPage(self.institution_id, entity, ({"id": "S1"},),
                       self.next_cursor, evidence(self.institution_id))


def test_sis_bounded_read_and_exact_tenant():
    adapter = ReadAdapter()
    pages = asyncio.run(read_pages(adapter, "A", Entity.STUDENT))
    assert len(pages) == 1 and adapter.calls == 1
    with pytest.raises(SISFailure) as exc:
        asyncio.run(read_pages(adapter, "B", Entity.STUDENT))
    assert exc.value.code is Failure.TENANT_MISMATCH and adapter.calls == 1
    with pytest.raises(SISFailure) as exc:
        asyncio.run(read_pages(adapter, "A", Entity.PLAN))
    assert exc.value.code is Failure.UNAVAILABLE


def test_sis_cursor_loop_and_timeout_fail_closed():
    adapter = ReadAdapter(next_cursor="same")
    with pytest.raises(SISFailure) as exc:
        asyncio.run(read_pages(adapter, "A", Entity.STUDENT))
    assert exc.value.code is Failure.INVALID_RESPONSE and adapter.calls == 2
    adapter = ReadAdapter(delay=0.02)
    with pytest.raises(SISFailure) as exc:
        asyncio.run(read_pages(adapter, "A", Entity.STUDENT, timeout_seconds=0.001))
    assert exc.value.code is Failure.TIMEOUT and adapter.calls == 1


def test_sis_next_page_empty_page_and_provider_failure():
    class Sequenced(ReadAdapter):
        async def fetch_page(self, entity, *, cursor, limit):
            self.calls += 1
            return SISPage("A", entity, ({"id": "one"},) if cursor is None else (),
                           "next" if cursor is None else None, evidence())

    adapter = Sequenced()
    pages = asyncio.run(read_pages(adapter, "A", Entity.STUDENT))
    assert len(pages) == 2 and pages[1].records == () and adapter.calls == 2

    class Broken(ReadAdapter):
        async def fetch_page(self, entity, *, cursor, limit):
            raise RuntimeError("provider secret must not be surfaced")

    with pytest.raises(SISFailure) as exc:
        asyncio.run(read_pages(Broken(), "A", Entity.STUDENT))
    assert exc.value.code is Failure.UNAVAILABLE
    assert "secret" not in str(exc.value)


def test_sis_foreign_page_is_rejected_without_affecting_other_tenant():
    class Foreign(ReadAdapter):
        async def fetch_page(self, entity, *, cursor, limit):
            return SISPage("B", entity, (), None, evidence("B"))

    with pytest.raises(SISFailure) as exc:
        asyncio.run(read_pages(Foreign("A"), "A", Entity.STUDENT))
    assert exc.value.code is Failure.TENANT_MISMATCH
    assert len(asyncio.run(read_pages(ReadAdapter("B"), "B", Entity.STUDENT))) == 1


@pytest.mark.parametrize("field,value", [("page_size", 0), ("page_size", 101),
                                         ("max_pages", 21), ("timeout_seconds", 11)])
def test_sis_read_limits(field, value):
    with pytest.raises(ValueError):
        asyncio.run(read_pages(ReadAdapter(), "A", Entity.STUDENT, **{field: value}))


def test_sis_identifier_isolation_and_conflicts():
    registry = IdentifierRegistry((IdentifierMapping("A", Entity.STUDENT, "x", "a", "m1"),
                                   IdentifierMapping("B", Entity.STUDENT, "x", "b", "m1")))
    assert registry.resolve("A", Entity.STUDENT, "x") == "a"
    assert registry.resolve("B", Entity.STUDENT, "x") == "b"
    with pytest.raises(SISFailure):
        registry.resolve("A", Entity.STUDENT, "other")
    with pytest.raises(SISFailure):
        IdentifierRegistry((IdentifierMapping("A", Entity.STUDENT, "x", "a", "m1"),
                            IdentifierMapping("A", Entity.STUDENT, "y", "a", "m1")))
    with pytest.raises(SISFailure):
        IdentifierRegistry((IdentifierMapping("A", Entity.STUDENT, "x", "a", "m1"),
                            IdentifierMapping("A", Entity.COURSE, "x", "C101", "m1")))


def test_canonical_academic_mapping_and_malformed_payload():
    mappings = IdentifierRegistry(tuple(IdentifierMapping("A", kind, external, local, "m1")
                                    for kind, external, local in (
                                        (Entity.STUDENT, "s-ext", "s-local"),
                                        (Entity.PROGRAM, "p-ext", "p-local"),
                                        (Entity.MAJOR, "m-ext", "m-local"),
                                        (Entity.PLAN, "plan-ext", "plan-local"),
                                        (Entity.PLAN_VERSION, "v-ext", "v-local"),
                                        (Entity.COURSE, "c-ext", "C101"))))
    payload = {"schema_version": "P15_SIS_RECORD_V1", "institution_id": "A",
               "student_external_id": "s-ext", "program_external_id": "p-ext",
               "major_external_id": "m-ext", "plan_external_id": "plan-ext",
               "plan_version_external_id": "v-ext", "earned_credits": "3.5",
               "attempts": [{"course_external_id": "c-ext", "outcome": "PASSED"}],
               "enrollments": [{"course_external_id": "c-ext"}]}
    record = map_academic_record(payload, institution_id="A", mappings=mappings,
                                 evidence=evidence())
    assert record.student_id == "s-local" and record.plan_id == "plan-local"
    assert record.attempts[0].course_code == "C101"
    assert record.enrolled_course_codes == ("C101",)
    for change, code in (({"institution_id": "B"}, Failure.TENANT_MISMATCH),
                         ({"schema_version": "other"}, Failure.SCHEMA_MISMATCH),
                         ({"earned_credits": "NaN"}, Failure.INVALID_RESPONSE),
                         ({"attempts": [{"course_external_id": "c-ext", "outcome": "MAGIC"}]},
                          Failure.INVALID_RESPONSE)):
        with pytest.raises(SISFailure) as exc:
            map_academic_record({**payload, **change}, institution_id="A",
                                mappings=mappings, evidence=evidence())
        assert exc.value.code is code


def test_read_only_contract_and_safe_health():
    assert set(SISReadAdapter.__dict__) & {"register_course", "drop_course", "change_grade",
                                            "publish_curriculum", "update_student_record"} == set()
    health = asyncio.run(ReadAdapter().health())
    assert health.capabilities == frozenset({Entity.STUDENT})
    assert "secret" not in repr(health).lower()


@pytest.mark.parametrize("source,local,source_delta,local_delta,expected", [
    ("x", "x", 0, 0, Reconciliation.MATCH),
    ("x", "y", 1, 0, Reconciliation.SOURCE_NEWER),
    ("x", "y", 0, 1, Reconciliation.LOCAL_NEWER),
    ("x", "y", 0, 0, Reconciliation.CONFLICT),
    (None, "x", 0, 0, Reconciliation.MISSING_SOURCE),
    ("x", None, 0, 0, Reconciliation.MISSING_LOCAL),
])
def test_reconciliation_classification(source, local, source_delta, local_delta, expected):
    assert reconcile(source, local, source_updated_at=NOW + timedelta(seconds=source_delta),
                     local_updated_at=NOW + timedelta(seconds=local_delta)) is expected


def test_unmapped_invalid_and_freshness():
    assert reconcile("x", "y", source_updated_at=NOW, local_updated_at=NOW,
                     mapped=False) is Reconciliation.UNMAPPED
    assert reconcile("x", "y", source_updated_at=NOW, local_updated_at=NOW,
                     valid=False) is Reconciliation.INVALID
    assert evidence().freshness_at(NOW) is Freshness.FRESH
    assert decision_ready(evidence(), NOW)
    assert not decision_ready(evidence(fresh=False), NOW)
    assert not decision_ready(replace(evidence(), fresh_until=None), NOW)


def test_sis_reuses_p12_staging_and_p10_snapshot():
    document = {"schema_version": "P12_PLAN_V1", "identity": {
        "institution_id": "A", "program_id": "P", "major_id": "M",
        "plan_id": "PLAN", "version_id": "V1", "effective_from": "2026-01-01",
        "effective_to": None, "source_version": "v1"},
        "groups": [{"group_id": "G", "required_credits": "3"}],
        "courses": [{"course_id": "C", "code": "C101", "group_id": "G",
                     "credits": "3", "prerequisites": []}]}
    preview = stage_curriculum(document, institution_id="A", evidence=evidence())
    assert preview.state is IngestionState.READY_FOR_REVIEW
    assert preview.plan is not None
    with pytest.raises(SISFailure):
        stage_curriculum(document, institution_id="B", evidence=evidence("B"))
    snapshot = OfferingSnapshot("A", "2026-FALL", "snap", "v1", SourceType.SYNTHETIC,
                                NOW, NOW + timedelta(minutes=1), True, (), "SYNTHETIC P15 TEST")
    assert validate_offering_snapshot(snapshot, institution_id="A", evidence=evidence(), now=NOW) is snapshot
    with pytest.raises(SISFailure):
        validate_offering_snapshot(snapshot, institution_id="B", evidence=evidence("B"), now=NOW)
    with pytest.raises(SISFailure):
        validate_offering_snapshot(snapshot, institution_id="A", evidence=evidence(fresh=False), now=NOW)


def config(tenant="A"):
    return FederationConfig(tenant, "idp", ProtocolKind.OIDC, "https://idp.example/issuer",
                            "morshidi-client", "https://app.example/callback", "review-1")


def assertion(challenge, tenant="A"):
    return VerifiedAssertion(tenant, "idp", ProtocolKind.OIDC, "https://idp.example/issuer",
                             "morshidi-client", "stable-subject", challenge.nonce,
                             challenge.redirect_uri, NOW + timedelta(minutes=2), NOW,
                             True, True, True, ("student",))


def test_oidc_post_verification_guards_and_single_use_state():
    store = ChallengeStore()
    challenge = store.begin(config(), pkce_challenge="S256-challenge", now=NOW)
    consumed = store.consume(challenge.state, now=NOW)
    validate_oidc_assertion(config(), consumed, assertion(consumed), now=NOW)
    with pytest.raises(FederationDenied) as exc:
        store.consume(challenge.state, now=NOW)
    assert exc.value.code is FederationFailure.REPLAY
    with pytest.raises(FederationDenied):
        store.consume("attacker-controlled-state", now=NOW)
    for change in ({"signature_verified": False}, {"pkce_verified": False},
                   {"authorization_code_exchanged": False}, {"nonce": "wrong"},
                   {"issuer": "https://other.example"}, {"audience": "other"},
                   {"redirect_uri": "https://other.example/callback"},
                   {"expires_at": NOW}):
        with pytest.raises(FederationDenied):
            validate_oidc_assertion(config(), consumed, replace(assertion(consumed), **change), now=NOW)
    with pytest.raises(FederationDenied) as exc:
        validate_oidc_assertion(config(), consumed, assertion(consumed, "B"), now=NOW)
    assert exc.value.code is FederationFailure.TENANT_MISMATCH


def test_oidc_role_mapping_is_candidate_only_and_conflicts_deny():
    challenge = ChallengeStore().begin(config(), pkce_challenge="S256", now=NOW)
    identity = assertion(challenge)
    rules = (RoleRule("A", "idp", "student", Role.STUDENT, "review-1", True),)
    assert map_candidate_role(config(), identity, rules) is Role.STUDENT
    assert map_candidate_role(config(), identity, ()) is None
    assert map_candidate_role(config(), identity,
                              (replace(rules[0], approved=False),)) is None
    with pytest.raises(FederationDenied) as exc:
        map_candidate_role(config(), replace(identity, external_roles=("student", "staff")),
                           rules + (RoleRule("A", "idp", "staff", Role.INSTITUTIONAL_ANALYST,
                                             "review-1", True),))
    assert exc.value.code is FederationFailure.ROLE_CONFLICT
    with pytest.raises(FederationDenied):
        map_candidate_role(config(), assertion(challenge, "B"), rules)
    assert map_candidate_role(config(), replace(identity, external_roles=("arbitrary-admin",)),
                              rules) is None


def test_trusted_identity_normalization_and_audit_redaction():
    challenge = ChallengeStore().begin(config(), pkce_challenge="S256", now=NOW)
    identity = normalize_identity(config(), challenge, assertion(challenge),
                                  (RoleRule("A", "idp", "student", Role.STUDENT,
                                            "review-1", True),),
                                  AccountLinks((AccountLink("A", "idp", "stable-subject",
                                                            "local-user", True),)), now=NOW)
    assert identity.institution_id == "A" and identity.candidate_role is Role.STUDENT
    assert identity.linked_local_user_id == "local-user"
    event = AuthAuditEvent("A", "idp", AuditCode.SSO_LOGIN_SUCCESS, NOW)
    assert "token" not in repr(event).lower() and "secret" not in repr(event).lower()
    assert set(UniversityIdentityProvider.__dict__) & {"password", "token", "secret"} == set()


def test_stable_subject_link_and_local_logout():
    challenge = ChallengeStore().begin(config(), pkce_challenge="S256", now=NOW)
    identity = assertion(challenge)
    links = AccountLinks((AccountLink("A", "idp", "stable-subject", "user-1", True),))
    assert links.resolve(identity) == "user-1"
    assert links.resolve(replace(identity, institution_id="B")) is None
    assert AccountLinks((AccountLink("A", "idp", "stable-subject", "user-1", False),)).resolve(identity) is None
    with pytest.raises(FederationDenied):
        AccountLinks((AccountLink("A", "idp", "s1", "user-1", True),
                      AccountLink("A", "idp", "s2", "user-1", True)))
    sessions = LocalSessionStore()
    sessions.add(LocalSession("session", "A", "idp", "user-1", NOW + timedelta(minutes=1)))
    assert sessions.require("session", "A", NOW).local_user_id == "user-1"
    with pytest.raises(FederationDenied):
        sessions.require("session", "B", NOW)
    with pytest.raises(FederationDenied):
        sessions.require("session", "A", NOW, provider_id="other")
    with pytest.raises(FederationDenied):
        sessions.require("session", "A", NOW, mapping_version="other")
    with pytest.raises(FederationDenied):
        sessions.require("session", "A", NOW + timedelta(minutes=1))
    sessions.logout("session")
    with pytest.raises(FederationDenied):
        sessions.require("session", "A", NOW)


def test_internal_registry_supports_only_scoped_p15_kinds():
    assert {"sis", "identity"} <= PROVIDER_KINDS


def test_registry_binds_sis_and_identity_exactly_per_institution():
    configs = []
    adapters = {}
    for tenant, slug in (("A", "alpha"), ("B", "beta")):
        context = InstitutionContext(tenant, slug, slug, "ACTIVE", "JO", "en", ("en",),
                                     "UTC", "academic", "branding", "v1")
        bindings = {kind: ProviderBinding(f"{slug}-{kind}", tenant)
                    for kind in ("sis", "identity")}
        configs.append(InstitutionConfig(context, {}, bindings, "default", "P15_TEST", "v1"))
        for kind, binding in bindings.items():
            adapter = ReadAdapter(tenant) if kind == "sis" else type("IdentityStub", (),
                                                                      {"institution_id": tenant})()
            adapters[(tenant, binding.provider_key)] = adapter
    registry = InstitutionProviderRegistry(tuple(configs), adapters)
    assert registry.resolve("A").require("sis").institution_id == "A"
    assert registry.resolve("B").require("identity").institution_id == "B"
    assert registry.resolve("A").cache_key("x") != registry.resolve("B").cache_key("x")
    with pytest.raises(ValueError):
        InstitutionProviderRegistry(tuple(configs),
                                    {**adapters, ("A", "alpha-sis"): ReadAdapter("B")})
