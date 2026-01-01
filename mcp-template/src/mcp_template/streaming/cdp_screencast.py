"""CDP screencast streamer via Playwright."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import Any

import socketio

from ..screenshot_manager import ScreenshotManager
from .env import StreamingQuality
from .stats import StreamingStats

logger = logging.getLogger("mcp_template.streaming")


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

        self._seq = 0
        self._cdp_session: Any | None = None
        self._sender_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self, *, page: Any, session_id: str) -> None:
        if self._running:
            return

        self._running = True
        self._seq = 0
        self._sender_task = asyncio.create_task(self._sender_loop(session_id=session_id))

        self._cdp_session = await page.context.new_cdp_session(page)
        self._cdp_session.on(
            "Page.screencastFrame",
            lambda params: asyncio.create_task(
                self._on_frame(params=params, session_id=session_id)
            ),
        )

        await self._cdp_session.send("Page.startScreencast", _quality_to_cdp_params(self._quality))
        logger.info(
            "CDP screencast started",
            extra={"session_id": session_id, "quality": self._quality},
        )

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        if self._cdp_session is not None:
            try:
                await self._cdp_session.send("Page.stopScreencast")
            except Exception:  # noqa: BLE001
                logger.exception("Failed to stop CDP screencast")
            self._cdp_session = None

        if self._sender_task is not None:
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass
            self._sender_task = None

        logger.info("CDP screencast stopped")

    async def _on_frame(self, *, params: dict[str, Any], session_id: str) -> None:
        if not self._running or self._cdp_session is None:
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

        frame = CdpFrame(
            seq=seq,
            session_id=session_id,
            received_ts=received_ts,
            data_base64=str(params.get("data", "")),
            metadata=dict(params.get("metadata") or {}),
        )

        try:
            self._frame_queue.put_nowait(frame)
        except asyncio.QueueFull:
            self._stats.note_frame_dropped()

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

            await self._sio.emit("frame", payload, namespace=self._namespace)
            self._stats.note_frame_emitted(emitted_ts=emitted_ts, latency_ms=latency_ms)

            if frame.seq % self._sample_every_n == 0 and frame.data_base64:
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
