#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "== inspect =="
"$DIR/inspect_prod_api.sh"
echo

echo "== build + push =="
image_ref="$("$DIR/build_push_prod_api_image.sh" | tail -n 1)"
echo

echo "== update =="
"$DIR/update_prod_api_image.sh" "$image_ref"
echo

echo "== verify =="
"$DIR/verify_prod_api.sh"

