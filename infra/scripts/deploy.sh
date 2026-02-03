#!/usr/bin/env bash
# deploy.sh — One-shot deployment of GSD infrastructure to Azure
#
# Prerequisites:
#   - az CLI logged in (`az login`)
#   - Subscription set (`az account set -s "Microsoft Azure Sponsorship"`)
#   - ANTHROPIC_API_KEY environment variable set
#
# Usage:
#   ./infra/scripts/deploy.sh                    # Deploy (or update)
#   ./infra/scripts/deploy.sh --what-if          # Dry-run / preview
#   IMAGE_TAG=v1.2.3 ./infra/scripts/deploy.sh   # Deploy specific tag

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$INFRA_DIR")"

LOCATION="${LOCATION:-eastus}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DEPLOYMENT_NAME="gsd-deploy-$(date +%Y%m%d-%H%M%S)"

# ── Preflight checks ────────────────────────────────────────────────────

if ! command -v az &>/dev/null; then
  echo "ERROR: az CLI not found. Install: https://aka.ms/install-azure-cli" >&2
  exit 1
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ERROR: ANTHROPIC_API_KEY environment variable is required" >&2
  exit 1
fi

# Verify subscription
CURRENT_SUB=$(az account show --query name -o tsv 2>/dev/null || echo "")
echo "Active subscription: ${CURRENT_SUB}"
echo "Deployment: ${DEPLOYMENT_NAME}"
echo "Location: ${LOCATION}"
echo "Image tag: ${IMAGE_TAG}"
echo ""

# ── What-if or deploy ────────────────────────────────────────────────────

EXTRA_ARGS=()
if [[ "${1:-}" == "--what-if" ]]; then
  echo "=== WHAT-IF MODE (no changes will be made) ==="
  EXTRA_ARGS+=("--what-if")
fi

echo "Deploying infrastructure..."
az deployment sub create \
  --name "$DEPLOYMENT_NAME" \
  --location "$LOCATION" \
  --template-file "$INFRA_DIR/main.bicep" \
  --parameters "$INFRA_DIR/parameters/prod.bicepparam" \
  --parameters imageTag="$IMAGE_TAG" \
  "${EXTRA_ARGS[@]}"

if [[ "${1:-}" == "--what-if" ]]; then
  echo ""
  echo "What-if complete. Run without --what-if to deploy."
  exit 0
fi

# ── Print outputs ────────────────────────────────────────────────────────

echo ""
echo "=== Deployment Outputs ==="
az deployment sub show \
  --name "$DEPLOYMENT_NAME" \
  --query properties.outputs \
  -o table 2>/dev/null || \
az deployment sub show \
  --name "$DEPLOYMENT_NAME" \
  --query properties.outputs \
  -o json

echo ""
echo "=== Quick Verification ==="
API_FQDN=$(az deployment sub show --name "$DEPLOYMENT_NAME" --query "properties.outputs.apiFqdn.value" -o tsv 2>/dev/null || echo "")
WORKER_FQDN=$(az deployment sub show --name "$DEPLOYMENT_NAME" --query "properties.outputs.workerFqdn.value" -o tsv 2>/dev/null || echo "")

if [ -n "$API_FQDN" ]; then
  echo "API health:    curl https://${API_FQDN}/.well-known/oauth-protected-resource"
fi
if [ -n "$WORKER_FQDN" ]; then
  echo "Worker health: curl https://${WORKER_FQDN}/healthz"
fi

echo ""
echo "Deployment complete."
