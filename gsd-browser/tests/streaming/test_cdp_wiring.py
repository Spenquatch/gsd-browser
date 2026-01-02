from __future__ import annotations

import asyncio
import base64
import inspect
import time
from collections.abc import Callable
from typing import Any

from gsd_browser.screenshot_manager import ScreenshotManager
from gsd_browser.streaming.cdp_screencast import CdpScreencastStreamer
from gsd_browser.streaming.server import DEFAULT_STREAM_NAMESPACE, ControlState, StreamingRuntime
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


class FakeAsyncServer:
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


class FakeCdpSession:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self.send_calls: list[tuple[str, dict[str, Any] | None]] = []

    def on(self, event: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        self.handlers[event] = handler

    async def send(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.send_calls.append((method, params))

    def trigger(self, event: str, params: dict[str, Any]) -> None:
        handler = self.handlers.get(event)
        if handler is None:
            raise AssertionError(f"No handler registered for {event!r}")
        handler(params)


class FakeContext:
    def __init__(self, session: FakeCdpSession) -> None:
        self._session = session

    async def new_cdp_session(self, _page: Any) -> FakeCdpSession:
        return self._session


class FakePage:
    def __init__(self, session: FakeCdpSession) -> None:
        self.context = FakeContext(session)


def test_cdp_start_wires_handler_and_start_screencast() -> None:
    async def _exercise() -> None:
        sio = FakeAsyncServer()
        stats = StreamingStats(streaming_mode="cdp", frame_queue_max=2)
        screenshots = ScreenshotManager()
        session = FakeCdpSession()
        page = FakePage(session)

        streamer = CdpScreencastStreamer(
            sio=sio,  # type: ignore[arg-type]
            stats=stats,
            screenshot_manager=screenshots,
            quality="med",
            namespace=DEFAULT_STREAM_NAMESPACE,
            frame_queue_max=2,
            sample_every_n=999,
        )

        await streamer.start(page=page, session_id="sess-1")

        assert "Page.screencastFrame" in session.handlers
        assert any(method == "Page.startScreencast" for method, _ in session.send_calls)

        session.trigger(
            "Page.screencastFrame",
            {"data": "", "metadata": {"foo": "bar"}, "sessionId": "ack-1"},
        )
        await _wait_for(lambda: any(m == "Page.screencastFrameAck" for m, _ in session.send_calls))
        assert stats.frames_received == 1

        await streamer.stop()

    _run(_exercise())


def test_cdp_frame_callback_updates_stats_and_tracks_drops() -> None:
    async def _exercise() -> None:
        sio = FakeAsyncServer()
        stats = StreamingStats(streaming_mode="cdp", frame_queue_max=1)
        screenshots = ScreenshotManager()
        session = FakeCdpSession()

        streamer = CdpScreencastStreamer(
            sio=sio,  # type: ignore[arg-type]
            stats=stats,
            screenshot_manager=screenshots,
            quality="med",
            namespace=DEFAULT_STREAM_NAMESPACE,
            frame_queue_max=1,
        )

        streamer._running = True
        streamer._cdp_session = session

        await streamer._on_frame(
            params={"data": "", "metadata": {}, "sessionId": "ack-1"},
            session_id="sess-1",
        )
        await streamer._on_frame(
            params={"data": "", "metadata": {}, "sessionId": "ack-2"},
            session_id="sess-1",
        )

        assert stats.frames_received == 2
        assert stats.frames_dropped == 1
        assert [m for m, _ in session.send_calls if m == "Page.screencastFrameAck"] == [
            "Page.screencastFrameAck",
            "Page.screencastFrameAck",
        ]

    _run(_exercise())


def test_cdp_sender_samples_and_records_screenshot_and_sampler_totals() -> None:
    async def _exercise() -> None:
        sio = FakeAsyncServer()
        stats = StreamingStats(streaming_mode="cdp", frame_queue_max=2)
        screenshots = ScreenshotManager()
        session = FakeCdpSession()

        streamer = CdpScreencastStreamer(
            sio=sio,  # type: ignore[arg-type]
            stats=stats,
            screenshot_manager=screenshots,
            quality="med",
            namespace=DEFAULT_STREAM_NAMESPACE,
            frame_queue_max=2,
            sample_every_n=1,
        )
        streamer._running = True
        streamer._cdp_session = session

        image_bytes = b"not-a-real-jpeg"
        data_base64 = base64.b64encode(image_bytes).decode("ascii")

        sender_task = asyncio.create_task(streamer._sender_loop(session_id="sess-1"))
        try:
            await streamer._on_frame(
                params={"data": data_base64, "metadata": {"k": "v"}, "sessionId": "ack-1"},
                session_id="sess-1",
            )

            await _wait_for(lambda: any(e["event"] == "frame" for e in sio.emits))
            await _wait_for(lambda: stats.sampler_frames_stored == 1)

            assert stats.frames_received == 1
            assert stats.frames_emitted == 1
            assert stats.sampler_frames_seen == 1
            assert stats.sampler_frames_stored == 1

            stored = screenshots.get_screenshots(last_n=1, screenshot_type="stream_sample")
            assert stored
            assert stored[0]["session_id"] == "sess-1"
            assert stored[0]["mime_type"] == "image/jpeg"
            assert stored[0]["metadata"]["streaming_mode"] == "cdp"
            assert stored[0]["metadata"]["seq"] == 1
        finally:
            sender_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass

    _run(_exercise())


def test_cdp_sampler_seen_increments_even_on_decode_failure() -> None:
    async def _exercise() -> None:
        sio = FakeAsyncServer()
        stats = StreamingStats(streaming_mode="cdp", frame_queue_max=2)
        screenshots = ScreenshotManager()
        session = FakeCdpSession()

        streamer = CdpScreencastStreamer(
            sio=sio,  # type: ignore[arg-type]
            stats=stats,
            screenshot_manager=screenshots,
            quality="med",
            namespace=DEFAULT_STREAM_NAMESPACE,
            frame_queue_max=2,
            sample_every_n=1,
        )
        streamer._running = True
        streamer._cdp_session = session

        sender_task = asyncio.create_task(streamer._sender_loop(session_id="sess-1"))
        try:
            await streamer._on_frame(
                params={"data": "a", "metadata": {}, "sessionId": "ack-1"},
                session_id="sess-1",
            )

            await _wait_for(lambda: stats.frames_emitted == 1)

            assert stats.sampler_frames_seen == 1
            assert stats.sampler_frames_stored == 0
            assert screenshots.get_screenshots(screenshot_type="stream_sample") == []
        finally:
            sender_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass

    _run(_exercise())


def test_emit_browser_update_emits_and_records_stream_sample() -> None:
    async def _exercise() -> None:
        sio = FakeAsyncServer()
        stats = StreamingStats(streaming_mode="screenshot", frame_queue_max=1)
        screenshots = ScreenshotManager()

        runtime = StreamingRuntime(
            asgi_app=None,
            api_app=None,  # type: ignore[arg-type]
            sio=sio,  # type: ignore[arg-type]
            stats=stats,
            screenshots=screenshots,
            cdp_streamer=None,  # type: ignore[arg-type]
            control_state=ControlState(),
        )

        image_bytes = b"pngbytes"
        await runtime.emit_browser_update(
            session_id="sess-2",
            image_bytes=image_bytes,
            mime_type="image/png",
            timestamp=123.0,
            metadata={"hello": "world"},
        )

        assert sio.emits
        emitted = sio.emits[0]
        assert emitted["event"] == "browser_update"
        assert emitted["namespace"] == DEFAULT_STREAM_NAMESPACE
        assert emitted["payload"]["session_id"] == "sess-2"
        assert emitted["payload"]["timestamp"] == 123.0
        assert emitted["payload"]["mime_type"] == "image/png"
        assert emitted["payload"]["image_base64"] == base64.b64encode(image_bytes).decode("ascii")
        assert emitted["payload"]["metadata"]["hello"] == "world"

        stored = screenshots.get_screenshots(last_n=1, screenshot_type="stream_sample")
        assert stored
        assert stored[0]["session_id"] == "sess-2"
        assert stored[0]["mime_type"] == "image/png"
        assert stored[0]["metadata"]["streaming_mode"] == "screenshot"
        assert stored[0]["metadata"]["hello"] == "world"

        assert stats.sampler_frames_seen == 0
        assert stats.sampler_frames_stored == 0

    _run(_exercise())
