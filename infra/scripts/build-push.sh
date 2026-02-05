#!/usr/bin/env bash
# build-push.sh — Build Docker image and push to Azure Container Registry
#
# Usage:
#   ./infra/scripts/build-push.sh                     # Build + push :latest
#   IMAGE_TAG=v1.2.3 ./infra/scripts/build-push.sh    # Build + push specific tag
#   ACR_NAME=myacr ./infra/scripts/build-push.sh      # Override ACR name

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

IMAGE_TAG="${IMAGE_TAG:-latest}"
RESOURCE_GROUP="${RESOURCE_GROUP:-gsd-prod-rg}"

# ── Resolve ACR name ─────────────────────────────────────────────────────

if [ -z "${ACR_NAME:-}" ]; then
  ACR_NAME=$(az acr list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")
  if [ -z "$ACR_NAME" ]; then
    echo "ERROR: Could not find ACR in resource group $RESOURCE_GROUP" >&2
    echo "Set ACR_NAME explicitly or deploy infrastructure first." >&2
    exit 1
  fi
fi

ACR_LOGIN_SERVER=$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)
IMAGE="${ACR_LOGIN_SERVER}/gsd-browser:${IMAGE_TAG}"

echo "ACR:       ${ACR_NAME} (${ACR_LOGIN_SERVER})"
echo "Image:     ${IMAGE}"
echo "Context:   ${REPO_ROOT}/gsd-browser"
echo ""

# ── Login to ACR ─────────────────────────────────────────────────────────

echo "Logging in to ACR..."
az acr login -n "$ACR_NAME"

# ── Build ────────────────────────────────────────────────────────────────

echo "Building Docker image..."
docker build \
  -t "$IMAGE" \
  -t "${ACR_LOGIN_SERVER}/gsd-browser:latest" \
  -f "${REPO_ROOT}/gsd-browser/docker/Dockerfile" \
  "${REPO_ROOT}/gsd-browser"

# ── Push ─────────────────────────────────────────────────────────────────

echo "Pushing to ACR..."
docker push "$IMAGE"

if [ "$IMAGE_TAG" != "latest" ]; then
  docker push "${ACR_LOGIN_SERVER}/gsd-browser:latest"
fi

echo ""
echo "Done. Image pushed: ${IMAGE}"
