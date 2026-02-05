from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import jsonschema
import pytest
import redis
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp.shared.exceptions import McpError
from mcp.types import TextContent


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _redis_ready(url: str) -> bool:
    client = redis.Redis.from_url(url, decode_responses=True)
    try:
        return bool(client.ping())
    except Exception:  # noqa: BLE001
        return False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _is_endpoint_reachable(host: str, port: int, *, timeout_s: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _wait_for_port(port: int, *, timeout_s: float = 10.0) -> None:
    deadline = time.time() + float(timeout_s)
    while time.time() < deadline:
        if _is_endpoint_reachable("127.0.0.1", port):
            return
        time.sleep(0.05)
    raise AssertionError(f"Server did not become ready on 127.0.0.1:{port} within {timeout_s}s")


def _start_uvicorn(*, port: int, env: dict[str, str]) -> subprocess.Popen[str]:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "gsd_browser.testsupport.restart_resilience_asgi:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(_repo_root()),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _stop_process(proc: subprocess.Popen[str], *, timeout_s: float = 10.0) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout_s)


def _drain_process_output(proc: subprocess.Popen[str]) -> str:
    try:
        out, err = proc.communicate(timeout=1.0)
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join([out or "", err or ""]).strip()


def _assert_running(proc: subprocess.Popen[str], *, label: str) -> None:
    code = proc.poll()
    if code is None:
        return
    output = _drain_process_output(proc)
    message = f"{label} exited early (code={code})"
    if output:
        message = f"{message}:\n{output}"
    raise AssertionError(message)


@pytest.mark.integration
def test_restart_resilience_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    docket_url = "redis://localhost:6379/0"
    if not _redis_ready(docket_url):
        pytest.skip(
            "Redis/Valkey not available at redis://localhost:6379/0. "
            "Start with `docker compose -f docker/compose.redistest.yml up -d`."
        )

    docket_name = f"gsd-e2e-restart-{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(_repo_root() / "src")
    env["FASTMCP_DOCKET_URL"] = docket_url
    env["GSD_TEST_DOCKET_NAME"] = docket_name
    env["GSD_TASK_POLL_INTERVAL_MS"] = "50"
    env["GSD_TEST_REDELIVERY_TIMEOUT_MS"] = "250"
    env["GSD_TEST_TASK_WORK_S"] = "2.0"

    schema_path = _repo_root() / "docs" / "api" / "jsonschema" / "gsd.web_eval_agent.v1.schema.json"
    web_validator = jsonschema.Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8"))
    )

    port = _free_port()
    proc = _start_uvicorn(port=port, env=env)
    try:
        _wait_for_port(port, timeout_s=15.0)
        _assert_running(proc, label="uvicorn(1)")
        url = f"http://127.0.0.1:{port}/mcp"

        async def enqueue_task() -> str:
            transport = StreamableHttpTransport(
                url,
                headers={
                    "mcp-session-id": session_id,
                    "x-gsd-test-tenant": "tA",
                    "x-gsd-test-subject": "sA",
                },
            )
            async with Client(transport) as client:
                task = await client.call_tool(
                    "web_eval_agent",
                    {"url": "http://example.test", "task": "x"},
                    task=True,
                    ttl=60_000,
                )
                return str(task.task_id)

        task_id = asyncio.run(enqueue_task())
        assert task_id

        _stop_process(proc, timeout_s=10.0)

        port2 = _free_port()
        proc2 = _start_uvicorn(port=port2, env=env)
        try:
            _wait_for_port(port2, timeout_s=15.0)
            _assert_running(proc2, label="uvicorn(2)")
            url2 = f"http://127.0.0.1:{port2}/mcp"

            async def fetch_result_and_verify() -> None:
                transport_a = StreamableHttpTransport(
                    url2,
                    headers={
                        "mcp-session-id": session_id,
                        "x-gsd-test-tenant": "tA",
                        "x-gsd-test-subject": "sA",
                    },
                )
                async with Client(transport_a) as client_a:
                    deadline = time.time() + 15.0
                    status_value: str | None = None
                    while time.time() < deadline:
                        status = await client_a.get_task_status(task_id)
                        status_value = str(getattr(status, "status", "")).strip().lower()
                        if status_value in {"completed", "failed", "cancelled"}:
                            break
                        await asyncio.sleep(0.05)
                    assert status_value == "completed"

                    result = await client_a.get_task_result(task_id)
                    if isinstance(result, dict):
                        assert result.get("isError") is False
                        content = list(result.get("content") or [])
                    else:
                        assert getattr(result, "isError", False) is False
                        content = list(getattr(result, "content", None) or [])
                    assert content

                    first = content[0]
                    if isinstance(first, TextContent):
                        text_payload = first.text
                    elif isinstance(first, dict):
                        text_payload = str(first.get("text") or "")
                    else:
                        text_payload = str(getattr(first, "text", "") or "")

                    payload = json.loads(text_payload)
                    web_validator.validate(payload)

                transport_b = StreamableHttpTransport(
                    url2,
                    headers={
                        "mcp-session-id": session_id,
                        "x-gsd-test-tenant": "tB",
                        "x-gsd-test-subject": "sB",
                    },
                )
                async with Client(transport_b) as client_b:
                    with pytest.raises(McpError) as excinfo:
                        _ = await client_b.get_task_status(task_id)
                    assert "not found" in str(excinfo.value).lower()

                    with pytest.raises(McpError) as excinfo:
                        _ = await client_b.get_task_result(task_id)
                    assert "not found" in str(excinfo.value).lower()

                    with pytest.raises(McpError) as excinfo:
                        await client_b.cancel_task(task_id)
                    assert "not found" in str(excinfo.value).lower()

            asyncio.run(fetch_result_and_verify())
        finally:
            _stop_process(proc2, timeout_s=10.0)
    finally:
        if proc.poll() is None:
            _stop_process(proc, timeout_s=10.0)
