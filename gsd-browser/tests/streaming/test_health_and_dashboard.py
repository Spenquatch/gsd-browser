from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd_browser.config import Settings
from gsd_browser.streaming.server import create_streaming_app


def _make_client(monkeypatch: pytest.MonkeyPatch, *, auth_mode: str) -> tuple[TestClient, object]:
    monkeypatch.setenv("GSD_STREAMING_AUTH_MODE", auth_mode)
    runtime = create_streaming_app(settings=Settings(), screenshots=None)
    return TestClient(runtime.api_app), runtime


def test_healthz_sessions_requires_active_session(monkeypatch: pytest.MonkeyPatch) -> None:
    client, runtime = _make_client(monkeypatch, auth_mode="hmac")
    session_id = "sess_123"

    missing = client.get(f"/healthz/sessions/{session_id}")
    assert missing.status_code == 404

    runtime.registry.create_session(
        session_id=session_id,
        owner_tenant_id="tenant_a",
        owner_subject_id="subject_a",
        worker_id="worker_a",
        stream_url="http://localhost:5009",
    )

    active = client.get(f"/healthz/sessions/{session_id}")
    assert active.status_code == 200
    payload = active.json()
    assert payload["ok"] is True
    assert payload["session_id"] == session_id

    runtime.registry.terminate_session(session_id)
    terminated = client.get(f"/healthz/sessions/{session_id}")
    assert terminated.status_code == 404


def test_auth_nonce_disabled_in_jwt_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _runtime = _make_client(monkeypatch, auth_mode="jwt")
    resp = client.get("/auth/nonce")
    assert resp.status_code == 404


def test_dashboard_path_requires_token_in_jwt_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _runtime = _make_client(monkeypatch, auth_mode="jwt")
    resp = client.get("/dashboard")
    assert resp.status_code == 401


def test_dashboard_path_serves_html_in_hmac_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _runtime = _make_client(monkeypatch, auth_mode="hmac")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "GSD Browser Dashboard" in resp.text

