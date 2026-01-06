# A3 — Persist LLM/provider/schema failures as run events

## Scope
Ensure that the most common “early abort” failures (LLM/provider/schema validation) produce persisted, actionable run events.

### Requirements
- Persist schema validation / provider errors as run events with:
  - `event_type="agent"`
  - `has_error=true`
  - bounded, privacy-safe summaries
- Events must be queryable via `get_run_events(..., has_error=true)` and eligible for compact `errors_top` ranking.

## Acceptance criteria
1. Fixture tests cover:
   - schema validation failure emits a `has_error=true` agent event
   - provider error emits a `has_error=true` agent event

## Out of scope
- Changing harness classification rules (A4).
- Prompt wrapper content changes (A1).
- Screenshot capture timing changes (A2).

*** Add File: docs/project_management/next/browser-use-contract-alignment/A4-spec.md
# A4 — Harness actionable classification for agent failures

## Scope
Make the real-world sanity harness treat “agent/provider/schema validation” failures as actionable so expected failure scenarios classify as `soft_fail` when artifacts exist.

### Requirements
- Update the harness “actionable reason” predicate so that:
  - agent/provider/schema failure summaries (from tool payload and/or run events) count as actionable, even without console/network errors
  - judge failure_reason remains actionable (when present)
- Keep the classification rules stable:
  - `pass`: `status=success` and non-empty `result`
  - `soft_fail`: `status=failed|partial` + artifacts + actionable reason
  - `hard_fail`: missing artifacts OR no actionable reason

## Acceptance criteria
1. Fixture tests cover:
   - schema validation failure + artifacts → `soft_fail`
   - provider error + artifacts → `soft_fail`
   - failed + no artifacts → `hard_fail`
2. Real-world harness expected-soft-fail scenarios classify as `soft_fail` (not `hard_fail`) when artifacts are present.

## Out of scope
- Recording new run event types (A3 owns persistence).
- Prompt wrapper content changes (A1).
- Screenshot capture timing changes (A2).

*** Add File: docs/project_management/next/browser-use-contract-alignment/session_log.md
# Browser-use Contract Alignment Session Log

Only START/END entries. Docs edits happen on the orchestration branch only.

## Entries

*** Add File: docs/project_management/next/browser-use-contract-alignment/tasks.json
{
  "tasks": [
    {
      "id": "A1-code",
      "name": "Prompt wrapper contract alignment (code)",
      "type": "code",
      "phase": "A1",
      "status": "pending",
      "description": "Update the browser-use prompt wrapper so stop conditions and completion are expressed via the `done` action (no conflicting alternate JSON schema).",
      "references": [
        "docs/adr/ADR-0005-browser-use-contract-alignment-and-artifact-reliability.md",
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A1-spec.md",
        "gsd-browser/src/gsd_browser/mcp_server.py"
      ],
      "acceptance_criteria": [
        "Prompt wrapper does not instruct a non-ActionModel JSON output schema.",
        "Prompt wrapper explicitly instructs using a single `done` action for stop conditions and completion.",
        "Ruff format/check pass."
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A1-spec.md, kickoff_prompts/A1-code.md",
        "Set A1-code status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A1-code)",
        "git branch buca-a1-prompt-code feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a1-prompt-code buca-a1-prompt-code",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run ruff check",
        "Commit changes inside wt/buca-a1-prompt-code",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A1-code)",
        "git worktree remove wt/buca-a1-prompt-code"
      ],
      "worktree": "wt/buca-a1-prompt-code",
      "integration_task": "A1-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A1-code.md",
      "depends_on": [],
      "concurrent_with": ["A1-test"]
    },
    {
      "id": "A1-test",
      "name": "Prompt wrapper contract alignment (test)",
      "type": "test",
      "phase": "A1",
      "status": "pending",
      "description": "Update/add deterministic tests asserting the prompt wrapper does not instruct alternate schemas and does instruct done-action semantics.",
      "references": [
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A1-spec.md",
        "gsd-browser/tests/mcp/test_c2_prompt_wrapper.py"
      ],
      "acceptance_criteria": [
        "Targeted pytest passes for the updated/added tests.",
        "Ruff format passes."
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A1-spec.md, kickoff_prompts/A1-test.md",
        "Set A1-test status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A1-test)",
        "git branch buca-a1-prompt-test feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a1-prompt-test buca-a1-prompt-test",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run pytest gsd-browser/tests -k \"prompt_wrapper\"",
        "Commit changes inside wt/buca-a1-prompt-test",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A1-test)",
        "git worktree remove wt/buca-a1-prompt-test"
      ],
      "worktree": "wt/buca-a1-prompt-test",
      "integration_task": "A1-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A1-test.md",
      "depends_on": [],
      "concurrent_with": ["A1-code"]
    },
    {
      "id": "A1-integ",
      "name": "Prompt wrapper contract alignment (integration)",
      "type": "integration",
      "phase": "A1",
      "status": "pending",
      "description": "Integrate A1 code+tests, reconcile to spec, and ensure ruff+pytest+smoke are green.",
      "references": [
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A1-spec.md"
      ],
      "acceptance_criteria": [
        "uv run ruff format --check passes",
        "uv run ruff check passes",
        "uv run pytest passes",
        "make smoke passes"
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A1-spec.md, kickoff_prompts/A1-integ.md",
        "Set A1-integ status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A1-integ)",
        "git branch buca-a1-prompt-integ feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a1-prompt-integ buca-a1-prompt-integ",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run ruff check",
        "uv run pytest",
        "make smoke",
        "Commit changes inside wt/buca-a1-prompt-integ",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A1-integ)",
        "git worktree remove wt/buca-a1-prompt-integ"
      ],
      "worktree": "wt/buca-a1-prompt-integ",
      "integration_task": "A1-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A1-integ.md",
      "depends_on": ["A1-code", "A1-test"],
      "concurrent_with": []
    },

    {
      "id": "A2-code",
      "name": "Pre-teardown screenshot guarantee (code)",
      "type": "code",
      "phase": "A2",
      "status": "pending",
      "description": "Guarantee at least one step screenshot is captured before browser-use session teardown (especially on early aborts).",
      "references": [
        "docs/adr/ADR-0005-browser-use-contract-alignment-and-artifact-reliability.md",
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A2-spec.md",
        "gsd-browser/src/gsd_browser/mcp_server.py"
      ],
      "acceptance_criteria": [
        "Screenshot guarantee occurs pre-teardown via browser-use hooks/callbacks.",
        "Ruff format/check pass."
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A2-spec.md, kickoff_prompts/A2-code.md",
        "Set A2-code status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A2-code)",
        "git branch buca-a2-screenshot-code feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a2-screenshot-code buca-a2-screenshot-code",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run ruff check",
        "Commit changes inside wt/buca-a2-screenshot-code",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A2-code)",
        "git worktree remove wt/buca-a2-screenshot-code"
      ],
      "worktree": "wt/buca-a2-screenshot-code",
      "integration_task": "A2-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A2-code.md",
      "depends_on": ["A1-integ"],
      "concurrent_with": ["A2-test"]
    },
    {
      "id": "A2-test",
      "name": "Pre-teardown screenshot guarantee (test)",
      "type": "test",
      "phase": "A2",
      "status": "pending",
      "description": "Add deterministic tests simulating early abort paths and asserting at least one screenshot is recorded.",
      "references": [
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A2-spec.md"
      ],
      "acceptance_criteria": [
        "Targeted pytest passes for the new tests.",
        "Ruff format passes."
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A2-spec.md, kickoff_prompts/A2-test.md",
        "Set A2-test status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A2-test)",
        "git branch buca-a2-screenshot-test feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a2-screenshot-test buca-a2-screenshot-test",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run pytest gsd-browser/tests -k \"screenshot\"",
        "Commit changes inside wt/buca-a2-screenshot-test",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A2-test)",
        "git worktree remove wt/buca-a2-screenshot-test"
      ],
      "worktree": "wt/buca-a2-screenshot-test",
      "integration_task": "A2-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A2-test.md",
      "depends_on": ["A1-integ"],
      "concurrent_with": ["A2-code"]
    },
    {
      "id": "A2-integ",
      "name": "Pre-teardown screenshot guarantee (integration)",
      "type": "integration",
      "phase": "A2",
      "status": "pending",
      "description": "Integrate A2 code+tests, reconcile to spec, and ensure ruff+pytest+smoke are green.",
      "references": [
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A2-spec.md"
      ],
      "acceptance_criteria": [
        "uv run ruff format --check passes",
        "uv run ruff check passes",
        "uv run pytest passes",
        "make smoke passes"
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A2-spec.md, kickoff_prompts/A2-integ.md",
        "Set A2-integ status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A2-integ)",
        "git branch buca-a2-screenshot-integ feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a2-screenshot-integ buca-a2-screenshot-integ",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run ruff check",
        "uv run pytest",
        "make smoke",
        "Commit changes inside wt/buca-a2-screenshot-integ",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A2-integ)",
        "git worktree remove wt/buca-a2-screenshot-integ"
      ],
      "worktree": "wt/buca-a2-screenshot-integ",
      "integration_task": "A2-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A2-integ.md",
      "depends_on": ["A2-code", "A2-test"],
      "concurrent_with": []
    },

    {
      "id": "A3-code",
      "name": "Persist agent/provider failures as run events (code)",
      "type": "code",
      "phase": "A3",
      "status": "pending",
      "description": "Record LLM/provider/schema validation failures as `RunEventStore` error events (`event_type=agent`, `has_error=true`) so they persist into artifacts.",
      "references": [
        "docs/adr/ADR-0005-browser-use-contract-alignment-and-artifact-reliability.md",
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A3-spec.md",
        "gsd-browser/src/gsd_browser/mcp_server.py",
        "gsd-browser/src/gsd_browser/run_event_store.py"
      ],
      "acceptance_criteria": [
        "LLM/provider/schema failures record a `has_error=true` agent run event.",
        "Ruff format/check pass."
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A3-spec.md, kickoff_prompts/A3-code.md",
        "Set A3-code status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A3-code)",
        "git branch buca-a3-run-events-code feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a3-run-events-code buca-a3-run-events-code",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run ruff check",
        "Commit changes inside wt/buca-a3-run-events-code",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A3-code)",
        "git worktree remove wt/buca-a3-run-events-code"
      ],
      "worktree": "wt/buca-a3-run-events-code",
      "integration_task": "A3-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A3-code.md",
      "depends_on": ["A2-integ"],
      "concurrent_with": ["A3-test"]
    },
    {
      "id": "A3-test",
      "name": "Persist agent/provider failures as run events (test)",
      "type": "test",
      "phase": "A3",
      "status": "pending",
      "description": "Add deterministic tests asserting that schema/provider failures emit `has_error=true` agent run events.",
      "references": [
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A3-spec.md"
      ],
      "acceptance_criteria": [
        "Targeted pytest passes for the new tests.",
        "Ruff format passes."
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A3-spec.md, kickoff_prompts/A3-test.md",
        "Set A3-test status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A3-test)",
        "git branch buca-a3-run-events-test feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a3-run-events-test buca-a3-run-events-test",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run pytest gsd-browser/tests -k \"run_event\"",
        "Commit changes inside wt/buca-a3-run-events-test",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A3-test)",
        "git worktree remove wt/buca-a3-run-events-test"
      ],
      "worktree": "wt/buca-a3-run-events-test",
      "integration_task": "A3-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A3-test.md",
      "depends_on": ["A2-integ"],
      "concurrent_with": ["A3-code"]
    },
    {
      "id": "A3-integ",
      "name": "Persist agent/provider failures as run events (integration)",
      "type": "integration",
      "phase": "A3",
      "status": "pending",
      "description": "Integrate A3 code+tests, reconcile to spec, and ensure ruff+pytest+smoke are green.",
      "references": [
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A3-spec.md"
      ],
      "acceptance_criteria": [
        "uv run ruff format --check passes",
        "uv run ruff check passes",
        "uv run pytest passes",
        "make smoke passes"
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A3-spec.md, kickoff_prompts/A3-integ.md",
        "Set A3-integ status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A3-integ)",
        "git branch buca-a3-run-events-integ feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a3-run-events-integ buca-a3-run-events-integ",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run ruff check",
        "uv run pytest",
        "make smoke",
        "Commit changes inside wt/buca-a3-run-events-integ",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A3-integ)",
        "git worktree remove wt/buca-a3-run-events-integ"
      ],
      "worktree": "wt/buca-a3-run-events-integ",
      "integration_task": "A3-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A3-integ.md",
      "depends_on": ["A3-code", "A3-test"],
      "concurrent_with": []
    },

    {
      "id": "A4-code",
      "name": "Harness actionable classification for agent failures (code)",
      "type": "code",
      "phase": "A4",
      "status": "pending",
      "description": "Update the real-world harness actionable predicate so agent/provider/schema failures are considered actionable and classify as soft_fail when artifacts exist.",
      "references": [
        "docs/adr/ADR-0005-browser-use-contract-alignment-and-artifact-reliability.md",
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A4-spec.md",
        "gsd-browser/src/gsd_browser/real_world_sanity.py"
      ],
      "acceptance_criteria": [
        "Harness treats agent/provider/schema failure signals as actionable.",
        "Ruff format/check pass."
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A4-spec.md, kickoff_prompts/A4-code.md",
        "Set A4-code status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A4-code)",
        "git branch buca-a4-harness-classify-code feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a4-harness-classify-code buca-a4-harness-classify-code",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run ruff check",
        "Commit changes inside wt/buca-a4-harness-classify-code",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A4-code)",
        "git worktree remove wt/buca-a4-harness-classify-code"
      ],
      "worktree": "wt/buca-a4-harness-classify-code",
      "integration_task": "A4-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A4-code.md",
      "depends_on": ["A3-integ"],
      "concurrent_with": ["A4-test"]
    },
    {
      "id": "A4-test",
      "name": "Harness actionable classification for agent failures (test)",
      "type": "test",
      "phase": "A4",
      "status": "pending",
      "description": "Add fixture-based tests validating harness classification for agent/provider/schema failures.",
      "references": [
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A4-spec.md"
      ],
      "acceptance_criteria": [
        "Targeted pytest passes for the new tests.",
        "Ruff format passes."
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A4-spec.md, kickoff_prompts/A4-test.md",
        "Set A4-test status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A4-test)",
        "git branch buca-a4-harness-classify-test feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a4-harness-classify-test buca-a4-harness-classify-test",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run pytest gsd-browser/tests -k \"real_world_sanity\"",
        "Commit changes inside wt/buca-a4-harness-classify-test",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A4-test)",
        "git worktree remove wt/buca-a4-harness-classify-test"
      ],
      "worktree": "wt/buca-a4-harness-classify-test",
      "integration_task": "A4-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A4-test.md",
      "depends_on": ["A3-integ"],
      "concurrent_with": ["A4-code"]
    },
    {
      "id": "A4-integ",
      "name": "Harness actionable classification for agent failures (integration)",
      "type": "integration",
      "phase": "A4",
      "status": "pending",
      "description": "Integrate A4 code+tests, reconcile to spec, and ensure ruff+pytest+smoke are green.",
      "references": [
        "docs/project_management/next/browser-use-contract-alignment/plan.md",
        "docs/project_management/next/browser-use-contract-alignment/A4-spec.md"
      ],
      "acceptance_criteria": [
        "uv run ruff format --check passes",
        "uv run ruff check passes",
        "uv run pytest passes",
        "make smoke passes"
      ],
      "start_checklist": [
        "git checkout feat/browser-use-contract-alignment && git pull --ff-only",
        "Read plan.md, tasks.json, session_log.md, A4-spec.md, kickoff_prompts/A4-integ.md",
        "Set A4-integ status to in_progress in tasks.json",
        "Add START entry to session_log.md; commit docs (docs: start A4-integ)",
        "git branch buca-a4-harness-classify-integ feat/browser-use-contract-alignment",
        "git worktree add wt/buca-a4-harness-classify-integ buca-a4-harness-classify-integ",
        "Do not edit docs/tasks/session_log from the worktree"
      ],
      "end_checklist": [
        "uv run ruff format --check",
        "uv run ruff check",
        "uv run pytest",
        "make smoke",
        "Commit changes inside wt/buca-a4-harness-classify-integ",
        "Update tasks.json and session_log.md on feat/browser-use-contract-alignment (docs: finish A4-integ)",
        "git worktree remove wt/buca-a4-harness-classify-integ"
      ],
      "worktree": "wt/buca-a4-harness-classify-integ",
      "integration_task": "A4-integ",
      "kickoff_prompt": "docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A4-integ.md",
      "depends_on": ["A4-code", "A4-test"],
      "concurrent_with": []
    }
  ]
}

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A1-code.md
# Kickoff Prompt – A1-code (Prompt wrapper contract alignment)

## Scope
- Production code only; no tests. Implement `A1-spec.md`.
- Make the prompt wrapper contract-correct with browser-use: keep “anchor + stop conditions”, but express completion/stopping only via the `done` action (no alternate JSON schemas that conflict with `AgentOutput.action`).

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A1-spec.md`, this prompt.
3. Set `A1-code` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A1-code`).
5. Create branch `buca-a1-prompt-code` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a1-prompt-code buca-a1-prompt-code`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Update the prompt wrapper to:
  - anchor to base URL
  - define stop conditions (login, captcha/bot wall, impossible task)
  - instruct to use a single `done(success=true|false, text=...)` action to complete or stop
- Do not introduce any instruction that asks for a “JSON object only” output during the action loop.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`

## End Checklist
1. Run the required commands above and capture outputs.
2. Inside `wt/buca-a1-prompt-code`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A1-code`).
4. Remove worktree `wt/buca-a1-prompt-code`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A1-test.md
# Kickoff Prompt – A1-test (Prompt wrapper contract alignment)

## Scope
- Tests/fixtures only; no production code. Implement `A1-spec.md` acceptance tests.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A1-spec.md`, this prompt.
3. Set `A1-test` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A1-test`).
5. Create branch `buca-a1-prompt-test` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a1-prompt-test buca-a1-prompt-test`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Add/update tests to assert the wrapper:
  - does not instruct alternate output schemas (e.g., “single-line JSON object only”)
  - does instruct `done(success=...)` semantics
- Required commands:
  - `uv run ruff format --check`
  - `uv run pytest gsd-browser/tests -k "prompt_wrapper"`

## End Checklist
1. Run the required commands above and capture outputs.
2. Inside `wt/buca-a1-prompt-test`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A1-test`).
4. Remove worktree `wt/buca-a1-prompt-test`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A1-integ.md
# Kickoff Prompt – A1-integ (Prompt wrapper contract alignment)

## Scope
- Integration only: merge A1 code+tests, reconcile to `A1-spec.md`, and ensure green checks.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A1-spec.md`, this prompt.
3. Set `A1-integ` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A1-integ`).
5. Create branch `buca-a1-prompt-integ` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a1-prompt-integ buca-a1-prompt-integ`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Merge `buca-a1-prompt-code` + `buca-a1-prompt-test` and reconcile to spec.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`
  - `uv run pytest`
  - `make smoke`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a1-prompt-integ`, commit integration changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A1-integ`).
4. Remove worktree `wt/buca-a1-prompt-integ`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A2-code.md
# Kickoff Prompt – A2-code (Pre-teardown screenshot guarantee)

## Scope
- Production code only; no tests. Implement `A2-spec.md`.
- Guarantee screenshot capture before browser-use session teardown (don’t rely on post-run “current page”).

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A2-spec.md`, this prompt.
3. Set `A2-code` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A2-code`).
5. Create branch `buca-a2-screenshot-code` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a2-screenshot-code buca-a2-screenshot-code`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Implement a pre-teardown screenshot guarantee using browser-use hooks (prefer done callback).
- Keep scope narrow: only change timing/placement of screenshot guarantee logic.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a2-screenshot-code`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A2-code`).
4. Remove worktree `wt/buca-a2-screenshot-code`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A2-test.md
# Kickoff Prompt – A2-test (Pre-teardown screenshot guarantee)

## Scope
- Tests/fixtures only; no production code. Implement `A2-spec.md` acceptance tests.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A2-spec.md`, this prompt.
3. Set `A2-test` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A2-test`).
5. Create branch `buca-a2-screenshot-test` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a2-screenshot-test buca-a2-screenshot-test`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Add deterministic tests that simulate an early abort and assert at least one `agent_step` screenshot is recorded.
- Required commands:
  - `uv run ruff format --check`
  - `uv run pytest gsd-browser/tests -k "screenshot"`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a2-screenshot-test`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A2-test`).
4. Remove worktree `wt/buca-a2-screenshot-test`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A2-integ.md
# Kickoff Prompt – A2-integ (Pre-teardown screenshot guarantee)

## Scope
- Integration only: merge A2 code+tests, reconcile to `A2-spec.md`, and ensure green checks.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A2-spec.md`, this prompt.
3. Set `A2-integ` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A2-integ`).
5. Create branch `buca-a2-screenshot-integ` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a2-screenshot-integ buca-a2-screenshot-integ`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Merge `buca-a2-screenshot-code` + `buca-a2-screenshot-test` and reconcile to spec.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`
  - `uv run pytest`
  - `make smoke`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a2-screenshot-integ`, commit integration changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A2-integ`).
4. Remove worktree `wt/buca-a2-screenshot-integ`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A3-code.md
# Kickoff Prompt – A3-code (Persist agent/provider failures as run events)

## Scope
- Production code only; no tests. Implement `A3-spec.md`.
- Persist LLM/provider/schema validation failures into `RunEventStore` as `has_error=true` agent events.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A3-spec.md`, this prompt.
3. Set `A3-code` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A3-code`).
5. Create branch `buca-a3-run-events-code` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a3-run-events-code buca-a3-run-events-code`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Record early abort failures as run events:
  - schema validation failures
  - provider failures (ModelProviderError / equivalent)
- Keep event summaries privacy-safe and bounded.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a3-run-events-code`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A3-code`).
4. Remove worktree `wt/buca-a3-run-events-code`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A3-test.md
# Kickoff Prompt – A3-test (Persist agent/provider failures as run events)

## Scope
- Tests/fixtures only; no production code. Implement `A3-spec.md` acceptance tests.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A3-spec.md`, this prompt.
3. Set `A3-test` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A3-test`).
5. Create branch `buca-a3-run-events-test` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a3-run-events-test buca-a3-run-events-test`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Add deterministic tests that assert schema/provider failures emit `has_error=true` agent events.
- Required commands:
  - `uv run ruff format --check`
  - `uv run pytest gsd-browser/tests -k "run_event"`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a3-run-events-test`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A3-test`).
4. Remove worktree `wt/buca-a3-run-events-test`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A3-integ.md
# Kickoff Prompt – A3-integ (Persist agent/provider failures as run events)

## Scope
- Integration only: merge A3 code+tests, reconcile to `A3-spec.md`, and ensure green checks.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A3-spec.md`, this prompt.
3. Set `A3-integ` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A3-integ`).
5. Create branch `buca-a3-run-events-integ` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a3-run-events-integ buca-a3-run-events-integ`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Merge `buca-a3-run-events-code` + `buca-a3-run-events-test` and reconcile to spec.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`
  - `uv run pytest`
  - `make smoke`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a3-run-events-integ`, commit integration changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A3-integ`).
4. Remove worktree `wt/buca-a3-run-events-integ`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A4-code.md
# Kickoff Prompt – A4-code (Harness actionable classification)

## Scope
- Production code only; no tests. Implement `A4-spec.md`.
- Update harness actionable predicate so agent/provider/schema failures count as actionable when artifacts exist.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A4-spec.md`, this prompt.
3. Set `A4-code` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A4-code`).
5. Create branch `buca-a4-harness-classify-code` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a4-harness-classify-code buca-a4-harness-classify-code`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Treat common agent/provider/schema failures as actionable (without weakening `pass` semantics).
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a4-harness-classify-code`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A4-code`).
4. Remove worktree `wt/buca-a4-harness-classify-code`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A4-test.md
# Kickoff Prompt – A4-test (Harness actionable classification)

## Scope
- Tests/fixtures only; no production code. Implement `A4-spec.md` acceptance tests.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A4-spec.md`, this prompt.
3. Set `A4-test` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A4-test`).
5. Create branch `buca-a4-harness-classify-test` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a4-harness-classify-test buca-a4-harness-classify-test`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Add fixture-based tests covering classification outcomes for agent/provider/schema failures.
- Required commands:
  - `uv run ruff format --check`
  - `uv run pytest gsd-browser/tests -k "real_world_sanity"`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a4-harness-classify-test`, commit changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A4-test`).
4. Remove worktree `wt/buca-a4-harness-classify-test`.

*** Add File: docs/project_management/next/browser-use-contract-alignment/kickoff_prompts/A4-integ.md
# Kickoff Prompt – A4-integ (Harness actionable classification)

## Scope
- Integration only: merge A4 code+tests, reconcile to `A4-spec.md`, and ensure green checks.

## Start Checklist
1. `git checkout feat/browser-use-contract-alignment && git pull --ff-only`
2. Read: `plan.md`, `tasks.json`, `session_log.md`, `A4-spec.md`, this prompt.
3. Set `A4-integ` status to `in_progress` in `tasks.json` (orchestration branch only).
4. Add START entry to `session_log.md`; commit docs (`docs: start A4-integ`).
5. Create branch `buca-a4-harness-classify-integ` from `feat/browser-use-contract-alignment`; run `git worktree add wt/buca-a4-harness-classify-integ buca-a4-harness-classify-integ`.
6. Do **not** edit docs/tasks/session_log from the worktree.

## Requirements
- Merge `buca-a4-harness-classify-code` + `buca-a4-harness-classify-test` and reconcile to spec.
- Required commands:
  - `uv run ruff format --check`
  - `uv run ruff check`
  - `uv run pytest`
  - `make smoke`

## End Checklist
1. Run required commands and capture outputs.
2. Inside `wt/buca-a4-harness-classify-integ`, commit integration changes (no docs/tasks/session_log edits).
3. Checkout `feat/browser-use-contract-alignment`; update `tasks.json` + add END entry to `session_log.md`; commit docs (`docs: finish A4-integ`).
4. Remove worktree `wt/buca-a4-harness-classify-integ`.
