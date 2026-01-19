from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from gsd_browser.fastmcp_v2_http import build_http_app
from gsd_browser.fastmcp_v2_stdio import mcp as v2_mcp


def _tool_names_from_docs() -> set[str]:
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "api" / "MCP_TOOLS.md").read_text(encoding="utf-8")
    return set(re.findall(r"^### `([^`]+)`", text, flags=re.MULTILINE))


def test_http_entrypoint_refuses_to_start_without_jwt_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GSD_TRANSPORT", "http")
    monkeypatch.setenv("FASTMCP_DOCKET_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("GSD_JWT_JWKS_URL", raising=False)
    monkeypatch.delenv("GSD_JWT_ISSUER", raising=False)
    monkeypatch.delenv("GSD_JWT_AUDIENCE", raising=False)

    with pytest.raises(RuntimeError, match="GSD_JWT_JWKS_URL"):
        build_http_app()


def test_http_entrypoint_starts_and_exposes_expected_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GSD_TRANSPORT", "http")
    monkeypatch.setenv("FASTMCP_DOCKET_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GSD_JWT_JWKS_URL", "https://example.com/jwks.json")
    monkeypatch.setenv("GSD_JWT_ISSUER", "https://issuer.example.com")
    monkeypatch.setenv("GSD_JWT_AUDIENCE", "gsd")

    app = build_http_app()
    assert app is not None

    tools = asyncio.run(v2_mcp._list_tools_mcp())  # noqa: SLF001
    assert {tool.name for tool in tools} == _tool_names_from_docs()
