#!/usr/bin/env python3
"""Smoke test for FastMCP v2 with SEP-1686 tasks.

Usage:
    # First, start Redis/Valkey:
    docker compose -f docker/compose.redistest.yml up -d

    # Then run this script:
    cd gsd-browser
    source .venv/bin/activate
    python scripts/smoke-fastmcp-tasks.py

    # Cleanup:
    docker compose -f docker/compose.redistest.yml down -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

# Ensure we're using the local source
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Configure environment before imports
os.environ.setdefault("FASTMCP_DOCKET_URL", "redis://localhost:6379/0")
os.environ.setdefault("GSD_USE_FASTMCP_V2", "true")


def main() -> int:
    """Run the smoke test."""
    import fastmcp
    from fastmcp import Client

    # Configure Docket for Redis
    fastmcp.settings.docket.url = os.environ["FASTMCP_DOCKET_URL"]
    fastmcp.settings.docket.name = "gsd-smoke"

    # Import after environment is configured
    from gsd_browser.fastmcp_v2_stdio import mcp

    print("=" * 60)
    print("FastMCP v2 Tasks Smoke Test")
    print("=" * 60)
    print(f"Docket URL: {fastmcp.settings.docket.url}")
    print(f"Server: {mcp.name}")
    print(f"Tools: {list(mcp._tool_manager._tools.keys())}")
    print()

    async def run_smoke_test() -> bool:
        async with Client(mcp) as client:
            print("[1/4] Listing tools...")
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            print(f"      Found {len(tool_names)} tools: {tool_names}")

            if "web_eval_agent" not in tool_names:
                print("      ERROR: web_eval_agent not found!")
                return False

            print()
            print("[2/4] Calling web_eval_agent with task=True...")
            print("      (This will return immediately with a task_id)")

            try:
                task = await client.call_tool(
                    "web_eval_agent",
                    {
                        "url": "https://example.com",
                        "task": "Just load the page and report the title",
                        "headless_browser": True,
                        "budget_s": 60,
                        "max_steps": 5,
                    },
                    task=True,
                    ttl=120_000,  # 2 minute TTL
                )
                print(f"      Task created: {task.task_id}")
            except Exception as e:
                print(f"      ERROR creating task: {e}")
                return False

            print()
            print("[3/4] Polling task status...")
            deadline = time.time() + 90  # 90 second timeout
            last_status = None
            poll_count = 0

            while time.time() < deadline:
                poll_count += 1
                try:
                    status = await client.get_task_status(task.task_id)
                    status_value = str(getattr(status, "status", "unknown")).lower()

                    if status_value != last_status:
                        progress = getattr(status, "progress", None)
                        progress_str = ""
                        if progress:
                            current = getattr(progress, "current", None)
                            total = getattr(progress, "total", None)
                            if current is not None:
                                progress_str = f" (step {current}"
                                if total:
                                    progress_str += f"/{total}"
                                progress_str += ")"
                        print(f"      [{poll_count}] Status: {status_value}{progress_str}")
                        last_status = status_value

                    if status_value in {"completed", "failed", "cancelled"}:
                        break

                    poll_interval = float(getattr(status, "pollInterval", 2000) or 2000) / 1000
                    await asyncio.sleep(min(poll_interval, 2.0))

                except Exception as e:
                    print(f"      [{poll_count}] Poll error: {e}")
                    await asyncio.sleep(1.0)

            print()
            print("[4/4] Fetching task result...")
            try:
                result = await client.get_task_result(task.task_id)
                is_error = getattr(result, "isError", False)
                content = getattr(result, "content", [])

                if is_error:
                    print(f"      Task failed with error")
                    for item in content:
                        text = getattr(item, "text", str(item))
                        print(f"      Error: {text[:200]}...")
                    return False
                else:
                    print(f"      Task completed successfully!")
                    for item in content:
                        text = getattr(item, "text", str(item))
                        # Parse and show summary
                        if '"summary"' in text:
                            import json
                            try:
                                payload = json.loads(text)
                                print(f"      Summary: {payload.get('summary', 'N/A')}")
                                print(f"      Status: {payload.get('status', 'N/A')}")
                            except json.JSONDecodeError:
                                print(f"      Result: {text[:300]}...")
                        else:
                            print(f"      Result: {text[:300]}...")
                    return True

            except Exception as e:
                print(f"      ERROR fetching result: {e}")
                return False

    print("Starting async test...")
    print()

    try:
        success = asyncio.run(run_smoke_test())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print()
    print("=" * 60)
    if success:
        print("SMOKE TEST PASSED")
        return 0
    else:
        print("SMOKE TEST FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
