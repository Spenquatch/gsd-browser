# Execution Session Logs (per-task; required)

This directory contains deterministic, per-task execution logs for the Option B migration.

Why:
- Preserves context across sessions/agents.
- Makes it obvious what was changed, which commands were run, and how acceptance criteria were met.
- Prevents “tribal knowledge” drift when work spans multiple PRs.

## Rules (enforced by `FAST_MCP_V2_EXECUTION_TASKS.json`)
- For every task `T`, create a log file at:
  - `docs/planning/execution_logs/{task_id}.md`
- Write a **start-of-task** entry before making changes.
- Write an **end-of-task** entry after acceptance criteria are met.
- After writing the end-of-task entry, commit all changes related to the task (including the log).

## Template (copy/paste)

```md
# Task {task_id}: {task_title}

## Start
- started_at_utc:
- branch:
- executor:
- task_file: docs/planning/FAST_MCP_V2_EXECUTION_TASKS.json
- prerequisites_checked:
  - make -C gsd-browser bootstrap:
  - make -C gsd-browser check:
- notes:

## End
- finished_at_utc:
- commits:
  - <hash> (summary)
- commands_run:
  - make -C gsd-browser check
  - make -C gsd-browser test
- acceptance_criteria:
  - [ ] <id>: <statement>
  - [ ] <id>: <statement>
- files_changed:
  - <path>
  - <path>
- deepwiki_queries:
  - (optional) repo: jlowin/fastmcp, question: "...", outcome: "..."
- followups:
  - (optional) <notes>
```

