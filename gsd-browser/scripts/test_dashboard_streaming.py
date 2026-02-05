#!/usr/bin/env python3
"""Test dashboard streaming with a minimal browser task."""

from __future__ import annotations

import asyncio
import json
import time
import urllib.request

from gsd_browser.config import load_settings
from gsd_browser.runtime import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, get_runtime


async def check_healthz(host: str, port: int) -> dict:
    """Check dashboard health endpoint."""
    url = f"http://{host}:{port}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


async def run_minimal_task() -> None:
    """Run a minimal web task to test streaming."""
    print("=" * 60)
    print("Dashboard Streaming Test")
    print("=" * 60)

    # Step 1: Start dashboard
    print("\n[1/5] Starting dashboard...")
    settings = load_settings(strict=False)
    runtime = get_runtime()
    dashboard = runtime.ensure_dashboard_running(
        settings=settings, host=DEFAULT_DASHBOARD_HOST, port=DEFAULT_DASHBOARD_PORT
    )
    print(f"✓ Dashboard running at http://{dashboard.host}:{dashboard.port}/")

    # Step 2: Check initial state
    print("\n[2/5] Checking initial state...")
    health = await check_healthz(dashboard.host, dashboard.port)
    print(f"  streaming_mode: {health.get('streaming_mode')}")
    print(f"  cdp_available: {health.get('cdp_available')}")
    print(f"  frames_received: {health.get('frames_received')}")

    # Step 3: Run minimal browser task
    print("\n[3/5] Running minimal browser task...")
    print("  Task: Visit example.com and read the heading")
    print("  (This should take ~10-20 seconds)")

    # Import here to ensure dashboard is already running
    from gsd_browser.mcp_server import web_eval_agent

    class FakeContext:
        """Minimal context for tool call."""

    start_time = time.time()
    try:
        await web_eval_agent(
            url="https://example.com",
            task="Read the main heading on the page and confirm you can see it.",
            ctx=FakeContext(),
            headless_browser=True,  # Run headless to avoid popup
            budget_s=30.0,  # Short timeout
            max_steps=3,  # Minimal steps
        )
        elapsed = time.time() - start_time
        print(f"✓ Task completed in {elapsed:.1f}s")
    except Exception as e:  # noqa: BLE001
        elapsed = time.time() - start_time
        print(f"✗ Task failed after {elapsed:.1f}s: {e}")

    # Step 4: Check streaming state during/after task
    print("\n[4/5] Checking streaming state after task...")
    await asyncio.sleep(1)  # Let frames settle
    health = await check_healthz(dashboard.host, dashboard.port)

    print(f"  streaming_mode: {health.get('streaming_mode')}")
    print(f"  cdp_available: {health.get('cdp_available')}")
    print(f"  active_run_session_id: {health.get('active_run_session_id')}")
    print(f"  active_cdp_session_id: {health.get('active_cdp_session_id')}")
    print(f"  frames_received: {health.get('frames_received')}")
    print(f"  frames_emitted: {health.get('frames_emitted')}")
    print(f"  frames_dropped: {health.get('frames_dropped')}")
    totals = health.get("sampler_totals", {}) or {}
    print(
        f"  sampler (seen/stored): {totals.get('seen')}/{totals.get('stored')}"
    )

    # Step 5: Diagnose issues
    print("\n[5/5] Diagnosis:")
    frames_received = health.get("frames_received", 0)
    frames_emitted = health.get("frames_emitted", 0)
    cdp_available = health.get("cdp_available", False)

    if frames_received > 0 and frames_emitted > 0:
        print("  ✓ CDP streaming is WORKING!")
        print(f"    - Received {frames_received} frames")
        print(f"    - Emitted {frames_emitted} frames")
        print("    - Dashboard should show live browser view")
    elif cdp_available and frames_received == 0:
        print("  ⚠ CDP attached but no frames received")
        print("    - CDP session connected but not streaming")
        print("    - Check if Page.startScreencast was called")
    elif not cdp_available:
        print("  ✗ CDP NOT available")
        error = health.get("last_cdp_error")
        if error:
            print(f"    - Last error: {error}")
        print("    - CDP attachment failed or not attempted")
        print("    - Check browser-use integration")
    else:
        print("  ✗ Frames received but not emitted")
        print("    - Issue with Socket.IO emission")

    print("\n" + "=" * 60)
    print(f"Open http://{dashboard.host}:{dashboard.port}/ in your browser")
    print("Click 'Connect' to view the stream")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_minimal_task())
