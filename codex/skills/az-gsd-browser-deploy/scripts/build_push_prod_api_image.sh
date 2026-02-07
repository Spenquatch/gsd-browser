#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$DIR/_lib.sh"

require_cmd az
require_cmd docker

RG="$(default_rg)"
APP="$(default_app)"
ACR="$(default_acr)"
REPO="$(default_repo)"

ROOT="$(repo_root)"
DOCKERFILE="${GSD_DOCKERFILE:-$ROOT/gsd-browser/docker/Dockerfile}"
CONTEXT_DIR="${GSD_DOCKER_CONTEXT:-$ROOT/gsd-browser}"

[ -f "$DOCKERFILE" ] || die "dockerfile not found: $DOCKERFILE"
[ -d "$CONTEXT_DIR" ] || die "docker context dir not found: $CONTEXT_DIR"

LOGIN_SERVER="$(acr_login_server)"
SHA="$(git_short_sha)"
TAG="${GSD_IMAGE_TAG:-fix-${SHA}-$(utc_tag_suffix)}"
IMAGE="${LOGIN_SERVER}/${REPO}:${TAG}"

echo "== azure context =="
az account show --query "{subscription:id,name:name,user:user.name}" -o jsonc >/dev/null || die "not logged into az"
echo "resource_group=$RG app=$APP acr=$ACR image=$IMAGE"
echo

echo "== acr login =="
az acr login -n "$ACR"
echo

echo "== docker build =="
docker build --platform linux/amd64 -f "$DOCKERFILE" -t "$IMAGE" "$CONTEXT_DIR"
echo

echo "== docker push =="
docker push "$IMAGE"
echo

OUT_FILE="${GSD_IMAGE_OUT_FILE:-/tmp/gsd_prod_api_image.txt}"
printf "%s" "$IMAGE" > "$OUT_FILE"

echo "wrote_image_ref=$OUT_FILE"
echo "$IMAGE"

