from __future__ import annotations

import json
from pathlib import Path

from gsd_browser.contracts.v1 import (
    GetRunEventsPayloadV1,
    GetScreenshotsPayloadV1,
    SetupBrowserStatePayloadV1,
    TasksAdminListPayloadV1,
    TasksListPayloadV1,
    WebEvalAgentPayloadV1,
    WebTaskAgentGitHubPayloadV1,
    WebTaskAgentPayloadV1,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_exported_jsonschema_files_are_in_sync() -> None:
    root = Path(__file__).resolve().parents[1]
    base = root / "docs" / "api" / "jsonschema"

    expected = {
        "gsd.web_eval_agent.v1.schema.json": WebEvalAgentPayloadV1.model_json_schema(),
        "gsd.web_task_agent.v1.schema.json": WebTaskAgentPayloadV1.model_json_schema(),
        "gsd.web_task_agent_github.v1.schema.json": WebTaskAgentGitHubPayloadV1.model_json_schema(),
        "gsd.get_run_events.v1.schema.json": GetRunEventsPayloadV1.model_json_schema(),
        "gsd.get_screenshots.v1.schema.json": GetScreenshotsPayloadV1.model_json_schema(),
        "gsd.setup_browser_state.v1.schema.json": SetupBrowserStatePayloadV1.model_json_schema(),
        "gsd.tasks_list.v1.schema.json": TasksListPayloadV1.model_json_schema(),
        "gsd.tasks_admin_list.v1.schema.json": TasksAdminListPayloadV1.model_json_schema(),
    }

    for filename, schema in expected.items():
        path = base / filename
        assert path.exists(), f"Missing schema file: {path}"
        assert _load(path) == schema, (
            f"Schema file out of date: {path}\n"
            "Run `./.venv/bin/python tools/export_contract_schemas.py` and commit the results."
        )
