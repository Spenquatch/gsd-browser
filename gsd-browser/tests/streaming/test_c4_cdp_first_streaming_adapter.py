from __future__ import annotations

import asyncio
import base64
import importlib
import inspect
import pkgutil
import time
from collections.abc import Callable
from typing import Any

import pytest

from gsd_browser.screenshot_manager import ScreenshotManager
from gsd_browser.streaming.server import DEFAULT_STREAM_NAMESPACE
from gsd_browser.streaming.stats import StreamingStats


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


async def _wait_for(predicate: Callable[[], bool], *, timeout_s: float = 1.0) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("Timed out waiting for condition")


class _FakeAsyncServer:
    def __init__(self) -> None:
        self.emits: list[dict[str, Any]] = []

    async def emit(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        namespace: str | None = None,
        to: str | None = None,
    ) -> None:
        self.emits.append(
            {
                "event": event,
                "payload": payload,
                "namespace": namespace,
                "to": to,
            }
        )


class _FakeCdpClient:
    def __init__(self) -> None:
        self.send_calls: list[dict[str, Any]] = []
        self.register_calls: list[dict[str, Any]] = []
        self._handlers: dict[str, Callable[..., Any]] = {}

        self.send = _FakeCdpSend(self)
        self.register = _FakeCdpRegister(self)

    def _record_send(
        self, *, method: str, params: dict[str, Any] | None, session_id: str | None
    ) -> None:
        self.send_calls.append({"method": method, "params": params, "session_id": session_id})

    def _record_register(self, *, event: str, handler: Callable[..., Any]) -> None:
        self.register_calls.append({"event": event, "handler": handler})
        self._handlers[event] = handler

    def trigger(self, event: str, payload: dict[str, Any], cdp_session_id: str | None) -> Any:
        handler = self._handlers.get(event)
        if handler is None:
            raise AssertionError(f"No handler registered for {event!r}")
        return handler(payload, cdp_session_id)


class _FakeCdpSend:
    def __init__(self, client: _FakeCdpClient) -> None:
        self._client = client
        self.Page = _FakeCdpSendPage(client)

    async def __call__(
        self, method: str, params: dict[str, Any] | None = None, *, session_id: str | None = None
    ) -> None:
        self._client._record_send(method=method, params=params, session_id=session_id)


class _FakeCdpSendPage:
    def __init__(self, client: _FakeCdpClient) -> None:
        self._client = client

    async def startScreencast(
        self, *, params: dict[str, Any] | None = None, session_id: str | None = None
    ) -> None:
        self._client._record_send(
            method="Page.startScreencast", params=params, session_id=session_id
        )

    async def screencastFrameAck(
        self, *, params: dict[str, Any] | None = None, session_id: str | None = None
    ) -> None:
        self._client._record_send(
            method="Page.screencastFrameAck", params=params, session_id=session_id
        )

    async def stopScreencast(self, *, session_id: str | None = None) -> None:
        self._client._record_send(method="Page.stopScreencast", params=None, session_id=session_id)


class _FakeCdpRegister:
    def __init__(self, client: _FakeCdpClient) -> None:
        self.Page = _FakeCdpRegisterPage(client)


class _FakeCdpRegisterPage:
    def __init__(self, client: _FakeCdpClient) -> None:
        self._client = client

    def screencastFrame(self, handler: Callable[..., Any]) -> None:
        self._client._record_register(event="Page.screencastFrame", handler=handler)


class _FakeBrowserUseCdpSession:
    def __init__(self, *, session_id: str, cdp_client: _FakeCdpClient) -> None:
        self.session_id = session_id
        self.cdp_client = cdp_client


class _FakeBrowserSession:
    def __init__(self, cdp_session: _FakeBrowserUseCdpSession) -> None:
        self._cdp_session = cdp_session

    async def get_or_create_cdp_session(self, *_: Any, **__: Any) -> _FakeBrowserUseCdpSession:
        return self._cdp_session


def _discover_c4_streamer_class() -> type[Any]:
    import gsd_browser.streaming as streaming_pkg

    candidate_modules: list[str] = ["gsd_browser.streaming.cdp_screencast"]
    for info in pkgutil.iter_modules(streaming_pkg.__path__):
        candidate_modules.append(f"{streaming_pkg.__name__}.{info.name}")

    for module_name in candidate_modules:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001
            continue

        for obj in vars(module).values():
            if not inspect.isclass(obj):
                continue
            if obj.__module__ != module.__name__:
                continue
            start = getattr(obj, "start", None)
            stop = getattr(obj, "stop", None)
            if not callable(start) or not callable(stop):
                continue
            try:
                sig = inspect.signature(start)
            except (TypeError, ValueError):
                continue
            if "browser_session" in sig.parameters:
                return obj

    pytest.xfail(
        "C4 CDP-first streaming adapter not implemented yet (expected a streamer with "
        "`start(..., browser_session=..., session_id=...)` somewhere under gsd_browser.streaming)."
    )


def _construct_streamer(
    streamer_cls: type[Any], *, sio: Any, stats: StreamingStats, screenshots: ScreenshotManager
) -> Any:
    sig = inspect.signature(streamer_cls)
    kwargs: dict[str, Any] = {
        "sio": sio,
        "stats": stats,
        "screenshot_manager": screenshots,
        "quality": "med",
        "namespace": DEFAULT_STREAM_NAMESPACE,
        "frame_queue_max": stats.frame_queue_max,
        "sample_every_n": 1,
    }
    return streamer_cls(**{k: v for k, v in kwargs.items() if k in sig.parameters})


async def _call_start(streamer: Any, *, browser_session: Any, session_id: str) -> None:
    start = getattr(streamer, "start", None)
    if not callable(start):
        raise AssertionError("streamer has no start()")
    sig = inspect.signature(start)
    kwargs: dict[str, Any] = {}
    if "browser_session" in sig.parameters:
        kwargs["browser_session"] = browser_session
    if "session_id" in sig.parameters:
        kwargs["session_id"] = session_id
    await start(**kwargs)


async def _maybe_await(value: Any) -> None:
    if inspect.isawaitable(value):
        await value


def test_c4_start_stop_does_not_leak_tasks() -> None:
    async def _exercise() -> None:
        streamer_cls = _discover_c4_streamer_class()

        sio = _FakeAsyncServer()
        stats = StreamingStats(streaming_mode="cdp", frame_queue_max=1)
        screenshots = ScreenshotManager()

        cdp_client = _FakeCdpClient()
        cdp_session = _FakeBrowserUseCdpSession(session_id="cdp-1", cdp_client=cdp_client)
        browser_session = _FakeBrowserSession(cdp_session)

        streamer = _construct_streamer(streamer_cls, sio=sio, stats=stats, screenshots=screenshots)

        current = asyncio.current_task()
        baseline = {task for task in asyncio.all_tasks() if task is not current}

        await _call_start(streamer, browser_session=browser_session, session_id="sess-1")

        assert any(call["method"] == "Page.startScreencast" for call in cdp_client.send_calls)
        assert any(call["event"] == "Page.screencastFrame" for call in cdp_client.register_calls)

        payload = {
            "data": base64.b64encode(b"jpegbytes").decode("ascii"),
            "metadata": {"k": "v"},
            "sessionId": "ack-1",
        }
        await _maybe_await(cdp_client.trigger("Page.screencastFrame", payload, "cdp-1"))
        await _wait_for(
            lambda: any(
                call["method"] == "Page.screencastFrameAck" for call in cdp_client.send_calls
            )
        )

        await streamer.stop()
        await asyncio.sleep(0)

        remaining = {task for task in asyncio.all_tasks() if task is not current}
        assert remaining.issubset(baseline)

    _run(_exercise())


def test_c4_backpressure_increments_drops_and_still_acks() -> None:
    async def _exercise() -> None:
        streamer_cls = _discover_c4_streamer_class()

        sio = _FakeAsyncServer()
        stats = StreamingStats(streaming_mode="cdp", frame_queue_max=1)
        screenshots = ScreenshotManager()
        cdp_client = _FakeCdpClient()
        cdp_session = _FakeBrowserUseCdpSession(session_id="cdp-1", cdp_client=cdp_client)

        streamer = _construct_streamer(streamer_cls, sio=sio, stats=stats, screenshots=screenshots)

        on_frame = getattr(streamer, "_on_frame", None)
        if not callable(on_frame):
            pytest.xfail(
                "C4 streamer does not expose _on_frame for deterministic backpressure tests."
            )

        for attr in ("_running", "_cdp_session", "_cdp"):
            if hasattr(streamer, attr):
                setattr(streamer, attr, True if attr == "_running" else cdp_session)

        params_1 = {"data": "", "metadata": {}, "sessionId": "ack-1"}
        params_2 = {"data": "", "metadata": {}, "sessionId": "ack-2"}

        def _call_kwargs(params: dict[str, Any]) -> dict[str, Any]:
            sig = inspect.signature(on_frame)
            kwargs: dict[str, Any] = {}
            if "params" in sig.parameters:
                kwargs["params"] = params
            elif "event" in sig.parameters:
                kwargs["event"] = params
            if "session_id" in sig.parameters:
                kwargs["session_id"] = "sess-1"
            if "cdp_session_id" in sig.parameters:
                kwargs["cdp_session_id"] = "cdp-1"
            return kwargs

        result = on_frame(**_call_kwargs(params_1))
        await _maybe_await(result)
        result = on_frame(**_call_kwargs(params_2))
        await _maybe_await(result)

        assert stats.frames_received == 2
        assert stats.frames_dropped == 1
        assert [c for c in cdp_client.send_calls if c["method"] == "Page.screencastFrameAck"] == [
            {
                "method": "Page.screencastFrameAck",
                "params": {"sessionId": "ack-1"},
                "session_id": "cdp-1",
            },
            {
                "method": "Page.screencastFrameAck",
                "params": {"sessionId": "ack-2"},
                "session_id": "cdp-1",
            },
        ]

    _run(_exercise())


def test_c4_sampling_records_stream_sample_and_sampler_totals() -> None:
    async def _exercise() -> None:
        streamer_cls = _discover_c4_streamer_class()

        sio = _FakeAsyncServer()
        stats = StreamingStats(streaming_mode="cdp", frame_queue_max=2)
        screenshots = ScreenshotManager()
        cdp_client = _FakeCdpClient()
        cdp_session = _FakeBrowserUseCdpSession(session_id="cdp-1", cdp_client=cdp_client)

        streamer = _construct_streamer(streamer_cls, sio=sio, stats=stats, screenshots=screenshots)

        sender_loop = getattr(streamer, "_sender_loop", None)
        on_frame = getattr(streamer, "_on_frame", None)
        if not callable(sender_loop) or not callable(on_frame):
            pytest.xfail(
                "C4 streamer does not expose _sender_loop/_on_frame for deterministic sampling tests."
            )

        for attr in ("_running", "_cdp_session", "_cdp"):
            if hasattr(streamer, attr):
                setattr(streamer, attr, True if attr == "_running" else cdp_session)

        sender_task = asyncio.create_task(sender_loop(session_id="sess-1"))
        try:
            image_bytes = b"not-a-real-jpeg"
            data_base64 = base64.b64encode(image_bytes).decode("ascii")

            sig = inspect.signature(on_frame)
            kwargs: dict[str, Any] = {}
            if "params" in sig.parameters:
                kwargs["params"] = {
                    "data": data_base64,
                    "metadata": {"k": "v"},
                    "sessionId": "ack-1",
                }
            else:
                kwargs["event"] = {
                    "data": data_base64,
                    "metadata": {"k": "v"},
                    "sessionId": "ack-1",
                }
            if "session_id" in sig.parameters:
                kwargs["session_id"] = "sess-1"
            if "cdp_session_id" in sig.parameters:
                kwargs["cdp_session_id"] = "cdp-1"

            await _maybe_await(on_frame(**kwargs))
            await _wait_for(
                lambda: any(e["event"] == "frame" for e in sio.emits) or bool(sio.emits)
            )
            await _wait_for(lambda: stats.sampler_frames_stored == 1)

            stored = screenshots.get_screenshots(last_n=1, screenshot_type="stream_sample")
            assert stored
            assert stored[0]["session_id"] == "sess-1"
            assert stored[0]["metadata"]["streaming_mode"] == "cdp"

            assert stats.sampler_frames_seen == 1
            assert stats.sampler_frames_stored == 1
        finally:
            sender_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass

    _run(_exercise())


def test_c4_cdp_unavailable_fallback_does_not_raise_or_start_tasks() -> None:
    async def _exercise() -> None:
        streamer_cls = _discover_c4_streamer_class()

        sio = _FakeAsyncServer()
        stats = StreamingStats(streaming_mode="cdp", frame_queue_max=1)
        screenshots = ScreenshotManager()
        streamer = _construct_streamer(streamer_cls, sio=sio, stats=stats, screenshots=screenshots)

        class _NoCdpBrowserSession:
            pass

        current = asyncio.current_task()
        baseline = {task for task in asyncio.all_tasks() if task is not current}

        await _call_start(streamer, browser_session=_NoCdpBrowserSession(), session_id="sess-1")
        await streamer.stop()
        await asyncio.sleep(0)

        remaining = {task for task in asyncio.all_tasks() if task is not current}
        assert remaining.issubset(baseline)
        assert stats.frames_received == 0

    _run(_exercise())
