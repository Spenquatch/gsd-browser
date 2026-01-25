from __future__ import annotations

import pytest

from gsd_browser.http_base_path import detect_base_path, normalize_base_path


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "/"),
        ("", "/"),
        ("   ", "/"),
        ("/", "/"),
        ("/mcp/gsd", "/mcp/gsd"),
        ("/mcp/gsd/", "/mcp/gsd"),
        ("mcp/gsd", "/mcp/gsd"),
        ("mcp/gsd/", "/mcp/gsd"),
    ],
)
def test_normalize_base_path(value: str | None, expected: str) -> None:
    assert normalize_base_path(value) == expected


def test_detect_base_path_prefers_env_override() -> None:
    assert detect_base_path("/from-env/", "/from-header/") == "/from-env"


def test_detect_base_path_falls_back_to_x_forwarded_prefix_first_value() -> None:
    assert detect_base_path("", "/mcp/gsd/, /ignored") == "/mcp/gsd"


def test_detect_base_path_defaults_to_root() -> None:
    assert detect_base_path("", "") == "/"

