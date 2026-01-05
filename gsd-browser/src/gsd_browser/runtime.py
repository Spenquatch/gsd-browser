"""Shared in-process runtime state (screenshots, dashboard server)."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from dataclasses import dataclass

from .config import Settings, load_settings
from .run_event_store import RunEventStore
from .screenshot_manager import ScreenshotManager
from .streaming.server import StreamingRuntime, create_streaming_app

DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 5009


@dataclass(frozen=True)
class DashboardServer:
    host: str
    port: int
    runtime: StreamingRuntime
    thread: threading.Thread
    loop: asyncio.AbstractEventLoop | None


class AppRuntime:
    def __init__(self) -> None:
        self.screenshots = ScreenshotManager()
        self.run_events = RunEventStore()
        self._lock = threading.Lock()
        self._dashboard: DashboardServer | None = None

    def dashboard(self) -> DashboardServer | None:
        with self._lock:
            return self._dashboard

    def ensure_dashboard_running(
        self,
        *,
        settings: Settings | None = None,
        host: str = DEFAULT_DASHBOARD_HOST,
        port: int = DEFAULT_DASHBOARD_PORT,
        startup_timeout_s: float = 10.0,
    ) -> DashboardServer:
        with self._lock:
            existing = self._dashboard
            if existing is not None and existing.host == host and existing.port == port:
                loop = existing.loop
                if loop is not None:
                    streamer = getattr(existing.runtime, "cdp_streamer", None)
                    set_emit_loop = getattr(streamer, "set_emit_loop", None)
                    if callable(set_emit_loop):
                        set_emit_loop(loop)
                return existing

            effective_settings = settings or load_settings(strict=False)
            runtime = create_streaming_app(
                settings=effective_settings, screenshots=self.screenshots
            )

            loop_ready = threading.Event()
            loop_holder: dict[str, asyncio.AbstractEventLoop] = {}

            thread = threading.Thread(
                target=_run_uvicorn_in_thread,
                kwargs={
                    "runtime": runtime,
                    "host": host,
                    "port": port,
                    "loop_ready": loop_ready,
                    "loop_holder": loop_holder,
                },
                name="gsd-browser-dashboard",
                daemon=True,
            )
            thread.start()

            loop: asyncio.AbstractEventLoop | None = None
            if loop_ready.wait(timeout=startup_timeout_s):
                loop = loop_holder.get("loop")
                if loop is not None:
                    streamer = getattr(runtime, "cdp_streamer", None)
                    set_emit_loop = getattr(streamer, "set_emit_loop", None)
                    if callable(set_emit_loop):
                        set_emit_loop(loop)

            server = DashboardServer(
                host=host, port=port, runtime=runtime, thread=thread, loop=loop
            )
            self._dashboard = server

        _wait_for_port(host=host, port=port, timeout_s=startup_timeout_s)
        return server


_RUNTIME: AppRuntime | None = None
_RUNTIME_LOCK = threading.Lock()


def get_runtime() -> AppRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = AppRuntime()
        return _RUNTIME


def _run_uvicorn_in_thread(
    *,
    runtime: StreamingRuntime,
    host: str,
    port: int,
    loop_ready: threading.Event,
    loop_holder: dict[str, asyncio.AbstractEventLoop],
) -> None:
    import uvicorn

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop_holder["loop"] = loop
    loop_ready.set()

    config = uvicorn.Config(
        runtime.asgi_app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())


def _wait_for_port(*, host: str, port: int, timeout_s: float) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                result = sock.connect_ex((host, port))
            except OSError:
                result = 1
        if result == 0:
            return
        time.sleep(0.1)
