from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType

import pytest

from gsd_browser import browser_state


def test_browser_use_connect_prefers_connect_no_args_when_no_cdp_url() -> None:
    class Profile:
        cdp_url = None

    class Session:
        browser_profile = Profile()
        called_with: tuple[object, ...] | None = None

        def connect(self, *args: object, **kwargs: object) -> None:
            if args or kwargs:
                raise AssertionError("connect() should be called with no args for local launch")
            self.called_with = args

    session = Session()
    asyncio.run(browser_state._browser_use_connect(session))
    assert session.called_with == ()


def test_force_load_storage_state_dispatches_event_after_focus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"cookies": [], "origins": []}', encoding="utf-8")

    events_mod = ModuleType("browser_use.browser.events")

    class LoadStorageStateEvent:
        def __init__(self, path: str | None = None) -> None:
            self.path = path

    events_mod.LoadStorageStateEvent = LoadStorageStateEvent

    browser_mod = ModuleType("browser_use.browser")
    monkeypatch.setitem(sys.modules, "browser_use.browser", browser_mod)
    monkeypatch.setitem(sys.modules, "browser_use.browser.events", events_mod)

    class EventBus:
        def __init__(self) -> None:
            self.events: list[object] = []

        def dispatch(self, event: object) -> None:
            self.events.append(event)

    class Session:
        def __init__(self) -> None:
            self.event_bus = EventBus()
            self.focus_calls: list[object] = []

        def get_or_create_cdp_session(self, *args: object, **kwargs: object) -> None:
            self.focus_calls.append((args, kwargs))

    session = Session()
    asyncio.run(browser_state._browser_use_force_load_storage_state(session, state_path=state_path))
    assert session.focus_calls
    assert session.event_bus.events
    event = session.event_bus.events[0]
    assert isinstance(event, LoadStorageStateEvent)
    assert event.path == str(state_path)
