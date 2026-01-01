"""Logging helpers for the MCP template."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """Simple JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
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
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
        )
    handlers.append(handler)

    normalized_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=normalized_level, handlers=handlers, force=True)


__all__ = ["setup_logging"]
