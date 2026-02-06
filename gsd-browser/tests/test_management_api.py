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
    monkeypatch.delenv("GSD_PRESIGNED_URL_TTL_S", raising=False)


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

    assert resp.status_code == 405


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "localhost", "Origin": "http://localhost"},
        {"Host": "localhost", "Origin": "http://localhost", "Authorization": "Bearer not-a-jwt"},
    ],
)
def test_management_metrics_requires_auth(
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_management_env(monkeypatch)

    app = build_management_app()
    with TestClient(app) as client:
        resp = client.get("/metrics", headers=headers)

    assert resp.status_code == 401


def test_management_metrics_requires_jwt_admin_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_management_env(monkeypatch)
    _configure_memory_docket(monkeypatch, label="management-metrics-jwt-admin")

    from gsd_browser.management_api import app as mgmt_app

    class _Token:
        def __init__(self, claims: dict[str, object]) -> None:
            self.claims = claims

    class _Verifier:
        async def verify_token(self, _: str) -> _Token:  # noqa: ANN001
            return _Token(
                {
                    "tenant_id": "tenant-a",
                    "sub": "subject-a",
                    "scope": "gsd:admin",
                    "aud": "gsd",
                    "iss": "https://issuer.example",
                }
            )

    monkeypatch.setattr(mgmt_app, "_optional_jwt_verifier", lambda: _Verifier())

    app = build_management_app()
    headers = {"Host": "localhost", "Origin": "http://localhost", "Authorization": "Bearer ok"}
    with TestClient(app) as client:
        resp = client.get("/metrics", headers=headers)

    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/plain")
    body = resp.text
    assert "gsd_docket_stream_len" in body
    assert "gsd_docket_queue_len" in body


def test_management_metrics_rejects_api_keys_even_with_admin_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    _clear_management_env(monkeypatch)
    _configure_memory_docket(monkeypatch, label="management-metrics-api-key-forbidden")

    api_keys_file = _write_api_keys_file(
        tmp_path_factory,
        [
            {
                "key": "key-admin",
                "tenant_id": "tenant-a",
                "subject_id": "subject-a",
                "scopes": ["gsd:admin"],
            }
        ],
    )
    monkeypatch.setenv("GSD_API_KEYS_FILE", api_keys_file)

    app = build_management_app()
    headers = {"Host": "localhost", "Origin": "http://localhost", "X-API-Key": "key-admin"}
    with TestClient(app) as client:
        resp = client.get("/metrics", headers=headers)

    assert resp.status_code == 403


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


def test_management_tasks_list_is_identity_scoped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    _clear_management_env(monkeypatch)
    _configure_memory_docket(monkeypatch, label="management-tasks-list-identity")

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
    headers = {"Host": "localhost", "Origin": "http://localhost", "X-API-Key": "key-a"}
    with TestClient(app) as client:
        from gsd_browser.optionb import task_ownership
        from gsd_browser.optionb.identity import Identity

        docket = client.app.state.docket
        store = task_ownership.TaskOwnershipStore(docket_getter=lambda: docket)

        base_ms = 2_000_000_000_000
        identity_a = Identity(tenant_id="tenant-a", subject_id="subject-a", transport="http")
        identity_b = Identity(tenant_id="tenant-b", subject_id="subject-b", transport="http")

        async def seed() -> None:
            await store.write(
                task_ownership.build_record(
                    task_id="task-a",
                    tool_name="web_eval_agent",
                    identity=identity_a,
                    session_id="sess-a",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 1000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id="task-b",
                    tool_name="web_task_agent",
                    identity=identity_b,
                    session_id="sess-b",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 2000,
                )
            )

        assert client.portal is not None
        client.portal.call(seed)
        resp = client.get("/api/v1/tasks", headers=headers)

    assert resp.status_code == 200
    payload = resp.json()
    assert [task["task_id"] for task in payload["tasks"]] == ["task-a"]
    assert payload["next_cursor"] is None


def test_management_sessions_list_is_identity_scoped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    _clear_management_env(monkeypatch)
    _configure_memory_docket(monkeypatch, label="management-sessions-list-identity")

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
    headers = {"Host": "localhost", "Origin": "http://localhost", "X-API-Key": "key-a"}
    with TestClient(app) as client:
        from gsd_browser.optionb import task_ownership
        from gsd_browser.optionb.identity import Identity

        docket = client.app.state.docket
        store = task_ownership.TaskOwnershipStore(docket_getter=lambda: docket)

        base_ms = 2_000_000_000_000
        identity_a = Identity(tenant_id="tenant-a", subject_id="subject-a", transport="http")
        identity_b = Identity(tenant_id="tenant-b", subject_id="subject-b", transport="http")

        async def seed() -> None:
            await store.write(
                task_ownership.build_record(
                    task_id="task-a",
                    tool_name="web_eval_agent",
                    identity=identity_a,
                    session_id="sess-a",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 1000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id="task-b",
                    tool_name="web_task_agent",
                    identity=identity_b,
                    session_id="sess-b",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 2000,
                )
            )

        assert client.portal is not None
        client.portal.call(seed)
        resp = client.get("/api/v1/sessions", headers=headers)

    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload, list)
    assert [session["session_id"] for session in payload] == ["sess-a"]
    session = payload[0]
    assert session["tenant_id"] == "tenant-a"
    assert session["subject_id"] == "subject-a"
    assert session["status"] == "create"
    assert session["created_at"] == int((base_ms + 1000) / 1000)
    assert session["last_activity_at"] >= session["created_at"]


def test_management_admin_tasks_list_requires_admin_mode_and_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    _clear_management_env(monkeypatch)
    _configure_memory_docket(monkeypatch, label="management-admin-tasks-gating")

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
    headers_user = {
        "Host": "localhost",
        "Origin": "http://localhost",
        "X-API-Key": "key-user",
    }

    with TestClient(app) as client:
        resp_disabled = client.get("/api/v1/admin/tasks", headers=headers_admin)
        resp_no_scope = client.get("/api/v1/admin/tasks", headers=headers_user)

    assert resp_disabled.status_code == 403
    assert resp_no_scope.status_code == 403

    monkeypatch.setenv("GSD_ADMIN_MODE", "1")
    with TestClient(app) as client:
        resp_enabled = client.get("/api/v1/admin/tasks", headers=headers_admin)

    assert resp_enabled.status_code == 200


def test_management_tasks_list_invalid_cursor_returns_pinned_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    _clear_management_env(monkeypatch)
    _configure_memory_docket(monkeypatch, label="management-tasks-invalid-cursor")

    api_keys_file = _write_api_keys_file(
        tmp_path_factory,
        [
            {
                "key": "key-a",
                "tenant_id": "tenant-a",
                "subject_id": "subject-a",
                "scopes": ["gsd:browser:read"],
            }
        ],
    )
    monkeypatch.setenv("GSD_API_KEYS_FILE", api_keys_file)

    app = build_management_app()
    headers = {"Host": "localhost", "Origin": "http://localhost", "X-API-Key": "key-a"}
    with TestClient(app) as client:
        from gsd_browser.optionb import task_ownership
        from gsd_browser.optionb.identity import Identity

        docket = client.app.state.docket
        store = task_ownership.TaskOwnershipStore(docket_getter=lambda: docket)
        identity = Identity(tenant_id="tenant-a", subject_id="subject-a", transport="http")
        base_ms = 2_000_000_000_000

        async def seed() -> None:
            await store.write(
                task_ownership.build_record(
                    task_id="task-2",
                    tool_name="web_eval_agent",
                    identity=identity,
                    session_id="sess",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 2000,
                )
            )
            await store.write(
                task_ownership.build_record(
                    task_id="task-1",
                    tool_name="web_task_agent",
                    identity=identity,
                    session_id="sess",
                    ttl_ms=60_000,
                    created_at_ms=base_ms + 1000,
                )
            )

        assert client.portal is not None
        client.portal.call(seed)
        first = client.get("/api/v1/tasks?limit=1", headers=headers)
        cursor = first.json()["next_cursor"]
        assert cursor

        resp = client.get(
            f"/api/v1/tasks?limit=1&cursor={cursor}&tool_name=web_eval_agent",
            headers=headers,
        )

    assert resp.status_code == 400
    assert resp.json() == {
        "error": {
            "code": "invalid_cursor",
            "message": "Cursor does not match query",
            "details": {"hint": "Do not reuse cursors across filters."},
        }
    }


def test_management_screenshots_presign_ttl_respects_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    import time
    import uuid

    _clear_management_env(monkeypatch)
    _configure_memory_docket(monkeypatch, label="management-screenshots-ttl")

    api_keys_file = _write_api_keys_file(
        tmp_path_factory,
        [
            {
                "key": "key-a",
                "tenant_id": "tenant-a",
                "subject_id": "subject-a",
                "scopes": ["gsd:browser:read"],
            }
        ],
    )
    monkeypatch.setenv("GSD_API_KEYS_FILE", api_keys_file)
    monkeypatch.setenv("GSD_PRESIGNED_URL_TTL_S", "999999")

    from gsd_browser.optionb import s3_client as s3_client_mod

    captured_ttls: list[int] = []

    class _FakeS3:
        def presign_get(self, *, key: str, ttl_s: int) -> tuple[str, float]:
            captured_ttls.append(int(ttl_s))
            return f"https://example.test/{key}?ttl={int(ttl_s)}", float(time.time() + int(ttl_s))

    monkeypatch.setattr(s3_client_mod, "has_complete_s3_config", lambda: True)
    monkeypatch.setattr(s3_client_mod, "get_s3_client", lambda: _FakeS3())

    app = build_management_app()
    headers = {"Host": "localhost", "Origin": "http://localhost", "X-API-Key": "key-a"}
    with TestClient(app) as client:
        from gsd_browser.optionb.artifact_index import (
            ArtifactIndexStore,
            ArtifactWriter,
            build_record,
        )
        from gsd_browser.optionb.identity import Identity

        docket = client.app.state.docket

        session_id = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        created_at_ms = int(time.time() * 1000)

        store = ArtifactIndexStore(docket_getter=lambda: docket)
        writer = ArtifactWriter(index=store)

        record = build_record(
            artifact_id=artifact_id,
            artifact_kind="screenshot",
            identity=Identity(tenant_id="tenant-a", subject_id="subject-a", transport="http"),
            session_id=session_id,
            created_at_ms=created_at_ms,
            content_type="image/png",
            size_bytes=5,
            s3_bucket="bucket",
            s3_key=f"tenants/t/subjects/s/sessions/{session_id}/screenshots/{artifact_id}.png",
            screenshot_type="agent_step",
            page_url="https://page.example",
            artifact_backend="s3",
        )

        async def seed() -> None:
            await writer.write(record, upload=lambda: None)

        assert client.portal is not None
        client.portal.call(seed)
        resp = client.get(
            f"/api/v1/sessions/{session_id}/screenshots?last_n=1",
            headers=headers,
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["session_id"] == session_id
    assert payload["screenshots"]
    assert captured_ttls, "expected presign_get to be called"
    assert captured_ttls[-1] == 3600
    assert "ttl=3600" in str(payload["screenshots"][0]["url"] or "")
