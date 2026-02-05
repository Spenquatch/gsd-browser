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

import pytest
import redis
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
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
        "gsd_browser.testsupport.compat_jobs_restart_asgi:app",
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


def _extract_json(result: object) -> object:
    content = getattr(result, "content", None)
    if content is None:
        content = result

    items = list(content or [])
    assert items, "Expected at least one tool content item"

    first = items[0]
    if isinstance(first, TextContent):
        text_payload = first.text
    elif isinstance(first, dict):
        text_payload = str(first.get("text") or "")
    else:
        text_payload = str(getattr(first, "text", "") or "")

    return json.loads(text_payload)


@pytest.mark.integration
def test_compat_jobs_restart_e2e() -> None:
    docket_url = "redis://localhost:6379/0"
    if not _redis_ready(docket_url):
        pytest.skip(
            "Redis/Valkey not available at redis://localhost:6379/0. "
            "Start with `docker compose -f docker/compose.redistest.yml up -d`."
        )

    docket_name = f"gsd-e2e-compat-jobs-restart-{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(_repo_root() / "src")
    env["FASTMCP_DOCKET_URL"] = docket_url
    env["GSD_TEST_DOCKET_NAME"] = docket_name
    env["GSD_TEST_REDELIVERY_TIMEOUT_MS"] = "250"
    env["GSD_TEST_TASK_WORK_S"] = "1.5"

    port = _free_port()
    proc = _start_uvicorn(port=port, env=env)
    try:
        _wait_for_port(port, timeout_s=15.0)
        _assert_running(proc, label="uvicorn(1)")
        url = f"http://127.0.0.1:{port}/mcp"

        async def submit_job_and_return_id() -> str:
            transport = StreamableHttpTransport(
                url,
                headers={
                    "mcp-session-id": session_id,
                    "x-gsd-test-tenant": "tA",
                    "x-gsd-test-subject": "sA",
                },
            )
            async with Client(transport) as client:
                submit = await client.call_tool_mcp(
                    "web_eval_agent_submit",
                    {"url": "http://example.test", "task": "x"},
                )
                assert submit.isError is False
                payload = _extract_json(submit)
                assert isinstance(payload, dict)
                assert payload.get("version") == "gsd.job_submit.v1"
                assert payload.get("error") is None
                job_id = str(payload.get("job_id") or "").strip()
                assert job_id
                return job_id

        job_id = asyncio.run(submit_job_and_return_id())
        assert job_id

        _stop_process(proc, timeout_s=10.0)

        port2 = _free_port()
        proc2 = _start_uvicorn(port=port2, env=env)
        try:
            _wait_for_port(port2, timeout_s=15.0)
            _assert_running(proc2, label="uvicorn(2)")
            url2 = f"http://127.0.0.1:{port2}/mcp"

            async def verify_job_get_and_job_result() -> None:
                transport_a = StreamableHttpTransport(
                    url2,
                    headers={
                        "mcp-session-id": session_id,
                        "x-gsd-test-tenant": "tA",
                        "x-gsd-test-subject": "sA",
                    },
                )
                async with Client(transport_a) as client_a:
                    get_result = await client_a.call_tool_mcp("job_get", {"job_id": job_id})
                    assert get_result.isError is False
                    get_payload = _extract_json(get_result)
                    assert isinstance(get_payload, dict)
                    assert get_payload.get("version") == "gsd.job_get.v1"
                    assert get_payload.get("found") is True
                    assert str(get_payload.get("job_id") or "").strip() == job_id

                    deadline = time.time() + 15.0
                    while time.time() < deadline:
                        result = await client_a.call_tool_mcp(
                            "job_result", {"job_id": job_id}
                        )
                        assert result.isError is False
                        payload = _extract_json(result)
                        assert isinstance(payload, dict)
                        if payload.get("version") != "gsd.job_result.not_ready.v1":
                            assert payload.get("version") == "gsd.web_eval_agent.v1"
                            return
                        await asyncio.sleep(0.05)

                    raise AssertionError("Timed out waiting for job_result to become ready")

                transport_b = StreamableHttpTransport(
                    url2,
                    headers={
                        "mcp-session-id": session_id,
                        "x-gsd-test-tenant": "tB",
                        "x-gsd-test-subject": "sB",
                    },
                )
                async with Client(transport_b) as client_b:
                    get_other = await client_b.call_tool_mcp("job_get", {"job_id": job_id})
                    assert get_other.isError is False
                    get_other_payload = _extract_json(get_other)
                    assert isinstance(get_other_payload, dict)
                    assert get_other_payload.get("version") == "gsd.job_get.v1"
                    assert get_other_payload.get("found") is False

                    result_other = await client_b.call_tool_mcp(
                        "job_result", {"job_id": job_id}
                    )
                    assert result_other.isError is False
                    result_other_payload = _extract_json(result_other)
                    assert isinstance(result_other_payload, dict)
                    assert result_other_payload.get("version") == "gsd.job_result.not_ready.v1"
                    assert result_other_payload.get("found") is False

            asyncio.run(verify_job_get_and_job_result())
        finally:
            _stop_process(proc2, timeout_s=10.0)
    finally:
        if proc.poll() is None:
            _stop_process(proc, timeout_s=10.0)

