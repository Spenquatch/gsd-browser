from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from gsd_browser.fastmcp_v2_http import build_http_app
from gsd_browser.http_oauth_metadata import resource_metadata_path_for_base_path


def _configure_required_http_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GSD_TRANSPORT", "http")
    monkeypatch.setenv("FASTMCP_DOCKET_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GSD_JWT_JWKS_URL", "https://example.com/jwks.json")
    monkeypatch.setenv("GSD_JWT_ISSUER", "https://issuer.example.com")
    monkeypatch.setenv("GSD_JWT_AUDIENCE", "gsd")


def test_resource_metadata_path_for_base_path() -> None:
    assert (
        resource_metadata_path_for_base_path("/")
        == "/.well-known/oauth-protected-resource"
    )
    assert (
        resource_metadata_path_for_base_path("/mcp/gsd")
        == "/mcp/gsd/.well-known/oauth-protected-resource"
    )
    assert (
        resource_metadata_path_for_base_path("/mcp/gsd/")
        == "/mcp/gsd/.well-known/oauth-protected-resource"
    )


def test_oauth_protected_resource_metadata_endpoint_responds_at_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_required_http_env(monkeypatch)

    app = build_http_app()
    with TestClient(app) as client:
        resp = client.get("/.well-known/oauth-protected-resource")

    assert resp.status_code == 200
    assert resp.json() == {
        "resource": "gsd",
        "authorization_servers": ["https://issuer.example.com"],
        "scopes_supported": ["gsd:browser:execute", "gsd:browser:read", "gsd:admin"],
        "bearer_methods_supported": ["header"],
    }


def test_oauth_protected_resource_metadata_endpoint_responds_under_env_base_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_required_http_env(monkeypatch)
    monkeypatch.setenv("GSD_HTTP_BASE_PATH", "/mcp/gsd")

    app = build_http_app()
    with TestClient(app) as client:
        resp = client.get("/mcp/gsd/.well-known/oauth-protected-resource")

    assert resp.status_code == 200


def test_oauth_protected_resource_metadata_endpoint_responds_under_header_base_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_required_http_env(monkeypatch)
    monkeypatch.delenv("GSD_HTTP_BASE_PATH", raising=False)

    app = build_http_app()
    with TestClient(app) as client:
        resp = client.get(
            "/mcp/gsd/.well-known/oauth-protected-resource",
            headers={"X-Forwarded-Prefix": "/mcp/gsd"},
        )

    assert resp.status_code == 200

