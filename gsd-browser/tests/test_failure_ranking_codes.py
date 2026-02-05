from __future__ import annotations

from dataclasses import dataclass

from gsd_browser.failure_ranking import RankedFailure, rank_failures_for_session


@dataclass(frozen=True)
class _Judgement:
    failure_reason: str | None = None
    reached_captcha: bool = False
    impossible_task: bool = False


@dataclass(frozen=True)
class _History:
    _judgement: _Judgement

    def judgement(self) -> _Judgement:
        return self._judgement


def test_ranked_failure_public_dict_always_includes_code_key() -> None:
    failure = RankedFailure(
        score=1,
        type="agent",
        code=None,
        summary="boom",
        step=None,
        url="https://example.com/path?secret=1",
    )
    payload = failure.to_public_dict()
    assert "code" in payload
    assert payload["code"] is None


def test_rank_failures_emits_stable_judge_code_prefixes() -> None:
    payloads = rank_failures_for_session(
        run_events=None,
        session_id="s1",
        base_url="https://example.com",
        history=_History(
            _Judgement(
                failure_reason="bad",
                reached_captcha=True,
                impossible_task=True,
            )
        ),
        max_items=10,
    )
    codes = {entry.get("code") for entry in payloads if isinstance(entry, dict)}
    assert "judge.failure_reason" in codes
    assert "judge.reached_captcha" in codes
    assert "judge.impossible_task" in codes

