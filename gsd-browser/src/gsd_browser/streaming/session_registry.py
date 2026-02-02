"""Session registry for multi-session concurrency.

Maps session_id → SessionState, replacing global ControlState and CdpScreencastStreamer
singletons. Each session gets independent control state and streamer instances.

See ADR-0026 for design rationale.
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cdp_screencast import CdpScreencastStreamer

from .control_state import ControlState

logger = logging.getLogger("gsd_browser.streaming.registry")


class SessionStatus(str, enum.Enum):
    CREATE = "create"
    ACTIVE = "active"
    PAUSED = "paused"
    TERMINATED = "terminated"


@dataclass
class SessionState:
    """Per-session state container."""

    session_id: str
    control: ControlState
    owner_tenant_id: str
    owner_subject_id: str
    worker_id: str
    status: SessionStatus = SessionStatus.CREATE
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    stream_url: str | None = None
    streamer: CdpScreencastStreamer | None = None

    def touch(self) -> None:
        """Update last_activity_at timestamp."""
        self.last_activity_at = time.time()

    def is_active(self) -> bool:
        return self.status in (
            SessionStatus.CREATE,
            SessionStatus.ACTIVE,
            SessionStatus.PAUSED,
        )


class SessionRegistry:
    """Thread-safe registry mapping session_id → SessionState.

    This is a local in-memory data structure. Cross-worker session queries
    go through TaskOwnershipStore (Redis).
    """

    def __init__(
        self,
        *,
        retention_seconds: float = 3600.0,
    ) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.Lock()
        self._retention_seconds = retention_seconds

    def create_session(
        self,
        *,
        session_id: str,
        owner_tenant_id: str,
        owner_subject_id: str,
        worker_id: str,
        auto_pause_on_take_control: bool = True,
        stream_url: str | None = None,
    ) -> SessionState:
        """Create and register a new session.

        Raises ValueError if session_id already exists.
        """
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"Session {session_id} already exists")

            control = ControlState(
                auto_pause_on_take_control=auto_pause_on_take_control,
            )
            state = SessionState(
                session_id=session_id,
                control=control,
                owner_tenant_id=owner_tenant_id,
                owner_subject_id=owner_subject_id,
                worker_id=worker_id,
                stream_url=stream_url,
            )
            self._sessions[session_id] = state
            logger.info(
                "Session created: %s (tenant=%s, worker=%s)",
                session_id,
                owner_tenant_id,
                worker_id,
            )
            return state

    def get_session(self, session_id: str) -> SessionState | None:
        """Get session state by ID, or None if not found."""
        with self._lock:
            return self._sessions.get(session_id)

    def get_sessions_by_tenant(self, tenant_id: str) -> list[SessionState]:
        """Get all sessions owned by a tenant."""
        with self._lock:
            return [
                s
                for s in self._sessions.values()
                if s.owner_tenant_id == tenant_id
            ]

    def count_active_sessions(self, tenant_id: str) -> int:
        """Count sessions in active states (create, active, paused) for a tenant."""
        with self._lock:
            return sum(
                1
                for s in self._sessions.values()
                if s.owner_tenant_id == tenant_id and s.is_active()
            )

    def activate_session(self, session_id: str) -> None:
        """Transition session to ACTIVE status."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session {session_id} not found")
            session.status = SessionStatus.ACTIVE
            session.touch()
            logger.info("Session activated: %s", session_id)

    def pause_session(self, session_id: str) -> None:
        """Transition session to PAUSED status."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session {session_id} not found")
            session.status = SessionStatus.PAUSED
            session.touch()

    def terminate_session(self, session_id: str) -> None:
        """Transition session to TERMINATED status.

        Does not remove the session — it remains for retention_seconds
        for post-mortem viewing, then is cleaned up by cleanup_expired().
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return  # Idempotent
            session.status = SessionStatus.TERMINATED
            session.touch()
            logger.info("Session terminated: %s", session_id)

    def cleanup_expired(self) -> int:
        """Remove terminated sessions that have exceeded the retention period.

        Returns the number of sessions cleaned up.
        """
        now = time.time()
        cutoff = now - self._retention_seconds
        to_remove: list[str] = []

        with self._lock:
            for sid, state in self._sessions.items():
                if (
                    state.status == SessionStatus.TERMINATED
                    and state.last_activity_at < cutoff
                ):
                    to_remove.append(sid)

            for sid in to_remove:
                del self._sessions[sid]

        if to_remove:
            logger.info("Cleaned up %d expired sessions", len(to_remove))
        return len(to_remove)

    def all_sessions(self) -> list[SessionState]:
        """Return a snapshot list of all sessions."""
        with self._lock:
            return list(self._sessions.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def set_streamer(
        self, session_id: str, streamer: CdpScreencastStreamer
    ) -> None:
        """Attach a CDP streamer to a session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session {session_id} not found")
            session.streamer = streamer
