from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from gsd_browser.management_api.app import build_management_app


def _clear_management_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GSD_API_KEYS_FILE", raising=False)
    monkeypatch.delenv("GSD_JWT_JWKS_URL", raising=False)
    monkeypatch.delenv("GSD_JWT_ISSUER", raising=False)
    monkeypatch.delenv("GSD_JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("GSD_HTTP_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("GSD_HTTP_ALLOW_NULL_ORIGIN", raising=False)


def test_management_healthz_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_management_env(monkeypatch)
    app = build_management_app()
    with TestClient(app) as client:
        resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "localhost", "Origin": "http://localhost"},
        {"Host": "localhost", "Origin": "http://localhost", "Authorization": "Bearer not-a-jwt"},
    ],
)
def test_management_api_paths_require_auth(
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_management_env(monkeypatch)

    app = build_management_app()
    with TestClient(app) as client:
        resp = client.get("/api/v1/tasks", headers=headers)

    assert resp.status_code == 401

def test_management_hardening_exempts_options_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_management_env(monkeypatch)

    app = build_management_app()
    with TestClient(app) as client:
        resp = client.options("/api/v1/tasks", headers={"Origin": "https://evil.example"})

    assert resp.status_code == 404
