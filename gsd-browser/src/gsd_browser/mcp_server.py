"""FastMCP stdio server exposing browser integration tools."""

from __future__ import annotations

import base64
import inspect
import json
import logging
import os
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent
from playwright.async_api import async_playwright

from .config import load_settings
from .llm.browser_use import create_browser_use_llm
from .run_event_capture import CDPRunEventCapture
from .run_event_store import RunEventStore
from .runtime import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, get_runtime

logger = logging.getLogger("gsd_browser.mcp")

mcp = FastMCP("gsd-browser")

os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")

_WEB_EVAL_AGENT_MODES = {"compact", "dev"}
_RUN_EVENT_TYPES = {"agent", "console", "network"}


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


def _parse_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        pass

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()
    except ValueError:
        return None


def _select_web_eval_agent_mode(*, normalized_url: str, explicit: str | None) -> str:
    if explicit is not None:
        candidate = str(explicit).strip().lower()
        if candidate not in _WEB_EVAL_AGENT_MODES:
            raise ValueError(
                f"Invalid mode={explicit!r}. Expected one of {sorted(_WEB_EVAL_AGENT_MODES)}."
            )
        return candidate

    hostname = urlparse(normalized_url).hostname
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return "dev"
    return "compact"


def _dev_run_event_excerpts(
    run_events: RunEventStore | None, *, session_id: str, max_per_type: int = 5
) -> dict[str, Any]:
    max_value = min(max(int(max_per_type), 0), 10)
    if run_events is None or max_value <= 0:
        return {"console_errors": [], "network_errors": []}

    get_events = getattr(run_events, "get_events", None)
    if not callable(get_events):
        return {"console_errors": [], "network_errors": []}

    events: list[dict[str, Any]] = get_events(
        session_id=session_id,
        last_n=100,
        event_types=["console", "network"],
        from_timestamp=None,
        has_error=True,
        include_details=True,
    )

    console_errors: list[dict[str, Any]] = []
    network_errors: list[dict[str, Any]] = []
    for event in events:
        event_type = event.get("event_type") or event.get("type")
        if event_type == "console" and len(console_errors) < max_value:
            console_errors.append(event)
        elif event_type == "network" and len(network_errors) < max_value:
            network_errors.append(event)
        if len(console_errors) >= max_value and len(network_errors) >= max_value:
            break

    return {"console_errors": console_errors, "network_errors": network_errors}


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


def _decode_base64_image(data: str) -> bytes | None:
    if not data:
        return None
    payload = data.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1].strip()
    try:
        return base64.b64decode(payload)
    except Exception:  # noqa: BLE001
        return None


def _agent_output_summary(agent_output: Any) -> str | None:
    actions = getattr(agent_output, "action", None)
    if actions is None and isinstance(agent_output, dict):
        actions = agent_output.get("action")
    if not isinstance(actions, list):
        return None

    action_names: list[str] = []
    for action in actions:
        payload: Any = action
        if hasattr(action, "model_dump") and callable(action.model_dump):
            try:
                payload = action.model_dump()
            except Exception:  # noqa: BLE001
                payload = action

        if isinstance(payload, dict):
            present = [key for key, value in payload.items() if value not in (None, {}, [], "")]
            if present:
                action_names.append(str(present[0]))
            continue

        action_names.append(type(payload).__name__)

    if not action_names:
        return None
    unique: list[str] = []
    for name in action_names:
        if name not in unique:
            unique.append(name)
    return _truncate("actions=" + ",".join(unique[:8]), max_len=1000)


@mcp.tool(name="web_eval_agent")
async def web_eval_agent(
    url: str,
    task: str,
    ctx: Context,
    headless_browser: bool = False,
    mode: str | None = None,
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
        mode: Optional. Response mode:
          - "compact": minimal summary + references (default for non-localhost)
          - "dev": includes bounded console/network excerpts (default for localhost/127.0.0.1)

    Returns:
        list[TextContent]: A single JSON payload encoded as text (no inline images).
    """
    _ = ctx
    runtime = get_runtime()
    settings = load_settings(strict=False)
    ensure_dashboard_running = getattr(runtime, "ensure_dashboard_running", None)
    if callable(ensure_dashboard_running):
        ensure_dashboard_running(
            settings=settings, host=DEFAULT_DASHBOARD_HOST, port=DEFAULT_DASHBOARD_PORT
        )

    dashboard_fn = getattr(runtime, "dashboard", None)
    dashboard = dashboard_fn() if callable(dashboard_fn) else None
    control_state = (
        getattr(getattr(dashboard, "runtime", None), "control_state", None) if dashboard else None
    )

    tool_call_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    started = datetime.now(UTC).timestamp()
    normalized_url = _normalize_url(url)
    try:
        selected_mode = _select_web_eval_agent_mode(normalized_url=normalized_url, explicit=mode)
    except ValueError as exc:
        payload = {
            "version": "gsd-browser.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": str(mode) if mode is not None else None,
            "status": "failed",
            "result": None,
            "summary": _truncate(str(exc), max_len=2000),
            "artifacts": {"screenshots": 0, "stream_samples": 0, "run_events": 0},
            "next_actions": [
                "Use mode='compact' or mode='dev' to override response behavior.",
                f"Open dashboard: http://{DEFAULT_DASHBOARD_HOST}:{DEFAULT_DASHBOARD_PORT}",
            ],
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    run_events = getattr(runtime, "run_events", None)
    if run_events is None:
        run_events = RunEventStore()
    ensure_session = getattr(run_events, "ensure_session", None)
    if callable(ensure_session):
        ensure_session(session_id, created_at=started)

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

        step_screenshot_count = 0
        cdp_capture = CDPRunEventCapture(store=run_events, session_id=session_id)

        async def record_step_screenshot(*args: Any, **kwargs: Any) -> None:
            nonlocal step_screenshot_count

            browser_state_summary = args[0] if args else kwargs.get("browser_state_summary")
            step = kwargs.get("step")
            if step is None and len(args) >= 3:
                step = args[2]

            screenshot_base64 = None
            if browser_state_summary is not None:
                screenshot_base64 = getattr(browser_state_summary, "screenshot", None)
                if screenshot_base64 is None:
                    screenshot_base64 = getattr(browser_state_summary, "screenshot_base64", None)
                if screenshot_base64 is None and hasattr(browser_state_summary, "get"):
                    try:
                        screenshot_base64 = browser_state_summary.get("screenshot")
                    except Exception:  # noqa: BLE001
                        screenshot_base64 = None
                if screenshot_base64 is None and hasattr(browser_state_summary, "get"):
                    try:
                        screenshot_base64 = browser_state_summary.get("screenshot_base64")
                    except Exception:  # noqa: BLE001
                        screenshot_base64 = None

            if screenshot_base64 is None:
                screenshot_base64 = kwargs.get("screenshot")

            if step is None and browser_state_summary is not None:
                step = getattr(browser_state_summary, "step", None)
                if step is None and hasattr(browser_state_summary, "get"):
                    try:
                        step = browser_state_summary.get("step")
                    except Exception:  # noqa: BLE001
                        step = None

            image_bytes = (
                _decode_base64_image(screenshot_base64)
                if isinstance(screenshot_base64, str)
                else None
            )
            if not image_bytes:
                return

            screenshots_manager = getattr(runtime, "screenshots", None)
            record = getattr(screenshots_manager, "record_screenshot", None)
            if not callable(record):
                return

            page_url_value = getattr(browser_state_summary, "url", None)
            if page_url_value is None and hasattr(browser_state_summary, "get"):
                try:
                    page_url_value = browser_state_summary.get("url")
                except Exception:  # noqa: BLE001
                    page_url_value = None

            page_title_value = getattr(browser_state_summary, "title", None)
            if page_title_value is None and hasattr(browser_state_summary, "get"):
                try:
                    page_title_value = browser_state_summary.get("title")
                except Exception:  # noqa: BLE001
                    page_title_value = None

            browser_errors = getattr(browser_state_summary, "browser_errors", None)
            if browser_errors is None and hasattr(browser_state_summary, "get"):
                try:
                    browser_errors = browser_state_summary.get("browser_errors")
                except Exception:  # noqa: BLE001
                    browser_errors = None

            page_url = str(page_url_value or "")
            page_title = str(page_title_value or "")
            has_error = bool(browser_errors)
            record(
                screenshot_type="agent_step",
                image_bytes=image_bytes,
                mime_type="image/png",
                session_id=session_id,
                captured_at=datetime.now(UTC).timestamp(),
                has_error=has_error,
                metadata={"title": page_title, "browser_errors": browser_errors or []},
                url=page_url or None,
                step=step,
            )
            step_screenshot_count += 1

        def record_step_event(*args: Any, **kwargs: Any) -> None:
            browser_state_summary = args[0] if args else kwargs.get("browser_state_summary")
            agent_output = args[1] if len(args) >= 2 else kwargs.get("agent_output")
            step = kwargs.get("step")
            if step is None and len(args) >= 3:
                step = args[2]

            summary = _agent_output_summary(agent_output)

            page_url = None
            page_title = None
            if browser_state_summary is not None:
                page_url = getattr(browser_state_summary, "url", None)
                if page_url is None and hasattr(browser_state_summary, "get"):
                    try:
                        page_url = browser_state_summary.get("url")
                    except Exception:  # noqa: BLE001
                        page_url = None

                page_title = getattr(browser_state_summary, "title", None)
                if page_title is None and hasattr(browser_state_summary, "get"):
                    try:
                        page_title = browser_state_summary.get("title")
                    except Exception:  # noqa: BLE001
                        page_title = None

            record_agent_event = getattr(run_events, "record_agent_event", None)
            if callable(record_agent_event):
                record_agent_event(
                    session_id,
                    captured_at=datetime.now(UTC).timestamp(),
                    step=int(step) if isinstance(step, int) else None,
                    url=str(page_url) if page_url else None,
                    title=str(page_title) if page_title else None,
                    summary=summary,
                )

        async def on_new_step(*args: Any, **kwargs: Any) -> None:
            try:
                await record_step_screenshot(*args, **kwargs)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to record step screenshot", exc_info=True)
            try:
                record_step_event(*args, **kwargs)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to record agent step event", exc_info=True)

        async def pause_gate(*_: Any, **__: Any) -> None:
            if control_state is None:
                return
            await control_state.wait_until_unpaused()

        llm = create_browser_use_llm(settings)
        browser_session = BrowserSession(headless=headless_browser, storage_state=storage_state)

        try:
            await browser_session.start()
            cdp_capture.attach(browser_session.cdp_client)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to attach CDP event capture", exc_info=True)

        agent_task = f"{task}\n\nURL: {normalized_url}"
        agent_kwargs: dict[str, Any] = {
            "task": agent_task,
            "llm": llm,
            "browser_session": browser_session,
        }
        try:
            signature = inspect.signature(Agent)
            if "register_new_step_callback" in signature.parameters:
                agent_kwargs["register_new_step_callback"] = on_new_step
        except (TypeError, ValueError):
            pass

        agent = Agent(**agent_kwargs)
        register_callback = getattr(agent, "register_new_step_callback", None)
        if callable(register_callback):
            try:
                callback_sig = inspect.signature(register_callback)
                if len(callback_sig.parameters) == 1:
                    register_callback(on_new_step)
            except (TypeError, ValueError):
                pass

        run_kwargs: dict[str, Any] = {}
        try:
            signature = inspect.signature(agent.run)
            has_kwargs = any(
                param.kind is inspect.Parameter.VAR_KEYWORD
                for param in signature.parameters.values()
            )
            if "on_step_end" in signature.parameters or has_kwargs:
                run_kwargs["on_step_end"] = pause_gate
        except (TypeError, ValueError):
            run_kwargs["on_step_end"] = pause_gate

        try:
            history = await agent.run(**run_kwargs)
        finally:
            try:
                cdp_capture.detach(browser_session.cdp_client)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to detach CDP event capture", exc_info=True)

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
            "mode": selected_mode,
            "status": status,
            "result": result,
            "summary": _truncate(summary, max_len=2000),
            "artifacts": {
                "screenshots": step_screenshot_count,
                "stream_samples": 0,
                "run_events": (
                    getattr(run_events, "get_counts", lambda _sid: {"total": 0})(session_id).get(
                        "total", 0
                    )
                    if run_events is not None
                    else 0
                ),
            },
            "next_actions": [
                (
                    "Use get_screenshots(session_id="
                    f"'{session_id}', screenshot_type='agent_step', last_n=5)"
                ),
                (
                    "Use get_screenshots(session_id="
                    f"'{session_id}', screenshot_type='agent_step', include_images=false)"
                ),
                (
                    "Use get_run_events(session_id="
                    f"'{session_id}', event_types=['console','network'], has_error=true, last_n=50)"
                ),
                f"Open dashboard: http://{DEFAULT_DASHBOARD_HOST}:{DEFAULT_DASHBOARD_PORT}",
            ],
        }
        if selected_mode == "dev":
            payload["dev_excerpts"] = _dev_run_event_excerpts(
                run_events, session_id=session_id, max_per_type=5
            )

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
            "mode": selected_mode,
            "status": "failed",
            "result": None,
            "summary": _truncate(f"{type(exc).__name__}: {exc}", max_len=2000),
            "artifacts": {"screenshots": 0, "stream_samples": 0, "run_events": 0},
            "next_actions": [
                "Use get_screenshots(screenshot_type='agent_step', last_n=5, include_images=false)",
                f"Open dashboard: http://{DEFAULT_DASHBOARD_HOST}:{DEFAULT_DASHBOARD_PORT}",
            ],
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


@mcp.tool(name="get_run_events")
async def get_run_events(
    session_id: str | None = None,
    last_n: int = 50,
    event_types: list[str] | None = None,
    from_timestamp: Any | None = None,
    has_error: bool | None = None,
    include_details: bool = False,
    ctx: Context | None = None,
) -> list[TextContent]:
    """Retrieve stored run events for web_eval_agent sessions as a JSON payload.

    This tool is designed to keep web_eval_agent responses compact while still allowing
    clients to fetch detailed console/network/agent events on demand.

    Args:
        session_id: Filter to a single session_id (optional).
        last_n: Max number of events to return (default 50, max 200).
        event_types: Optional list of event types ("agent", "console", "network").
        from_timestamp: Only include events after this timestamp (epoch seconds or ISO-8601).
        has_error: Filter for events marked as errors (optional).
        include_details: Whether to include event details payloads (default false).

    Returns:
        list[TextContent]: A single JSON payload encoded as text.
    """
    _ = ctx
    runtime = get_runtime()
    run_events = getattr(runtime, "run_events", None)

    last_n_value = min(max(int(last_n), 0), 200)

    normalized_types: list[str] | None = None
    error: str | None = None
    if event_types is not None:
        normalized: list[str] = []
        invalid: set[str] = set()
        for item in event_types:
            candidate = str(item).strip().lower()
            if not candidate:
                continue
            if candidate not in _RUN_EVENT_TYPES:
                invalid.add(candidate)
                continue
            if candidate not in normalized:
                normalized.append(candidate)
        if invalid:
            error = (
                f"Invalid event_types={sorted(invalid)}. "
                f"Expected subset of {sorted(_RUN_EVENT_TYPES)}."
            )
        else:
            normalized_types = normalized or None

    parsed_from_timestamp = _parse_timestamp(from_timestamp)
    if error is None and from_timestamp is not None and parsed_from_timestamp is None:
        error = "from_timestamp must be epoch seconds or ISO-8601 timestamp."

    get_events = getattr(run_events, "get_events", None) if run_events is not None else None
    events: list[dict[str, Any]]
    if error is None and callable(get_events):
        events = get_events(
            session_id=session_id,
            last_n=last_n_value,
            event_types=normalized_types,
            from_timestamp=parsed_from_timestamp,
            has_error=has_error,
            include_details=bool(include_details),
        )
    else:
        events = []

    counts: dict[str, int] = {"agent": 0, "console": 0, "network": 0, "total": len(events)}
    timestamps: list[float] = []
    for event in events:
        event_type_value = event.get("event_type") or event.get("type")
        if isinstance(event_type_value, str) and event_type_value in counts:
            counts[event_type_value] += 1
        timestamp_value = event.get("timestamp") or event.get("captured_at")
        if isinstance(timestamp_value, (int, float)):
            timestamps.append(float(timestamp_value))

    payload = {
        "version": "gsd-browser.get_run_events.v1",
        "session_id": session_id,
        "events": events,
        "stats": {
            "counts": counts,
            "oldest_timestamp": min(timestamps) if timestamps else None,
            "newest_timestamp": max(timestamps) if timestamps else None,
        },
        "error": error,
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
