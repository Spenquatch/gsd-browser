"""Failure ranking helpers for compact web_eval_agent responses.

This module intentionally stays privacy-respecting:
- No response bodies are captured.
- URLs are normalized to remove query/fragment parameters (common secret carriers).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .run_event_store import RunEventStore


def _truncate(text: str, *, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)] + "…"


def _safe_url(url: str | None) -> str | None:
    if not url:
        return None
    raw = str(url).strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except Exception:  # noqa: BLE001
        return _truncate(raw, max_len=1000)
    if not parsed.scheme or not parsed.netloc:
        return _truncate(raw, max_len=1000)
    stripped = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "", "", ""))
    return _truncate(stripped, max_len=1000)


def _host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlsplit(url)
    except Exception:  # noqa: BLE001
        return None
    host = parsed.hostname
    return host.lower() if host else None


_NOISE_ERROR_SUBSTRINGS = (
    "net::err_blocked_by_client",
    "err_blocked_by_client",
    "blocked_by_client",
    "blocked by client",
)

_NOISE_HOST_SUBSTRINGS = (
    "doubleclick.net",
    "googletagmanager.com",
    "google-analytics.com",
    "googlesyndication.com",
    "sentry.io",
    "stats.g.doubleclick.net",
)

_NOISE_PATH_SUBSTRINGS = (
    "/collect",
    "/analytics",
    "/beacon",
    "/cdn-cgi/beacon",
    "/cdn-cgi/rum",
    "/cdn-cgi/trace",
    "/pixel",
)


def _is_noise_network(*, url: str | None, error: str | None) -> bool:
    url_value = (url or "").lower()
    error_value = (error or "").lower()
    if any(token in error_value for token in _NOISE_ERROR_SUBSTRINGS):
        return True
    if any(token in url_value for token in _NOISE_PATH_SUBSTRINGS):
        return True
    host = _host(url_value)
    if host and any(token in host for token in _NOISE_HOST_SUBSTRINGS):
        return True
    return False


@dataclass(frozen=True)
class RankedFailure:
    score: int
    type: str
    summary: str
    step: int | None
    url: str | None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "summary": _truncate(self.summary, max_len=400),
            "step": self.step,
            "url": _safe_url(self.url),
        }


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _nearest_step_context(
    *,
    agent_timeline: list[tuple[float, int | None, str | None]],
    timestamp: float | None,
) -> tuple[int | None, str | None]:
    if not agent_timeline or timestamp is None:
        return None, None

    chosen_step: int | None = None
    chosen_url: str | None = None
    for ts, step, url in agent_timeline:
        if ts > timestamp:
            break
        chosen_step = step
        chosen_url = url
    return chosen_step, chosen_url


def rank_failures_for_session(
    *,
    run_events: RunEventStore | None,
    session_id: str,
    base_url: str | None,
    history: Any | None = None,
    max_items: int = 8,
) -> list[dict[str, Any]]:
    """Return bounded, ranked failure summaries for the given run session."""

    limit = min(max(int(max_items), 0), 10)
    if limit <= 0:
        return []

    base_host = _host(base_url) if base_url else None

    events: list[dict[str, Any]] = []
    if run_events is not None:
        get_events = getattr(run_events, "get_events", None)
        if callable(get_events):
            events = get_events(
                session_id=session_id,
                last_n=250,
                event_types=["agent", "console", "network"],
                from_timestamp=None,
                has_error=None,
                include_details=True,
            )

    def _event_ts(item: dict[str, Any]) -> float | None:
        ts = item.get("timestamp")
        if ts is None:
            ts = item.get("captured_at")
        try:
            return float(ts) if ts is not None else None
        except Exception:  # noqa: BLE001
            return None

    agent_timeline: list[tuple[float, int | None, str | None]] = []
    for event in reversed(events):
        if (event.get("event_type") or event.get("type")) != "agent":
            continue
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        ts = _event_ts(event)
        if ts is None:
            continue
        step = _coerce_int(details.get("step"))
        url = details.get("url")
        agent_timeline.append((ts, step, str(url) if url else None))

    candidates: list[RankedFailure] = []
    seen: set[str] = set()

    for event in events:
        event_type = event.get("event_type") or event.get("type")
        if event_type not in {"console", "network"}:
            continue
        if not event.get("has_error"):
            continue

        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        ts = _event_ts(event)
        step_ctx, url_ctx = _nearest_step_context(agent_timeline=agent_timeline, timestamp=ts)

        if event_type == "console":
            level = str(details.get("level") or "").lower()
            message = str(event.get("summary") or "").strip() or str(event.get("message") or "")
            summary = f"{level}: {message}".strip(": ").strip()
            summary_lower = summary.lower()
            score = 70
            if level in {"exception", "fatal"}:
                score += 40
            if any(token in summary_lower for token in _NOISE_ERROR_SUBSTRINGS):
                score -= 80
            if summary and summary not in seen:
                seen.add(summary)
                candidates.append(
                    RankedFailure(
                        score=score,
                        type="console",
                        summary=summary,
                        step=step_ctx,
                        url=url_ctx,
                    )
                )
            continue

        url = str(details.get("url") or "")
        method = str(details.get("method") or "")
        status = _coerce_int(details.get("status"))
        error = str(details.get("error") or "").strip() or None

        url_safe = _safe_url(url) or url_ctx
        host = _host(url_safe) if url_safe else None
        same_origin = bool(base_host and host and host == base_host)

        score = 60
        if status is not None:
            if status >= 500:
                score += 80
            elif status >= 400:
                score += 30
        if error:
            score += 40
        if same_origin:
            score += 25
        else:
            score -= 5
        if _is_noise_network(url=url_safe, error=error):
            score -= 90

        status_part = f"{status}" if status is not None else ""
        error_part = f"{error}" if error else ""
        extra = " ".join(part for part in (status_part, error_part) if part).strip()
        summary = f"{method} {url_safe or url}".strip()
        if extra:
            summary = f"{summary} ({extra})"

        if summary and summary not in seen:
            seen.add(summary)
            candidates.append(
                RankedFailure(
                    score=score,
                    type="network",
                    summary=summary,
                    step=step_ctx,
                    url=url_safe or url_ctx,
                )
            )

    if history is not None:
        errors_attr = getattr(history, "errors", None)
        if callable(errors_attr):
            errors_iter = errors_attr()
        else:
            errors_iter = errors_attr

        if errors_iter is not None:
            try:
                iterator = iter(errors_iter)
            except TypeError:
                iterator = iter([errors_iter])

            for err in iterator:
                if not err:
                    continue
                text = str(err).strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                score = 85
                lowered = text.lower()
                if "timeout" in lowered:
                    score += 10
                if "captcha" in lowered or "bot" in lowered:
                    score += 20
                candidates.append(
                    RankedFailure(
                        score=score,
                        type="agent",
                        summary=text,
                        step=None,
                        url=_safe_url(base_url),
                    )
                )
                if len(candidates) >= 50:
                    break

        judgement = getattr(history, "judgement", None)
        if callable(judgement):
            try:
                judgement_value = judgement()
            except Exception:  # noqa: BLE001
                judgement_value = None
            if judgement_value is not None:
                failure_reason = getattr(judgement_value, "failure_reason", None)
                if failure_reason:
                    text = str(failure_reason).strip()
                    if text and text not in seen:
                        seen.add(text)
                        candidates.append(
                            RankedFailure(
                                score=120,
                                type="judge",
                                summary=f"judge: {text}",
                                step=None,
                                url=_safe_url(base_url),
                            )
                        )
                for flag, label in (
                    ("reached_captcha", "judge: reached_captcha"),
                    ("impossible_task", "judge: impossible_task"),
                ):
                    value = getattr(judgement_value, flag, None)
                    if isinstance(value, bool) and value and label not in seen:
                        seen.add(label)
                        candidates.append(
                            RankedFailure(
                                score=120,
                                type="judge",
                                summary=label,
                                step=None,
                                url=_safe_url(base_url),
                            )
                        )

    candidates.sort(key=lambda item: item.score, reverse=True)
    return [candidate.to_public_dict() for candidate in candidates[:limit]]
