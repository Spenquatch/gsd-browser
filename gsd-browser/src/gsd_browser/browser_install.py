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
from glob import glob
from pathlib import Path


def _detect_playwright_chromium_executable() -> str | None:
    """Ask Playwright where Chromium is installed (works with PLAYWRIGHT_BROWSERS_PATH=0)."""

    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

        playwright = sync_playwright().start()
        try:
            path = getattr(playwright.chromium, "executable_path", None)
        finally:
            playwright.stop()

        if not path:
            return None
        exe = Path(str(path)).expanduser()
        if exe.exists() and exe.is_file():
            return str(exe)
        return None
    except Exception:
        return None


def _detect_playwright_cache_executable() -> str | None:
    """Detect Playwright-installed Chromium by checking known cache locations."""

    browsers_path = (os.getenv("PLAYWRIGHT_BROWSERS_PATH") or "").strip()

    roots: list[Path] = []
    if browsers_path:
        if browsers_path == "0":
            try:
                import playwright  # type: ignore[import-not-found]

                package_dir = Path(playwright.__file__).resolve().parent
                roots.append(package_dir / ".local-browsers")
                roots.append(package_dir / "driver" / "package" / ".local-browsers")
            except Exception:
                pass
        else:
            roots.append(Path(browsers_path).expanduser())
    else:
        system = platform.system()
        if system == "Darwin":
            roots.append(Path("~/Library/Caches/ms-playwright").expanduser())
        elif system == "Windows":
            # Best-effort; Playwright expands these for Windows.
            local_app_data = os.getenv("LOCALAPPDATA")
            if local_app_data:
                roots.append(Path(local_app_data) / "ms-playwright")
        else:
            roots.append(Path("~/.cache/ms-playwright").expanduser())

    patterns: list[str] = []
    system = platform.system()
    for root in roots:
        if system == "Darwin":
            patterns += [
                str(
                    root
                    / "chromium-*"
                    / "chrome-mac"
                    / "Chromium.app"
                    / "Contents"
                    / "MacOS"
                    / "Chromium"
                ),
                str(
                    root
                    / "chromium_headless_shell-*"
                    / "chrome-mac"
                    / "Chromium.app"
                    / "Contents"
                    / "MacOS"
                    / "Chromium"
                ),
            ]
        elif system == "Windows":
            patterns += [
                str(root / "chromium-*" / "chrome-win" / "chrome.exe"),
                str(root / "chromium_headless_shell-*" / "chrome-win" / "chrome.exe"),
            ]
        else:
            patterns += [
                str(root / "chromium-*" / "chrome-linux*" / "chrome"),
                str(root / "chromium_headless_shell-*" / "chrome-linux*" / "chrome"),
            ]

    candidates: list[Path] = []
    for pattern in patterns:
        for match in glob(pattern):
            candidates.append(Path(match))

    for candidate in sorted(candidates):
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


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
        if found:
            return str(found)
        return _detect_playwright_cache_executable() or _detect_playwright_chromium_executable()
    except Exception:
        # Fall back to Playwright-native detection. This is slower but more robust across
        # PLAYWRIGHT_BROWSERS_PATH configurations.
        return _detect_playwright_cache_executable() or _detect_playwright_chromium_executable()


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
