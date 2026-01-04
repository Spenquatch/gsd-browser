#!/usr/bin/env python3
"""Thin wrapper for `python -m gsd_browser.real_world_sanity`."""

from __future__ import annotations

import sys

from gsd_browser.real_world_sanity import main

if __name__ == "__main__":
    main(sys.argv[1:])
