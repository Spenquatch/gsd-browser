"""Local browser bootstrap helpers.

browser-use v0.11+ drives Chromium/Chrome via CDP but still requires a local
chromium-based browser binary to launch. In production installs (pipx), we
proactively ensure a browser exists by installing Playwright's Chromium bundle
using the *current* Python environment (no uv/uvx dependency).
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


def detect_local_browser_executable() -> str | None:
    """Return a local browser executable path if one is available, else None."""

    # Allow users/operators to pin an explicit browser path.
    pinned = (os.getenv("GSD_BROWSER_BROWSER_EXECUTABLE_PATH") or "").strip()
    if pinned:
        path = Path(pinned).expanduser()
        if path.exists() and path.is_file():
            return str(path)
        return None

    try:
        # Prefer the browser-use internal detector since it matches its runtime behavior.
        from browser_use.browser.watchdogs.local_browser_watchdog import (  # type: ignore[import-not-found]
            LocalBrowserWatchdog,
        )

        found = LocalBrowserWatchdog._find_installed_browser_path()  # noqa: SLF001
        return str(found) if found else None
    except Exception:
        return None


def install_playwright_chromium(*, with_deps: bool = False) -> subprocess.CompletedProcess[str]:
    """Install Playwright Chromium into the user's cache.

    Uses the current interpreter so pipx installs work without requiring uv/uvx.
    """

    cmd: list[str] = [sys.executable, "-m", "playwright", "install", "chromium"]
    if with_deps and platform.system() == "Linux":
        cmd.append("--with-deps")
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def should_use_with_deps() -> bool:
    """Best-effort heuristic to decide if we can use `playwright install --with-deps`."""

    if platform.system() != "Linux":
        return False
    if os.geteuid() == 0:
        return True
    return False

