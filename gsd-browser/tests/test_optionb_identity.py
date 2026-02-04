from __future__ import annotations

import asyncio

import pytest
from fastmcp import Context
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.jwt import RSAKeyPair

from gsd_browser.fastmcp_v2_stdio import mcp
from gsd_browser.optionb.identity import (
    STDIO_IDENTITY,
    GsdJwtVerifier,
    identity_from_claims,
)
from gsd_browser.optionb.request_context import (
    get_current_identity,
    require_current_identity,
)


def test_identity_from_claims_accepts_valid_values() -> None:
    identity = identity_from_claims(
        {"tenant_id": "tenant-1", "sub": "user_1"},
        tenant_id_claim="tenant_id",
        subject_id_claim="sub",
    )
    assert identity.tenant_id == "tenant-1"
    assert identity.subject_id == "user_1"
    assert identity.transport == "http"


def test_identity_from_claims_falls_back_to_org_id_when_tenant_id_missing() -> None:
    identity = identity_from_claims(
        {"org_id": "org_1", "sub": "user_1"},
        tenant_id_claim="tenant_id",
        subject_id_claim="sub",
    )
    assert identity.tenant_id == "org_1"
    assert identity.subject_id == "user_1"


def test_identity_from_claims_falls_back_to_subject_when_tenant_id_missing() -> None:
    identity = identity_from_claims(
        {"sub": "user_1"},
        tenant_id_claim="tenant_id",
        subject_id_claim="sub",
    )
    assert identity.tenant_id == "user_1"
    assert identity.subject_id == "user_1"


@pytest.mark.parametrize(
    ("claims", "match"),
    [
        ({}, "tenant_id"),
        ({"tenant_id": "t"}, "subject_id"),
        ({"tenant_id": " ", "sub": "u"}, "tenant_id"),
        ({"tenant_id": "t", "sub": " "}, "subject_id"),
        ({"tenant_id": "_bad", "sub": "u"}, "tenant_id"),
        ({"tenant_id": "t", "sub": "_bad"}, "subject_id"),
        ({"tenant_id": "t$", "sub": "u"}, "tenant_id"),
        ({"tenant_id": "t", "sub": "u$"}, "subject_id"),
        ({"tenant_id": "a" * 65, "sub": "u"}, "tenant_id"),
        ({"tenant_id": "t", "sub": "a" * 65}, "subject_id"),
    ],
)
def test_identity_from_claims_rejects_invalid_values(
    claims: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _ = identity_from_claims(
            claims,
            tenant_id_claim="tenant_id",
            subject_id_claim="sub",
        )


def test_gsd_jwt_verifier_rejects_tokens_with_invalid_identity_claims() -> None:
    keys = RSAKeyPair.generate()
    verifier = GsdJwtVerifier(
        public_key=keys.public_key,
        issuer="https://issuer.example.com",
        audience="gsd",
        tenant_id_claim="tenant_id",
        subject_id_claim="sub",
    )

    ok = keys.create_token(
        subject="user_1",
        issuer="https://issuer.example.com",
        audience="gsd",
        additional_claims={"tenant_id": "tenant-1"},
    )
    assert asyncio.run(verifier.verify_token(ok)) is not None

    wrong_issuer = keys.create_token(
        subject="user_1",
        issuer="https://wrong.example.com",
        audience="gsd",
        additional_claims={"tenant_id": "tenant-1"},
    )
    assert asyncio.run(verifier.verify_token(wrong_issuer)) is None

    missing_audience = keys.create_token(
        subject="user_1",
        issuer="https://issuer.example.com",
        audience=None,
        additional_claims={"tenant_id": "tenant-1"},
    )
    assert asyncio.run(verifier.verify_token(missing_audience)) is None

    expired = keys.create_token(
        subject="user_1",
        issuer="https://issuer.example.com",
        audience="gsd",
        expires_in_seconds=-1,
        additional_claims={"tenant_id": "tenant-1"},
    )
    assert asyncio.run(verifier.verify_token(expired)) is None

    bad_tenant = keys.create_token(
        subject="user_1",
        issuer="https://issuer.example.com",
        audience="gsd",
        additional_claims={"tenant_id": "_bad"},
    )
    assert asyncio.run(verifier.verify_token(bad_tenant)) is None

    missing_tenant_claim = keys.create_token(
        subject="user_1",
        issuer="https://issuer.example.com",
        audience="gsd",
    )
    # Personal workspace fallback: tenant_id defaults to subject_id.
    assert asyncio.run(verifier.verify_token(missing_tenant_claim)) is not None


def test_tool_wrappers_set_identity_scope_in_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    from gsd_browser import mcp_server as sdk_server
    from gsd_browser.fastmcp_v2_stdio import setup_browser_state

    async def fake_setup_browser_state(**_kwargs: object) -> list[object]:
        assert require_current_identity() == STDIO_IDENTITY
        return []

    monkeypatch.setattr(sdk_server, "setup_browser_state", fake_setup_browser_state)

    assert get_current_identity() is None
    _ = asyncio.run(setup_browser_state.fn(ctx=Context(mcp)))
    assert get_current_identity() is None


def test_tool_wrappers_set_identity_scope_in_http(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastmcp.server import dependencies

    from gsd_browser import mcp_server as sdk_server
    from gsd_browser.fastmcp_v2_stdio import setup_browser_state

    access_token = AccessToken(
        token="t",
        client_id="c",
        scopes=[],
        claims={"tenant_id": "tenant-1", "sub": "user_1"},
    )
    monkeypatch.setattr(dependencies, "get_access_token", lambda: access_token)

    async def fake_setup_browser_state(**_kwargs: object) -> list[object]:
        identity = require_current_identity()
        assert identity.tenant_id == "tenant-1"
        assert identity.subject_id == "user_1"
        assert identity.transport == "http"
        return []

    monkeypatch.setattr(sdk_server, "setup_browser_state", fake_setup_browser_state)

    assert get_current_identity() is None
    _ = asyncio.run(setup_browser_state.fn(ctx=Context(mcp)))
    assert get_current_identity() is None
