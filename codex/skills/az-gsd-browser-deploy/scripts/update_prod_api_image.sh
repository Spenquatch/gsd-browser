#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$DIR/_lib.sh"

require_cmd az

RG="$(default_rg)"
APP="$(default_app)"

IMAGE="${1:-}"
if [ -z "$IMAGE" ]; then
  IN_FILE="${GSD_IMAGE_OUT_FILE:-/tmp/gsd_prod_api_image.txt}"
  [ -f "$IN_FILE" ] || die "missing image arg and no image file found at: $IN_FILE"
  IMAGE="$(cat "$IN_FILE")"
fi

echo "== update containerapp image =="
echo "app=$APP rg=$RG image=$IMAGE"
az containerapp update -n "$APP" -g "$RG" --image "$IMAGE" \
  --query "{provisioningState:properties.provisioningState,latestRevisionName:properties.latestRevisionName,latestRevisionFqdn:properties.latestRevisionFqdn}" \
  -o jsonc

