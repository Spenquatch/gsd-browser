from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from gsd_browser.mcp_tool_policy import (
    compute_tool_exposure_policy,
    normalize_tool_name,
    parse_tool_selector,
)


def test_parse_tool_selector_modes() -> None:
    assert parse_tool_selector(None) == (None, set())
    assert parse_tool_selector("") == (None, set())
    assert parse_tool_selector("all") == ("all", set())
    assert parse_tool_selector("*") == ("all", set())
    assert parse_tool_selector("none") == ("none", set())


def test_parse_tool_selector_list() -> None:
    mode, names = parse_tool_selector("web_eval_agent, get_run_events")
    assert mode is None
    assert names == {"web_eval_agent", "get_run_events"}


def test_normalize_tool_name() -> None:
    assert normalize_tool_name(" web-eval-agent ") == "web_eval_agent"


def test_compute_policy_baseline_all() -> None:
    known = {"a", "b", "c"}
    policy = compute_tool_exposure_policy(known_tools=known, enabled_raw="", disabled_raw="b")
    assert policy.advertised_tools == {"a", "c"}


def test_compute_policy_allowlist_then_denylist() -> None:
    known = {"a", "b", "c"}
    policy = compute_tool_exposure_policy(known_tools=known, enabled_raw="a,b", disabled_raw="b")
    assert policy.advertised_tools == {"a"}


def test_apply_policy_removes_tools() -> None:
    mcp = FastMCP("test")

    @mcp.tool(name="a")
    def tool_a() -> str:
        return "a"

    @mcp.tool(name="b")
    def tool_b() -> str:
        return "b"

    @mcp.tool(name="c")
    def tool_c() -> str:
        return "c"

    from gsd_browser.mcp_tool_policy import apply_tool_exposure_policy

    policy = compute_tool_exposure_policy(
        known_tools={"a", "b", "c"},
        enabled_raw="a,b",
        disabled_raw="b",
    )
    apply_tool_exposure_policy(mcp=mcp, policy=policy)

    tools = asyncio.run(mcp.list_tools())
    assert sorted([t.name for t in tools]) == ["a"]

