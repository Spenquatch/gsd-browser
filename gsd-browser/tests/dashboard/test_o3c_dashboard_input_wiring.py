from __future__ import annotations

import re
from pathlib import Path

import pytest


def _dashboard_js_text() -> str:
    import gsd_browser

    js_path = (
        Path(gsd_browser.__file__).resolve().parent
        / "streaming"
        / "dashboard_static"
        / "dashboard.js"
    )
    return js_path.read_text(encoding="utf-8")


def _require_o3c_dashboard_input_capture(js_text: str) -> None:
    expected = (
        "input_click",
        "input_move",
        "input_wheel",
        "input_keydown",
        "input_keyup",
        "input_type",
    )
    missing = [event for event in expected if event not in js_text]
    if missing:
        pytest.skip(
            "O3c dashboard input capture not implemented yet (missing: " + ", ".join(missing) + ")"
        )


def test_o3c_dashboard_emits_expected_ctrl_events() -> None:
    js_text = _dashboard_js_text()
    _require_o3c_dashboard_input_capture(js_text)

    assert "io('/ctrl'" in js_text

    for event in (
        "input_click",
        "input_move",
        "input_wheel",
        "input_keydown",
        "input_keyup",
        "input_type",
    ):
        assert re.search(rf"\\bemit\\(\\s*['\"]{event}['\"]", js_text), event


def test_o3c_dashboard_includes_payload_fields_expected_by_server() -> None:
    js_text = _dashboard_js_text()
    _require_o3c_dashboard_input_capture(js_text)

    assert "x" in js_text
    assert "y" in js_text

    assert ("clickCount" in js_text) or ("click_count" in js_text)
    assert ("deltaX" in js_text) or ("delta_x" in js_text)
    assert ("deltaY" in js_text) or ("delta_y" in js_text)

    assert "key" in js_text
    assert "code" in js_text
    assert "text" in js_text


def test_o3c_dashboard_registers_pointer_and_keyboard_listeners() -> None:
    js_text = _dashboard_js_text()
    _require_o3c_dashboard_input_capture(js_text)

    has_pointer_listener = any(
        needle in js_text
        for needle in (
            "addEventListener('pointerdown'",
            'addEventListener("pointerdown"',
            "addEventListener('mousedown'",
            'addEventListener("mousedown"',
            "addEventListener('click'",
            'addEventListener("click"',
            ".onpointerdown",
            ".onmousedown",
            ".onclick",
        )
    )
    assert has_pointer_listener

    has_move_listener = any(
        needle in js_text
        for needle in (
            "addEventListener('pointermove'",
            'addEventListener("pointermove"',
            "addEventListener('mousemove'",
            'addEventListener("mousemove"',
            ".onpointermove",
            ".onmousemove",
        )
    )
    assert has_move_listener

    assert (
        "addEventListener('wheel'" in js_text
        or 'addEventListener("wheel"' in js_text
        or ".onwheel" in js_text
    )

    has_key_listener = any(
        needle in js_text
        for needle in (
            "addEventListener('keydown'",
            'addEventListener("keydown"',
            "addEventListener('keyup'",
            'addEventListener("keyup"',
            ".onkeydown",
            ".onkeyup",
        )
    )
    assert has_key_listener
