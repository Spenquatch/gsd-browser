"""Tests for SessionRegistry (ADR-0026)."""

from __future__ import annotations

import time

import pytest

from gsd_browser.streaming.session_registry import (
    SessionRegistry,
    SessionState,
    SessionStatus,
)


@pytest.fixture()
def registry() -> SessionRegistry:
    return SessionRegistry(retention_seconds=60.0)


def _create(
    registry: SessionRegistry,
    session_id: str = "sess-1",
    tenant_id: str = "tenant-a",
    subject_id: str = "user-1",
    worker_id: str = "worker-0",
) -> SessionState:
    return registry.create_session(
        session_id=session_id,
        owner_tenant_id=tenant_id,
        owner_subject_id=subject_id,
        worker_id=worker_id,
    )


class TestCreateSession:
    def test_creates_session(self, registry: SessionRegistry) -> None:
        state = _create(registry)
        assert state.session_id == "sess-1"
        assert state.owner_tenant_id == "tenant-a"
        assert state.owner_subject_id == "user-1"
        assert state.worker_id == "worker-0"
        assert state.status == SessionStatus.CREATE
        assert state.control is not None

    def test_duplicate_raises(self, registry: SessionRegistry) -> None:
        _create(registry)
        with pytest.raises(ValueError, match="already exists"):
            _create(registry)

    def test_creates_independent_control_states(self, registry: SessionRegistry) -> None:
        s1 = _create(registry, session_id="sess-1")
        s2 = _create(registry, session_id="sess-2")
        assert s1.control is not s2.control


class TestGetSession:
    def test_get_existing(self, registry: SessionRegistry) -> None:
        _create(registry)
        assert registry.get_session("sess-1") is not None
        assert registry.get_session("sess-1").session_id == "sess-1"

    def test_get_missing_returns_none(self, registry: SessionRegistry) -> None:
        assert registry.get_session("nonexistent") is None


class TestGetSessionsByTenant:
    def test_filters_by_tenant(self, registry: SessionRegistry) -> None:
        _create(registry, session_id="s1", tenant_id="t1")
        _create(registry, session_id="s2", tenant_id="t1")
        _create(registry, session_id="s3", tenant_id="t2")

        t1_sessions = registry.get_sessions_by_tenant("t1")
        assert len(t1_sessions) == 2
        assert {s.session_id for s in t1_sessions} == {"s1", "s2"}

    def test_empty_tenant(self, registry: SessionRegistry) -> None:
        _create(registry, session_id="s1", tenant_id="t1")
        assert registry.get_sessions_by_tenant("t99") == []


class TestCountActiveSessions:
    def test_counts_active_states(self, registry: SessionRegistry) -> None:
        _create(registry, session_id="s1", tenant_id="t1")
        _create(registry, session_id="s2", tenant_id="t1")
        registry.activate_session("s1")
        # s1=active, s2=create — both count as active
        assert registry.count_active_sessions("t1") == 2

    def test_terminated_not_counted(self, registry: SessionRegistry) -> None:
        _create(registry, session_id="s1", tenant_id="t1")
        _create(registry, session_id="s2", tenant_id="t1")
        registry.terminate_session("s1")
        assert registry.count_active_sessions("t1") == 1

    def test_different_tenants_isolated(self, registry: SessionRegistry) -> None:
        _create(registry, session_id="s1", tenant_id="t1")
        _create(registry, session_id="s2", tenant_id="t2")
        assert registry.count_active_sessions("t1") == 1
        assert registry.count_active_sessions("t2") == 1


class TestSessionLifecycle:
    def test_activate(self, registry: SessionRegistry) -> None:
        _create(registry)
        registry.activate_session("sess-1")
        assert registry.get_session("sess-1").status == SessionStatus.ACTIVE

    def test_pause(self, registry: SessionRegistry) -> None:
        _create(registry)
        registry.activate_session("sess-1")
        registry.pause_session("sess-1")
        assert registry.get_session("sess-1").status == SessionStatus.PAUSED
        assert registry.get_session("sess-1").is_active()

    def test_terminate(self, registry: SessionRegistry) -> None:
        _create(registry)
        registry.terminate_session("sess-1")
        assert registry.get_session("sess-1").status == SessionStatus.TERMINATED
        assert not registry.get_session("sess-1").is_active()

    def test_terminate_idempotent(self, registry: SessionRegistry) -> None:
        registry.terminate_session("nonexistent")  # Should not raise

    def test_activate_missing_raises(self, registry: SessionRegistry) -> None:
        with pytest.raises(KeyError, match="not found"):
            registry.activate_session("nonexistent")


class TestCleanupExpired:
    def test_cleans_terminated_past_retention(self, registry: SessionRegistry) -> None:
        reg = SessionRegistry(retention_seconds=0.0)  # Immediate expiry
        _create(reg, session_id="s1")
        reg.terminate_session("s1")
        # Force last_activity_at into the past
        reg.get_session("s1").last_activity_at = time.time() - 1.0
        cleaned = reg.cleanup_expired()
        assert cleaned == 1
        assert reg.get_session("s1") is None

    def test_does_not_clean_active(self, registry: SessionRegistry) -> None:
        reg = SessionRegistry(retention_seconds=0.0)
        _create(reg, session_id="s1")
        cleaned = reg.cleanup_expired()
        assert cleaned == 0
        assert reg.get_session("s1") is not None

    def test_does_not_clean_within_retention(self, registry: SessionRegistry) -> None:
        _create(registry, session_id="s1")
        registry.terminate_session("s1")
        cleaned = registry.cleanup_expired()
        assert cleaned == 0  # retention_seconds=60, not expired yet


class TestAllSessions:
    def test_returns_all(self, registry: SessionRegistry) -> None:
        _create(registry, session_id="s1")
        _create(registry, session_id="s2")
        all_s = registry.all_sessions()
        assert len(all_s) == 2
        assert {s.session_id for s in all_s} == {"s1", "s2"}


class TestLen:
    def test_empty(self, registry: SessionRegistry) -> None:
        assert len(registry) == 0

    def test_after_create(self, registry: SessionRegistry) -> None:
        _create(registry)
        assert len(registry) == 1


class TestTenantSessionLimit:
    """MS-7: Verify count_active_sessions works for limit enforcement."""

    def test_count_excludes_terminated(
        self, registry: SessionRegistry
    ) -> None:
        _create(registry, session_id="s1")
        _create(registry, session_id="s2")
        registry.activate_session("s1")
        registry.activate_session("s2")
        assert registry.count_active_sessions("tenant-a") == 2

        registry.terminate_session("s1")
        assert registry.count_active_sessions("tenant-a") == 1

    def test_count_excludes_other_tenants(
        self, registry: SessionRegistry
    ) -> None:
        _create(registry, session_id="s1")
        registry.activate_session("s1")
        registry.create_session(
            session_id="s2",
            owner_tenant_id="other-tenant",
            owner_subject_id="sub",
            worker_id="",
        )
        registry.activate_session("s2")
        assert registry.count_active_sessions("tenant-a") == 1
        assert registry.count_active_sessions("other-tenant") == 1

    def test_count_includes_created_and_paused(
        self, registry: SessionRegistry
    ) -> None:
        _create(registry, session_id="s1")  # CREATED
        _create(registry, session_id="s2")
        registry.activate_session("s2")
        registry.pause_session("s2")  # PAUSED
        _create(registry, session_id="s3")
        registry.activate_session("s3")  # ACTIVE
        assert registry.count_active_sessions("tenant-a") == 3
