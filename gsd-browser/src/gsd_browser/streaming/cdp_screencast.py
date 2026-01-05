"""CDP screencast streamer.

Primary integration is browser-use CDP sessions (C4). A legacy Playwright entrypoint remains
for local tooling but must not be used as a fallback when browser-use CDP attach fails.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import logging
import time
from dataclasses import dataclass
from typing import Any

import socketio

from ..screenshot_manager import ScreenshotManager
from .env import StreamingQuality
from .stats import StreamingStats

logger = logging.getLogger("gsd_browser.streaming")


@dataclass(frozen=True)
class CdpFrame:
    seq: int
    session_id: str
    received_ts: float
    data_base64: str
    metadata: dict[str, Any]


def _quality_to_cdp_params(quality: StreamingQuality) -> dict[str, Any]:
    if quality == "low":
        return {"format": "jpeg", "quality": 35, "maxWidth": 800, "maxHeight": 600}
    if quality == "high":
        return {"format": "jpeg", "quality": 80, "maxWidth": 1920, "maxHeight": 1080}
    return {"format": "jpeg", "quality": 60, "maxWidth": 1280, "maxHeight": 720}


class CdpScreencastStreamer:
    def __init__(
        self,
        *,
        sio: socketio.AsyncServer,
        stats: StreamingStats,
        screenshot_manager: ScreenshotManager,
        quality: StreamingQuality,
        namespace: str,
        frame_queue_max: int,
        sample_every_n: int = 10,
    ) -> None:
        self._sio = sio
        self._namespace = namespace
        self._stats = stats
        self._screenshot_manager = screenshot_manager
        self._quality = quality
        self._frame_queue: asyncio.Queue[CdpFrame] = asyncio.Queue(maxsize=frame_queue_max)
        self._sample_every_n = max(1, sample_every_n)

        self._lifecycle_lock = asyncio.Lock()
        self._emit_loop: asyncio.AbstractEventLoop | None = None

        self._seq = 0
        self._cdp_session: Any | None = None  # Playwright CDP session (legacy).
        self._active_run_session_id: str | None = None
        self._active_cdp_session_id: str | None = None  # browser-use CDP session id.
        self._active_cdp_client: Any | None = None
        self._registered_cdp_clients: set[int] = set()
        self._focus_task: asyncio.Task[None] | None = None
        self._sender_task: asyncio.Task[None] | None = None
        self._running = False

    def set_emit_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._emit_loop = loop

    async def start(self, *, page: Any, session_id: str) -> None:
        async with self._lifecycle_lock:
            if self._running:
                return

            self._running = True
            self._seq = 0
            self._active_run_session_id = session_id
            self._drain_queue()
            self._sender_task = asyncio.create_task(self._sender_loop(session_id=session_id))

            self._cdp_session = await page.context.new_cdp_session(page)
            self._cdp_session.on(
                "Page.screencastFrame",
                lambda params: asyncio.create_task(
                    self._on_playwright_frame(params=params, session_id=session_id)
                ),
            )

            await self._cdp_session.send(
                "Page.startScreencast", _quality_to_cdp_params(self._quality)
            )
            logger.info(
                "CDP screencast started (playwright)",
                extra={"session_id": session_id, "quality": self._quality},
            )

    async def start_browser_use(
        self,
        *,
        browser_session: Any,
        session_id: str,
        focus_poll_interval_s: float = 0.75,
    ) -> bool:
        if self._stats.streaming_mode != "cdp":
            return False

        async with self._lifecycle_lock:
            await self._stop_locked()

            cdp_session = await self._get_or_create_browser_use_cdp_session(browser_session)
            cdp_client = getattr(cdp_session, "cdp_client", None)
            cdp_session_id = getattr(cdp_session, "session_id", None)
            if cdp_client is None or not isinstance(cdp_session_id, str) or not cdp_session_id:
                raise RuntimeError("browser-use CDPSession missing cdp_client/session_id")

            await self._register_browser_use_handlers(cdp_client)

            self._active_run_session_id = session_id
            self._active_cdp_client = cdp_client
            self._active_cdp_session_id = cdp_session_id
            self._running = True
            self._seq = 0
            self._drain_queue()

            await self._browser_use_send(
                cdp_client=cdp_client,
                cdp_session_id=cdp_session_id,
                method="Page.startScreencast",
                params=_quality_to_cdp_params(self._quality),
            )

            self._stats.note_cdp_attached(run_session_id=session_id, cdp_session_id=cdp_session_id)
            self._sender_task = asyncio.create_task(self._sender_loop(session_id=session_id))
            self._focus_task = asyncio.create_task(
                self._focus_monitor(
                    browser_session=browser_session,
                    run_session_id=session_id,
                    poll_interval_s=max(0.2, float(focus_poll_interval_s)),
                )
            )
            logger.info(
                "CDP screencast started (browser-use)",
                extra={"session_id": session_id, "cdp_session_id": cdp_session_id},
            )
            return True

    async def stop(self, *, session_id: str | None = None) -> None:
        async with self._lifecycle_lock:
            if session_id is not None and self._active_run_session_id not in {None, session_id}:
                return
            await self._stop_locked()

    async def _stop_locked(self) -> None:
        if not self._running:
            self._active_run_session_id = None
            self._active_cdp_session_id = None
            self._active_cdp_client = None
            self._cdp_session = None
            return

        self._running = False
        active_run_session_id = self._active_run_session_id
        active_cdp_client = self._active_cdp_client
        active_cdp_session_id = self._active_cdp_session_id
        active_playwright = self._cdp_session

        self._active_run_session_id = None
        self._active_cdp_session_id = None
        self._active_cdp_client = None
        self._cdp_session = None

        if self._focus_task is not None:
            self._focus_task.cancel()
            try:
                await self._focus_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                logger.debug("Failed waiting for CDP focus task", exc_info=True)
            self._focus_task = None

        if self._sender_task is not None:
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                logger.debug("Failed waiting for CDP sender task", exc_info=True)
            self._sender_task = None

        if active_playwright is not None:
            try:
                await active_playwright.send("Page.stopScreencast")
            except Exception:  # noqa: BLE001
                logger.exception("Failed to stop CDP screencast (playwright)")

        if active_cdp_client is not None and active_cdp_session_id:
            try:
                await self._browser_use_send(
                    cdp_client=active_cdp_client,
                    cdp_session_id=active_cdp_session_id,
                    method="Page.stopScreencast",
                    params=None,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to stop CDP screencast (browser-use)",
                    extra={
                        "session_id": active_run_session_id,
                        "cdp_session_id": active_cdp_session_id,
                    },
                )

        self._stats.note_cdp_detached()
        logger.info("CDP screencast stopped", extra={"session_id": active_run_session_id})

    def _drain_queue(self) -> None:
        try:
            while True:
                self._frame_queue.get_nowait()
        except asyncio.QueueEmpty:
            return

    async def _emit(self, *, event: str, payload: dict[str, Any]) -> None:
        coro = self._sio.emit(event, payload, namespace=self._namespace)
        target_loop = self._emit_loop
        if target_loop is None:
            await coro
            return
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is target_loop:
            await coro
            return
        future = asyncio.run_coroutine_threadsafe(coro, target_loop)
        await asyncio.wrap_future(future)

    async def _on_playwright_frame(self, *, params: dict[str, Any], session_id: str) -> None:
        if (
            not self._running
            or self._cdp_session is None
            or self._active_run_session_id != session_id
        ):
            return

        self._seq += 1
        seq = self._seq
        received_ts = time.time()

        self._stats.note_frame_received(seq=seq, received_ts=received_ts)

        ack_session_id = params.get("sessionId")
        if ack_session_id is not None:
            try:
                await self._cdp_session.send(
                    "Page.screencastFrameAck", {"sessionId": ack_session_id}
                )
            except Exception:  # noqa: BLE001
                logger.exception("Failed to ACK screencast frame", extra={"seq": seq})

        self._enqueue_frame(
            frame=CdpFrame(
                seq=seq,
                session_id=session_id,
                received_ts=received_ts,
                data_base64=str(params.get("data", "")),
                metadata=dict(params.get("metadata") or {}),
            )
        )

    async def _on_browser_use_frame(self, *, params: Any, cdp_session_id: str | None) -> None:
        if not self._running:
            return
        active_cdp_session_id = self._active_cdp_session_id
        if not active_cdp_session_id or cdp_session_id != active_cdp_session_id:
            return

        active_run_session_id = self._active_run_session_id
        active_cdp_client = self._active_cdp_client
        if not active_run_session_id or active_cdp_client is None:
            return

        if not isinstance(params, dict):
            return

        self._seq += 1
        seq = self._seq
        received_ts = time.time()

        self._stats.note_frame_received(seq=seq, received_ts=received_ts)

        ack_id = params.get("sessionId")
        if ack_id is not None:
            try:
                await self._browser_use_send(
                    cdp_client=active_cdp_client,
                    cdp_session_id=active_cdp_session_id,
                    method="Page.screencastFrameAck",
                    params={"sessionId": ack_id},
                )
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Failed to ACK screencast frame (browser-use)",
                    exc_info=True,
                    extra={"seq": seq, "cdp_session_id": active_cdp_session_id},
                )

        self._enqueue_frame(
            frame=CdpFrame(
                seq=seq,
                session_id=active_run_session_id,
                received_ts=received_ts,
                data_base64=str(params.get("data", "")),
                metadata={
                    "cdp_session_id": active_cdp_session_id,
                    **dict(params.get("metadata") or {}),
                },
            )
        )

    def _enqueue_frame(self, *, frame: CdpFrame) -> None:
        try:
            self._frame_queue.put_nowait(frame)
        except asyncio.QueueFull:
            self._stats.note_frame_dropped()

    async def _get_or_create_browser_use_cdp_session(self, browser_session: Any) -> Any:
        get_or_create = getattr(browser_session, "get_or_create_cdp_session", None)
        if not callable(get_or_create):
            raise AttributeError("BrowserSession.get_or_create_cdp_session is unavailable")
        cdp_session = get_or_create()
        if inspect.isawaitable(cdp_session):
            cdp_session = await cdp_session
        return cdp_session

    async def _register_browser_use_handlers(self, cdp_client: Any) -> None:
        client_id = id(cdp_client)
        if client_id in self._registered_cdp_clients:
            return

        register = getattr(cdp_client, "register", None)
        page = getattr(register, "Page", None) if register is not None else None
        register_frame = getattr(page, "screencastFrame", None) if page is not None else None
        if not callable(register_frame):
            raise RuntimeError("CDP client missing register.Page.screencastFrame")

        def _handler(event: Any, cdp_session_id: str | None = None) -> None:
            asyncio.create_task(
                self._on_browser_use_frame(params=event, cdp_session_id=cdp_session_id)
            )

        register_frame(_handler)
        self._registered_cdp_clients.add(client_id)

    async def _browser_use_send(
        self,
        *,
        cdp_client: Any,
        cdp_session_id: str,
        method: str,
        params: dict[str, Any] | None,
    ) -> None:
        send_obj = getattr(cdp_client, "send", None)
        if send_obj is None:
            raise RuntimeError("CDP client missing send")

        domain, _, command = method.partition(".")
        typed_domain = getattr(send_obj, domain, None)
        typed_method = getattr(typed_domain, command, None) if typed_domain is not None else None
        if callable(typed_method):
            kwargs: dict[str, Any] = {"session_id": cdp_session_id}
            if params is not None:
                kwargs["params"] = params
            result = typed_method(**kwargs)
            if inspect.isawaitable(result):
                await result
            return

        if callable(send_obj):
            if params is None:
                try:
                    result = send_obj(method, session_id=cdp_session_id)
                except TypeError:
                    result = send_obj(method, None, session_id=cdp_session_id)
            else:
                try:
                    result = send_obj(method, params, session_id=cdp_session_id)
                except TypeError:
                    result = send_obj(method, params=params, session_id=cdp_session_id)
            if inspect.isawaitable(result):
                await result
            return

        raise RuntimeError(f"Unsupported CDP client send surface for {method}")

    async def _focus_monitor(
        self,
        *,
        browser_session: Any,
        run_session_id: str,
        poll_interval_s: float,
    ) -> None:
        while self._running and self._active_run_session_id == run_session_id:
            await asyncio.sleep(poll_interval_s)
            try:
                cdp_session = await self._get_or_create_browser_use_cdp_session(browser_session)
            except Exception:  # noqa: BLE001
                continue

            cdp_client = getattr(cdp_session, "cdp_client", None)
            cdp_session_id = getattr(cdp_session, "session_id", None)
            if cdp_client is None or not isinstance(cdp_session_id, str) or not cdp_session_id:
                continue

            async with self._lifecycle_lock:
                if (
                    not self._running
                    or self._active_run_session_id != run_session_id
                    or self._active_cdp_session_id == cdp_session_id
                ):
                    continue

                previous_client = self._active_cdp_client
                previous_session_id = self._active_cdp_session_id

                if previous_client is not None and previous_session_id:
                    try:
                        await self._browser_use_send(
                            cdp_client=previous_client,
                            cdp_session_id=previous_session_id,
                            method="Page.stopScreencast",
                            params=None,
                        )
                    except Exception:  # noqa: BLE001
                        logger.debug(
                            "Failed to stop screencast during focus switch",
                            exc_info=True,
                            extra={"cdp_session_id": previous_session_id},
                        )

                try:
                    await self._register_browser_use_handlers(cdp_client)
                    await self._browser_use_send(
                        cdp_client=cdp_client,
                        cdp_session_id=cdp_session_id,
                        method="Page.startScreencast",
                        params=_quality_to_cdp_params(self._quality),
                    )
                except Exception as exc:  # noqa: BLE001
                    self._stats.note_cdp_detached(error=_truncate_cdp_error(exc))
                    self._active_cdp_client = None
                    self._active_cdp_session_id = None
                else:
                    self._active_cdp_client = cdp_client
                    self._active_cdp_session_id = cdp_session_id
                    self._stats.note_cdp_attached(
                        run_session_id=run_session_id, cdp_session_id=cdp_session_id
                    )
                    logger.info(
                        "CDP focus switched",
                        extra={"session_id": run_session_id, "cdp_session_id": cdp_session_id},
                    )

    async def _sender_loop(self, *, session_id: str) -> None:
        while True:
            frame = await self._frame_queue.get()
            emitted_ts = time.time()
            latency_ms = (emitted_ts - frame.received_ts) * 1000.0

            payload = {
                "seq": frame.seq,
                "session_id": frame.session_id,
                "received_ts": frame.received_ts,
                "emitted_ts": emitted_ts,
                "latency_ms": latency_ms,
                "data_base64": frame.data_base64,
                "metadata": frame.metadata,
            }

            await self._emit(event="frame", payload=payload)
            self._stats.note_frame_emitted(emitted_ts=emitted_ts, latency_ms=latency_ms)

            should_sample = bool(frame.data_base64) and (
                frame.seq == 1 or frame.seq % self._sample_every_n == 0
            )
            if should_sample:
                self._stats.note_sampler_seen()
                try:
                    image_bytes = base64.b64decode(frame.data_base64)
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to decode sampled frame", extra={"seq": frame.seq})
                else:
                    self._screenshot_manager.record_screenshot(
                        screenshot_type="stream_sample",
                        image_bytes=image_bytes,
                        mime_type="image/jpeg",
                        session_id=session_id,
                        captured_at=emitted_ts,
                        metadata={
                            "seq": frame.seq,
                            "latency_ms": latency_ms,
                            "streaming_mode": "cdp",
                        },
                    )
                    self._stats.note_sampler_stored()

            logger.debug(
                "Emitted screencast frame",
                extra={"seq": frame.seq, "latency_ms": latency_ms, "session_id": session_id},
            )


def _truncate_cdp_error(exc: Exception) -> str:
    text = str(exc).strip()
    if not text:
        text = type(exc).__name__
    return text[:200]
