from __future__ import annotations

import asyncio

from gsd_browser.fastmcp_v2_stdio import mcp as v2_mcp


def test_fastmcp_v2_stdio_registers_expected_tools() -> None:
    tools = asyncio.run(v2_mcp.get_tools())
    names = set(tools.keys())

    expected = {
        "web_eval_agent",
        "web_task_agent",
        "web_task_agent_github",
        "get_run_events",
        "setup_browser_state",
        "get_screenshots",
    }
    assert expected.issubset(names)
