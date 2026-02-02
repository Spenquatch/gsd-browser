#!/usr/bin/env python3
"""Interactive dashboard test - keeps browser open so you can view the stream."""

from __future__ import annotations

import asyncio
import webbrowser

from gsd_browser.config import load_settings
from gsd_browser.runtime import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, get_runtime


async def run_interactive_test() -> None:
    """Run an interactive dashboard test with a long-running browser session."""
    print("=" * 70)
    print("Interactive Dashboard Streaming Test")
    print("=" * 70)

    # Start dashboard
    print("\n[1/3] Starting dashboard...")
    settings = load_settings(strict=False)
    runtime = get_runtime()
    dashboard = runtime.ensure_dashboard_running(
        settings=settings, host=DEFAULT_DASHBOARD_HOST, port=DEFAULT_DASHBOARD_PORT
    )
    dashboard_url = f"http://{dashboard.host}:{dashboard.port}/"
    print(f"✓ Dashboard running at {dashboard_url}")

    # Open dashboard in browser
    print("\n[2/3] Opening dashboard in your browser...")
    print("  The dashboard will open automatically in a few seconds.")
    print("  Click 'Connect' when it loads to view the stream.")
    await asyncio.sleep(2)
    try:
        webbrowser.open(dashboard_url)
    except Exception as e:  # noqa: BLE001
        print(f"  (Could not auto-open browser: {e})")
        print(f"  Please manually open: {dashboard_url}")

    # Run longer task
    print("\n[3/3] Running browser task...")
    print("  Task: Browse a few pages (will take ~30-45 seconds)")
    print("  Watch the dashboard to see live CDP frames streaming!")
    print()

    from gsd_browser.mcp_server import web_eval_agent

    class FakeContext:
        """Minimal context for tool call."""

    await asyncio.sleep(3)  # Give time to connect to dashboard

    try:
        await web_eval_agent(
            url="https://apple.com",
            task=(
                "Visit apple.com and find me the price of the cheapest ipad."
            ),
            ctx=FakeContext(),
            headless_browser=False,  # Show browser window
            budget_s=45.0,
            max_steps=8,
        )
    except Exception as e:  # noqa: BLE001
        print(f"\nTask error (expected after timeout): {e}")

    print("\n" + "=" * 70)
    print("Test complete!")
    print(f"Dashboard is still running at {dashboard_url}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_interactive_test())
