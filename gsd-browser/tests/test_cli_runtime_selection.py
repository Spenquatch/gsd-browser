from __future__ import annotations

from gsd_browser.cli import _select_stdio_runtime


def test_stdio_runtime_defaults_to_fastmcp_v2(monkeypatch) -> None:
    monkeypatch.delenv("GSD_USE_LEGACY_MCP_RUNTIME", raising=False)
    monkeypatch.delenv("GSD_USE_FASTMCP_V2", raising=False)
    assert _select_stdio_runtime() == "fastmcp_v2"


def test_stdio_runtime_escape_hatch_selects_legacy(monkeypatch) -> None:
    monkeypatch.delenv("GSD_USE_FASTMCP_V2", raising=False)
    monkeypatch.setenv("GSD_USE_LEGACY_MCP_RUNTIME", "true")
    assert _select_stdio_runtime() == "legacy"


def test_stdio_runtime_legacy_overrides_deprecated_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("GSD_USE_FASTMCP_V2", "true")
    monkeypatch.setenv("GSD_USE_LEGACY_MCP_RUNTIME", "true")
    assert _select_stdio_runtime() == "legacy"

