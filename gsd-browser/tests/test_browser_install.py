from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from gsd_browser import browser_install


def _touch_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    path.chmod(0o755)


def test_detect_local_browser_uses_pinned_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = tmp_path / "bin" / "chrome"
    _touch_executable(exe)
    monkeypatch.setenv("GSD_BROWSER_EXECUTABLE_PATH", str(exe))
    assert browser_install.detect_local_browser_executable() == str(exe)


def test_detect_local_browser_uses_browser_use_detector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = tmp_path / "bin" / "chrome"
    _touch_executable(exe)

    browser_use_mod = ModuleType("browser_use")
    browser_mod = ModuleType("browser_use.browser")
    watchdogs_mod = ModuleType("browser_use.browser.watchdogs")
    local_watchdog_mod = ModuleType("browser_use.browser.watchdogs.local_browser_watchdog")

    class LocalBrowserWatchdog:
        @staticmethod
        def _find_installed_browser_path() -> str:
            return str(exe)

    local_watchdog_mod.LocalBrowserWatchdog = LocalBrowserWatchdog

    monkeypatch.setitem(sys.modules, "browser_use", browser_use_mod)
    monkeypatch.setitem(sys.modules, "browser_use.browser", browser_mod)
    monkeypatch.setitem(sys.modules, "browser_use.browser.watchdogs", watchdogs_mod)
    monkeypatch.setitem(
        sys.modules,
        "browser_use.browser.watchdogs.local_browser_watchdog",
        local_watchdog_mod,
    )

    assert browser_install.detect_local_browser_executable() == str(exe)
