"""FastMCP v2 (Option B) stdio entrypoint.

This module wires the existing tool implementations into `fastmcp` v2 without changing tool
semantics. Task support, Redis/Docket, and multi-tenant auth are implemented in later tasks.
"""

from __future__ import annotations

import logging

from fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent

from . import mcp_server as sdk_server
from .config import Settings

logger = logging.getLogger("gsd_browser.fastmcp_v2")

mcp = FastMCP("gsd")


def apply_configured_tool_policy(*, settings: Settings) -> None:
    """Apply env/config-driven tool exposure policy before serving MCP."""

    from .mcp_tool_policy import (
        KNOWN_MCP_TOOLS,
        apply_tool_exposure_policy,
        compute_tool_exposure_policy,
    )

    policy = compute_tool_exposure_policy(
        known_tools=set(KNOWN_MCP_TOOLS),
        enabled_raw=getattr(settings, "mcp_enabled_tools", ""),
        disabled_raw=getattr(settings, "mcp_disabled_tools", ""),
    )
    if policy.unknown_requested:
        logger.warning(
            "unknown_mcp_tools_requested",
            extra={"unknown": sorted(policy.unknown_requested)},
        )
    apply_tool_exposure_policy(mcp=mcp, policy=policy)


@mcp.tool(name="web_eval_agent")
async def web_eval_agent(
    url: str,
    task: str,
    ctx: Context,
    headless_browser: bool = False,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
) -> list[TextContent]:
    return await sdk_server.web_eval_agent(
        url=url,
        task=task,
        ctx=ctx,  # type: ignore[arg-type]
        headless_browser=headless_browser,
        mode=mode,
        budget_s=budget_s,
        max_steps=max_steps,
        step_timeout_s=step_timeout_s,
    )


@mcp.tool(name="web_task_agent")
async def web_task_agent(
    url: str,
    task: str,
    ctx: Context,
    headless_browser: bool = False,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
) -> list[TextContent]:
    return await sdk_server.web_task_agent(
        url=url,
        task=task,
        ctx=ctx,  # type: ignore[arg-type]
        headless_browser=headless_browser,
        mode=mode,
        budget_s=budget_s,
        max_steps=max_steps,
        step_timeout_s=step_timeout_s,
    )


@mcp.tool(name="web_task_agent_github")
async def web_task_agent_github(
    url: str,
    task: str,
    ctx: Context,
    headless_browser: bool = False,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
) -> list[TextContent]:
    return await sdk_server.web_task_agent_github(
        url=url,
        task=task,
        ctx=ctx,  # type: ignore[arg-type]
        headless_browser=headless_browser,
        mode=mode,
        budget_s=budget_s,
        max_steps=max_steps,
        step_timeout_s=step_timeout_s,
    )


@mcp.tool(name="get_run_events")
async def get_run_events(
    session_id: str = "",
    last_n: int = 50,
    event_types: list[str] | None = None,
    from_timestamp: object | None = None,
    has_error: bool | None = None,
    include_details: bool = False,
    ctx: Context | None = None,
) -> list[TextContent]:
    return await sdk_server.get_run_events(
        session_id=session_id,
        last_n=last_n,
        event_types=event_types,
        from_timestamp=from_timestamp,
        has_error=has_error,
        include_details=include_details,
        ctx=ctx,  # type: ignore[arg-type]
    )


@mcp.tool(name="setup_browser_state")
async def setup_browser_state(
    url: str | None = None,
    state_id: str | None = None,
    ctx: Context | None = None,
) -> list[TextContent]:
    return await sdk_server.setup_browser_state(url=url, state_id=state_id, ctx=ctx)  # type: ignore[arg-type]


@mcp.tool(name="get_screenshots")
async def get_screenshots(
    last_n: int = 5,
    screenshot_type: str = "agent_step",
    session_id: str = "",
    from_timestamp: float | None = None,
    has_error: bool | None = None,
    include_images: bool = True,
    ctx: Context | None = None,
) -> list[TextContent | ImageContent]:
    return await sdk_server.get_screenshots(
        last_n=last_n,
        screenshot_type=screenshot_type,
        session_id=session_id,
        from_timestamp=from_timestamp,
        has_error=has_error,
        include_images=include_images,
        ctx=ctx,  # type: ignore[arg-type]
    )


def run_stdio() -> None:
    mcp.run(transport="stdio")
