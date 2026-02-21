from __future__ import annotations

from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    errors_top: list[RankedFailureV1] = Field(max_length=8)
    timeouts: TimeoutsV1
    warnings: list[str] = Field(max_length=20)
    artifacts: ArtifactsCountV1
    next_actions: list[str] = Field(max_length=20)
    dev_excerpts: DevExcerptsV1 | None = None


class WebTaskAgentPayloadV1(WebEvalAgentPayloadV1):
    version: Literal["gsd.web_task_agent.v1"]
    tool: Literal["web_task_agent"]


class WebTaskAgentGitHubPayloadV1(WebEvalAgentPayloadV1):
    version: Literal["gsd.web_task_agent_github.v1"]
    tool: Literal["web_task_agent_github"]


class StructuredFlowFieldSpecV1(ContractModel):
    name: str = Field(min_length=1, max_length=200)
    selector: str = Field(min_length=1, max_length=2000)
    kind: Literal["inner_text", "text_content", "html", "attr", "value"]
    attr: str | None = Field(default=None, max_length=200)
    nth: int = Field(default=0, ge=0)
    all: bool = False
    required: bool = False

    @model_validator(mode="after")
    def _validate_attr_requirement(self) -> Self:
        if self.kind == "attr" and not (self.attr and str(self.attr).strip()):
            raise ValueError("attr is required when kind='attr'")
        if self.kind != "attr" and self.attr is not None:
            raise ValueError("attr must be null unless kind='attr'")
        return self


class StructuredFlowStepResultV1(ContractModel):
    id: str = Field(min_length=1, max_length=200)
    type: Literal[
        "goto",
        "click",
        "fill",
        "press",
        "wait_selector",
        "wait_text",
        "eval_js",
        "extract_fields",
    ]
    status: Literal["success", "failed"]
    started_at: float | None = None
    finished_at: float | None = None
    url_before: str | None = Field(default=None, max_length=2000)
    url_after: str | None = Field(default=None, max_length=2000)
    value: Any | None = None
    fields: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=2000)


class RecordingInfoV1(ContractModel):
    enabled: bool
    dir: str | None = Field(default=None, max_length=2000)
    path: str | None = Field(default=None, max_length=2000)
    available: bool
    warning: str | None = Field(default=None, max_length=2000)
    size: dict[str, int] | None = None
    framerate: int | None = Field(default=None, ge=1, le=240)


class ExportedScriptV1(ContractModel):
    language: Literal["python"]
    content: str = Field(min_length=1)


class TemplateInfoV1(ContractModel):
    template_id: str = Field(min_length=1, max_length=200)
    template_name: str | None = Field(default=None, max_length=500)
    base_origin: str = Field(min_length=1, max_length=2000)
    created_at: float
    updated_at: float
    script_path: str = Field(min_length=1, max_length=2000)
    dsl_path: str | None = Field(default=None, max_length=2000)
    manifest_path: str = Field(min_length=1, max_length=2000)
    sha256: str = Field(min_length=1, max_length=128)
    uses_llm_at_replay: bool


class WebStructuredFlowPayloadV1(ContractModel):
    version: Literal["gsd.web_structured_flow.v1"]
    mode: Literal["record", "replay"]
    session_id: UUID
    tool_call_id: UUID
    status: Literal["success", "failed", "partial"]
    summary: str = Field(max_length=2048)
    url: str = Field(min_length=1, max_length=2000)
    final_url: str | None = Field(default=None, max_length=2000)
    extracted: dict[str, Any] | None = None
    template: TemplateInfoV1 | None = None
    runner_used: Literal["script", "dsl"] | None = None
    runner_fallback_used: bool = False
    steps: list[StructuredFlowStepResultV1] = Field(default_factory=list, max_length=500)
    script_logs: list[str] = Field(default_factory=list, max_length=400)
    warnings: list[str] = Field(default_factory=list, max_length=50)
    recording: RecordingInfoV1 | None = None
    exported_script: ExportedScriptV1 | None = None


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
    session_id: UUID | None
    events: list[dict[str, Any]] = Field(max_length=200)
    stats: RunEventStatsV1
    error: str | None


class ArtifactRefV1(ContractModel):
    key: UUID
    url: str | None
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: float | None = None
    url_expires_at: float | None = None


class ScreenshotHeaderV1(ContractModel):
    id: UUID
    timestamp: float | None
    type: Literal["agent_step", "stream_sample"] | None
    session_id: UUID
    has_error: bool | None
    mime_type: str | None
    url: str | None
    step: int | None
    inline_included: bool
    metadata: dict[str, Any]
    artifact: ArtifactRefV1

    @model_validator(mode="after")
    def _artifact_key_matches_id(self) -> Self:
        if self.artifact.key != self.id:
            raise ValueError("artifact.key must equal id")
        return self


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
    session_id: UUID | None
    filters: ScreenshotFiltersV1
    screenshots: list[ScreenshotHeaderV1] = Field(max_length=20)
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


class OpsErrorPayloadV1(ContractModel):
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, Any] | None = None


class JobProgressV1(ContractModel):
    current: int = Field(ge=0)
    total: int = Field(ge=0)
    percentage: float = Field(ge=0.0, le=100.0)


class JobSubmitPayloadV1(ContractModel):
    version: Literal["gsd.job_submit.v1"]
    job_id: UUID | None
    tool_name: str | None = Field(default=None, max_length=200)
    state: Literal["queued"] | None = None
    session_id: UUID | None = None
    created_at: float | None = None
    expires_at: float | None = None
    error: OpsErrorPayloadV1 | None = None


class JobGetPayloadV1(ContractModel):
    version: Literal["gsd.job_get.v1"]
    job_id: UUID | None
    found: bool
    tool_name: str | None = Field(default=None, max_length=200)
    state: Literal["queued", "running", "completed", "failed", "cancelled"] | None = None
    progress_message: str = Field(default="", max_length=2000)
    progress: JobProgressV1 | None = None
    session_id: UUID | None = None
    created_at: float | None = None
    started_at: float | None = None
    updated_at: float | None = None
    finished_at: float | None = None
    expires_at: float | None = None
    error: OpsErrorPayloadV1 | None = None


class JobResultNotReadyErrorV1(OpsErrorPayloadV1):
    code: Literal["NOT_READY"]


class JobResultNotReadyPayloadV1(ContractModel):
    version: Literal["gsd.job_result.not_ready.v1"]
    job_id: UUID | None
    found: bool
    state: Literal["queued", "running"] | None = None
    progress_message: str = Field(default="", max_length=2000)
    progress: JobProgressV1 | None = None
    error: JobResultNotReadyErrorV1 | None = None


class JobCancelPayloadV1(ContractModel):
    version: Literal["gsd.job_cancel.v1"]
    job_id: UUID | None
    found: bool
    state: Literal["queued", "running", "completed", "failed", "cancelled"] | None = None
    error: OpsErrorPayloadV1 | None = None


class JobWaitTimeoutErrorDetailsV1(ContractModel):
    max_wait_s: int = Field(ge=0)


class JobWaitTimeoutErrorV1(ContractModel):
    code: Literal["TIMEOUT"]
    message: str = Field(min_length=1, max_length=500)
    details: JobWaitTimeoutErrorDetailsV1


class JobWaitTimeoutPayloadV1(ContractModel):
    version: Literal["gsd.job_wait.timeout.v1"]
    job_id: UUID
    state: Literal["queued", "running"]
    progress_message: str = Field(min_length=1, max_length=2000)
    progress: JobProgressV1 | None = None
    error: JobWaitTimeoutErrorV1


class TasksListItemV1(ContractModel):
    task_id: UUID
    tool_name: str = Field(min_length=1, max_length=200)
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    created_at: str = Field(min_length=1, max_length=64)
    updated_at: str | None = Field(default=None, max_length=64)
    expires_at: str = Field(min_length=1, max_length=64)
    session_id: UUID


class TasksListPayloadV1(ContractModel):
    version: Literal["gsd.tasks_list.v1"]
    tasks: list[TasksListItemV1] = Field(max_length=1000)
    next_cursor: str | None
    error: OpsErrorPayloadV1 | None


class TasksAdminListItemV1(TasksListItemV1):
    tenant_id: str = Field(min_length=1, max_length=200)
    subject_id: str = Field(min_length=1, max_length=200)
    transport: Literal["stdio", "http"]


class TasksAdminListPayloadV1(ContractModel):
    version: Literal["gsd.tasks_admin_list.v1"]
    tasks: list[TasksAdminListItemV1] = Field(max_length=1000)
    next_cursor: str | None
    error: OpsErrorPayloadV1 | None
