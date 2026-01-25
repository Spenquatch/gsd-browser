from __future__ import annotations

import types

import pytest
from starlette.testclient import TestClient

from gsd_browser.fastmcp_v2_http import build_http_app
from gsd_browser.fastmcp_v2_stdio import mcp as v2_mcp
from gsd_browser.optionb.identity import JwtAudienceMismatch


def _configure_required_http_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GSD_TRANSPORT", "http")
    monkeypatch.setenv("FASTMCP_DOCKET_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GSD_JWT_JWKS_URL", "https://example.com/jwks.json")
    monkeypatch.setenv("GSD_JWT_ISSUER", "https://issuer.example.com")
    monkeypatch.setenv("GSD_JWT_AUDIENCE", "gsd")


def test_http_auth_missing_token_returns_401_with_resource_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_required_http_env(monkeypatch)
    monkeypatch.delenv("GSD_HTTP_BASE_PATH", raising=False)

    app = build_http_app()
    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            headers={"Host": "localhost", "Origin": "http://localhost"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == (
        'Bearer resource_metadata="/.well-known/oauth-protected-resource"'
    )


def test_http_auth_insufficient_scope_execute_tool_returns_403_with_scope_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_required_http_env(monkeypatch)

    app = build_http_app()

    async def _fake_verify_token_with_audience_details(
        token: str,
    ) -> tuple[object | None, JwtAudienceMismatch | None]:
        if token != "token-read-only":
            return None, None
        return (
            types.SimpleNamespace(
                claims={
                    "tenant_id": "tenant",
                    "sub": "subject",
                    "scope": "gsd:browser:read",
                }
            ),
            None,
        )

    monkeypatch.setattr(
        v2_mcp.auth,
        "verify_token_with_audience_details",
        _fake_verify_token_with_audience_details,
    )

    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer token-read-only",
                "Host": "localhost",
                "Origin": "http://localhost",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "web_eval_agent", "arguments": {"url": "x", "task": "y"}},
            },
        )

    assert resp.status_code == 403
    assert resp.headers["www-authenticate"] == (
        'Bearer error="insufficient_scope", scope="gsd:browser:execute gsd:admin"'
    )


def test_http_auth_insufficient_scope_read_tool_returns_403_with_scope_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_required_http_env(monkeypatch)

    app = build_http_app()

    async def _fake_verify_token_with_audience_details(
        token: str,
    ) -> tuple[object | None, JwtAudienceMismatch | None]:
        if token != "token-execute-only":
            return None, None
        return (
            types.SimpleNamespace(
                claims={
                    "tenant_id": "tenant",
                    "sub": "subject",
                    "scope": "gsd:browser:execute",
                }
            ),
            None,
        )

    monkeypatch.setattr(
        v2_mcp.auth,
        "verify_token_with_audience_details",
        _fake_verify_token_with_audience_details,
    )

    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer token-execute-only",
                "Host": "localhost",
                "Origin": "http://localhost",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_screenshots", "arguments": {"session_id": "x"}},
            },
        )

    assert resp.status_code == 403
    assert resp.headers["www-authenticate"] == (
        'Bearer error="insufficient_scope", scope="gsd:browser:read gsd:admin"'
    )


def test_http_auth_wrong_audience_returns_403_with_pinned_invalid_token_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_required_http_env(monkeypatch)

    app = build_http_app()

    async def _fake_verify_token_with_audience_details(
        token: str,
    ) -> tuple[object | None, JwtAudienceMismatch | None]:
        if token != "token-wrong-aud":
            return None, None
        return None, JwtAudienceMismatch(expected_audience="gsd", actual_audience="other")

    monkeypatch.setattr(
        v2_mcp.auth,
        "verify_token_with_audience_details",
        _fake_verify_token_with_audience_details,
    )

    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer token-wrong-aud",
                "Host": "localhost",
                "Origin": "http://localhost",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert resp.status_code == 403
    assert resp.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    assert resp.json() == {
        "error": "invalid_token",
        "error_description": "Token audience does not match protected resource",
        "expected_audience": "gsd",
        "actual_audience": "other",
    }
