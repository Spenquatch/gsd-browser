"""Opt-in real-world scenario harness for gsd-browser web_eval_agent.

This harness is intentionally not part of `pytest` or `make smoke`:
- it depends on external websites
- it requires a configured LLM provider and credentials
- results can vary over time
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context

from .config import load_settings
from .mcp_server import web_eval_agent
from .runtime import get_runtime


@dataclass(frozen=True)
class Scenario:
    id: str
    url: str
    task: str
    mode: str = "compact"
    headless_browser: bool = True
    expected: str = "pass"  # pass | soft_fail


DEFAULT_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        id="wikipedia-openai-first-sentence",
        url="https://en.wikipedia.org/wiki/OpenAI",
        task=(
            "Find the first paragraph of this article and return the first sentence. "
            "Also return the final URL of the page you used."
        ),
        expected="pass",
    ),
    Scenario(
        id="hackernews-top-story",
        url="https://news.ycombinator.com/",
        task=(
            "Return the title and direct URL of the first story on the page. "
            "Do not include comment links."
        ),
        expected="pass",
    ),
    Scenario(
        id="github-search-and-stars",
        url="https://github.com/search?q=browser+automation&type=repositories",
        task=(
            "Find the first repository in the search results, open it, and return the "
            "repository name and the number of stars it has."
        ),
        expected="pass",
    ),
    Scenario(
        id="wikipedia-link-navigation",
        url="https://en.wikipedia.org/wiki/Artificial_intelligence",
        task=(
            "Find the first link in the main article content (not in the sidebar or infobox) "
            "that goes to another Wikipedia article. Click it and return the title of the new "
            "article and its URL."
        ),
        expected="pass",
    ),
    Scenario(
        id="stackoverflow-question-check",
        url="https://stackoverflow.com/questions/tagged/python",
        task=(
            "Find the first question on the page (not pinned or featured), open it, and report: "
            "the question title, whether it has an accepted answer (yes/no), and the final URL."
        ),
        expected="pass",
    ),
    Scenario(
        id="npm-package-downloads",
        url="https://www.npmjs.com/search?q=playwright",
        task=(
            "Find the first package in the search results (should be 'playwright'), open it, "
            "and return the package name and weekly download count."
        ),
        expected="pass",
    ),
    Scenario(
        id="github-issue-investigation",
        url="https://github.com/microsoft/playwright/issues",
        task=(
            "Navigate to the Issues tab (if not already there), filter to show only open issues "
            "with the 'bug' label, open the first matching issue, check if it's assigned to someone, "
            "count how many comments it has, and return: issue number, title, assignment status "
            "(assigned/unassigned), and comment count."
        ),
        expected="soft_fail",  # Complex 7+ step task - may timeout
    ),
    Scenario(
        id="wikipedia-research-chain",
        url="https://en.wikipedia.org/wiki/Python_(programming_language)",
        task=(
            "Starting from this page: (1) Find and click the link to 'Guido van Rossum' in the main "
            "article content. (2) On his page, find and click the link to 'Netherlands'. "
            "(3) On the Netherlands page, find and click the link to 'Amsterdam'. "
            "(4) Extract the population of Amsterdam and return it along with the final URL."
        ),
        expected="soft_fail",  # Complex 7+ step task - may timeout
    ),
    Scenario(
        id="npm-package-deep-research",
        url="https://www.npmjs.com/package/playwright",
        task=(
            "From the playwright package page: (1) Note the weekly download count. "
            "(2) Find and click the 'Repository' link to go to GitHub. (3) On GitHub, find the number "
            "of stars. (4) Click on the 'Issues' tab. (5) Count the number of open issues (look for the "
            "count in the UI). (6) Return: package name, weekly downloads, GitHub stars, and open issues count."
        ),
        expected="pass",
    ),
    Scenario(
        id="huggingface-papers-botwall-probe",
        url="https://huggingface.co/papers",
        task=(
            "Identify the top paper and open it. Return the paper title and the final URL. "
            "If blocked by bot defenses or JS rendering issues, report exactly what is blocking "
            "progress and suggest the best remediation (e.g., use setup_browser_state, "
            "take control, try dev mode)."
        ),
        expected="soft_fail",
    ),
)


def _now_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def _write_json(path: Path, payload: Any, *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=sort_keys),
        encoding="utf-8",
    )


def _decode_image_bytes(image_b64: str) -> bytes | None:
    try:
        return base64.b64decode(image_b64, validate=False)
    except Exception:  # noqa: BLE001
        return None


def _ext_for_mime(mime: str | None) -> str:
    if mime == "image/png":
        return ".png"
    if mime == "image/jpeg":
        return ".jpg"
    if mime == "image/webp":
        return ".webp"
    return ".bin"


def _event_type(event: dict[str, Any]) -> str:
    value = event.get("event_type") or event.get("type") or ""
    return str(value).strip().lower()


def _event_details(event: dict[str, Any]) -> dict[str, Any]:
    details = event.get("details")
    return details if isinstance(details, dict) else {}


def _has_actionable_error_events(events: list[dict[str, Any]]) -> bool:
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = _event_type(event)
        details = _event_details(event)

        if event_type == "agent":
            if event.get("has_error") is True:
                return True

        if event_type == "console":
            level = str(details.get("level") or "").strip().lower()
            if level in {"error", "exception", "fatal"}:
                return True
            if event.get("has_error") is True:
                return True

        if event_type == "network":
            status = details.get("status")
            if isinstance(status, int) and status >= 400:
                return True
            if event.get("has_error") is True:
                return True

    return False


_FAILURE_REASON_KEYS = {"failure_reason", "failureReason"}


def _has_agent_provider_schema_failure(payload: dict[str, Any]) -> bool:
    """Check if payload indicates an agent/provider/schema validation failure."""
    summary = str(payload.get("summary") or "").lower()
    if not summary:
        return False

    # Common indicators of agent/provider/schema failures
    agent_failure_indicators = [
        "validation error",
        "pydantic",
        "schema",
        "provider error",
        "api error",
        "rate limit",
        "authentication",
        "invalid response",
        "parsing error",
        "json decode",
    ]

    return any(indicator in summary for indicator in agent_failure_indicators)


def _has_payload_failure_reason(payload: dict[str, Any]) -> bool:
    errors_top = payload.get("errors_top")
    if isinstance(errors_top, list):
        for item in errors_top:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip().lower() == "judge":
                summary = str(item.get("summary") or "").strip()
                if summary:
                    return True

    max_depth = 8
    max_nodes = 250
    visited = 0
    pending: list[tuple[Any, int]] = [(payload, max_depth)]

    while pending and visited < max_nodes:
        current, depth = pending.pop()
        visited += 1

        if isinstance(current, dict):
            for key, value in current.items():
                if key in _FAILURE_REASON_KEYS:
                    text = str(value).strip() if value is not None else ""
                    if text:
                        return True
                if depth > 0 and isinstance(value, (dict, list)):
                    pending.append((value, depth - 1))
        elif isinstance(current, list) and depth > 0:
            for value in current:
                if isinstance(value, (dict, list)):
                    pending.append((value, depth - 1))

    return False


def _classify(
    *,
    payload: dict[str, Any],
    artifact_screenshots: int,
    artifact_events: int,
    has_actionable_reason: bool,
) -> str:
    status = payload.get("status")
    result = payload.get("result")

    # Check for task failure indicators in the result text
    if isinstance(result, str):
        result_lower = result.strip().lower()
        failure_indicators = [
            "unable to complete",
            "cannot complete",
            "could not complete",
            "failed to complete",
            "impossible to complete",
            "task is impossible",
            "blocked by",
            "prevented from",
            "cannot proceed",
            "stopped",
            "bot detection",
            "bot wall",
            "captcha",
            "cloudflare",
            "security challenge",
        ]
        if any(indicator in result_lower for indicator in failure_indicators):
            # Agent explicitly stated it failed
            has_artifacts = artifact_screenshots > 0 or artifact_events > 0
            if has_artifacts and has_actionable_reason:
                return "soft_fail"
            return "hard_fail"

    if status == "success" and isinstance(result, str) and result.strip():
        return "pass"

    has_artifacts = artifact_screenshots > 0 or artifact_events > 0
    if status in {"failed", "partial"} and has_artifacts and has_actionable_reason:
        return "soft_fail"

    return "hard_fail"


def _summarize_errors(payload: dict[str, Any], events: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []

    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.append(f"summary: {summary.strip()}")

    dev_excerpts = payload.get("dev_excerpts")
    if isinstance(dev_excerpts, dict):
        for key in ("console_errors", "network_errors"):
            items = dev_excerpts.get(key)
            if isinstance(items, list) and items:
                lines.append(f"{key}: {len(items)}")

    for event in events[:10]:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("event_type") or event.get("type") or "unknown").strip()
        msg = event.get("summary")
        if isinstance(msg, str) and msg.strip():
            lines.append(f"{event_type}: {msg.strip()}")

    return lines


def _relative_path(path: Path, *, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except Exception:  # noqa: BLE001
        return os.path.relpath(path, start=base).replace(os.sep, "/")


async def _run_one(
    *, scenario: Scenario, out_dir: Path, run_root: Path, settings: Any
) -> dict[str, Any]:
    ctx = Context()
    result = await web_eval_agent(
        url=scenario.url,
        task=scenario.task,
        headless_browser=scenario.headless_browser,
        mode=scenario.mode,
        ctx=ctx,
    )

    if not result or not hasattr(result[0], "text"):
        raise RuntimeError("web_eval_agent returned no TextContent payload")

    payload = json.loads(result[0].text)
    session_id = str(payload.get("session_id") or "")

    runtime = get_runtime()
    screenshots = runtime.screenshots.get_screenshots(
        last_n=200,
        screenshot_type="agent_step",
        session_id=session_id or None,
        include_images=True,
    )

    screenshots_dir = out_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    written: list[dict[str, Any]] = []
    for shot in screenshots:
        image_b64 = shot.get("image_data")
        image_bytes = _decode_image_bytes(str(image_b64)) if image_b64 else None
        if not image_bytes:
            continue
        step = shot.get("step")
        ext = _ext_for_mime(shot.get("mime_type"))
        filename = f"step-{step if isinstance(step, int) else 'x'}-{shot.get('id')}{ext}"
        (screenshots_dir / filename).write_bytes(image_bytes)
        written.append(
            {
                "id": shot.get("id"),
                "timestamp": shot.get("timestamp") or shot.get("captured_at"),
                "type": shot.get("type"),
                "source": shot.get("source"),
                "session_id": shot.get("session_id"),
                "has_error": shot.get("has_error"),
                "metadata": shot.get("metadata"),
                "mime_type": shot.get("mime_type"),
                "url": shot.get("url"),
                "step": shot.get("step"),
                "filename": filename,
            }
        )

    # Capture error-focused run events.
    events = runtime.run_events.get_events(
        session_id=session_id or None,
        last_n=200,
        event_types=["agent", "console", "network"],
        from_timestamp=None,
        has_error=True,
        include_details=True,
    )

    response_path = out_dir / "response.json"
    events_path = out_dir / "events.json"
    screenshots_index = out_dir / "screenshots.json"

    _write_json(response_path, payload)
    _write_json(events_path, events)
    _write_json(screenshots_index, written)

    actionable = (
        _has_actionable_error_events(events)
        or _has_payload_failure_reason(payload)
        or _has_agent_provider_schema_failure(payload)
    )

    classification = _classify(
        payload=payload,
        artifact_screenshots=len(written),
        artifact_events=len(events),
        has_actionable_reason=actionable,
    )

    bundle_dir = _relative_path(out_dir, base=run_root)

    return {
        "scenario": {"id": scenario.id, "url": scenario.url, "expected": scenario.expected},
        "result": {
            "status": payload.get("status"),
            "classification": classification,
            "session_id": session_id,
            "screenshots_written": len(written),
            "events_with_error": len(events),
            "result_present": bool(
                isinstance(payload.get("result"), str) and payload["result"].strip()
            ),
        },
        "paths": {
            "dir": str(out_dir),
            "response_json": f"{bundle_dir}/response.json",
            "events_json": f"{bundle_dir}/events.json",
            "screenshots_index": f"{bundle_dir}/screenshots.json",
            "screenshots_dir": f"{bundle_dir}/screenshots",
        },
        "highlights": _summarize_errors(payload, events),
        "settings": {
            "llm_provider": settings.llm_provider,
            "model": settings.model,
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run opt-in real-world sanity scenarios for gsd-browser"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts") / "real_world_sanity" / _now_slug(),
        help="Output directory for the report bundle",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help="Scenario id to run (repeatable). Default: run all.",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in non-headless mode (applies to all scenarios).",
    )
    return parser.parse_args(argv)


def _select_scenarios(selected: list[str] | None) -> list[Scenario]:
    if not selected:
        return list(DEFAULT_SCENARIOS)
    wanted = {item.strip() for item in selected if item and item.strip()}
    scenarios = [s for s in DEFAULT_SCENARIOS if s.id in wanted]
    missing = sorted(wanted - {s.id for s in scenarios})
    if missing:
        raise SystemExit(
            f"Unknown scenario ids: {missing}. Known: {[s.id for s in DEFAULT_SCENARIOS]}"
        )
    return scenarios


def _render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# gsd-browser real-world sanity report")
    lines.append("")
    lines.append(f"- Timestamp (UTC): `{summary['started_at']}`")
    lines.append(f"- Output dir: `{summary['out_dir']}`")
    lines.append("")

    runs = list(summary["runs"])
    for idx, item in enumerate(runs):
        if idx:
            lines.append("")

        sid = item["scenario"]["id"]
        lines.append(f"## {sid}")
        lines.append("")
        lines.append(f"- URL: {item['scenario']['url']}")
        lines.append(f"- Expected: `{item['scenario']['expected']}`")
        lines.append(f"- Tool status: `{item['result']['status']}`")
        lines.append(f"- Classification: `{item['result']['classification']}`")
        lines.append(f"- Session: `{item['result']['session_id']}`")
        lines.append(f"- Screenshots: `{item['result']['screenshots_written']}`")
        lines.append(f"- Error events: `{item['result']['events_with_error']}`")
        lines.append(f"- Response: `{item['paths']['response_json']}`")
        lines.append(f"- Events: `{item['paths']['events_json']}`")
        lines.append(f"- Screenshots index: `{item['paths']['screenshots_index']}`")

        highlights = item.get("highlights")
        if isinstance(highlights, list) and highlights:
            lines.append("")
            lines.append("Highlights:")
            for hl in highlights:
                lines.append(f"- {hl}")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    print(
        "NOTE: This is an opt-in harness that hits external websites and "
        "requires credentials + internet.",
        file=sys.stderr,
    )
    print(
        "NOTE: It is intentionally not part of default CI, pytest, or make smoke.",
        file=sys.stderr,
    )

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    settings = load_settings(strict=False)

    scenarios = _select_scenarios(args.scenarios)
    if args.no_headless:
        scenarios = [
            Scenario(
                id=s.id,
                url=s.url,
                task=s.task,
                mode=s.mode,
                headless_browser=False,
                expected=s.expected,
            )
            for s in scenarios
        ]

    # Avoid printing secrets; just a quick “configured?” hint.
    env_hint = {
        "GSD_BROWSER_LLM_PROVIDER": os.environ.get("GSD_BROWSER_LLM_PROVIDER", ""),
        "GSD_BROWSER_MODEL": os.environ.get("GSD_BROWSER_MODEL", ""),
        "ANTHROPIC_API_KEY_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "OPENAI_API_KEY_set": bool(os.environ.get("OPENAI_API_KEY")),
        "BROWSER_USE_API_KEY_set": bool(os.environ.get("BROWSER_USE_API_KEY")),
        "OLLAMA_HOST_set": bool(os.environ.get("OLLAMA_HOST")),
    }

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    import asyncio

    runs: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_dir = out_dir / scenario.id
        scenario_dir.mkdir(parents=True, exist_ok=True)
        runs.append(
            asyncio.run(
                _run_one(
                    scenario=scenario,
                    out_dir=scenario_dir,
                    run_root=out_dir,
                    settings=settings,
                )
            )
        )

    summary = {
        "started_at": started_at,
        "out_dir": str(out_dir),
        "env_hint": env_hint,
        "runs": runs,
    }

    _write_json(out_dir / "summary.json", summary, sort_keys=True)
    (out_dir / "report.md").write_text(_render_markdown(summary), encoding="utf-8")

    # Minimal terminal summary.
    for run in runs:
        print(
            f"{run['scenario']['id']}: {run['result']['classification']} "
            f"(status={run['result']['status']} screenshots={run['result']['screenshots_written']})"
        )
    print(f"Wrote report bundle to {out_dir}")


__all__ = ["Scenario", "DEFAULT_SCENARIOS", "main"]


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
