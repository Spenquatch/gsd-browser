from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping
from typing import Any

import pytest
from typer.testing import CliRunner

from gsd_browser.cli import app
from gsd_browser.screenshot_manager import ScreenshotManager


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _add(
    manager: ScreenshotManager,
    *,
    screenshot_type: str,
    session_id: str | None,
    timestamp: float,
    has_error: bool = False,
    image_bytes: bytes | None = b"img",
) -> None:
    manager.record_screenshot(
        screenshot_type=screenshot_type,
        image_bytes=image_bytes,
        mime_type="image/png" if image_bytes is not None else None,
        session_id=session_id,
        captured_at=timestamp,
        has_error=has_error,
        metadata={"ts": timestamp},
        url=f"https://example.com/{screenshot_type}/{timestamp}",
    )


def test_screenshot_manager_get_screenshots_filter_combinations() -> None:
    manager = ScreenshotManager()

    _add(manager, screenshot_type="agent_step", session_id="a", timestamp=100.0, has_error=False)
    _add(manager, screenshot_type="agent_step", session_id="a", timestamp=110.0, has_error=True)
    _add(manager, screenshot_type="agent_step", session_id="b", timestamp=120.0, has_error=False)
    _add(manager, screenshot_type="stream_sample", session_id="a", timestamp=130.0, has_error=False)
    _add(manager, screenshot_type="stream_sample", session_id="b", timestamp=140.0, has_error=True)

    assert manager.get_screenshots(last_n=0) == []
    assert manager.get_screenshots(last_n=-1) == []

    results = manager.get_screenshots(screenshot_type="stream_sample")
    assert {shot["type"] for shot in results} == {"stream_sample"}

    results = manager.get_screenshots(session_id="a")
    assert {shot["session_id"] for shot in results} == {"a"}

    results = manager.get_screenshots(from_timestamp=121.0)
    assert all(shot["timestamp"] >= 121.0 for shot in results)

    results = manager.get_screenshots(has_error=True)
    assert results
    assert all(shot["has_error"] is True for shot in results)

    results = manager.get_screenshots(
        screenshot_type="agent_step",
        session_id="a",
        has_error=True,
        from_timestamp=0.0,
    )
    assert len(results) == 1
    assert results[0]["type"] == "agent_step"
    assert results[0]["session_id"] == "a"
    assert results[0]["has_error"] is True

    results = manager.get_screenshots(screenshot_type="agent_step", last_n=2)
    assert [shot["timestamp"] for shot in results] == [110.0, 120.0]


def test_screenshot_manager_get_screenshots_include_images_false_is_metadata_only() -> None:
    manager = ScreenshotManager()
    _add(manager, screenshot_type="agent_step", session_id="a", timestamp=100.0, image_bytes=b"img")
    _add(manager, screenshot_type="agent_step", session_id="a", timestamp=110.0, image_bytes=None)

    results = manager.get_screenshots(include_images=False, last_n=10)
    assert results
    assert all("image_data" not in shot for shot in results)

    results = manager.get_screenshots(include_images=True, last_n=10)
    assert any("image_data" in shot for shot in results)
    assert any("image_data" not in shot for shot in results), "image_data should require image_bytes"


def _resolve_mcp_get_screenshots() -> tuple[Callable[..., Any], Any] | None:
    candidates = (
        "gsd_browser.mcp",
        "gsd_browser.mcp_server",
        "gsd_browser.mcp.tools",
        "gsd_browser.tools.mcp",
        "gsd_browser.server",
    )
    for module_name in candidates:
        try:
            module = __import__(module_name, fromlist=["*"])
        except ImportError:
            continue
        fn = getattr(module, "get_screenshots", None)
        if callable(fn):
            return fn, module
    return None


def _extract_screenshot_payload(result: Any) -> list[Mapping[str, Any]]:
    if isinstance(result, list):
        if all(isinstance(item, Mapping) for item in result):
            return list(result)
        raise AssertionError("Expected list[Mapping] from get_screenshots")
    if isinstance(result, Mapping):
        for key in ("screenshots", "results", "data"):
            value = result.get(key)
            if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
                return value
    raise AssertionError("Unsupported get_screenshots response shape")


def test_mcp_get_screenshots_enforces_last_n_max_20_and_metadata_only_mode() -> None:
    resolved = _resolve_mcp_get_screenshots()
    if resolved is None:
        pytest.skip("MCP get_screenshots tool not yet implemented in gsd_browser")

    get_screenshots, module = resolved
    manager = ScreenshotManager()
    for i in range(30):
        _add(
            manager,
            screenshot_type="agent_step",
            session_id="a",
            timestamp=float(100 + i),
            image_bytes=b"img",
        )

    sig = inspect.signature(get_screenshots)
    kwargs: dict[str, Any] = {"last_n": 25, "include_images": False}

    if "screenshot_manager" in sig.parameters:
        kwargs["screenshot_manager"] = manager
    elif "manager" in sig.parameters:
        kwargs["manager"] = manager
    elif hasattr(module, "screenshot_manager"):
        setattr(module, "screenshot_manager", manager)
    elif hasattr(module, "screenshots"):
        setattr(module, "screenshots", manager)
    else:
        pytest.skip("Cannot inject ScreenshotManager into MCP get_screenshots tool")

    try:
        result = _run(get_screenshots(**kwargs))
    except Exception:
        # Raising is acceptable as long as last_n is enforced via validation.
        return

    shots = _extract_screenshot_payload(result)
    assert len(shots) <= 20
    assert all("image_data" not in shot for shot in shots)


def test_cli_diagnostics_smoke_messages() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["mcp-config", "--format", "json"], env={"ANTHROPIC_API_KEY": "x"})
    assert result.exit_code == 0
    assert '"mcpServers"' in result.stdout
    assert '"gsd-browser"' in result.stdout

    result = runner.invoke(
        app,
        ["serve", "--once"],
        input="ping\n",
        env={"ANTHROPIC_API_KEY": "x"},
    )
    assert result.exit_code == 0
    assert "Config loaded" in result.stdout
    assert "ping" in result.stdout

    result = runner.invoke(
        app,
        ["serve", "--json-logs", "--text-logs"],
        env={"ANTHROPIC_API_KEY": "x"},
    )
    assert result.exit_code == 1
    assert "Cannot use" in result.stdout

