#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import socketio

from gsd_browser.config import load_settings
from gsd_browser.runtime import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, get_runtime
from gsd_browser.streaming.telemetry import hmac_sha256_hex, summarize_latency


def _fetch_json(url: str, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_seconds) as resp:  # noqa: S310
        data = resp.read()
    parsed = json.loads(data.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return parsed


def _build_auth(*, base_url: str, api_key: str | None) -> dict[str, Any] | None:
    if not api_key:
        return None
    nonce_payload = _fetch_json(f"{base_url}/auth/nonce")
    nonce = nonce_payload.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        raise RuntimeError("Nonce endpoint returned invalid payload")
    return {"nonce": nonce, "sig": hmac_sha256_hex(api_key=api_key, nonce=nonce)}


async def measure_stream_latency(
    *,
    base_url: str,
    duration_seconds: float,
    mode: str,
    api_key: str | None,
    drive: bool,
    drive_url: str,
    headless: bool,
) -> dict[str, Any]:
    sio = socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)

    server_latency_ms: list[float] = []
    client_delta_ms: list[float] = []
    started = time.time()
    drive_error: str | None = None
    dashboard_runtime = None

    async def drive_stream() -> None:
        nonlocal drive_error
        if dashboard_runtime is None:
            drive_error = "dashboard_runtime not initialized"
            return

        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                if mode == "cdp":
                    await dashboard_runtime.cdp_streamer.start(page=page, session_id="measure")
                await page.goto(drive_url, wait_until="domcontentloaded")
                if mode == "screenshot":
                    end = time.time() + duration_seconds
                    while time.time() < end:
                        image_bytes = await page.screenshot(full_page=True, type="png")
                        await dashboard_runtime.emit_browser_update(
                            session_id="measure",
                            image_bytes=image_bytes,
                            mime_type="image/png",
                            timestamp=time.time(),
                            metadata={"streaming_mode": "screenshot"},
                        )
                        await asyncio.sleep(0.5)
                else:
                    await asyncio.sleep(duration_seconds)
            except Exception as exc:  # noqa: BLE001
                drive_error = str(exc)
            finally:
                if mode == "cdp":
                    await dashboard_runtime.cdp_streamer.stop()
                await context.close()
                await browser.close()

    def record_latency(payload: dict[str, Any]) -> None:
        latency = payload.get("latency_ms")
        emitted_ts = payload.get("emitted_ts")
        if isinstance(latency, (int, float)):
            server_latency_ms.append(float(latency))
        if isinstance(emitted_ts, (int, float)):
            client_delta_ms.append(max(0.0, (time.time() - float(emitted_ts)) * 1000.0))

    @sio.on("frame", namespace="/stream")
    async def on_frame(payload: Any) -> None:
        if mode != "cdp":
            return
        if isinstance(payload, dict):
            record_latency(payload)

    @sio.on("browser_update", namespace="/stream")
    async def on_browser_update(_: Any) -> None:
        return

    if drive:
        parsed = urlparse(base_url)
        host = parsed.hostname or DEFAULT_DASHBOARD_HOST
        port = parsed.port or DEFAULT_DASHBOARD_PORT
        settings = load_settings(env={"STREAMING_MODE": mode}, strict=False)
        runtime = get_runtime()
        dashboard = runtime.ensure_dashboard_running(settings=settings, host=host, port=port)
        dashboard_runtime = dashboard.runtime

    auth = _build_auth(base_url=base_url, api_key=api_key)
    await sio.connect(
        base_url,
        socketio_path="socket.io",
        namespaces=["/stream"],
        auth=auth,
        transports=["websocket"],
        wait_timeout=5,
    )

    try:
        drive_task: asyncio.Task[None] | None = None
        if drive:
            drive_task = asyncio.create_task(drive_stream())

        while time.time() - started < duration_seconds:
            await asyncio.sleep(0.1)
    finally:
        if drive_task is not None:
            if not drive_task.done():
                drive_task.cancel()
            try:
                await drive_task
            except asyncio.CancelledError:
                pass
        if sio.connected:
            await sio.disconnect()

    healthz: dict[str, Any] | None = None
    try:
        healthz = _fetch_json(f"{base_url}/healthz", timeout_seconds=2.0)
    except Exception:  # noqa: BLE001
        healthz = None

    return {
        "base_url": base_url,
        "duration_seconds": duration_seconds,
        "mode": mode,
        "drive": drive,
        "drive_url": drive_url,
        "drive_error": drive_error,
        "healthz": healthz,
        "summary": summarize_latency(
            server_latency_ms=server_latency_ms, client_delta_ms=client_delta_ms
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure streaming latency from /stream frames.")
    parser.add_argument("--host", default=DEFAULT_DASHBOARD_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_DASHBOARD_PORT)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--mode", choices=["cdp", "screenshot"], default="cdp")
    parser.add_argument(
        "--drive",
        dest="drive",
        action="store_true",
        default=True,
        help="Drive a short Playwright run while measuring (default)",
    )
    parser.add_argument(
        "--no-drive",
        dest="drive",
        action="store_false",
        help="Only measure an existing stream (do not launch Playwright)",
    )
    parser.add_argument("--drive-url", default="https://example.com")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--out", default=None, help="Optional JSON output path")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    report = asyncio.run(
        measure_stream_latency(
            base_url=base_url,
            duration_seconds=float(args.duration),
            mode=str(args.mode),
            api_key=str(args.api_key) if args.api_key else None,
            drive=bool(args.drive),
            drive_url=str(args.drive_url),
            headless=bool(args.headless),
        )
    )

    summary = report.get("summary", {})
    p95 = (summary.get("server_latency_ms") or {}).get("p95") if isinstance(summary, dict) else None
    print(json.dumps(report, indent=2, sort_keys=True))
    if p95 is not None:
        print(f"p95 server latency: {p95:.1f} ms")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
