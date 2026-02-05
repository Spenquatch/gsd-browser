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
        JobCancelPayloadV1,
        JobGetPayloadV1,
        JobResultNotReadyPayloadV1,
        JobSubmitPayloadV1,
        JobWaitTimeoutPayloadV1,
        SetupBrowserStatePayloadV1,
        TasksAdminListPayloadV1,
        TasksListPayloadV1,
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
        "gsd.tasks_list.v1.schema.json": TasksListPayloadV1.model_json_schema(),
        "gsd.tasks_admin_list.v1.schema.json": TasksAdminListPayloadV1.model_json_schema(),
        "gsd.job_submit.v1.schema.json": JobSubmitPayloadV1.model_json_schema(),
        "gsd.job_get.v1.schema.json": JobGetPayloadV1.model_json_schema(),
        "gsd.job_result.not_ready.v1.schema.json": JobResultNotReadyPayloadV1.model_json_schema(),
        "gsd.job_cancel.v1.schema.json": JobCancelPayloadV1.model_json_schema(),
        "gsd.job_wait.timeout.v1.schema.json": JobWaitTimeoutPayloadV1.model_json_schema(),
    }

    for name, schema in schemas.items():
        _write(out_dir / name, schema)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
