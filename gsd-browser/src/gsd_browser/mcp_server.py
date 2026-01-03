"""FastMCP stdio server exposing browser integration tools."""

from __future__ import annotations

import json
import logging
import os
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent
from playwright.async_api import async_playwright

from .config import load_settings
from .llm.browser_use import create_browser_use_llm
from .runtime import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, get_runtime

logger = logging.getLogger("gsd_browser.mcp")

mcp = FastMCP("gsd-browser")

os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")


def _normalize_url(url: str) -> str:
    if url.startswith(("http://", "https://", "file://", "data:", "chrome:", "javascript:")):
        return url
    return f"https://{url}"


def _browser_state_path() -> Path:
    return Path(os.path.expanduser("~/.operative/browser_state/state.json"))


def _truncate(text: str, *, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)] + "…"


def _load_browser_use_classes() -> tuple[type[Any], type[Any]]:
    from browser_use import Agent, BrowserSession

    return Agent, BrowserSession


def _history_final_result(history: Any) -> str | None:
    final_result = getattr(history, "final_result", None)
    if callable(final_result):
        return final_result()
    return None


def _history_has_errors(history: Any) -> bool:
    has_errors = getattr(history, "has_errors", None)
    if callable(has_errors):
        return bool(has_errors())
    if isinstance(has_errors, bool):
        return has_errors
    return False


def _history_error_count(history: Any) -> int:
    errors_attr = getattr(history, "errors", None)
    if callable(errors_attr):
        errors_iter = errors_attr()
    else:
        errors_iter = errors_attr

    if errors_iter is None:
        return 0

    try:
        return sum(1 for err in errors_iter if err)
    except TypeError:
        return int(bool(errors_iter))


def _history_step_count(history: Any) -> int:
    steps = getattr(history, "history", None)
    if steps is None:
        return 0
    try:
        return len(steps)
    except TypeError:
        return 0


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
        list[TextContent]: A single JSON payload encoded as text (no inline images).
    """
    _ = ctx
    runtime = get_runtime()
    settings = load_settings(strict=False)

    normalized_url = _normalize_url(url)
    tool_call_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    started = datetime.now(UTC).timestamp()

    if hasattr(runtime, "screenshots"):
        try:
            runtime.screenshots.current_session_id = session_id
            runtime.screenshots.current_session_start = started
        except Exception:  # noqa: BLE001
            pass

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
        Agent, BrowserSession = _load_browser_use_classes()

        llm = create_browser_use_llm(settings)
        browser_session = BrowserSession(headless=headless_browser, storage_state=storage_state)

        agent_task = f"{task}\n\nURL: {normalized_url}"
        agent = Agent(task=agent_task, llm=llm, browser_session=browser_session)
        history = await agent.run()

        result = _history_final_result(history)
        error_count = _history_error_count(history)
        has_errors = _history_has_errors(history)

        if result is not None:
            status = "partial" if has_errors else "success"
        else:
            status = "failed" if has_errors else "partial"

        summary = (
            f"browser_use_steps={_history_step_count(history)} "
            f"errors={error_count} "
            f"result_present={result is not None}"
        )
        payload = {
            "version": "gsd-browser.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": "compact",
            "status": status,
            "result": result,
            "summary": _truncate(summary, max_len=2000),
            "artifacts": {"screenshots": 0, "stream_samples": 0, "run_events": 0},
            "next_actions": [],
        }

        logger.info(
            "web_eval_agent completed",
            extra={
                "tool_call_id": tool_call_id,
                "session_id": session_id,
                "status": status,
                "duration_s": max(0.0, datetime.now(UTC).timestamp() - started),
                "result_present": result is not None,
                "errors": error_count,
            },
        )

        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "web_eval_agent failed",
            extra={
                "tool_call_id": tool_call_id,
                "session_id": session_id,
                "url": normalized_url,
                "duration_s": max(0.0, datetime.now(UTC).timestamp() - started),
            },
        )
        payload = {
            "version": "gsd-browser.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": "compact",
            "status": "failed",
            "result": None,
            "summary": _truncate(f"{type(exc).__name__}: {exc}", max_len=2000),
            "artifacts": {"screenshots": 0, "stream_samples": 0, "run_events": 0},
            "next_actions": [],
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


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
