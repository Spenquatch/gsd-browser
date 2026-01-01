from __future__ import annotations

import asyncio
import importlib
import inspect
from collections.abc import Mapping
from typing import Any

import pytest

from mcp_template.config import load_settings


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _get_screenshot_manager_class() -> type[Any] | None:
    candidates = [
        "mcp_template.screenshot_manager",
        "mcp_template.screenshots",
        "mcp_template.streaming",
    ]
    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        cls = getattr(module, "ScreenshotManager", None)
        if cls is not None:
            return cls
    return None


def _reset_screenshot_manager(manager: Any) -> None:
    for attr in ("key_screenshots", "metadata_index"):
        container = getattr(manager, attr, None)
        if container is None:
            continue
        clear = getattr(container, "clear", None)
        if callable(clear):
            clear()
    for attr, value in (
        ("stream_counter", 0),
        ("total_size_bytes", 0),
        ("current_session_id", None),
        ("current_session_start", None),
    ):
        if hasattr(manager, attr):
            setattr(manager, attr, value)


def test_streaming_env_defaults_and_invalid_input_fallback() -> None:
    base_env = {
        "ANTHROPIC_API_KEY": "test",
        "MCP_TEMPLATE_MODEL": "claude-haiku-4-5",
        "LOG_LEVEL": "INFO",
        "MCP_TEMPLATE_JSON_LOGS": False,
    }
    settings = load_settings(env=base_env, env_file=None)

    if not hasattr(settings, "streaming_mode") or not hasattr(settings, "streaming_quality"):
        pytest.skip("Streaming settings not yet implemented in mcp_template.config.Settings")

    default_mode = settings.streaming_mode
    default_quality = settings.streaming_quality

    assert default_mode in {"cdp", "screenshot"}
    assert default_quality in {"low", "med", "high"}

    settings = load_settings(env={**base_env, "STREAMING_MODE": " CDP "}, env_file=None)
    assert settings.streaming_mode == "cdp"

    settings = load_settings(env={**base_env, "STREAMING_QUALITY": " HIGH "}, env_file=None)
    assert settings.streaming_quality == "high"

    settings = load_settings(env={**base_env, "STREAMING_MODE": "nope"}, env_file=None)
    assert settings.streaming_mode == default_mode

    settings = load_settings(env={**base_env, "STREAMING_QUALITY": "nope"}, env_file=None)
    assert settings.streaming_quality == default_quality


def test_screenshot_manager_get_screenshots_filters() -> None:
    cls = _get_screenshot_manager_class()
    if cls is None:
        pytest.skip("ScreenshotManager not yet implemented in mcp_template")

    manager = cls()
    _reset_screenshot_manager(manager)

    if not hasattr(manager, "add_key_screenshot") or not hasattr(manager, "get_screenshots"):
        pytest.skip(
            "ScreenshotManager API not yet complete (missing add_key_screenshot/get_screenshots)"
        )

    img = "aGVsbG8="
    session_a = "session-a"
    session_b = "session-b"

    _run(manager.add_key_screenshot(img, "https://example.com/a", 1, session_a, timestamp=100.0))
    _run(
        manager.add_key_screenshot(
            img, "https://example.com/b", 2, session_b, has_error=True, timestamp=200.0
        )
    )

    # Ensure we have at least one sampled stream frame (web-agent behavior stores every Nth frame).
    if hasattr(manager, "add_stream_screenshot"):
        sampling_rate = int(getattr(manager, "SAMPLING_RATE", 10))
        for i in range(sampling_rate):
            _run(
                manager.add_stream_screenshot(
                    img, f"https://example.com/stream/{i}", timestamp=300.0 + i
                )
            )

    results = _run(manager.get_screenshots(include_images=False))
    assert isinstance(results, list)
    assert results, "Expected screenshots to be stored"
    assert "image_data" not in results[0]

    results = _run(manager.get_screenshots(session_id=session_a))
    assert all(r.get("session_id") == session_a for r in results)

    results = _run(manager.get_screenshots(from_timestamp=150.0))
    assert all(r["timestamp"] >= 150.0 for r in results)

    results = _run(manager.get_screenshots(screenshot_type="stream_sample"))
    assert all(r.get("type") == "stream_sample" for r in results)


def _healthz_payload() -> Mapping[str, Any]:
    candidates = [
        "mcp_template.log_server",
        "mcp_template.server",
        "mcp_template.healthz",
        "mcp_template.streaming.server",
    ]
    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue

        create_streaming_app = getattr(module, "create_streaming_app", None)
        if callable(create_streaming_app):
            from fastapi.testclient import TestClient

            base_env = {
                "ANTHROPIC_API_KEY": "test",
                "MCP_TEMPLATE_MODEL": "claude-haiku-4-5",
                "LOG_LEVEL": "INFO",
                "MCP_TEMPLATE_JSON_LOGS": False,
            }
            runtime = create_streaming_app(settings=load_settings(env=base_env, env_file=None))
            client = TestClient(runtime.api_app)
            resp = client.get("/healthz")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, Mapping)
            return data

        app = getattr(module, "app", None)
        if app is not None and hasattr(app, "test_client"):
            client = app.test_client()
            resp = client.get("/healthz")
            assert resp.status_code == 200
            data = resp.get_json()
            assert isinstance(data, Mapping)
            return data

        for fn_name in ("healthcheck", "healthz", "health"):
            fn = getattr(module, fn_name, None)
            if fn is None or not callable(fn):
                continue
            if any(
                param.default is inspect._empty
                and param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
                for param in inspect.signature(fn).parameters.values()
            ):
                continue
            result = fn()
            if isinstance(result, Mapping):
                return result
            if hasattr(result, "get_json"):
                data = result.get_json()
                assert isinstance(data, Mapping)
                return data

    pytest.skip(
        "No /healthz handler exposed yet (expected under mcp_template.streaming.server or similar)"
    )


def test_healthz_json_includes_required_keys() -> None:
    payload = _healthz_payload()
    for key in (
        "streaming_mode",
        "frame_latency_ms",
        "frames_dropped",
        "last_frame_ts",
        "sampler_totals",
    ):
        assert key in payload
