"""Local browser bootstrap helpers.

browser-use drives Chromium/Chrome via CDP, but it still requires a local browser binary
to launch when not attaching to an existing CDP endpoint.

GSD prefers:
1) An explicit `GSD_BROWSER_EXECUTABLE_PATH`
2) browser-use's own local browser detector
3) A small set of common platform paths
"""

from __future__ import annotations

import os
import platform
from pathlib import Path


def _common_browser_executable_candidates() -> list[Path]:
    system = platform.system()

    if system == "Windows":
        program_files = os.getenv("ProgramFiles") or r"C:\Program Files"
        program_files_x86 = os.getenv("ProgramFiles(x86)") or r"C:\Program Files (x86)"
        local_app_data = os.getenv("LOCALAPPDATA") or ""
        return [
            Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(local_app_data) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]

    if system == "Darwin":
        return [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            Path("/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"),
        ]

    # Linux / other Unix
    return [
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/chromium-browser"),
        Path("/usr/bin/chromium"),
        Path("/snap/bin/chromium"),
    ]


def detect_local_browser_executable() -> str | None:
    """Return a local browser executable path if one is available, else None."""

    pinned = (os.getenv("GSD_BROWSER_EXECUTABLE_PATH") or "").strip()
    if pinned:
        path = Path(pinned).expanduser()
        if path.exists() and path.is_file():
            return str(path)
        return None

    try:
        from browser_use.browser.watchdogs.local_browser_watchdog import (  # type: ignore[import-not-found]
            LocalBrowserWatchdog,
        )

        found = LocalBrowserWatchdog._find_installed_browser_path()  # noqa: SLF001
        if found:
            candidate = Path(str(found)).expanduser()
            if candidate.exists() and candidate.is_file():
                return str(candidate)
            return None
    except Exception:
        pass

    for candidate in _common_browser_executable_candidates():
        try:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        except OSError:
            continue

    return None

