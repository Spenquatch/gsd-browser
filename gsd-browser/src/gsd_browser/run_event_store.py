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
    def __init__(
        self,
        *,
        config: RunEventStoreConfig | None = None,
        max_sessions: int | None = None,
        max_events_per_session_type: int | None = None,
        max_events_per_type: int | None = None,
        max_events: int | None = None,
        max_string_length: int | None = None,
        max_field_length: int | None = None,
        max_len: int | None = None,
    ) -> None:
        base = config or RunEventStoreConfig()
        max_events_value = next(
            (
                value
                for value in (max_events_per_session_type, max_events_per_type, max_events)
                if value is not None
            ),
            None,
        )
        max_len_value = next(
            (
                value
                for value in (max_string_length, max_field_length, max_len)
                if value is not None
            ),
            None,
        )

        self._config = RunEventStoreConfig(
            max_sessions=base.max_sessions if max_sessions is None else int(max_sessions),
            max_agent_events=base.max_agent_events
            if max_events_value is None
            else int(max_events_value),
            max_console_events=base.max_console_events
            if max_events_value is None
            else int(max_events_value),
            max_network_events=base.max_network_events
            if max_events_value is None
            else int(max_events_value),
            max_url_len=base.max_url_len if max_len_value is None else int(max_len_value),
            max_message_len=base.max_message_len if max_len_value is None else int(max_len_value),
            max_summary_len=base.max_summary_len if max_len_value is None else int(max_len_value),
        )
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

    def record_event(
        self,
        *,
        session_id: str,
        event_type: str,
        timestamp: float,
        summary: str,
        details: dict[str, Any] | None = None,
        has_error: bool = False,
    ) -> None:
        normalized = str(event_type or "").strip()
        if not normalized:
            normalized = "unknown"

        payload: dict[str, Any] = {
            "event_type": normalized,
            "timestamp": float(timestamp),
            "summary": _truncate(str(summary), max_len=self._config.max_summary_len),
            "has_error": bool(has_error),
        }
        if details:
            safe_details: dict[str, Any] = {}
            for key, value in details.items():
                if value is None:
                    continue
                if isinstance(value, str):
                    safe_details[key] = _truncate(value, max_len=self._config.max_message_len)
                else:
                    safe_details[key] = value
            if safe_details:
                payload["details"] = safe_details

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                self._sessions[session_id] = _RunSessionEvents(
                    created_at=float(timestamp),
                    agent_events=deque(maxlen=self._config.max_agent_events),
                    console_events=deque(maxlen=self._config.max_console_events),
                    network_events=deque(maxlen=self._config.max_network_events),
                )
                session = self._sessions[session_id]
                self._prune_locked()

            if normalized == "agent":
                target = session.agent_events
                dropped_key = "agent"
            elif normalized == "console":
                target = session.console_events
                dropped_key = "console"
            elif normalized == "network":
                target = session.network_events
                dropped_key = "network"
            else:
                target = session.agent_events
                dropped_key = "agent"

            if len(target) >= target.maxlen:  # type: ignore[operator]
                session.dropped[dropped_key] += 1
            target.append(payload)

    def get_events(
        self,
        *,
        session_id: str | None = None,
        last_n: int = 50,
        event_types: list[str] | None = None,
        from_timestamp: float | None = None,
        has_error: bool | None = None,
        include_details: bool = False,
    ) -> list[dict[str, Any]]:
        normalized_types = (
            {str(item).strip() for item in event_types if str(item).strip()}
            if event_types
            else None
        )

        with self._lock:
            sessions: list[tuple[str, _RunSessionEvents]]
            if session_id is None:
                sessions = list(self._sessions.items())
            else:
                session = self._sessions.get(session_id)
                sessions = [] if session is None else [(session_id, session)]

            events: list[dict[str, Any]] = []
            for sid, session in sessions:
                for entry in (
                    tuple(session.agent_events)
                    + tuple(session.console_events)
                    + tuple(session.network_events)
                ):
                    if not isinstance(entry, dict):
                        continue
                    event_type_value = entry.get("event_type") or entry.get("type")
                    if normalized_types and event_type_value not in normalized_types:
                        continue
                    timestamp_value = entry.get("timestamp")
                    if timestamp_value is None:
                        timestamp_value = entry.get("captured_at")
                    if from_timestamp is not None and isinstance(timestamp_value, (int, float)):
                        if float(timestamp_value) < float(from_timestamp):
                            continue
                    if has_error is not None and entry.get("has_error") is not None:
                        if bool(entry.get("has_error")) is not bool(has_error):
                            continue
                    if session_id is None:
                        item = dict(entry)
                        item["session_id"] = sid
                    else:
                        item = dict(entry)
                    if not include_details:
                        item.pop("details", None)
                        item.pop("location", None)
                    events.append(item)

        def sort_key(item: dict[str, Any]) -> float:
            value = item.get("timestamp")
            if value is None:
                value = item.get("captured_at")
            if value is None:
                value = 0.0
            try:
                return float(value)
            except Exception:  # noqa: BLE001
                return 0.0

        events.sort(key=sort_key, reverse=True)
        if last_n is not None:
            last_n_value = max(0, int(last_n))
            if last_n_value:
                events = events[:last_n_value]
        return events

    def record_agent_event(
        self,
        session_id: str,
        *,
        captured_at: float,
        step: int | None = None,
        url: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        has_error: bool = False,
    ) -> None:
        details: dict[str, Any] = {}
        if step is not None:
            details["step"] = int(step)
        if url:
            details["url"] = _truncate(str(url), max_len=self._config.max_url_len)
        if title:
            details["title"] = _truncate(str(title), max_len=self._config.max_summary_len)

        self.record_event(
            session_id=session_id,
            event_type="agent",
            timestamp=captured_at,
            summary=_truncate(str(summary or ""), max_len=self._config.max_summary_len),
            details=details or None,
            has_error=bool(has_error),
        )

    def record_console_event(
        self,
        session_id: str,
        *,
        captured_at: float,
        level: str,
        message: str,
        location: dict[str, Any] | None = None,
    ) -> None:
        safe_level = _truncate(str(level), max_len=50)
        safe_message = _truncate(str(message), max_len=self._config.max_message_len)
        details: dict[str, Any] = {"level": safe_level}
        if location:
            safe_location: dict[str, Any] = {}
            url = location.get("url")
            if url:
                safe_location["url"] = _truncate(str(url), max_len=self._config.max_url_len)
            for key in ("line", "column", "function"):
                if key in location and location[key] is not None:
                    safe_location[key] = location[key]
            if safe_location:
                details["location"] = safe_location

        self.record_event(
            session_id=session_id,
            event_type="console",
            timestamp=captured_at,
            summary=safe_message,
            details=details,
            has_error=safe_level in {"error", "exception", "fatal"},
        )

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
        safe_method = _truncate(str(method), max_len=20)
        safe_url = _truncate(str(url), max_len=self._config.max_url_len)
        details: dict[str, Any] = {"method": safe_method, "url": safe_url}
        if status is not None:
            details["status"] = int(status)
        if duration_ms is not None:
            details["duration_ms"] = float(duration_ms)
        if error:
            details["error"] = _truncate(str(error), max_len=self._config.max_message_len)

        summary = f"{safe_method} {safe_url}".strip()
        inferred_error = bool(error) or (status is not None and int(status) >= 400)
        self.record_event(
            session_id=session_id,
            event_type="network",
            timestamp=captured_at,
            summary=_truncate(summary, max_len=self._config.max_summary_len),
            details=details,
            has_error=inferred_error,
        )

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
