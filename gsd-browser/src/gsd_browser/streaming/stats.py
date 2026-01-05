"""In-memory metrics for the streaming pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from .env import StreamingMode


@dataclass
class StreamingStats:
    streaming_mode: StreamingMode
    frame_queue_max: int

    cdp_available: bool = False
    active_run_session_id: str | None = None
    active_cdp_session_id: str | None = None
    last_cdp_error: str | None = None

    frames_received: int = 0
    frames_emitted: int = 0
    frames_dropped: int = 0

    last_frame_received_ts: float | None = None
    last_frame_emitted_ts: float | None = None
    last_frame_latency_ms: float | None = None
    last_frame_seq: int | None = None

    sampler_frames_seen: int = 0
    sampler_frames_stored: int = 0

    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    def note_frame_received(self, *, seq: int, received_ts: float) -> None:
        with self._lock:
            self.frames_received += 1
            self.last_frame_received_ts = received_ts
            self.last_frame_seq = seq

    def note_frame_dropped(self) -> None:
        with self._lock:
            self.frames_dropped += 1

    def note_frame_emitted(self, *, emitted_ts: float, latency_ms: float | None) -> None:
        with self._lock:
            self.frames_emitted += 1
            self.last_frame_emitted_ts = emitted_ts
            self.last_frame_latency_ms = latency_ms

    def note_sampler_seen(self) -> None:
        with self._lock:
            self.sampler_frames_seen += 1

    def note_sampler_stored(self) -> None:
        with self._lock:
            self.sampler_frames_stored += 1

    def note_cdp_attached(self, *, run_session_id: str, cdp_session_id: str) -> None:
        with self._lock:
            self.cdp_available = True
            self.active_run_session_id = run_session_id
            self.active_cdp_session_id = cdp_session_id
            self.last_cdp_error = None

    def note_cdp_detached(self, *, error: str | None = None) -> None:
        with self._lock:
            self.cdp_available = False
            self.active_cdp_session_id = None
            self.active_run_session_id = None
            if error:
                self.last_cdp_error = error

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "streaming_mode": self.streaming_mode,
                "cdp_available": self.cdp_available,
                "active_run_session_id": self.active_run_session_id,
                "active_cdp_session_id": self.active_cdp_session_id,
                "last_cdp_error": self.last_cdp_error,
                "frame_latency_ms": self.last_frame_latency_ms,
                "frames_dropped": self.frames_dropped,
                "last_frame_ts": self.last_frame_emitted_ts,
                "last_frame_received_ts": self.last_frame_received_ts,
                "last_frame_seq": self.last_frame_seq,
                "frame_queue_max": self.frame_queue_max,
                "frames_received": self.frames_received,
                "frames_emitted": self.frames_emitted,
                "sampler_totals": {
                    "seen": self.sampler_frames_seen,
                    "stored": self.sampler_frames_stored,
                },
            }
