"""In-memory screenshot storage and filtering, compatible with web-agent semantics."""

from __future__ import annotations

import base64
import time
import uuid
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class Screenshot:
    id: str
    timestamp: float
    screenshot_type: str
    session_id: str | None
    has_error: bool
    metadata: dict[str, Any]
    image_bytes: bytes | None
    mime_type: str | None
    url: str | None = None
    step: int | None = None

    def to_dict(self, *, include_images: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "timestamp": self.timestamp,
            "type": self.screenshot_type,
            "session_id": self.session_id,
            "has_error": self.has_error,
            "metadata": self.metadata,
            "mime_type": self.mime_type,
            "url": self.url,
            "step": self.step,
        }
        if include_images and self.image_bytes is not None:
            payload["image_data"] = base64.b64encode(self.image_bytes).decode("ascii")
        return payload


class ScreenshotManager:
    SAMPLING_RATE = 10

    def __init__(self, *, max_screenshots: int = 500) -> None:
        self._items: deque[Screenshot] = deque(maxlen=max_screenshots)
        self._lock = Lock()

        # Compatibility attributes expected by downstream tooling/tests.
        self.key_screenshots = self._items
        self.metadata_index: dict[str, Any] = {}
        self.stream_counter = 0
        self.total_size_bytes = 0
        self.current_session_id: str | None = None
        self.current_session_start: float | None = None

    def record_screenshot(
        self,
        *,
        screenshot_type: str,
        image_bytes: bytes | None,
        mime_type: str | None = None,
        session_id: str | None = None,
        captured_at: float | None = None,
        has_error: bool = False,
        metadata: dict[str, Any] | None = None,
        url: str | None = None,
        step: int | None = None,
    ) -> Screenshot:
        timestamp = captured_at if captured_at is not None else time.time()
        shot = Screenshot(
            id=str(uuid.uuid4()),
            timestamp=timestamp,
            screenshot_type=screenshot_type,
            session_id=session_id,
            has_error=has_error,
            metadata=dict(metadata or {}),
            image_bytes=image_bytes,
            mime_type=mime_type,
            url=url,
            step=step,
        )
        with self._lock:
            self._items.append(shot)
            if image_bytes is not None:
                self.total_size_bytes += len(image_bytes)
        return shot

    async def add_key_screenshot(
        self,
        image_data: str,
        url: str,
        step: int,
        session_id: str,
        *,
        timestamp: float | None = None,
        has_error: bool = False,
        mime_type: str = "image/png",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            image_bytes = base64.b64decode(image_data) if image_data else b""
        except Exception:  # noqa: BLE001
            image_bytes = b""
        shot = self.record_screenshot(
            screenshot_type="agent_step",
            image_bytes=image_bytes,
            mime_type=mime_type,
            session_id=session_id,
            captured_at=timestamp,
            has_error=has_error,
            metadata=dict(metadata or {}),
            url=url,
            step=step,
        )
        return shot.to_dict(include_images=True)

    async def add_stream_screenshot(
        self,
        image_data: str,
        url: str,
        *,
        timestamp: float | None = None,
        session_id: str | None = None,
        mime_type: str = "image/jpeg",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        self.stream_counter += 1
        if self.stream_counter % self.SAMPLING_RATE != 0:
            return None
        try:
            image_bytes = base64.b64decode(image_data) if image_data else b""
        except Exception:  # noqa: BLE001
            image_bytes = b""
        shot = self.record_screenshot(
            screenshot_type="stream_sample",
            image_bytes=image_bytes,
            mime_type=mime_type,
            session_id=session_id,
            captured_at=timestamp,
            metadata=dict(metadata or {}),
            url=url,
        )
        return shot.to_dict(include_images=True)

    def get_screenshots(
        self,
        *,
        last_n: int = 5,
        screenshot_type: str | None = None,
        session_id: str | None = None,
        from_timestamp: float | None = None,
        has_error: bool | None = None,
        include_images: bool = True,
    ) -> list[dict[str, Any]]:
        if last_n <= 0:
            return []

        with self._lock:
            items = list(self._items)

        filtered: list[Screenshot] = []
        for shot in items:
            if screenshot_type and shot.screenshot_type != screenshot_type:
                continue
            if session_id and shot.session_id != session_id:
                continue
            if from_timestamp is not None and shot.timestamp < from_timestamp:
                continue
            if has_error is not None and shot.has_error != has_error:
                continue
            filtered.append(shot)

        return [shot.to_dict(include_images=include_images) for shot in filtered[-last_n:]]
