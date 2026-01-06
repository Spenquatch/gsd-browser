from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_fixture(name: str) -> Any:
    path = Path(__file__).parent / "fixtures" / "a4" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_a4_agent_event_with_has_error_is_actionable() -> None:
    """A4: Agent events with has_error=True are considered actionable."""
    from gsd_browser.real_world_sanity import _has_actionable_error_events

    events = _load_fixture("events_agent_schema_error.json")
    assert _has_actionable_error_events(events) is True


def test_a4_agent_provider_error_event_is_actionable() -> None:
    """A4: Agent events with provider errors are considered actionable."""
    from gsd_browser.real_world_sanity import _has_actionable_error_events

    events = _load_fixture("events_agent_provider_error.json")
    assert _has_actionable_error_events(events) is True


def test_a4_schema_validation_failure_summary_is_actionable() -> None:
    """A4: Payloads with schema validation failure summaries are actionable."""
    from gsd_browser.real_world_sanity import _has_agent_provider_schema_failure

    payload = _load_fixture("payload_failed_schema_validation.json")
    assert _has_agent_provider_schema_failure(payload) is True


def test_a4_provider_error_summary_is_actionable() -> None:
    """A4: Payloads with provider error summaries are actionable."""
    from gsd_browser.real_world_sanity import _has_agent_provider_schema_failure

    payload = _load_fixture("payload_failed_provider_error.json")
    assert _has_agent_provider_schema_failure(payload) is True


def test_a4_pydantic_error_summary_is_actionable() -> None:
    """A4: Payloads with Pydantic error summaries are actionable."""
    from gsd_browser.real_world_sanity import _has_agent_provider_schema_failure

    payload = _load_fixture("payload_failed_pydantic.json")
    assert _has_agent_provider_schema_failure(payload) is True


def test_a4_schema_validation_with_artifacts_classifies_soft_fail() -> None:
    """A4: Schema validation failure + artifacts → soft_fail."""
    from gsd_browser.real_world_sanity import _classify

    payload = _load_fixture("payload_failed_schema_validation.json")

    # Schema validation failure + artifacts (screenshots) → soft_fail
    assert (
        _classify(
            payload=payload,
            artifact_screenshots=1,
            artifact_events=0,
            has_actionable_reason=True,
        )
        == "soft_fail"
    )


def test_a4_provider_error_with_artifacts_classifies_soft_fail() -> None:
    """A4: Provider error + artifacts → soft_fail."""
    from gsd_browser.real_world_sanity import _classify

    payload = _load_fixture("payload_failed_provider_error.json")

    # Provider error + artifacts (events) → soft_fail
    assert (
        _classify(
            payload=payload,
            artifact_screenshots=0,
            artifact_events=2,
            has_actionable_reason=True,
        )
        == "soft_fail"
    )


def test_a4_failed_without_artifacts_classifies_hard_fail() -> None:
    """A4: Failed + no artifacts → hard_fail (even with actionable reason)."""
    from gsd_browser.real_world_sanity import _classify

    payload = _load_fixture("payload_failed_schema_validation.json")

    # Failed + no artifacts → hard_fail
    assert (
        _classify(
            payload=payload,
            artifact_screenshots=0,
            artifact_events=0,
            has_actionable_reason=True,
        )
        == "hard_fail"
    )


def test_a4_failed_with_artifacts_but_no_actionable_reason_classifies_hard_fail() -> None:
    """A4: Failed + artifacts but no actionable reason → hard_fail."""
    from gsd_browser.real_world_sanity import _classify

    payload = {"status": "failed", "result": "", "summary": "Unknown error"}

    # Failed + artifacts but no actionable reason → hard_fail
    assert (
        _classify(
            payload=payload,
            artifact_screenshots=1,
            artifact_events=1,
            has_actionable_reason=False,
        )
        == "hard_fail"
    )


def test_a4_integration_agent_events_make_classification_actionable() -> None:
    """A4: Integration test - agent events with has_error=True contribute to actionable classification."""
    from gsd_browser.real_world_sanity import (
        _classify,
        _has_actionable_error_events,
        _has_agent_provider_schema_failure,
        _has_payload_failure_reason,
    )

    # Simulate a scenario with agent error event but no other actionable signals
    payload = {"status": "failed", "result": "", "summary": "Agent execution failed"}
    events = _load_fixture("events_agent_schema_error.json")

    # The agent event should be actionable
    has_event_actionable = _has_actionable_error_events(events)
    has_payload_reason = _has_payload_failure_reason(payload)
    has_schema_failure = _has_agent_provider_schema_failure(payload)

    assert has_event_actionable is True
    actionable = has_event_actionable or has_payload_reason or has_schema_failure

    # With artifacts + actionable agent event → soft_fail
    classification = _classify(
        payload=payload,
        artifact_screenshots=1,
        artifact_events=len(events),
        has_actionable_reason=actionable,
    )
    assert classification == "soft_fail"
