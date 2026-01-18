from __future__ import annotations

import json
from pathlib import Path


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

    from gsd_browser.contracts.v1 import (
        GetRunEventsPayloadV1,
        GetScreenshotsPayloadV1,
        SetupBrowserStatePayloadV1,
        WebEvalAgentPayloadV1,
        WebTaskAgentGitHubPayloadV1,
        WebTaskAgentPayloadV1,
    )

    out_dir = root / "docs" / "api" / "jsonschema"

    schemas = {
        "gsd.web_eval_agent.v1.schema.json": WebEvalAgentPayloadV1.model_json_schema(),
        "gsd.web_task_agent.v1.schema.json": WebTaskAgentPayloadV1.model_json_schema(),
        "gsd.web_task_agent_github.v1.schema.json": WebTaskAgentGitHubPayloadV1.model_json_schema(),
        "gsd.get_run_events.v1.schema.json": GetRunEventsPayloadV1.model_json_schema(),
        "gsd.get_screenshots.v1.schema.json": GetScreenshotsPayloadV1.model_json_schema(),
        "gsd.setup_browser_state.v1.schema.json": SetupBrowserStatePayloadV1.model_json_schema(),
    }

    for name, schema in schemas.items():
        _write(out_dir / name, schema)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
