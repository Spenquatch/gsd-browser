from __future__ import annotations

import asyncio
import re
from pathlib import Path

from gsd_browser.fastmcp_v2_stdio import mcp as v2_mcp
from gsd_browser.mcp_tool_policy import KNOWN_MCP_TOOLS


def _tool_names_from_docs() -> set[str]:
    root = Path(__file__).resolve().parents[2]
    doc = root / "docs" / "api" / "MCP_TOOLS.md"
    text = doc.read_text(encoding="utf-8")
    text = text.split("\n## Tools (planned", 1)[0]
    return set(re.findall(r"^### `([^`]+)`", text, flags=re.MULTILINE))


def _tool_names_from_server_tools_list() -> set[str]:
    tools = asyncio.run(v2_mcp._list_tools_mcp())  # noqa: SLF001
    return {tool.name for tool in tools}


def test_v2_tools_list_matches_mcp_tools_doc_exactly() -> None:
    expected = _tool_names_from_docs()
    assert expected == set(KNOWN_MCP_TOOLS)
    assert _tool_names_from_server_tools_list() == expected
