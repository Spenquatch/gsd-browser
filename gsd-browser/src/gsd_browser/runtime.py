"""Shared in-process runtime state (screenshots, dashboard server)."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass

from .config import Settings, load_settings
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


class AppRuntime:
    def __init__(self) -> None:
        self.screenshots = ScreenshotManager()
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
                return existing

            effective_settings = settings or load_settings(strict=False)
            runtime = create_streaming_app(
                settings=effective_settings, screenshots=self.screenshots
            )

            thread = threading.Thread(
                target=_run_uvicorn_in_thread,
                kwargs={"runtime": runtime, "host": host, "port": port},
                name="gsd-browser-dashboard",
                daemon=True,
            )
            thread.start()

            server = DashboardServer(host=host, port=port, runtime=runtime, thread=thread)
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


def _run_uvicorn_in_thread(*, runtime: StreamingRuntime, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(runtime.asgi_app, host=host, port=port, log_level="info", access_log=False)


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
