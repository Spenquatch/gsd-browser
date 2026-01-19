from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.jwt import JWTVerifier

IDENTITY_COMPONENT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{0,63}$")

Transport = Literal["stdio", "http"]


@dataclass(frozen=True, slots=True)
class Identity:
    tenant_id: str
    subject_id: str
    transport: Transport


STDIO_IDENTITY = Identity(tenant_id="local", subject_id="local", transport="stdio")


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


def get_jwt_tenant_id_claim_name() -> str:
    return _env("GSD_JWT_TENANT_ID_CLAIM") or "tenant_id"


def get_jwt_subject_id_claim_name() -> str:
    return _env("GSD_JWT_SUBJECT_ID_CLAIM") or "sub"


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
    tenant_raw = claims.get(tenant_id_claim)
    subject_raw = claims.get(subject_id_claim)

    tenant_id = _normalize_identity_component(tenant_raw, field_name="tenant_id")
    subject_id = _normalize_identity_component(subject_raw, field_name="subject_id")

    return Identity(tenant_id=tenant_id, subject_id=subject_id, transport="http")


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
        access_token = await super().verify_token(token)
        if access_token is None:
            return None

        try:
            _ = identity_from_claims(
                access_token.claims,
                tenant_id_claim=self._tenant_id_claim,
                subject_id_claim=self._subject_id_claim,
            )
        except ValueError:
            return None

        return access_token
