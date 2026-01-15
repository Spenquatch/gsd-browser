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


def test_playwright_cache_detection_uses_playwright_browsers_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "pw-cache"
    exe = root / "chromium-1234" / "chrome-linux64" / "chrome"
    _touch_executable(exe)

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(root))
    assert browser_install._detect_playwright_cache_executable() == str(exe)  # noqa: SLF001


def test_playwright_cache_detection_handles_browsers_path_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")

    fake_pkg_dir = tmp_path / "site-packages" / "playwright"
    fake_init = fake_pkg_dir / "__init__.py"
    fake_init.parent.mkdir(parents=True, exist_ok=True)
    fake_init.write_text("", encoding="utf-8")

    # PLAYWRIGHT_BROWSERS_PATH=0 installs browsers relative to the bundled driver package.
    exe = (
        fake_pkg_dir
        / "driver"
        / "package"
        / ".local-browsers"
        / "chromium-9999"
        / "chrome-linux64"
        / "chrome"
    )
    _touch_executable(exe)

    fake_playwright = ModuleType("playwright")
    fake_playwright.__file__ = str(fake_init)
    monkeypatch.setitem(sys.modules, "playwright", fake_playwright)

    assert browser_install._detect_playwright_cache_executable() == str(exe)  # noqa: SLF001
