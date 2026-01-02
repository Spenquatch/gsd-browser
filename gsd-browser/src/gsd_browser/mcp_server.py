"""FastMCP stdio server exposing browser integration tools."""

from __future__ import annotations

import logging
import os
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent
from playwright.async_api import async_playwright

from .config import load_settings
from .runtime import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, get_runtime

logger = logging.getLogger("gsd_browser.mcp")

mcp = FastMCP("gsd-browser")


def _normalize_url(url: str) -> str:
    if url.startswith(("http://", "https://", "file://", "data:", "chrome:", "javascript:")):
        return url
    return f"https://{url}"


def _browser_state_path() -> Path:
    return Path(os.path.expanduser("~/.operative/browser_state/state.json"))


@mcp.tool(name="web_eval_agent")
async def web_eval_agent(
    url: str, task: str, ctx: Context, headless_browser: bool = False
) -> list[TextContent]:
    """Evaluate the user experience / interface of a web application.

    This tool allows the AI to assess the quality of user experience and interface design
    of a web application by performing specific tasks and analyzing the interaction flow.

    Before this tool is used, the web application should already be running locally on a port.

    Args:
        url: Required. The localhost URL of the web application to evaluate, including the port
            number. Example: http://localhost:3000, http://localhost:8080,
            http://localhost:4200, http://localhost:5173, etc.
            Try to avoid using the path segments of the URL, and instead use the root URL.
        task: Required. The specific UX/UI aspect to test (e.g., "test the checkout flow",
             "evaluate the navigation menu usability", "check form validation feedback")
             Be as detailed as possible in your task description. It could be anywhere from 2
             sentences to 2 paragraphs.
        headless_browser: Optional. Whether to hide the browser window popup during evaluation.
        If headless_browser is True, only the operative control center browser will show, and no
        popup browser will be shown.

    Returns:
        list[TextContent]: A detailed evaluation of the web application's UX/UI, including
        observations, issues found, and recommendations for improvement.
        Note: Screenshots are captured during evaluation and streamed to the dashboard.
        Use the get_screenshots tool to retrieve them if needed.
    """
    _ = ctx
    runtime = get_runtime()
    settings = load_settings(strict=False)
    runtime.ensure_dashboard_running(
        settings=settings, host=DEFAULT_DASHBOARD_HOST, port=DEFAULT_DASHBOARD_PORT
    )

    normalized_url = _normalize_url(url)
    tool_call_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    started = datetime.now(UTC).timestamp()

    runtime.screenshots.current_session_id = session_id
    runtime.screenshots.current_session_start = started

    logger.info(
        "web_eval_agent called",
        extra={
            "tool_call_id": tool_call_id,
            "session_id": session_id,
            "url": normalized_url,
            "headless": headless_browser,
        },
    )

    state_path = _browser_state_path()
    storage_state: str | None = str(state_path) if state_path.exists() else None

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=headless_browser)
            context = await browser.new_context(storage_state=storage_state)
            page = await context.new_page()

            await page.goto(normalized_url, wait_until="domcontentloaded")
            title = await page.title()
            screenshot_bytes = await page.screenshot(full_page=True, type="png")

            runtime.screenshots.record_screenshot(
                screenshot_type="agent_step",
                image_bytes=screenshot_bytes,
                mime_type="image/png",
                session_id=session_id,
                captured_at=datetime.now(UTC).timestamp(),
                metadata={"tool_call_id": tool_call_id, "title": title},
                url=normalized_url,
                step=1,
            )

            await context.close()
            await browser.close()

        return [
            TextContent(
                type="text",
                text=(
                    "Captured an initial page snapshot for UX review.\n"
                    f"- url: {normalized_url}\n"
                    f"- title: {title or '(no title)'}\n"
                    f"- session_id: {session_id}\n"
                    "Use get_screenshots(session_id=..., screenshot_type='agent_step') "
                    "to retrieve screenshots."
                ),
            )
        ]
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        runtime.screenshots.record_screenshot(
            screenshot_type="agent_step",
            image_bytes=None,
            mime_type=None,
            session_id=session_id,
            captured_at=datetime.now(UTC).timestamp(),
            has_error=True,
            metadata={"tool_call_id": tool_call_id, "error": str(exc)},
            url=normalized_url,
            step=1,
        )
        return [
            TextContent(
                type="text",
                text=f"Error executing web_eval_agent: {exc}\n\nTraceback:\n{tb}",
            )
        ]


@mcp.tool(name="setup_browser_state")
async def setup_browser_state(
    url: str | None = None, ctx: Context | None = None
) -> list[TextContent]:
    """Sets up and saves browser state for future use.

    This tool should only be called in one scenario:
    1. The user explicitly requests to set up browser state/authentication

    Launches a non-headless browser for user interaction, allows login/authentication,
    and saves the browser state (cookies, local storage, etc.) to a local file.

    Args:
        url: Optional URL to navigate to upon opening the browser.
        ctx: The MCP context (used for progress reporting, not directly here).

    Returns:
        list[TextContent]: Confirmation of state saving or error messages.
    """
    _ = ctx
    runtime = get_runtime()
    settings = load_settings(strict=False)
    runtime.ensure_dashboard_running(
        settings=settings, host=DEFAULT_DASHBOARD_HOST, port=DEFAULT_DASHBOARD_PORT
    )

    tool_call_id = str(uuid.uuid4())
    normalized_url = _normalize_url(url) if url else None
    state_path = _browser_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "setup_browser_state called",
        extra={"tool_call_id": tool_call_id, "url": normalized_url, "state_path": str(state_path)},
    )

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            if normalized_url:
                await page.goto(normalized_url, wait_until="domcontentloaded")

            await page.wait_for_event("close")

            await context.storage_state(path=str(state_path))
            await context.close()
            await browser.close()

        return [
            TextContent(
                type="text",
                text=(
                    "Saved browser state.\n"
                    f"- path: {state_path}\n"
                    "Use setup_browser_state(url=...) to refresh it if the session expires."
                ),
            ),
        ]
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        return [
            TextContent(
                type="text",
                text=f"Error executing setup_browser_state: {exc}\n\nTraceback:\n{tb}",
            )
        ]


@mcp.tool(name="get_screenshots")
async def get_screenshots(
    last_n: int = 5,
    screenshot_type: str = "agent_step",
    session_id: str | None = None,
    from_timestamp: float | None = None,
    has_error: bool | None = None,
    include_images: bool = True,
    ctx: Context | None = None,
) -> list[TextContent | ImageContent]:
    """Retrieve screenshots from evaluation sessions.

    Screenshots are automatically captured during web_eval_agent executions at key moments
    (agent steps) and periodically during browser streaming. This tool allows you to
    retrieve them without token overflow issues. The dashboard at port 5009 shows all
    screenshots in real-time, while this tool provides programmatic access.

    Args:
        last_n: Number of most recent screenshots (default: 5, max: 20)
        screenshot_type: Filter by type - "agent_step", "stream_sample", or "all"
        session_id: Filter by specific session
        from_timestamp: Only get screenshots after this time
        has_error: Filter for error screenshots only
        include_images: If False, return metadata only

    Returns:
        Screenshot data or metadata with debugging information
    """
    _ = ctx
    runtime = get_runtime()
    last_n = min(max(last_n, 0), 20)

    screenshots = runtime.screenshots.get_screenshots(
        last_n=last_n,
        session_id=session_id,
        screenshot_type=screenshot_type,
        from_timestamp=from_timestamp,
        has_error=has_error,
        include_images=include_images,
    )
    stats = runtime.screenshots.get_stats()

    response: list[TextContent | ImageContent] = [
        TextContent(
            type="text",
            text=(
                f"Retrieved {len(screenshots)} screenshots from storage "
                f"(Total stored: {stats['total_screenshots']}, Sampling: {stats['sampling_rate']})"
            ),
        )
    ]

    if include_images:
        for shot in screenshots:
            image_data = shot.get("image_data")
            if not image_data:
                continue
            response.append(
                ImageContent(
                    type="image",
                    data=image_data,
                    mimeType=str(shot.get("mime_type") or "image/png"),
                )
            )
        return response

    if screenshots:
        lines: list[str] = []
        for shot in screenshots:
            prefix = f"[{shot.get('type', 'unknown')}] "
            step = shot.get("step")
            if step is not None:
                prefix += f"Step {step} | "
            url_value = str(shot.get("url") or "N/A")
            ts = shot.get("timestamp")
            time_value = "N/A"
            if isinstance(ts, (int, float)):
                time_value = datetime.fromtimestamp(ts, UTC).isoformat()
            err = " | ERROR" if shot.get("has_error") else ""
            lines.append(f"{prefix}URL: {url_value} | Time: {time_value}{err}")

        response.append(TextContent(type="text", text="\n".join(lines)))

    return response


def run_stdio() -> None:
    mcp.run(transport="stdio")
