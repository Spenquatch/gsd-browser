#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$DIR/_lib.sh"

require_cmd az

RG="$(default_rg)"
APP="$(default_app)"

echo "== containerapp =="
az containerapp show -n "$APP" -g "$RG" \
  --query "{name:name, location:location, fqdn:properties.configuration.ingress.fqdn, external:properties.configuration.ingress.external, targetPort:properties.configuration.ingress.targetPort, transport:properties.configuration.ingress.transport, activeRevisionsMode:properties.configuration.activeRevisionsMode, image:properties.template.containers[0].image, cpu:properties.template.containers[0].resources.cpu, memory:properties.template.containers[0].resources.memory}" \
  -o jsonc

echo
echo "== revisions =="
az containerapp revision list -n "$APP" -g "$RG" \
  --query "[].{name:name,active:properties.active,createdTime:properties.createdTime,runningState:properties.runningState,healthState:properties.healthState,replicas:properties.replicas,image:properties.template.containers[0].image}" \
  -o table

