"""In-memory run event store keyed by web_eval_agent session_id."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


def _truncate(value: str, *, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(value) <= max_len:
        return value
    return value[: max(0, max_len - 1)] + "…"


@dataclass(frozen=True)
class RunEventStoreConfig:
    max_sessions: int = 50
    max_agent_events: int = 200
    max_console_events: int = 200
    max_network_events: int = 500
    max_url_len: int = 1000
    max_message_len: int = 2000
    max_summary_len: int = 1000


@dataclass
class _RunSessionEvents:
    created_at: float
    agent_events: deque[dict[str, Any]]
    console_events: deque[dict[str, Any]]
    network_events: deque[dict[str, Any]]
    dropped: dict[str, int] = field(
        default_factory=lambda: {"agent": 0, "console": 0, "network": 0}
    )


class RunEventStore:
    def __init__(self, *, config: RunEventStoreConfig | None = None) -> None:
        self._config = config or RunEventStoreConfig()
        self._lock = Lock()
        self._sessions: dict[str, _RunSessionEvents] = {}

    def ensure_session(self, session_id: str, *, created_at: float) -> None:
        with self._lock:
            if session_id in self._sessions:
                return
            self._sessions[session_id] = _RunSessionEvents(
                created_at=created_at,
                agent_events=deque(maxlen=self._config.max_agent_events),
                console_events=deque(maxlen=self._config.max_console_events),
                network_events=deque(maxlen=self._config.max_network_events),
            )
            self._prune_locked()

    def record_agent_event(
        self,
        session_id: str,
        *,
        captured_at: float,
        step: int | None = None,
        url: str | None = None,
        title: str | None = None,
        summary: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "agent_step",
            "captured_at": captured_at,
        }
        if step is not None:
            payload["step"] = int(step)
        if url:
            payload["url"] = _truncate(str(url), max_len=self._config.max_url_len)
        if title:
            payload["title"] = _truncate(str(title), max_len=self._config.max_summary_len)
        if summary:
            payload["summary"] = _truncate(str(summary), max_len=self._config.max_summary_len)

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            if len(session.agent_events) >= session.agent_events.maxlen:  # type: ignore[operator]
                session.dropped["agent"] += 1
            session.agent_events.append(payload)

    def record_console_event(
        self,
        session_id: str,
        *,
        captured_at: float,
        level: str,
        message: str,
        location: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "console",
            "captured_at": captured_at,
            "level": _truncate(str(level), max_len=50),
            "message": _truncate(str(message), max_len=self._config.max_message_len),
        }
        if location:
            safe_location: dict[str, Any] = {}
            url = location.get("url")
            if url:
                safe_location["url"] = _truncate(str(url), max_len=self._config.max_url_len)
            for key in ("line", "column", "function"):
                if key in location and location[key] is not None:
                    safe_location[key] = location[key]
            if safe_location:
                payload["location"] = safe_location

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            if len(session.console_events) >= session.console_events.maxlen:  # type: ignore[operator]
                session.dropped["console"] += 1
            session.console_events.append(payload)

    def record_network_event(
        self,
        session_id: str,
        *,
        captured_at: float,
        method: str,
        url: str,
        status: int | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "network",
            "captured_at": captured_at,
            "method": _truncate(str(method), max_len=20),
            "url": _truncate(str(url), max_len=self._config.max_url_len),
        }
        if status is not None:
            payload["status"] = int(status)
        if duration_ms is not None:
            payload["duration_ms"] = float(duration_ms)
        if error:
            payload["error"] = _truncate(str(error), max_len=self._config.max_message_len)

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            if len(session.network_events) >= session.network_events.maxlen:  # type: ignore[operator]
                session.dropped["network"] += 1
            session.network_events.append(payload)

    def get_counts(self, session_id: str) -> dict[str, int]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return {"agent": 0, "console": 0, "network": 0, "total": 0}
            agent = len(session.agent_events)
            console = len(session.console_events)
            network = len(session.network_events)
            return {
                "agent": agent,
                "console": console,
                "network": network,
                "total": agent + console + network,
            }

    def _prune_locked(self) -> None:
        max_sessions = max(0, self._config.max_sessions)
        if max_sessions and len(self._sessions) <= max_sessions:
            return
        if max_sessions <= 0:
            self._sessions.clear()
            return
        while len(self._sessions) > max_sessions:
            oldest_session_id = min(self._sessions.items(), key=lambda item: item[1].created_at)[0]
            self._sessions.pop(oldest_session_id, None)
