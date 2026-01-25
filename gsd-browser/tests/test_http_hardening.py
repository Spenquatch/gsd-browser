from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from gsd_browser.fastmcp_v2_http import build_http_app


def _configure_required_http_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GSD_TRANSPORT", "http")
    monkeypatch.setenv("FASTMCP_DOCKET_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GSD_JWT_JWKS_URL", "https://example.com/jwks.json")
    monkeypatch.setenv("GSD_JWT_ISSUER", "https://issuer.example.com")
    monkeypatch.setenv("GSD_JWT_AUDIENCE", "gsd")


@pytest.mark.parametrize(
    ("headers", "expected_origin"),
    [
        ({"Host": "localhost"}, ""),
        ({"Host": "localhost", "Origin": "https://evil.example"}, "https://evil.example"),
    ],
)
def test_mcp_origin_hardening_rejects_missing_or_disallowed_origin(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    expected_origin: str,
) -> None:
    _configure_required_http_env(monkeypatch)

    app = build_http_app()
    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert resp.status_code == 403
    assert resp.json() == {"error": "origin_not_allowed", "origin": expected_origin}


def test_well_known_metadata_is_exempt_from_origin_and_host_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_required_http_env(monkeypatch)

    app = build_http_app()
    with TestClient(app) as client:
        resp = client.get("/.well-known/oauth-protected-resource")

    assert resp.status_code == 200


def test_null_origin_is_allowed_only_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_required_http_env(monkeypatch)

    app = build_http_app()
    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            headers={"Host": "localhost", "Origin": "null"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert resp.status_code == 403
    assert resp.json() == {"error": "origin_not_allowed", "origin": "null"}

    monkeypatch.setenv("GSD_HTTP_ALLOW_NULL_ORIGIN", "true")
    app = build_http_app()
    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            headers={"Host": "localhost", "Origin": "null"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == (
        'Bearer resource_metadata="/.well-known/oauth-protected-resource"'
    )

