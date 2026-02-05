from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from authlib.jose.errors import JoseError
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.jwt import JWTVerifier

IDENTITY_COMPONENT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{0,63}$")

Transport = Literal["stdio", "http"]


@dataclass(frozen=True, slots=True)
class Identity:
    tenant_id: str
    subject_id: str
    transport: Transport


@dataclass(frozen=True, slots=True)
class JwtAudienceMismatch:
    expected_audience: str
    actual_audience: str


STDIO_IDENTITY = Identity(tenant_id="local", subject_id="local", transport="stdio")

_JWT_VERIFIER_CACHE: tuple[
    tuple[str, str, str, str, str, str],
    GsdJwtVerifier | None,
] | None = None


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


def get_jwt_tenant_id_claim_name() -> str:
    return _env("GSD_JWT_TENANT_ID_CLAIM") or "tenant_id"


def get_jwt_subject_id_claim_name() -> str:
    return _env("GSD_JWT_SUBJECT_ID_CLAIM") or "sub"


def get_jwt_verifier() -> GsdJwtVerifier | None:
    """Return a configured JWT verifier for GSD services.

    Streaming and management endpoints treat JWT verification as optional unless explicitly
    enabled. Callers should fail closed when they require JWT mode.

    Required env vars:
    - `GSD_JWT_ISSUER`
    - `GSD_JWT_AUDIENCE`
    - Exactly one of:
      - `GSD_JWT_JWKS_URL` (preferred in production), or
      - `GSD_JWT_PUBLIC_KEY` (useful for offline tests/local dev)
    """
    global _JWT_VERIFIER_CACHE

    jwks_url = _env("GSD_JWT_JWKS_URL")
    public_key = _env("GSD_JWT_PUBLIC_KEY")
    issuer = _env("GSD_JWT_ISSUER")
    audience = _env("GSD_JWT_AUDIENCE")
    tenant_id_claim = get_jwt_tenant_id_claim_name()
    subject_id_claim = get_jwt_subject_id_claim_name()

    cache_key = (
        jwks_url,
        public_key,
        issuer,
        audience,
        tenant_id_claim,
        subject_id_claim,
    )
    if _JWT_VERIFIER_CACHE is not None and _JWT_VERIFIER_CACHE[0] == cache_key:
        return _JWT_VERIFIER_CACHE[1]

    if not issuer or not audience:
        _JWT_VERIFIER_CACHE = (cache_key, None)
        return None

    if bool(jwks_url) == bool(public_key):
        # Require exactly one: fail safe-by-default.
        _JWT_VERIFIER_CACHE = (cache_key, None)
        return None

    verifier = GsdJwtVerifier(
        jwks_uri=jwks_url or None,
        public_key=public_key or None,
        issuer=issuer,
        audience=audience,
        tenant_id_claim=tenant_id_claim,
        subject_id_claim=subject_id_claim,
    )
    _JWT_VERIFIER_CACHE = (cache_key, verifier)
    return verifier


def _normalize_identity_component(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")

    if not IDENTITY_COMPONENT_RE.fullmatch(normalized):
        raise ValueError(f"{field_name} must match {IDENTITY_COMPONENT_RE.pattern}")

    return normalized


def identity_from_claims(
    claims: Mapping[str, Any],
    *,
    tenant_id_claim: str,
    subject_id_claim: str,
) -> Identity:
    subject_raw = claims.get(subject_id_claim)
    if subject_raw is None and subject_id_claim != "sub":
        subject_raw = claims.get("sub")

    tenant_raw = claims.get(tenant_id_claim)
    # Backward/compat: allow Clerk default org claim when no custom tenant_id claim is present.
    if tenant_raw is None:
        if tenant_id_claim != "tenant_id":
            tenant_raw = claims.get("tenant_id")
        if tenant_raw is None:
            tenant_raw = claims.get("org_id") or claims.get("orgId")
        if tenant_raw is None:
            # Personal workspace fallback (ADR-0022): use subject_id as tenant_id.
            tenant_raw = subject_raw

    tenant_id = _normalize_identity_component(tenant_raw, field_name="tenant_id")
    subject_id = _normalize_identity_component(subject_raw, field_name="subject_id")

    return Identity(tenant_id=tenant_id, subject_id=subject_id, transport="http")


def _stringify_audience_claim(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value)
    except TypeError:
        return str(value)


class GsdJwtVerifier(JWTVerifier):
    """JWT verifier that also enforces canonical identity claim mapping rules."""

    def __init__(
        self,
        *,
        tenant_id_claim: str,
        subject_id_claim: str,
        public_key: str | None = None,
        jwks_uri: str | None = None,
        issuer: str | list[str] | None = None,
        audience: str | list[str] | None = None,
    ) -> None:
        super().__init__(
            public_key=public_key,
            jwks_uri=jwks_uri,
            issuer=issuer,
            audience=audience,
        )
        self._tenant_id_claim = str(tenant_id_claim).strip() or "tenant_id"
        self._subject_id_claim = str(subject_id_claim).strip() or "sub"

    async def verify_token(self, token: str) -> AccessToken | None:
        access_token, _audience_mismatch = await self.verify_token_with_audience_details(token)
        return access_token

    async def verify_token_with_audience_details(
        self, token: str
    ) -> tuple[AccessToken | None, JwtAudienceMismatch | None]:
        """Verify a token and preserve audience mismatch details.

        Returns:
        - (AccessToken, None) when valid and identity claims map cleanly.
        - (None, JwtAudienceMismatch) when token is otherwise valid but fails audience binding.
        - (None, None) for all other invalid token failures.
        """

        try:
            verification_key = await self._get_verification_key(token)
            claims_raw = self.jwt.decode(token, verification_key)
            claims: dict[str, Any] = dict(claims_raw)
        except JoseError:
            self.logger.debug("Token validation failed: JWT signature/format invalid")
            return None, None
        except Exception as exc:  # noqa: BLE001
            self.logger.debug("Token validation failed: %s", str(exc))
            return None, None

        client_id = claims.get("client_id") or claims.get("azp") or claims.get("sub") or "unknown"

        exp = claims.get("exp")
        if exp is not None and not isinstance(exp, (int, float)):
            self.logger.debug(
                "Token validation failed: exp claim not numeric for client %s",
                client_id,
            )
            self.logger.info("Bearer token rejected for client %s", client_id)
            return None, None

        if exp is not None and exp < time.time():
            self.logger.debug("Token validation failed: expired token for client %s", client_id)
            self.logger.info("Bearer token rejected for client %s", client_id)
            return None, None

        if self.issuer:
            iss = claims.get("iss")
            issuer_valid = False
            if isinstance(self.issuer, list):
                issuer_valid = iss in self.issuer
            else:
                issuer_valid = iss == self.issuer

            if not issuer_valid:
                self.logger.debug(
                    "Token validation failed: issuer mismatch for client %s",
                    client_id,
                )
                self.logger.info("Bearer token rejected for client %s", client_id)
                return None, None

        if self.audience:
            aud = claims.get("aud")

            audience_valid = False
            if isinstance(self.audience, list):
                expected_list = cast(list[str], self.audience)
                if isinstance(aud, list):
                    audience_valid = any(expected in aud for expected in expected_list)
                else:
                    audience_valid = aud in expected_list
            else:
                expected = cast(str, self.audience)
                if isinstance(aud, list):
                    audience_valid = expected in aud
                else:
                    audience_valid = aud == expected

            if not audience_valid:
                self.logger.debug(
                    "Token validation failed: audience mismatch for client %s",
                    client_id,
                )
                self.logger.info("Bearer token rejected for client %s", client_id)
                return (
                    None,
                    JwtAudienceMismatch(
                        expected_audience=_stringify_audience_claim(self.audience),
                        actual_audience=_stringify_audience_claim(aud),
                    ),
                )

        scopes = self._extract_scopes(claims)

        if self.required_scopes:
            token_scopes = set(scopes)
            required_scopes = set(self.required_scopes)
            if not required_scopes.issubset(token_scopes):
                self.logger.debug(
                    "Token missing required scopes. Has: %s, Required: %s",
                    token_scopes,
                    required_scopes,
                )
                self.logger.info("Bearer token rejected for client %s", client_id)
                return None, None

        access_token = AccessToken(
            token=token,
            client_id=str(client_id),
            scopes=scopes,
            expires_at=int(exp) if isinstance(exp, (int, float)) else None,
            claims=claims,
        )

        try:
            _ = identity_from_claims(
                access_token.claims,
                tenant_id_claim=self._tenant_id_claim,
                subject_id_claim=self._subject_id_claim,
            )
        except ValueError:
            return None, None

        return access_token, None
