"""Logging helpers for the MCP template."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from threading import Lock
from typing import Any


class JsonFormatter(logging.Formatter):
    """Simple JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        # Include custom attributes (extras) that are not standard LogRecord fields.
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in payload or key in (
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            ):
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", *, json_logs: bool = False) -> None:
    """Configure root logging with either JSON or human-friendly formatting."""
    handlers: list[logging.Handler] = []
    handler = logging.StreamHandler(stream=sys.stderr)
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    handlers.append(handler)

    normalized_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=normalized_level, handlers=handlers, force=True)


class Counter:
    """In-memory counter placeholder (for /healthz style metrics)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = Lock()
        self._value = 0

    def inc(self, value: int = 1) -> int:
        with self._lock:
            self._value += value
            return self._value

    def get(self) -> int:
        with self._lock:
            return self._value


class Gauge:
    """In-memory gauge placeholder (for /healthz style metrics)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = Lock()
        self._value: float | None = None

    def set(self, value: float | None) -> float | None:
        with self._lock:
            self._value = value
            return self._value

    def get(self) -> float | None:
        with self._lock:
            return self._value


__all__ = ["Counter", "Gauge", "setup_logging"]
