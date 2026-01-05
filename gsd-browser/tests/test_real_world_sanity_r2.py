from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_fixture(name: str) -> Any:
    path = Path(__file__).parent / "fixtures" / "r2" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_r2_actionable_reason_console_error_event() -> None:
    from gsd_browser.real_world_sanity import _has_actionable_error_events

    events = _load_fixture("events_console_error.json")
    assert _has_actionable_error_events(events) is True


def test_r2_actionable_reason_network_4xx_event() -> None:
    from gsd_browser.real_world_sanity import _has_actionable_error_events

    events = _load_fixture("events_network_403.json")
    assert _has_actionable_error_events(events) is True


def test_r2_actionable_reason_false_for_non_error_events() -> None:
    from gsd_browser.real_world_sanity import _has_actionable_error_events

    events = _load_fixture("events_non_actionable.json")
    assert _has_actionable_error_events(events) is False


def test_r2_actionable_reason_payload_failure_reason_key() -> None:
    from gsd_browser.real_world_sanity import _has_payload_failure_reason

    payload = _load_fixture("payload_failed_with_failure_reason.json")
    assert _has_payload_failure_reason(payload) is True


def test_r2_actionable_reason_payload_failureReason_key() -> None:
    from gsd_browser.real_world_sanity import _has_payload_failure_reason

    payload = _load_fixture("payload_failed_with_failureReason.json")
    assert _has_payload_failure_reason(payload) is True


def test_r2_actionable_reason_payload_errors_top_judge_summary() -> None:
    from gsd_browser.real_world_sanity import _has_payload_failure_reason

    payload = _load_fixture("payload_failed_with_errors_top_judge.json")
    assert _has_payload_failure_reason(payload) is True


def test_r2_actionable_reason_payload_missing_reason_is_false() -> None:
    from gsd_browser.real_world_sanity import _has_payload_failure_reason

    payload = _load_fixture("payload_failed_no_reason.json")
    assert _has_payload_failure_reason(payload) is False


def test_r2_classify_pass_success_non_empty_result() -> None:
    from gsd_browser.real_world_sanity import _classify

    payload = _load_fixture("payload_pass.json")
    assert (
        _classify(
            payload=payload,
            artifact_screenshots=0,
            artifact_events=0,
            has_actionable_reason=False,
        )
        == "pass"
    )


def test_r2_classify_soft_fail_failed_with_artifacts_and_reason() -> None:
    from gsd_browser.real_world_sanity import _classify

    payload = _load_fixture("payload_failed_no_reason.json")
    assert (
        _classify(
            payload=payload,
            artifact_screenshots=1,
            artifact_events=0,
            has_actionable_reason=True,
        )
        == "soft_fail"
    )


def test_r2_classify_soft_fail_partial_with_artifacts_and_reason() -> None:
    from gsd_browser.real_world_sanity import _classify

    payload = _load_fixture("payload_partial_no_reason.json")
    assert (
        _classify(
            payload=payload,
            artifact_screenshots=0,
            artifact_events=2,
            has_actionable_reason=True,
        )
        == "soft_fail"
    )


def test_r2_classify_hard_fail_when_artifacts_missing() -> None:
    from gsd_browser.real_world_sanity import _classify

    payload = _load_fixture("payload_failed_no_reason.json")
    assert (
        _classify(
            payload=payload,
            artifact_screenshots=0,
            artifact_events=0,
            has_actionable_reason=True,
        )
        == "hard_fail"
    )


def test_r2_classify_hard_fail_when_reason_missing() -> None:
    from gsd_browser.real_world_sanity import _classify

    payload = _load_fixture("payload_failed_no_reason.json")
    assert (
        _classify(
            payload=payload,
            artifact_screenshots=1,
            artifact_events=1,
            has_actionable_reason=False,
        )
        == "hard_fail"
    )


def test_r2_classify_hard_fail_success_with_empty_result() -> None:
    from gsd_browser.real_world_sanity import _classify

    payload = _load_fixture("payload_success_empty_result.json")
    assert (
        _classify(
            payload=payload,
            artifact_screenshots=1,
            artifact_events=1,
            has_actionable_reason=True,
        )
        == "hard_fail"
    )
