#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import socketio

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
) -> dict[str, Any]:
    sio = socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)

    server_latency_ms: list[float] = []
    client_delta_ms: list[float] = []
    started = time.time()

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
        while time.time() - started < duration_seconds:
            await asyncio.sleep(0.1)
    finally:
        if sio.connected:
            await sio.disconnect()

    return {
        "base_url": base_url,
        "duration_seconds": duration_seconds,
        "mode": mode,
        "summary": summarize_latency(
            server_latency_ms=server_latency_ms, client_delta_ms=client_delta_ms
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure streaming latency from /stream frames.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5009)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--mode", choices=["cdp", "screenshot"], default="cdp")
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
