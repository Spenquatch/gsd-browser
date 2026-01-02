#!/usr/bin/env python3
"""Thin wrapper for `python -m gsd_browser.mcp_tool_smoke`."""

from __future__ import annotations

import sys

from gsd_browser.mcp_tool_smoke import main

if __name__ == "__main__":
    main(sys.argv[1:])
