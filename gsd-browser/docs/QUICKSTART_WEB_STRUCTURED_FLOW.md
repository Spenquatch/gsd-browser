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
