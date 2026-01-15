"""Smoke-test helper for gsd MCP tools and dashboard server."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_settings
from .runtime import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, get_runtime

DEFAULT_URL = "https://example.com"
DEFAULT_TASK = "Load the homepage and confirm it renders without obvious errors."
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@dataclass
class ToolResult:
    success: bool
    error: str | None = None
    items_returned: int | None = None
    screenshot_validation: dict[str, Any] | None = None


@dataclass
class DashboardStatus:
    reachable: bool
    latency_seconds: float | None = None
    error: str | None = None


@dataclass
class HealthStatus:
    ok: bool
    payload: dict[str, Any] | None = None
    error: str | None = None


def wait_for_port(host: str, port: int, timeout: float) -> DashboardStatus:
    start = time.time()
    last_error: str | None = None
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                result = sock.connect_ex((host, port))
            except OSError as exc:
                last_error = str(exc)
            else:
                if result == 0:
                    return DashboardStatus(reachable=True, latency_seconds=time.time() - start)
                last_error = f"connect_ex returned {result}"
        time.sleep(0.25)
    return DashboardStatus(reachable=False, latency_seconds=None, error=last_error)


def fetch_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def fetch_text(url: str, timeout: float = 5.0) -> str:
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310
        data = resp.read()
    return data.decode("utf-8", errors="replace")


def _validate_png_base64(image_b64: str) -> bool:
    try:
        raw = base64.b64decode(image_b64, validate=True)
    except Exception:  # noqa: BLE001
        return False
    return raw.startswith(_PNG_MAGIC)


async def invoke_web_eval(
    *,
    url: str,
    task: str,
    host: str,
    port: int,
    headless: bool,
    skip_browser_task: bool,
) -> ToolResult:
    if skip_browser_task:
        runtime = get_runtime()
        settings = load_settings(strict=False)
        runtime.ensure_dashboard_running(settings=settings, host=host, port=port)
        runtime.screenshots.current_session_id = str(uuid.uuid4())
        runtime.screenshots.current_session_start = time.time()
        runtime.screenshots.record_screenshot(
            screenshot_type="agent_step",
            image_bytes=None,
            mime_type=None,
            session_id=runtime.screenshots.current_session_id,
            captured_at=time.time(),
            metadata={"tool_call_id": str(uuid.uuid4()), "note": "skip_browser_task=true"},
            url=url,
            step=1,
        )
        return ToolResult(success=True, items_returned=1)

    from mcp.server.fastmcp import Context

    from .mcp_server import web_eval_agent

    payload = {"url": url, "task": task, "headless_browser": headless}

    ctx = Context()
    try:
        result = await web_eval_agent(ctx=ctx, **payload)
    except Exception as exc:  # pragma: no cover - unexpected failure path
        return ToolResult(success=False, error=f"web_eval_agent raised: {exc}")

    items_returned = len(result) if isinstance(result, list) else None
    runtime = get_runtime()
    screenshots = runtime.screenshots.get_screenshots(
        last_n=10,
        screenshot_type="agent_step",
        session_id=runtime.screenshots.current_session_id,
        include_images=True,
    )
    png_ok = any(
        bool(shot.get("mime_type") == "image/png" and _validate_png_base64(str(shot["image_data"])))
        for shot in screenshots
        if shot.get("image_data")
    )
    validation = {
        "session_id": runtime.screenshots.current_session_id,
        "agent_step_count": len(screenshots),
        "agent_step_png_ok": png_ok,
    }
    return ToolResult(success=True, items_returned=items_returned, screenshot_validation=validation)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test MCP tool + dashboard streaming")
    parser.add_argument("--url", default=DEFAULT_URL, help="Target URL for the web_eval_agent tool")
    parser.add_argument("--task", default=DEFAULT_TASK, help="Task description for the evaluation")
    parser.add_argument(
        "--host", default=DEFAULT_DASHBOARD_HOST, help="Dashboard host (default 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_DASHBOARD_PORT, help="Dashboard port (default 5009)"
    )
    parser.add_argument(
        "--timeout", type=float, default=20.0, help="Seconds to wait for dashboard startup"
    )
    parser.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default)",
    )
    parser.add_argument(
        "--no-headless", dest="headless", action="store_false", help="Disable headless browser mode"
    )
    parser.add_argument(
        "--skip-browser-task",
        action="store_true",
        help="Skip Playwright navigation (for infra-only checks)",
    )
    parser.add_argument(
        "--expect-streaming-mode",
        default="cdp",
        help="Assert that /healthz reports this streaming mode (default: cdp)",
    )
    parser.add_argument("--output", type=Path, help="Optional path to write JSON report")
    parser.add_argument("--verbose", action="store_true", help="Print verbose diagnostics")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    tool_result = asyncio.run(
        invoke_web_eval(
            url=args.url,
            task=args.task,
            host=args.host,
            port=args.port,
            headless=args.headless,
            skip_browser_task=args.skip_browser_task,
        )
    )

    dashboard_status = wait_for_port(args.host, args.port, args.timeout)

    dashboard_html_ok = False
    dashboard_html_error: str | None = None
    if dashboard_status.reachable:
        try:
            html = fetch_text(f"http://{args.host}:{args.port}/", timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            dashboard_html_error = str(exc)
        else:
            dashboard_html_ok = "GSD Browser Dashboard" in html and (
                "/socket.io/socket.io.js" in html
            )

    health_status = HealthStatus(ok=False)
    if dashboard_status.reachable:
        health_url = f"http://{args.host}:{args.port}/healthz"
        try:
            payload = fetch_json(health_url, timeout=5.0)
        except urllib.error.HTTPError as exc:
            health_status = HealthStatus(ok=False, error=f"HTTP {exc.code}: {exc.reason}")
        except urllib.error.URLError as exc:  # pragma: no cover - network failure
            health_status = HealthStatus(ok=False, error=str(exc.reason))
        else:
            health_status = HealthStatus(ok=True, payload=payload)

    report: dict[str, Any] = {
        "tool": {
            "success": tool_result.success,
            "items_returned": tool_result.items_returned,
            "error": tool_result.error,
            "screenshot_validation": tool_result.screenshot_validation,
        },
        "dashboard": {
            "reachable": dashboard_status.reachable,
            "latency_seconds": dashboard_status.latency_seconds,
            "error": dashboard_status.error,
            "html_ok": dashboard_html_ok,
            "html_error": dashboard_html_error,
        },
        "healthz": {
            "ok": health_status.ok,
            "error": health_status.error,
            "payload": health_status.payload,
        },
    }

    expected_mode: str = args.expect_streaming_mode
    if expected_mode and health_status.payload:
        actual_mode = str((health_status.payload or {}).get("streaming_mode"))
        report["healthz"]["streaming_mode"] = actual_mode
        report["healthz"]["streaming_mode_match"] = actual_mode == expected_mode

    if args.verbose:
        print(json.dumps(report, indent=2))
    else:
        print("Tool success:", report["tool"]["success"])
        print("Dashboard reachable:", report["dashboard"]["reachable"])
        print("Healthz ok:", report["healthz"]["ok"])
        if report["healthz"].get("streaming_mode") is not None:
            match = report["healthz"].get("streaming_mode_match")
            print(
                f"Streaming mode: {report['healthz']['streaming_mode']} "
                f"(expected {expected_mode}) -> match={match}"
            )
        if report["tool"]["error"]:
            print("Tool error:", report["tool"]["error"])
        if report["dashboard"]["error"]:
            print("Dashboard error:", report["dashboard"]["error"])
        if report["healthz"]["error"]:
            print("Healthz error:", report["healthz"]["error"])

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))

    if not tool_result.success or not dashboard_status.reachable or not health_status.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
