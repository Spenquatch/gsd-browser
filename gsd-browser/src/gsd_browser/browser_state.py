"""Browser state persistence helpers.

This module defines:
- where GSD stores browser storage state files
- how to capture and re-open Playwright-compatible ``storage_state`` JSON files

GSD uses ``browser-use`` for browser automation. ``browser-use`` is CDP-based and can both
load and export Playwright-compatible storage state files.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen


def _infer_local_browser_executable() -> str | None:
    """Best-effort local browser detection for browser-use headful flows."""

    try:
        from .browser_install import detect_local_browser_executable

        return detect_local_browser_executable()
    except Exception:
        return None


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


def _load_browser_use_session_class() -> type[object]:
    try:
        from browser_use import BrowserSession  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "browser-use is not installed. Reinstall gsd with browser-use enabled."
        ) from exc
    return BrowserSession


async def _browser_use_connect(session: object) -> None:
    connect = getattr(session, "connect", None)
    if callable(connect):
        result = connect()
        if inspect.isawaitable(result):
            await result
        return

    start = getattr(session, "start", None)
    if callable(start):
        result = start()
        if inspect.isawaitable(result):
            await result
        return

    get_or_create = getattr(session, "get_or_create_cdp_session", None)
    if callable(get_or_create):
        result = get_or_create()
        if inspect.isawaitable(result):
            await result
        return

    raise AttributeError("BrowserSession has no connect/start/get_or_create_cdp_session")


async def _browser_use_stop(session: object) -> None:
    stop = getattr(session, "stop", None)
    if not callable(stop):
        return
    result = stop()
    if inspect.isawaitable(result):
        await result


async def _browser_use_navigate(session: object, url: str) -> None:
    navigate = getattr(session, "navigate_to", None)
    if callable(navigate):
        result = navigate(url, new_tab=False)
        if inspect.isawaitable(result):
            await result
        return

    # Fall back to best-effort API surface.
    goto = getattr(session, "goto", None)
    if callable(goto):
        result = goto(url)
        if inspect.isawaitable(result):
            await result


async def _browser_use_export_storage_state(session: object, *, output_path: Path) -> None:
    export = getattr(session, "export_storage_state", None)
    if not callable(export):
        raise AttributeError("BrowserSession.export_storage_state is unavailable")

    try:
        result = export(output_path=str(output_path))
    except TypeError:
        # Older/newer browser-use may take output_path as positional or `path=`.
        try:
            result = export(str(output_path))
        except TypeError:
            result = export(path=str(output_path))

    if inspect.isawaitable(result):
        await result

    try:
        output_path.chmod(0o600)
    except OSError:
        pass


async def _browser_use_poll_until_disconnect(
    session: object,
    *,
    close_timeout_ms: float,
    poll_interval_s: float,
    stop_event: asyncio.Event | None = None,
) -> None:
    timeout_s = max(0.0, float(close_timeout_ms)) / 1000.0
    poll_s = max(0.25, float(poll_interval_s))
    started = time.monotonic()

    get_or_create = getattr(session, "get_or_create_cdp_session", None)
    if not callable(get_or_create):
        if stop_event is not None:
            if timeout_s > 0:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=timeout_s)
                except TimeoutError:
                    return
            else:
                await stop_event.wait()
            return

        # Fall back to a sleep loop (no disconnect signal available).
        while True:
            if timeout_s > 0 and (time.monotonic() - started) >= timeout_s:
                return
            await asyncio.sleep(poll_s)

    while True:
        if stop_event is not None and stop_event.is_set():
            return
        if timeout_s > 0 and (time.monotonic() - started) >= timeout_s:
            return

        try:
            cdp_session = get_or_create()
            if inspect.isawaitable(cdp_session):
                cdp_session = await cdp_session

            cdp_client = getattr(cdp_session, "cdp_client", None)
            cdp_session_id = getattr(cdp_session, "session_id", None)
            send_obj = getattr(cdp_client, "send", None) if cdp_client is not None else None
            if callable(send_obj):
                # Ping the browser; should fail if the CDP connection is gone.
                try:
                    result = send_obj("Browser.getVersion", session_id=cdp_session_id)
                except TypeError:
                    try:
                        result = send_obj("Browser.getVersion")
                    except TypeError:
                        result = send_obj("Browser.getVersion", None)
                if inspect.isawaitable(result):
                    await result
        except Exception:
            return

        await asyncio.sleep(poll_s)


async def capture_state_interactive(
    *,
    url: str | None,
    state_id: str | None,
    close_timeout_ms: float = 0,
    browser_channel: str | None = None,
    executable_path: str | None = None,
    user_data_dir: str | None = None,
    profile_directory: str | None = None,
    auto_save_interval_s: float = 5.0,
) -> Path:
    """Launch a visible browser (via browser-use) and persist storage_state on close."""

    state_path = browser_state_path_for_id(state_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    inferred = executable_path or _infer_local_browser_executable()
    session_cls = _load_browser_use_session_class()
    session_kwargs: dict[str, object] = {
        "is_local": True,
        "headless": False,
        "user_data_dir": user_data_dir,
        "profile_directory": profile_directory,
    }
    if browser_channel:
        # Back-compat: `--browser-channel chrome` maps to browser-use's `channel` option.
        session_kwargs["channel"] = str(browser_channel)
    if inferred:
        session_kwargs["executable_path"] = inferred

    session = session_cls(**session_kwargs)  # type: ignore[arg-type]

    normalized_interval = max(0.5, float(auto_save_interval_s))

    try:
        try:
            await _browser_use_connect(session)
        except Exception as exc:
            raise RuntimeError(
                "Failed to launch a local browser for state capture. "
                "If you already have Chrome running with remote debugging, pass "
                "--cdp-url http://127.0.0.1:9222. Otherwise, install Chrome/Edge and/or set "
                "GSD_BROWSER_EXECUTABLE_PATH (or pass --executable-path)."
            ) from exc
        if url:
            try:
                await _browser_use_navigate(session, url)
            except Exception:
                pass

        stop = asyncio.Event()

        async def _autosave_loop() -> None:
            consecutive_failures = 0
            while not stop.is_set():
                try:
                    await _browser_use_export_storage_state(session, output_path=state_path)
                    consecutive_failures = 0
                except Exception:
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        stop.set()
                        break
                try:
                    await asyncio.wait_for(stop.wait(), timeout=normalized_interval)
                except TimeoutError:
                    continue

        autosave_task = asyncio.create_task(_autosave_loop())
        try:
            await _browser_use_poll_until_disconnect(
                session,
                close_timeout_ms=close_timeout_ms,
                poll_interval_s=min(1.0, normalized_interval),
                stop_event=stop,
            )
        finally:
            stop.set()
            try:
                await autosave_task
            except Exception:
                pass
    finally:
        try:
            await _browser_use_export_storage_state(session, output_path=state_path)
        except Exception:
            pass
        await _browser_use_stop(session)

    return state_path


async def capture_state_over_cdp(
    *,
    cdp_url: str,
    url: str | None,
    state_id: str | None,
    close_timeout_ms: float = 0,
    auto_save_interval_s: float = 5.0,
) -> Path:
    """Attach to an existing browser via CDP and export storage_state.

    Useful for capturing state from a non-automated browser session, e.g. attaching to a
    manually-launched Windows Chrome instance from WSL.
    """

    state_path = browser_state_path_for_id(state_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    normalized_interval = max(0.5, float(auto_save_interval_s))
    ws_url = _resolve_cdp_ws_url(endpoint=cdp_url)

    session_cls = _load_browser_use_session_class()
    session = session_cls(  # type: ignore[call-arg]
        headless=False,
        cdp_url=ws_url,
        is_local=True,
    )

    try:
        await _browser_use_connect(session)
        if url:
            try:
                await _browser_use_navigate(session, url)
            except Exception:
                pass

        stop = asyncio.Event()

        async def _autosave_loop() -> None:
            consecutive_failures = 0
            while not stop.is_set():
                try:
                    await _browser_use_export_storage_state(session, output_path=state_path)
                    consecutive_failures = 0
                except Exception:
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        stop.set()
                        break
                try:
                    await asyncio.wait_for(stop.wait(), timeout=normalized_interval)
                except TimeoutError:
                    continue

        autosave_task = asyncio.create_task(_autosave_loop())
        try:
            await _browser_use_poll_until_disconnect(
                session,
                close_timeout_ms=close_timeout_ms,
                poll_interval_s=min(1.0, normalized_interval),
                stop_event=stop,
            )
        finally:
            stop.set()
            try:
                await autosave_task
            except Exception:
                pass
    finally:
        try:
            await _browser_use_export_storage_state(session, output_path=state_path)
        except Exception:
            pass
        await _browser_use_stop(session)

    return state_path


async def open_with_state_interactive(
    *,
    url: str | None,
    state_id: str | None,
    close_timeout_ms: float = 0,
    browser_channel: str | None = None,
    executable_path: str | None = None,
    save_back: bool = False,
    user_data_dir: str | None = None,
    profile_directory: str | None = None,
    auto_save_interval_s: float = 5.0,
) -> Path:
    """Launch a visible browser with a saved storage_state loaded for manual verification."""

    state_path = browser_state_path_for_id(state_id)
    if not user_data_dir and not state_path.exists():
        raise FileNotFoundError(f"State file not found: {state_path}")
    state_path.parent.mkdir(parents=True, exist_ok=True)

    inferred = executable_path or _infer_local_browser_executable()
    session_cls = _load_browser_use_session_class()
    session_kwargs: dict[str, object] = {
        "is_local": True,
        "headless": False,
        "user_data_dir": user_data_dir,
        "profile_directory": profile_directory,
    }
    if browser_channel:
        session_kwargs["channel"] = str(browser_channel)
    if inferred:
        session_kwargs["executable_path"] = inferred
    if not user_data_dir:
        session_kwargs["storage_state"] = str(state_path)

    session = session_cls(**session_kwargs)  # type: ignore[arg-type]
    normalized_interval = max(0.5, float(auto_save_interval_s))

    try:
        await _browser_use_connect(session)
        if url:
            try:
                await _browser_use_navigate(session, url)
            except Exception:
                pass

        if save_back:
            started = time.monotonic()
            while True:
                if close_timeout_ms > 0:
                    elapsed = time.monotonic() - started
                    if elapsed >= (float(close_timeout_ms) / 1000.0):
                        break
                try:
                    await _browser_use_export_storage_state(session, output_path=state_path)
                except Exception:
                    break
                await asyncio.sleep(normalized_interval)
        else:
            await _browser_use_poll_until_disconnect(
                session, close_timeout_ms=close_timeout_ms, poll_interval_s=normalized_interval
            )
    finally:
        if save_back:
            try:
                await _browser_use_export_storage_state(session, output_path=state_path)
            except Exception:
                pass
        await _browser_use_stop(session)

    return state_path


async def open_with_state_over_cdp(
    *,
    cdp_url: str,
    url: str | None,
    state_id: str | None,
    close_timeout_ms: float = 0,
    save_back: bool = False,
    auto_save_interval_s: float = 5.0,
) -> Path:
    """Open a state-backed session inside an existing browser via CDP."""

    state_path = browser_state_path_for_id(state_id)
    if not state_path.exists():
        raise FileNotFoundError(f"State file not found: {state_path}")

    ws_url = _resolve_cdp_ws_url(endpoint=cdp_url)
    session_cls = _load_browser_use_session_class()
    session = session_cls(  # type: ignore[call-arg]
        headless=False,
        cdp_url=ws_url,
        storage_state=str(state_path),
        is_local=True,
    )

    normalized_interval = max(0.5, float(auto_save_interval_s))
    try:
        await _browser_use_connect(session)
        if url:
            try:
                await _browser_use_navigate(session, url)
            except Exception:
                pass

        if save_back:
            started = time.monotonic()
            while True:
                if close_timeout_ms > 0:
                    elapsed = time.monotonic() - started
                    if elapsed >= (float(close_timeout_ms) / 1000.0):
                        break
                try:
                    await _browser_use_export_storage_state(session, output_path=state_path)
                except Exception:
                    break
                await asyncio.sleep(normalized_interval)
        else:
            await _browser_use_poll_until_disconnect(
                session, close_timeout_ms=close_timeout_ms, poll_interval_s=normalized_interval
            )
    finally:
        if save_back:
            try:
                await _browser_use_export_storage_state(session, output_path=state_path)
            except Exception:
                pass
        await _browser_use_stop(session)

    return state_path
