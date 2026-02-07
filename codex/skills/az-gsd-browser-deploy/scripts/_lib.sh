#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

repo_root() {
  if [ -n "${GSD_REPO_ROOT:-}" ]; then
    echo "$GSD_REPO_ROOT"
    return 0
  fi

  if command -v git >/dev/null 2>&1; then
    local root
    root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
    if [ -n "$root" ]; then
      echo "$root"
      return 0
    fi
  fi

  pwd
}

default_rg() { echo "${GSD_ACA_RG:-gsd-prod-rg}"; }
default_app() { echo "${GSD_ACA_APP:-gsd-prod-api}"; }
default_acr() { echo "${GSD_ACR_NAME:-gsdprodacr}"; }
default_repo() { echo "${GSD_IMAGE_REPO:-gsd-browser}"; }

acr_login_server() {
  az acr show -n "$(default_acr)" --query loginServer -o tsv
}

containerapp_fqdn() {
  az containerapp show -n "$(default_app)" -g "$(default_rg)" \
    --query "properties.configuration.ingress.fqdn" -o tsv
}

git_short_sha() {
  local root sha
  root="$(repo_root)"
  sha="nosha"
  if command -v git >/dev/null 2>&1; then
    sha="$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo nosha)"
  fi
  echo "$sha"
}

utc_tag_suffix() {
  date -u +%Y%m%d%H%M%S
}

