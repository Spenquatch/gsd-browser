from __future__ import annotations

import uuid

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


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    import fastmcp

    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _write_api_keys_file(
    tmp_path: pytest.TempPathFactory,
    entries: list[dict[str, object]],
) -> str:
    import json

    path = tmp_path.mktemp("keys") / "api-keys.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return str(path)


def test_management_job_get_is_identity_scoped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    _clear_management_env(monkeypatch)
    _configure_memory_docket(monkeypatch, label="management-job-get-identity")

    api_keys_file = _write_api_keys_file(
        tmp_path_factory,
        [
            {
                "key": "key-a",
                "tenant_id": "tenant-a",
                "subject_id": "subject-a",
                "scopes": ["gsd:browser:read"],
            },
            {
                "key": "key-b",
                "tenant_id": "tenant-b",
                "subject_id": "subject-b",
                "scopes": ["gsd:browser:read"],
            },
        ],
    )
    monkeypatch.setenv("GSD_API_KEYS_FILE", api_keys_file)

    app = build_management_app()
    headers_a = {"Host": "localhost", "Origin": "http://localhost", "X-API-Key": "key-a"}
    headers_b = {"Host": "localhost", "Origin": "http://localhost", "X-API-Key": "key-b"}

    job_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    created_at_ms = 2_000_000_000_000
    expires_at_ms = created_at_ms + 60_000

    with TestClient(app) as client:
        from gsd_browser.optionb.identity import Identity
        from gsd_browser.optionb.job_store import JobRecord, JobStore

        docket = client.app.state.docket
        store = JobStore(docket_getter=lambda: docket)

        identity_a = Identity(tenant_id="tenant-a", subject_id="subject-a", transport="http")

        async def seed() -> None:
            await store.write(
                JobRecord(
                    job_id=job_id,
                    task_id=task_id,
                    tenant_id=identity_a.tenant_id,
                    subject_id=identity_a.subject_id,
                    transport=identity_a.transport,
                    tool_name="web_eval_agent",
                    created_at_ms=created_at_ms,
                    expires_at_ms=expires_at_ms,
                    session_id=session_id,
                )
            )

        assert client.portal is not None
        client.portal.call(seed)

        resp_ok = client.get(f"/api/v1/jobs/{job_id}", headers=headers_a)
        resp_cross = client.get(f"/api/v1/jobs/{job_id}", headers=headers_b)

    assert resp_ok.status_code == 200
    payload = resp_ok.json()
    assert payload["job"]["job_id"] == job_id
    assert payload["job"]["task_id"] == task_id
    assert payload["job"]["tool_name"] == "web_eval_agent"
    assert payload["job"]["state"] == "queued"
    assert isinstance(payload["job"]["progress_message"], str)
    assert payload["job"]["progress"] is None
    assert isinstance(payload["job"]["created_at"], str)
    assert isinstance(payload["job"]["expires_at"], str)
    assert "tenant_id" not in payload["job"]
    assert "subject_id" not in payload["job"]
    assert "transport" not in payload["job"]

    assert resp_cross.status_code == 404
    assert resp_cross.json() == {
        "error": {"code": "not_found", "message": "Not found", "details": {}}
    }


def test_management_admin_job_get_requires_admin_mode_and_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    _clear_management_env(monkeypatch)
    _configure_memory_docket(monkeypatch, label="management-admin-job-get-gating")

    api_keys_file = _write_api_keys_file(
        tmp_path_factory,
        [
            {
                "key": "key-user",
                "tenant_id": "tenant-a",
                "subject_id": "subject-a",
                "scopes": ["gsd:browser:read"],
            },
            {
                "key": "key-admin",
                "tenant_id": "tenant-a",
                "subject_id": "ops",
                "scopes": ["gsd:admin"],
            },
        ],
    )
    monkeypatch.setenv("GSD_API_KEYS_FILE", api_keys_file)
    monkeypatch.delenv("GSD_ADMIN_MODE", raising=False)

    app = build_management_app()
    headers_admin = {
        "Host": "localhost",
        "Origin": "http://localhost",
        "X-API-Key": "key-admin",
    }
    headers_user = {"Host": "localhost", "Origin": "http://localhost", "X-API-Key": "key-user"}

    job_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    created_at_ms = 2_000_000_000_000
    expires_at_ms = created_at_ms + 60_000

    with TestClient(app) as client:
        from gsd_browser.optionb.job_store import JobRecord, JobStore

        docket = client.app.state.docket
        store = JobStore(docket_getter=lambda: docket)

        async def seed() -> None:
            await store.write(
                JobRecord(
                    job_id=job_id,
                    task_id=task_id,
                    tenant_id="tenant-a",
                    subject_id="subject-a",
                    transport="http",
                    tool_name="web_eval_agent",
                    created_at_ms=created_at_ms,
                    expires_at_ms=expires_at_ms,
                    session_id=session_id,
                )
            )

        assert client.portal is not None
        client.portal.call(seed)

        resp_disabled = client.get(f"/api/v1/admin/jobs/{job_id}", headers=headers_admin)
        resp_no_scope = client.get(f"/api/v1/admin/jobs/{job_id}", headers=headers_user)

    assert resp_disabled.status_code == 403
    assert resp_no_scope.status_code == 403

    monkeypatch.setenv("GSD_ADMIN_MODE", "1")
    with TestClient(app) as client:
        resp_enabled = client.get(f"/api/v1/admin/jobs/{job_id}", headers=headers_admin)

    assert resp_enabled.status_code == 200
    payload = resp_enabled.json()
    assert payload["job"]["job_id"] == job_id
    assert payload["job"]["tenant_id"] == "tenant-a"
    assert payload["job"]["subject_id"] == "subject-a"
    assert payload["job"]["transport"] == "http"

