from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Contract models are intentionally forward-compatible.

    Clients must ignore unknown keys (schema uses `additionalProperties=true`).
    """

    model_config = ConfigDict(extra="allow")


class PageInfoV1(ContractModel):
    url: str | None
    title: str | None


class RankedFailureV1(ContractModel):
    type: Literal[
        "console",
        "network",
        "agent",
        "provider",
        "validation",
        "timeout",
        "cancelled",
    ]
    code: str | None = Field(default=None, max_length=120)
    summary: str = Field(max_length=400)
    step: int | None
    url: str | None


class TimeoutsV1(ContractModel):
    budget_s: float | None
    step_timeout_s: float | None
    max_steps: int | None
    timed_out: bool


class ArtifactsCountV1(ContractModel):
    screenshots: int
    stream_samples: int
    run_events: int


class DevExcerptsV1(ContractModel):
    console_errors: list[dict[str, Any]]
    network_errors: list[dict[str, Any]]
    errors_top: list[dict[str, Any]]


class WebEvalAgentPayloadV1(ContractModel):
    version: Literal["gsd.web_eval_agent.v1"]
    session_id: UUID
    tool_call_id: UUID
    url: str = Field(min_length=1, max_length=2000)
    task: str = Field(min_length=1)
    mode: Literal["compact", "dev"] | None
    requested_mode: str | None = None
    status: Literal["success", "failed", "partial"]
    result: str | None
    summary: str = Field(max_length=2048)
    page: PageInfoV1
    errors_top: list[RankedFailureV1]
    timeouts: TimeoutsV1
    warnings: list[str]
    artifacts: ArtifactsCountV1
    next_actions: list[str]
    dev_excerpts: DevExcerptsV1 | None = None


class WebTaskAgentPayloadV1(WebEvalAgentPayloadV1):
    version: Literal["gsd.web_task_agent.v1"]
    tool: Literal["web_task_agent"]


class WebTaskAgentGitHubPayloadV1(WebEvalAgentPayloadV1):
    version: Literal["gsd.web_task_agent_github.v1"]
    tool: Literal["web_task_agent_github"]


class RunEventStatsCountsV1(ContractModel):
    agent: int
    console: int
    network: int
    total: int


class RunEventStatsV1(ContractModel):
    counts: RunEventStatsCountsV1
    oldest_timestamp: float | None
    newest_timestamp: float | None


class GetRunEventsPayloadV1(ContractModel):
    version: Literal["gsd.get_run_events.v1"]
    session_id: str | None
    events: list[dict[str, Any]]
    stats: RunEventStatsV1
    error: str | None


class ArtifactRefV1(ContractModel):
    key: str | None
    url: str | None
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: float | None = None
    url_expires_at: float | None = None


class ScreenshotHeaderV1(ContractModel):
    id: str | None
    timestamp: float | None
    type: Literal["agent_step", "stream_sample"] | None
    session_id: str | None
    has_error: bool | None
    mime_type: str | None
    url: str | None
    step: int | None
    metadata: dict[str, Any]
    artifact: ArtifactRefV1


class ScreenshotFiltersV1(ContractModel):
    last_n: int
    screenshot_type: Literal["agent_step", "stream_sample", "all"]
    from_timestamp: float | None
    has_error: bool | None
    include_images: bool


class ScreenshotStatsV1(ContractModel):
    total_screenshots: int
    sampling_rate: int


class GetScreenshotsPayloadV1(ContractModel):
    version: Literal["gsd.get_screenshots.v1"]
    session_id: str | None
    filters: ScreenshotFiltersV1
    screenshots: list[ScreenshotHeaderV1]
    stats: ScreenshotStatsV1
    error: str | None


class SetupBrowserStatePayloadV1(ContractModel):
    version: Literal["gsd.setup_browser_state.v1"]
    status: Literal["success", "failed"]
    state_id: str | None
    url: str | None
    path: str | None
    summary: str
    traceback: str | None = None
    next_actions: list[str]
