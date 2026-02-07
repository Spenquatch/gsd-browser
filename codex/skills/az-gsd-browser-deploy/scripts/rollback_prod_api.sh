#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$DIR/_lib.sh"

require_cmd az

RG="$(default_rg)"
APP="$(default_app)"

MODE="${1:-previous}"

if [ "$MODE" = "latest" ]; then
  ACR="$(acr_login_server)"
  IMAGE="${ACR}/$(default_repo):latest"
  echo "== rollback to :latest =="
  az containerapp update -n "$APP" -g "$RG" --image "$IMAGE" -o none
  echo "rolled_back_image=$IMAGE"
  exit 0
fi

echo "== rollback to previous revision image =="
prev_image="$(
  az containerapp revision list -n "$APP" -g "$RG" \
    --query 'reverse(sort_by([].{created:properties.createdTime,image:properties.template.containers[0].image}, &created))[1].image' \
    -o tsv
)"

[ -n "$prev_image" ] || die "could not determine previous revision image"
echo "previous_image=$prev_image"

az containerapp update -n "$APP" -g "$RG" --image "$prev_image" -o none
echo "rolled_back_image=$prev_image"
