"""Browser state persistence helpers.

This module defines:
- where GSD stores browser storage state files
- how to interactively capture a Playwright-compatible storage_state JSON file

Note: browser-use runs via CDP, but it can load Playwright-compatible storage_state files.
Playwright is used here only for the interactive login capture flow.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

from playwright.async_api import async_playwright


def normalize_browser_state_id(state_id: str) -> str:
    """Normalize a browser state id into a safe filename component."""

    candidate = str(state_id).strip().lower()
    if not candidate:
        raise ValueError("state_id must be a non-empty string.")
    if candidate == "default":
        return candidate
    for ch in candidate:
        if ch.isalnum() or ch in {"-", "_"}:
            continue
        raise ValueError("state_id may only contain letters, numbers, '-' or '_'.")
    return candidate


def browser_state_path_for_id(state_id: str | None) -> Path:
    """Return the storage_state JSON path for a given state id."""

    base_dir = Path(os.path.expanduser("~/.gsd/browser_state"))
    if state_id is None:
        return base_dir / "state.json"

    normalized = normalize_browser_state_id(state_id)
    if normalized == "default":
        return base_dir / "state.json"
    return base_dir / "states" / f"{normalized}.json"


async def _wait_for_browser_disconnected(*, browser: object, timeout_ms: float) -> None:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[None] = loop.create_future()

    def _on_disconnected(*_args: object, **_kwargs: object) -> None:
        if not future.done():
            future.set_result(None)

    on = getattr(browser, "on", None)
    if not callable(on):
        # Fallback: no event emitter available; sleep until timeout (or forever).
        if timeout_ms > 0:
            await asyncio.sleep(timeout_ms / 1000.0)
        else:
            while True:
                await asyncio.sleep(3600)
        return

    on("disconnected", _on_disconnected)
    if timeout_ms > 0:
        await asyncio.wait_for(future, timeout=timeout_ms / 1000.0)
    else:
        await future


def _resolve_cdp_ws_url(*, endpoint: str, timeout_s: float = 3.0) -> str:
    parsed = urlparse(str(endpoint))
    if parsed.scheme in {"ws", "wss"}:
        return str(endpoint)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported cdp_url scheme: {parsed.scheme!r}")

    base = str(endpoint).rstrip("/")
    version_url = f"{base}/json/version"
    try:
        with urlopen(version_url, timeout=float(timeout_s)) as resp:  # noqa: S310
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001
        raise ConnectionError(
            f"Failed to fetch {version_url}: {type(exc).__name__}: {exc}"
        ) from exc

    raw_ws = data.get("webSocketDebuggerUrl")
    if not isinstance(raw_ws, str) or not raw_ws.strip():
        raise ConnectionError(f"No webSocketDebuggerUrl in {version_url} response.")

    ws_parsed = urlparse(raw_ws.strip())
    # Chrome often returns ws://127.0.0.1:9222/... even when accessed via another IP.
    # Replace with the host:port we successfully reached.
    fixed = ws_parsed._replace(netloc=parsed.netloc)
    return urlunparse(fixed)


async def capture_state_interactive(
    *,
    url: str | None,
    state_id: str | None,
    close_timeout_ms: float = 0,
    browser_channel: str | None = None,
    executable_path: str | None = None,
) -> Path:
    """Launch a visible browser for login and persist the resulting storage_state JSON."""

    state_path = browser_state_path_for_id(state_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        launch_kwargs: dict[str, object] = {"headless": False}
        if browser_channel:
            launch_kwargs["channel"] = str(browser_channel)
        if executable_path:
            launch_kwargs["executable_path"] = str(executable_path)

        browser = await playwright.chromium.launch(**launch_kwargs)  # type: ignore[arg-type]
        context = await browser.new_context()
        page = await context.new_page()
        if url:
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except Exception:
                # Interactive mode: if initial navigation is slow/blocked, let the user drive.
                pass

        # Playwright defaults many waits to 30s; for interactive login capture we want to wait
        # until the user closes the browser window (or the page is otherwise closed).
        await page.wait_for_event("close", timeout=close_timeout_ms)

        await context.storage_state(path=str(state_path))
        try:
            state_path.chmod(0o600)
        except OSError:
            pass

        await context.close()
        await browser.close()

    return state_path


async def capture_state_over_cdp(
    *,
    cdp_url: str,
    url: str | None,
    state_id: str | None,
    close_timeout_ms: float = 0,
    auto_save_interval_s: float = 5.0,
) -> Path:
    """Attach to an existing Chromium instance via CDP and export storage_state.

    This is useful for capturing state from a non-Playwright-launched browser (e.g. Windows
    Chrome from WSL). A small autosave loop runs while waiting for the page to close so
    abrupt browser shutdowns still tend to produce a usable state file.
    """

    state_path = browser_state_path_for_id(state_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    normalized_interval = max(0.5, float(auto_save_interval_s))

    async with async_playwright() as playwright:
        ws_url = _resolve_cdp_ws_url(endpoint=cdp_url)
        browser = await playwright.chromium.connect_over_cdp(ws_url)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()

        stop = asyncio.Event()

        async def _save_once() -> None:
            try:
                await context.storage_state(path=str(state_path))
                try:
                    state_path.chmod(0o600)
                except OSError:
                    pass
            except Exception:
                return

        async def _autosave_loop() -> None:
            while not stop.is_set():
                await _save_once()
                try:
                    await asyncio.wait_for(stop.wait(), timeout=normalized_interval)
                except TimeoutError:
                    continue

        autosave_task = asyncio.create_task(_autosave_loop())
        try:
            # Optionally open/navigate a page, but prefer a manual user-driven browser session
            # to avoid sites treating the capture as automated.
            if url:
                try:
                    page = await context.new_page()
                    await page.goto(url, wait_until="domcontentloaded")
                except Exception:
                    pass

            # Wait for the browser to disconnect (typically when the user closes the browser).
            await _wait_for_browser_disconnected(browser=browser, timeout_ms=close_timeout_ms)
        finally:
            stop.set()
            try:
                await autosave_task
            except Exception:
                pass

        await _save_once()

    return state_path


async def open_with_state_interactive(
    *,
    url: str | None,
    state_id: str | None,
    close_timeout_ms: float = 0,
    browser_channel: str | None = None,
    executable_path: str | None = None,
    save_back: bool = False,
) -> Path:
    """Launch a visible browser with a saved storage_state loaded for manual verification.

    This is intended for humans to confirm a saved state is valid (e.g. signed in) by
    browsing normally. If save_back is True, the state file is overwritten on exit.
    """

    state_path = browser_state_path_for_id(state_id)
    if not state_path.exists():
        raise FileNotFoundError(f"State file not found: {state_path}")

    async with async_playwright() as playwright:
        launch_kwargs: dict[str, object] = {"headless": False}
        if browser_channel:
            launch_kwargs["channel"] = str(browser_channel)
        if executable_path:
            launch_kwargs["executable_path"] = str(executable_path)

        browser = await playwright.chromium.launch(**launch_kwargs)  # type: ignore[arg-type]
        context = await browser.new_context(storage_state=str(state_path))
        page = await context.new_page()
        if url:
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except Exception:
                pass

        await _wait_for_browser_disconnected(browser=browser, timeout_ms=close_timeout_ms)

        if save_back:
            await context.storage_state(path=str(state_path))
            try:
                state_path.chmod(0o600)
            except OSError:
                pass

    return state_path


async def open_with_state_over_cdp(
    *,
    cdp_url: str,
    url: str | None,
    state_id: str | None,
    close_timeout_ms: float = 0,
    save_back: bool = False,
) -> Path:
    """Open a state-backed context inside an existing browser via CDP.

    This is useful on WSL: attach to Windows Chrome over CDP and open an incognito-like
    context that loads the saved storage_state for manual verification.
    """

    state_path = browser_state_path_for_id(state_id)
    if not state_path.exists():
        raise FileNotFoundError(f"State file not found: {state_path}")

    async with async_playwright() as playwright:
        ws_url = _resolve_cdp_ws_url(endpoint=cdp_url)
        browser = await playwright.chromium.connect_over_cdp(ws_url)
        context = await browser.new_context(storage_state=str(state_path))
        page = await context.new_page()
        if url:
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except Exception:
                pass

        await _wait_for_browser_disconnected(browser=browser, timeout_ms=close_timeout_ms)

        if save_back:
            await context.storage_state(path=str(state_path))
            try:
                state_path.chmod(0o600)
            except OSError:
                pass

    return state_path
