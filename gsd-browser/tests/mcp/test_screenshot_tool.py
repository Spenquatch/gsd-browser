from __future__ import annotations

import asyncio
import inspect
import re
from typing import Any

import pytest
from typer.testing import CliRunner

from gsd_browser import mcp_server as mcp_server_mod
from gsd_browser.cli import app
from gsd_browser.mcp_server import get_screenshots as mcp_get_screenshots
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
    assert any("image_data" not in shot for shot in results), (
        "image_data should require image_bytes"
    )


def test_mcp_get_screenshots_enforces_last_n_max_20_and_metadata_only_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ScreenshotManager()
    for i in range(30):
        _add(
            manager,
            screenshot_type="agent_step",
            session_id="a",
            timestamp=float(100 + i),
            image_bytes=b"img",
        )

    class DummyRuntime:
        def __init__(self, screenshots: ScreenshotManager) -> None:
            self.screenshots = screenshots

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: DummyRuntime(manager))

    result = _run(mcp_get_screenshots(last_n=25, include_images=False))
    assert isinstance(result, list)
    assert all(getattr(item, "type", None) != "image" for item in result)

    summary_text = next(
        (getattr(item, "text", "") for item in result if getattr(item, "type", None) == "text"),
        "",
    )
    match = re.search(r"Retrieved (\d+) screenshots", summary_text)
    assert match, f"Expected summary line with count; got: {summary_text!r}"
    assert int(match.group(1)) == 20


def test_cli_diagnostics_smoke_messages() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--version"], env={"ANTHROPIC_API_KEY": "x"})
    assert result.exit_code == 0
    assert "gsd v" in result.stdout

    result = runner.invoke(app, ["mcp-config", "--format", "json"], env={"ANTHROPIC_API_KEY": "x"})
    assert result.exit_code == 0
    assert '"mcpServers"' in result.stdout
    assert '"gsd"' in result.stdout

    result = runner.invoke(
        app,
        ["serve-echo", "--once"],
        input="ping\n",
        env={"ANTHROPIC_API_KEY": "x"},
    )
    assert result.exit_code == 0
    assert "ping" in result.stdout

    result = runner.invoke(
        app,
        ["serve", "--json-logs", "--text-logs"],
        env={"ANTHROPIC_API_KEY": "x"},
    )
    assert result.exit_code == 1
    assert "Cannot use" in result.stdout
