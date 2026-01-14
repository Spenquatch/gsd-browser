#!/usr/bin/env python3
"""Print MCP configuration snippet for this template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_repo_src = Path(__file__).resolve().parents[1] / "src"
if _repo_src.exists():
    sys.path.insert(0, str(_repo_src))

from gsd_browser.config import load_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Print MCP config snippet for gsd (legacy alias: "gsd-browser").'
    )
    parser.add_argument(
        "--format",
        choices=("json", "toml"),
        default="json",
        help="Output format",
    )
    args = parser.parse_args()
    settings = load_settings(strict=False)
    if args.format == "toml":
        print(settings.to_mcp_toml())
    else:
        print(settings.to_mcp_snippet())


if __name__ == "__main__":
    main()
