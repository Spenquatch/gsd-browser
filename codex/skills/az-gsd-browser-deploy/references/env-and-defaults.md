# Env vars and defaults

These scripts default to the production GSD resources, but can be overridden with env vars.

## Azure resource defaults

- `GSD_ACA_RG` (default: `gsd-prod-rg`)
- `GSD_ACA_APP` (default: `gsd-prod-api`)
- `GSD_ACR_NAME` (default: `gsdprodacr`)
- `GSD_IMAGE_REPO` (default: `gsd-browser`)

## Build inputs

- `GSD_REPO_ROOT` (default: auto-detect via `git rev-parse --show-toplevel`)
- `GSD_DOCKERFILE` (default: `$GSD_REPO_ROOT/gsd-browser/docker/Dockerfile`)
- `GSD_DOCKER_CONTEXT` (default: `$GSD_REPO_ROOT/gsd-browser`)
- `GSD_IMAGE_TAG` (default: `fix-<gitsha>-<utc_timestamp>`)
- `GSD_IMAGE_OUT_FILE` (default: `/tmp/gsd_prod_api_image.txt`)

## Verification inputs

- `GSD_TOKEN` (optional): if set, `verify_prod_api.sh` and `smoke_mcp.sh` will run MCP calls:
  - `POST /mcp` `initialize`
  - `POST /mcp` `tools/list`

