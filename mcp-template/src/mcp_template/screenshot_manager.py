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
    captured_at: float
    screenshot_type: str
    session_id: str | None
    has_error: bool
    metadata: dict[str, Any]
    image_bytes: bytes | None
    mime_type: str | None

    def to_dict(self, *, include_images: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "captured_at": self.captured_at,
            "screenshot_type": self.screenshot_type,
            "session_id": self.session_id,
            "has_error": self.has_error,
            "metadata": self.metadata,
            "mime_type": self.mime_type,
        }
        if include_images and self.image_bytes is not None:
            payload["image_base64"] = base64.b64encode(self.image_bytes).decode("ascii")
        return payload


class ScreenshotManager:
    def __init__(self, *, max_screenshots: int = 500) -> None:
        self._items: deque[Screenshot] = deque(maxlen=max_screenshots)
        self._lock = Lock()

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
    ) -> Screenshot:
        shot = Screenshot(
            id=str(uuid.uuid4()),
            captured_at=captured_at if captured_at is not None else time.time(),
            screenshot_type=screenshot_type,
            session_id=session_id,
            has_error=has_error,
            metadata=dict(metadata or {}),
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
        with self._lock:
            self._items.append(shot)
        return shot

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
            if from_timestamp is not None and shot.captured_at < from_timestamp:
                continue
            if has_error is not None and shot.has_error != has_error:
                continue
            filtered.append(shot)

        return [shot.to_dict(include_images=include_images) for shot in filtered[-last_n:]]
