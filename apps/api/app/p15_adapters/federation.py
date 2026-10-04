"""Unwired federation policy boundary, not an IdP or token verifier.

Only a future trusted cryptographic adapter may construct an assertion after
OIDC/SAML verification. This module cannot sign, exchange, or verify tokens and
must not replace the existing Supabase-authenticated request boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from secrets import token_urlsafe
from typing import Protocol


class FederationFailure(str, Enum):
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_CALLBACK = "INVALID_CALLBACK"
    INVALID_ASSERTION = "INVALID_ASSERTION"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    REPLAY = "REPLAY"
    ROLE_CONFLICT = "ROLE_CONFLICT"
    LINK_CONFLICT = "LINK_CONFLICT"
    SESSION_EXPIRED = "SESSION_EXPIRED"


class FederationDenied(PermissionError):
    def __init__(self, code: FederationFailure):
        self.code = code
        super().__init__(code.value)  # Safe audit code only; never a token/claim dump.


class ProtocolKind(str, Enum):
    OIDC = "OIDC"
    SAML = "SAML"


class Role(str, Enum):
    STUDENT = "STUDENT"
    ACADEMIC_ADVISOR = "ACADEMIC_ADVISOR"
    INSTITUTIONAL_ANALYST = "INSTITUTIONAL_ANALYST"


class AuditCode(str, Enum):
    SSO_LOGIN_SUCCESS = "SSO_LOGIN_SUCCESS"
    SSO_LOGIN_FAILED = "SSO_LOGIN_FAILED"
    ROLE_MAPPING_FAILED = "ROLE_MAPPING_FAILED"
    ACCOUNT_LINK_CONFLICT = "ACCOUNT_LINK_CONFLICT"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    LOGOUT = "LOGOUT"


@dataclass(frozen=True)
class AuthAuditEvent:
    institution_id: str
    provider_id: str
    code: AuditCode
    occurred_at: datetime
    subject_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.institution_id or not self.provider_id or not _aware(self.occurred_at):
            raise ValueError("Invalid audit scope")


class UniversityIdentityProvider(Protocol):
    """Future trusted verifier boundary; no implementation or endpoint in P15."""

    institution_id: str
    provider_id: str
    protocol: ProtocolKind

    async def verify_callback(self, *, authorization_code: str,
                              challenge: PendingChallenge) -> VerifiedAssertion:
        """Perform actual code exchange, PKCE, signature/JWKS checks before returning."""


@dataclass(frozen=True)
class FederationConfig:
    institution_id: str
    provider_id: str
    protocol: ProtocolKind
    issuer: str
    audience: str
    redirect_uri: str
    mapping_version: str

    def __post_init__(self) -> None:
        if not all((self.institution_id, self.provider_id, self.issuer, self.audience,
                    self.redirect_uri, self.mapping_version)):
            raise ValueError("Incomplete federation config")
        if not self.redirect_uri.startswith("https://"):
            raise ValueError("Federation redirect must use HTTPS")


@dataclass(frozen=True)
class PendingChallenge:
    """Server-held, single-use OIDC authorization-code challenge metadata."""

    institution_id: str
    provider_id: str
    state: str
    nonce: str
    pkce_challenge: str
    redirect_uri: str
    expires_at: datetime


class ChallengeStore:
    """In-memory policy test store; not durable, distributed, or production-ready."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingChallenge] = {}

    def begin(self, config: FederationConfig, *, pkce_challenge: str,
              now: datetime) -> PendingChallenge:
        if config.protocol is not ProtocolKind.OIDC or not pkce_challenge or not _aware(now):
            raise FederationDenied(FederationFailure.INVALID_CALLBACK)
        challenge = PendingChallenge(config.institution_id, config.provider_id,
                                     token_urlsafe(32), token_urlsafe(32), pkce_challenge,
                                     config.redirect_uri, now + timedelta(minutes=5))
        self._pending[challenge.state] = challenge
        return challenge

    def consume(self, state: str, *, now: datetime) -> PendingChallenge:
        # Consume even an expired challenge; it must never become valid again.
        challenge = self._pending.pop(state, None)
        if challenge is None or not _aware(now) or now >= challenge.expires_at:
            raise FederationDenied(FederationFailure.REPLAY)
        return challenge


@dataclass(frozen=True)
class VerifiedAssertion:
    """Facts a future trusted verifier must produce after signature/JWKS checks.

    A boolean flag alone is not cryptographic proof. No route accepts this type.
    """

    institution_id: str
    provider_id: str
    protocol: ProtocolKind
    issuer: str
    audience: str
    subject: str
    nonce: str
    redirect_uri: str
    expires_at: datetime
    issued_at: datetime
    signature_verified: bool
    authorization_code_exchanged: bool
    pkce_verified: bool
    external_roles: tuple[str, ...]


@dataclass(frozen=True)
class FederatedIdentity:
    institution_id: str
    provider_id: str
    issuer: str
    external_subject: str
    candidate_role: Role | None
    linked_local_user_id: str | None
    mapping_version: str
    authenticated_at: datetime


def normalize_identity(config: FederationConfig, challenge: PendingChallenge,
                       assertion: VerifiedAssertion, rules: tuple[RoleRule, ...],
                       links: AccountLinks, *, now: datetime) -> FederatedIdentity:
    """Trusted result only after post-crypto checks; no account or role mutation."""
    validate_oidc_assertion(config, challenge, assertion, now=now)
    role = map_candidate_role(config, assertion, rules)
    return FederatedIdentity(config.institution_id, config.provider_id, assertion.issuer,
                             assertion.subject, role, links.resolve(assertion),
                             config.mapping_version, assertion.issued_at)


def validate_oidc_assertion(config: FederationConfig, challenge: PendingChallenge,
                            assertion: VerifiedAssertion, *, now: datetime) -> None:
    """Post-crypto guard; never call this with untrusted decoded JWT claims."""
    if (config.protocol is not ProtocolKind.OIDC or assertion.protocol is not ProtocolKind.OIDC
            or not _aware(now) or not _aware(assertion.expires_at) or not _aware(assertion.issued_at)):
        raise FederationDenied(FederationFailure.INVALID_ASSERTION)
    if (challenge.institution_id != config.institution_id
            or assertion.institution_id != config.institution_id
            or challenge.provider_id != config.provider_id
            or assertion.provider_id != config.provider_id):
        raise FederationDenied(FederationFailure.TENANT_MISMATCH)
    if (not assertion.signature_verified or not assertion.authorization_code_exchanged
            or not assertion.pkce_verified or not assertion.subject
            or assertion.issuer != config.issuer or assertion.audience != config.audience
            or assertion.nonce != challenge.nonce
            or assertion.redirect_uri != challenge.redirect_uri
            or challenge.redirect_uri != config.redirect_uri
            or now >= assertion.expires_at or assertion.issued_at > now
            or now >= challenge.expires_at):
        raise FederationDenied(FederationFailure.INVALID_ASSERTION)


@dataclass(frozen=True)
class RoleRule:
    institution_id: str
    provider_id: str
    external_role: str
    mapped_role: Role
    review_version: str
    approved: bool


def map_candidate_role(config: FederationConfig, assertion: VerifiedAssertion,
                       rules: tuple[RoleRule, ...]) -> Role | None:
    """Unknown roles grant nothing; a match is never an advisor/analyst DB grant."""
    if assertion.institution_id != config.institution_id or assertion.provider_id != config.provider_id:
        raise FederationDenied(FederationFailure.TENANT_MISMATCH)
    matching = [rule.mapped_role for rule in rules if rule.approved
                and rule.review_version == config.mapping_version
                and rule.institution_id == config.institution_id
                and rule.provider_id == config.provider_id
                and rule.external_role in assertion.external_roles]
    if len(set(matching)) > 1:
        raise FederationDenied(FederationFailure.ROLE_CONFLICT)
    return matching[0] if matching else None


@dataclass(frozen=True)
class AccountLink:
    institution_id: str
    provider_id: str
    external_subject: str
    local_user_id: str
    reviewed: bool


class AccountLinks:
    """Exact stable-subject link; email and mutable display name are never keys."""

    def __init__(self, links: tuple[AccountLink, ...]):
        self._links: dict[tuple[str, str, str], AccountLink] = {}
        local_keys: set[tuple[str, str, str]] = set()
        for link in links:
            key = (link.institution_id, link.provider_id, link.external_subject)
            local_key = (link.institution_id, link.provider_id, link.local_user_id)
            if (not all(key) or not link.local_user_id or key in self._links
                    or local_key in local_keys):
                raise FederationDenied(FederationFailure.LINK_CONFLICT)
            self._links[key] = link
            local_keys.add(local_key)

    def resolve(self, assertion: VerifiedAssertion) -> str | None:
        link = self._links.get((assertion.institution_id, assertion.provider_id, assertion.subject))
        return link.local_user_id if link is not None and link.reviewed else None


@dataclass(frozen=True)
class LocalSession:
    session_id: str
    institution_id: str
    provider_id: str
    local_user_id: str
    expires_at: datetime
    issued_at: datetime | None = None
    auth_time: datetime | None = None
    mapping_version: str | None = None


class LocalSessionStore:
    """Model of local session invalidation; not wired to Supabase Auth sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, LocalSession] = {}

    def add(self, session: LocalSession) -> None:
        if not session.session_id or not _aware(session.expires_at):
            raise FederationDenied(FederationFailure.INVALID_ASSERTION)
        if (session.issued_at is not None and not _aware(session.issued_at)) or (
                session.auth_time is not None and not _aware(session.auth_time)):
            raise FederationDenied(FederationFailure.INVALID_ASSERTION)
        self._sessions[session.session_id] = session

    def require(self, session_id: str, institution_id: str, now: datetime, *,
                provider_id: str | None = None,
                mapping_version: str | None = None) -> LocalSession:
        session = self._sessions.get(session_id)
        if (session is None or session.institution_id != institution_id
                or not _aware(now) or now >= session.expires_at
                or (provider_id is not None and session.provider_id != provider_id)
                or (mapping_version is not None and session.mapping_version != mapping_version)):
            raise FederationDenied(FederationFailure.SESSION_EXPIRED)
        return session

    def logout(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None
