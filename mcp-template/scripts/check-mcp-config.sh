#!/usr/bin/env bash
# Inspect Claude MCP configuration files for mcp-template entries.
set -euo pipefail

TARGET_NAME="mcp-template"

show_section() {
  local file=$1
  local label=$2
  if [ -f "$file" ]; then
    echo "Checking $label ($file)"
    if grep -q "$TARGET_NAME" "$file"; then
      python3 - <<PY
import json
from pathlib import Path

path = Path("$file")
try:
    data = json.loads(path.read_text())
except Exception as exc:  # noqa: BLE001
    print(f"  Failed to parse JSON: {exc}")
else:
    found = data.get("mcpServers", {}).get("$TARGET_NAME")
    if found:
        import json as _json
        print("  Found entry:")
        print(_json.dumps(found, indent=2))
    else:
        print("  No entry for $TARGET_NAME")
PY
    else
      echo "  No occurrences of $TARGET_NAME"
    fi
  else
    echo "$label not found ($file)"
  fi
  echo
}

show_section "$HOME/.claude.json" "Global config"
show_section "$PWD/.claude.json" "Project config"
