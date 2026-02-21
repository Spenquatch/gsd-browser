#!/usr/bin/env python3
"""CLI helper for the `web_structured_flow` MCP tool (record + replay).

This is primarily for operator/dev usage in Docker, where calling the tool via an MCP host
is inconvenient. It invokes `gsd_browser.mcp_server.web_structured_flow(...)` directly and
prints the JSON payload to stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


def _maybe_add_repo_src_to_path() -> None:
    # Allow running from a repo checkout without an editable install.
    try:
        repo_src = Path(__file__).resolve().parents[1] / "src"
    except Exception:
        return
    if repo_src.exists():
        sys.path.insert(0, str(repo_src))


def _load_json_file(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("--extract-json must be a JSON object")
    return payload


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--template-id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--state-id", default=None)
    parser.add_argument("--budget-s", type=float, default=None)
    parser.add_argument("--step-timeout-s", type=float, default=None)
    parser.add_argument("--settle-ms", type=int, default=None)
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override headless mode (default varies by record/replay).",
    )
    parser.add_argument(
        "--enable-default-extensions",
        action=argparse.BooleanOptionalAction,
        default=None,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="web_structured_flow_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    record = sub.add_parser("record", help="Record once (LLM Agent) and export an LLM-free script")
    _add_common_args(record)
    record.add_argument("--task", required=True)
    record.add_argument("--template-name", default=None)
    record.add_argument(
        "--strategy",
        choices=["auto", "agent", "codeagent"],
        default="auto",
    )
    record.add_argument("--min-actions", type=int, default=None)
    record.add_argument("--max-steps", type=int, default=None)
    record.add_argument("--require-llm-free-replay", action="store_true", default=True)
    record.add_argument(
        "--no-require-llm-free-replay",
        dest="require_llm_free_replay",
        action="store_false",
    )
    record.add_argument("--extract-json", default=None, help="Path to extract block JSON object")
    record.add_argument("--use-vision", default=None, help='true|false|auto (default: "auto")')

    replay = sub.add_parser("replay", help="Replay using the stored script (no LLM)")
    _add_common_args(replay)
    replay.add_argument(
        "--runner",
        choices=["script", "dsl", "script_then_dsl"],
        default="script_then_dsl",
    )

    return parser


async def _run(args: argparse.Namespace) -> int:
    _maybe_add_repo_src_to_path()
    from gsd_browser import mcp_server

    if args.cmd == "record":
        extract = _load_json_file(args.extract_json)
        record: dict[str, Any] = {
            "template_id": args.template_id,
            "template_name": args.template_name,
            "url": args.url,
            "task": args.task,
            "state_id": args.state_id,
            "strategy": args.strategy,
            "budget_s": args.budget_s,
            "step_timeout_s": args.step_timeout_s,
            "max_steps": args.max_steps,
            "min_actions": args.min_actions,
            "settle_ms": args.settle_ms,
            "require_llm_free_replay": args.require_llm_free_replay,
        }
        if args.headless is not None:
            record["headless_browser"] = bool(args.headless)
        if args.enable_default_extensions is not None:
            record["enable_default_extensions"] = bool(args.enable_default_extensions)
        if args.use_vision is not None:
            record["use_vision"] = args.use_vision
        if extract is not None:
            record["extract"] = extract

        out = await mcp_server.web_structured_flow(record=record)
    else:
        replay: dict[str, Any] = {
            "template_id": args.template_id,
            "url": args.url,
            "state_id": args.state_id,
            "runner": args.runner,
            "budget_s": args.budget_s,
            "step_timeout_s": args.step_timeout_s,
            "settle_ms": args.settle_ms,
        }
        if args.headless is not None:
            replay["headless_browser"] = bool(args.headless)
        if args.enable_default_extensions is not None:
            replay["enable_default_extensions"] = bool(args.enable_default_extensions)

        out = await mcp_server.web_structured_flow(replay=replay)

    payload = json.loads(out[0].text)
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("status") in {"success", "partial"} else 2


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()

