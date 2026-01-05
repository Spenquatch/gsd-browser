from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_fixture_text(name: str) -> str:
    path = Path(__file__).parent / "fixtures" / "r3" / name
    return path.read_text(encoding="utf-8")


def _load_fixture_json(name: str) -> Any:
    return json.loads(_load_fixture_text(name))


def test_r3_render_markdown_fixed_summary_payload() -> None:
    from gsd_browser.real_world_sanity import _render_markdown

    summary = _load_fixture_json("summary.json")
    assert _render_markdown(summary) == _load_fixture_text("report.md")


def test_r3_summary_schema_shape_and_types() -> None:
    summary = _load_fixture_json("summary.json")

    assert isinstance(summary.get("started_at"), str)
    assert isinstance(summary.get("out_dir"), str)
    assert isinstance(summary.get("env_hint"), dict)
    assert isinstance(summary.get("runs"), list)
    assert summary["runs"], "fixture must include at least one run"

    for run in summary["runs"]:
        assert isinstance(run, dict)
        assert set(run).issuperset({"scenario", "result", "paths", "highlights", "settings"})

        scenario = run["scenario"]
        assert isinstance(scenario, dict)
        assert isinstance(scenario.get("id"), str)
        assert isinstance(scenario.get("url"), str)
        assert scenario.get("expected") in {"pass", "soft_fail"}

        result = run["result"]
        assert isinstance(result, dict)
        assert result.get("status") in {"success", "failed", "partial"}
        assert result.get("classification") in {"pass", "soft_fail", "hard_fail"}
        assert isinstance(result.get("session_id"), str)
        assert isinstance(result.get("screenshots_written"), int)
        assert isinstance(result.get("events_with_error"), int)
        assert isinstance(result.get("result_present"), bool)

        paths = run["paths"]
        assert isinstance(paths, dict)
        assert isinstance(paths.get("response_json"), str)
        assert isinstance(paths.get("events_json"), str)
        assert isinstance(paths.get("screenshots_index"), str)

        highlights = run["highlights"]
        assert isinstance(highlights, list)
        assert all(isinstance(item, str) for item in highlights)

        settings = run["settings"]
        assert isinstance(settings, dict)
        assert isinstance(settings.get("llm_provider"), str)
        assert isinstance(settings.get("model"), str)


def test_r3_summarize_errors_is_bounded_to_ten_events() -> None:
    from gsd_browser.real_world_sanity import _summarize_errors

    payload = {
        "summary": "top level summary",
        "dev_excerpts": {"console_errors": [{"a": 1}, {"a": 2}], "network_errors": [{"b": 3}]},
    }
    events = [{"event_type": "console", "summary": f"e{i}"} for i in range(25)]

    highlights = _summarize_errors(payload, events)

    assert highlights[:3] == [
        "summary: top level summary",
        "console_errors: 2",
        "network_errors: 1",
    ]
    assert "console: e0" in highlights
    assert "console: e9" in highlights
    assert "console: e10" not in highlights
    assert len(highlights) <= 13
