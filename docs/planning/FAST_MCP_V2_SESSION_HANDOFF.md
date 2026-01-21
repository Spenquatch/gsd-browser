# FastMCP v2 “Option B” — Session Handoff

Use this file to resume work in a new session without losing context.

## Branch
- Option B core has landed; follow-on work is tracked in `docs/planning/BACKLOG.md` and ADRs
  (`docs/adr/ADR-0010-*.md` onward).

## Local Redis/Valkey harness (do this)
Some integration tests are skipped unless Redis is running at `redis://localhost:6379/0`.

- Start: `cd gsd-browser && make redistest-up`
- Stop: `cd gsd-browser && make redistest-down`
- Logs: `cd gsd-browser && make redistest-logs`

## High-level goal
Migrate `gsd` MCP server to:
- FastMCP v2 (jlowin/fastmcp)
- SEP-1686 long-running tasks for long browser tools
- Redis/Valkey-backed task queue (Docket)
- Distributed artifact storage (S3-compatible + Redis index)
- Tenant-scoped authorization boundaries

## Where the “truth” lives
- ADRs: `docs/adr/ADR-0008-*.md`, `docs/adr/ADR-0009-*.md`
- API docs: `gsd-browser/docs/api/MCP_TOOLS.md`, `gsd-browser/docs/api/MCP_TASKS.md`
- Machine contracts:
  - Pydantic: `gsd-browser/src/gsd_browser/contracts/v1.py`
  - Exported JSON Schema: `gsd-browser/docs/api/jsonschema/`
  - Enforcement test: `gsd-browser/tests/test_exported_jsonschema_in_sync.py`

## Key decisions already made
- Long tools are task-required: `web_eval_agent`, `web_task_agent`, `web_task_agent_github`.
- Task TTL defaults are server-defined; client TTL override allowed only behind env toggle + bounded.
- Task authZ is identity/tenant-scoped (not session-only).
- Artifacts are stored in S3 from day 1; delivery is phased (inline now, presigned later).
- Retention defaults: dev ~24h, prod ~7d.
- Tenant-prefixed keys + TLS + SSE at-rest requirement.
- SeaweedFS is self-hosted S3 reference deployment.

## Reviewer feedback to address (most important)
1) Explicitly state migration boundary (docs/contract vs current code reality).
2) Resolve schema evolution policy (strict v1 vs extensible v1).
3) Expand diagnostic taxonomy (`errors_top`) to include agent/provider/cancel/timeout as needed.
4) Specify identity binding + presigned URL constraints in concrete invariants.
5) Expand artifact metadata to make Phase 2 safe without breaking clients.

Tracked resolutions (Option B checklist):
- S0 (boundary): `gsd-browser/docs/api/STATUS.md`
- S1 (schema evolution): `gsd-browser/docs/api/MCP_TOOLS.md` (Versioning policy)
- S2 (diagnostics taxonomy): `gsd-browser/docs/api/MCP_TOOLS.md` + contract schemas
- S3 (identity/tenant invariants): ADR-0008/ADR-0009 invariants sections
- S4 (artifact metadata): `gsd-browser/docs/api/MCP_TOOLS.md` + contract schemas
- S5 (task semantics): `gsd-browser/docs/api/MCP_TASKS.md`


## Next document to follow
- `docs/planning/FAST_MCP_V2_OPTION_B_PLAN.md`

## Recent commits (branch-only summary)
If working on a follow-on branch, use: `git log --oneline main..HEAD`
