#!/usr/bin/env python3
"""Print MCP configuration snippet for this template."""

from __future__ import annotations

import argparse

from gsd_browser.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Print MCP config snippet for gsd-browser.")
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
