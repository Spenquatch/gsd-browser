#!/usr/bin/env python3
"""Quick fallback LLM test - runs 4 selected scenarios to test Haiku + Sonnet fallback."""

from __future__ import annotations

import sys

from gsd_browser.real_world_sanity import main

# Run with only 4 selected scenarios
# - 2 simple/medium (likely to pass with Haiku)
# - 2 complex (likely to trigger fallback to Sonnet)
if __name__ == "__main__":
    scenarios_to_run = [
        "wikipedia-openai-first-sentence",  # Simple (2 steps)
        "hackernews-top-story",             # Medium (3-5 steps)
        "github-search-and-stars",          # Medium (3 steps)
        "npm-package-deep-research",        # High (6-7 steps) - likely to trigger fallback!
    ]

    # Build args with repeated --scenario flags
    args = sys.argv[1:]
    for scenario in scenarios_to_run:
        args.extend(["--scenario", scenario])

    main(args)
