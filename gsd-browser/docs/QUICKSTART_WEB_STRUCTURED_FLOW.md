# Quickstart: `web_structured_flow` (record once → replay many)

`web_structured_flow` is a two-phase workflow:

1) **Record** (uses an LLM-driven `browser-use` `Agent` once) to capture the sequence of actions.
2) **Replay** (runs an exported Actor-API Python script) with **no LLM required**.

Templates are stored under `~/.gsd/structured_flows/<template_id>/` (manifest + `replay.py` + optional DSL fallback).

## Prereqs

- A working browser-use OSS model behind an OpenAI-compatible endpoint (for **record**).
- `OPENAI_API_KEY` and `OPENAI_BASE_URL` available to the gsd process/container.
- Docker (recommended for repeatable runs).

## Recommended env vars (record phase)

These must be available to the process doing the record:

```bash
GSD_LLM_PROVIDER=openai
GSD_MODEL=browser-use/bu-30b-a3b-preview   # or your installed browser-use OSS model
OPENAI_API_KEY=...                         # local key/dummy string
OPENAI_BASE_URL=http://<host>:8000/v1      # your OpenAI-compatible endpoint
GSD_OPENAI_DONT_FORCE_STRUCTURED_OUTPUT=true
```

Optional but useful:

```bash
GSD_STRUCTURED_FLOW_CDP_WAIT_TIMEOUT_S=180
TIMEOUT_BrowserStartEvent=180
TIMEOUT_BrowserLaunchEvent=180
```

## Docker: build + start (Option B minimal stack)

From repo root:

```bash
docker compose --env-file "$HOME/.gsd/.env" -f gsd-browser/docker/compose.minimal.yml up -d --build
```

PowerShell equivalent:

```powershell
docker compose --env-file "$HOME\\.gsd\\.env" -f gsd-browser/docker/compose.minimal.yml up -d --build
```

Or, if you prefer separate build + up:

```bash
docker compose -f gsd-browser/docker/compose.minimal.yml build gsd
docker compose -f gsd-browser/docker/compose.minimal.yml up -d
```

If you already have something bound to `127.0.0.1:6379` or `0.0.0.0:8080`, bring up only the worker + mgmt services:

```bash
docker compose -f gsd-browser/docker/compose.minimal.yml up -d --no-deps gsd-worker gsd-mgmt
```

Health check:

```bash
curl -fsS http://localhost:8081/healthz
```

## Call the tool via MCP-over-HTTP (JSON-RPC 2.0)

If you’re running the **HTTP transport** (for example via `compose.minimal.yml`), you can call
`web_structured_flow` directly over HTTP using JSON-RPC 2.0.

Notes:
- The MCP endpoint path is `POST /mcp`.
- `compose.minimal.yml` maps container `8080` → host `8090`, so your local MCP URL is typically:
  - `http://localhost:8090/mcp`
- HTTP mode requires `Authorization: Bearer <token>` (see ADR-0019 for how tokens are obtained).
- Responses may be returned as **SSE** (`text/event-stream`). In that case, the final JSON-RPC message
  is the last `data: ...` line.

Set these once:

```bash
export GSD_BASE_URL="http://localhost:8090"
export GSD_MCP_URL="http://localhost:8090/mcp"
export GSD_TOKEN="..."        # Bearer JWT / developer token
export GSD_ORIGIN="http://localhost"
```

PowerShell equivalent (uses env vars for the current shell session):

```powershell
$env:GSD_BASE_URL = "http://localhost:8090"
$env:GSD_MCP_URL = "$env:GSD_BASE_URL/mcp"
$env:GSD_TOKEN = "..."     # Bearer JWT / developer token
$env:GSD_ORIGIN = "http://localhost"
```

Optional sanity check (OAuth protected resource metadata):

```bash
curl -fsS -H "Origin: $GSD_ORIGIN" "$GSD_BASE_URL/.well-known/oauth-protected-resource"
```

PowerShell equivalent (use `curl.exe` to avoid the `curl` alias in Windows PowerShell):

```powershell
curl.exe -fsS -H "Origin: $env:GSD_ORIGIN" "$env:GSD_BASE_URL/.well-known/oauth-protected-resource"
```

### JSON-RPC: record

```bash
curl -sN --max-time 600 -X POST "$GSD_MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $GSD_TOKEN" \
  -H "Origin: $GSD_ORIGIN" \
  -d @- <<'JSON'
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "web_structured_flow",
    "arguments": {
      "record": {
        "template_id": "example_flow",
        "url": "https://example.com/start",
        "task": "Click the JavaScript tab, extract fields, click final button and return the final URL",
        "strategy": "agent",
        "min_actions": 3,
        "require_llm_free_replay": true,
        "headless_browser": false
      }
    }
  }
}
JSON
```

PowerShell equivalent:

```powershell
@'
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "web_structured_flow",
    "arguments": {
      "record": {
        "template_id": "example_flow",
        "url": "https://example.com/start",
        "task": "Extract full job description, including all metadata fields from the \"Job Info\" section at the start of the page content. Then click the \"Apply now\" button let the new page open and record the URL from the page launched from the \"Apply now\" button. Then return with all of the job posting details",
        "strategy": "agent",
        "min_actions": 3,
        "require_llm_free_replay": true,
        "headless_browser": false
      }
    }
  }
}
'@ | curl.exe -sN -m 600 -X POST "$env:GSD_MCP_URL" `
  -H "Content-Type: application/json" `
  -H "Accept: application/json, text/event-stream" `
  -H "Authorization: Bearer $env:GSD_TOKEN" `
  -H "Origin: $env:GSD_ORIGIN" `
  --data-binary "@-"
```

### JSON-RPC: replay

```bash
curl -sN --max-time 600 -X POST "$GSD_MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $GSD_TOKEN" \
  -H "Origin: $GSD_ORIGIN" \
  -d @- <<'JSON'
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "web_structured_flow",
    "arguments": {
      "replay": {
        "template_id": "example_flow",
        "url": "https://example.com/items/123",
        "runner": "script_then_dsl",
        "headless_browser": true
      }
    }
  }
}
JSON
```

PowerShell equivalent:

```powershell
@'
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "web_structured_flow",
    "arguments": {
      "replay": {
        "template_id": "example_flow",
        "url": "https://example.com/items/123",
        "runner": "script_then_dsl",
        "headless_browser": true
      }
    }
  }
}
'@ | curl.exe -sN -m 600 -X POST "$env:GSD_MCP_URL" `
  -H "Content-Type: application/json" `
  -H "Accept: application/json, text/event-stream" `
  -H "Authorization: Bearer $env:GSD_TOKEN" `
  -H "Origin: $env:GSD_ORIGIN" `
  --data-binary "@-"
```

Result shape reminder:
- The JSON-RPC envelope contains `result.content[]`.
- The tool’s actual payload is a JSON string in `result.content[0].text` (schema:
  `gsd.web_structured_flow.v1`).

If you want to extract the tool payload JSON from an SSE response in PowerShell:

```powershell
$raw = @'
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": { "name": "web_structured_flow", "arguments": { "replay": { "template_id": "example_flow", "url": "https://example.com/items/123" } } }
}
'@ | curl.exe -sN -m 600 -X POST "$env:GSD_MCP_URL" `
  -H "Content-Type: application/json" `
  -H "Accept: application/json, text/event-stream" `
  -H "Authorization: Bearer $env:GSD_TOKEN" `
  -H "Origin: $env:GSD_ORIGIN" `
  --data-binary "@-"

$dataLines = $raw -split "`n" | Where-Object { $_ -like "data: *" } | ForEach-Object { $_.Substring(6) }
$msg = $dataLines[-1] | ConvertFrom-Json
$text = ($msg.result.content | Where-Object { $_.type -eq "text" } | Select-Object -First 1).text
$payload = $text | ConvertFrom-Json
$payload | ConvertTo-Json -Depth 50
```

## Record a template

Use the helper CLI (runs the tool directly, prints the JSON payload):

```bash
docker run --rm --shm-size=1g \
  -e GSD_LLM_PROVIDER -e GSD_MODEL -e OPENAI_API_KEY -e OPENAI_BASE_URL \
  -e GSD_OPENAI_DONT_FORCE_STRUCTURED_OUTPUT \
  -e GSD_STRUCTURED_FLOW_CDP_WAIT_TIMEOUT_S=180 \
  gsd-browser:local \
  python /app/scripts/web_structured_flow_cli.py record \
    --template-id example_flow \
    --url "https://example.com/start" \
    --task "Click the JavaScript tab, extract fields, click final button and return the final URL" \
    --min-actions 3 \
    --strategy agent \
    --no-headless
```

Notes:
- `--template-id` becomes the folder name under `~/.gsd/structured_flows/`.
- `record.url` and subsequent `replay.url` must be on the **same origin** (scheme + host + port), enforced at replay time.

### Optional extraction during replay

Create a JSON file (example: `extract.json`):

```json
{
  "timing": "before_last_click",
  "fields": [
    { "name": "title", "selector": "h1", "kind": "text_content" }
  ]
}
```

Then pass it during record (it gets embedded into the exported replay script):

```bash
python /app/scripts/web_structured_flow_cli.py record \
  --template-id example_flow \
  --url "https://example.com/start" \
  --task "..." \
  --extract-json /path/to/extract.json
```

## Replay a template (no LLM)

```bash
docker run --rm --shm-size=1g \
  -e GSD_STRUCTURED_FLOW_CDP_WAIT_TIMEOUT_S=180 \
  gsd-browser:local \
  python /app/scripts/web_structured_flow_cli.py replay \
    --template-id example_flow \
    --url "https://example.com/items/123" \
    --runner script_then_dsl \
    --headless
```

Replay reads the stored `replay.py` from `~/.gsd/structured_flows/<template_id>/replay.py`.

## Where templates live (Docker)

By default, templates created inside a container live in the container filesystem (`/root/.gsd/...`) and are lost when the container is removed.

To persist templates across runs, mount a volume:

```bash
docker volume create gsd-data

docker run --rm --shm-size=1g \
  -v gsd-data:/root/.gsd \
  ... \
  gsd-browser:local python /app/scripts/web_structured_flow_cli.py record ...
```
