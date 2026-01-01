#!/usr/bin/env bash
set -euo pipefail

TARGET="mcp-template-ts"

show_config() {
  local file=$1
  local label=$2
  if [ ! -f "$file" ]; then
    echo "$label not found ($file)"
    echo
    return
  fi

  echo "Checking $label ($file)"
  if grep -q "$TARGET" "$file"; then
    python3 - <<PY
import json, pathlib
path = pathlib.Path('$file')
try:
    data = json.loads(path.read_text())
except Exception as exc:
    print(f"  Failed to parse JSON: {exc}")
else:
    entry = data.get('mcpServers', {}).get('$TARGET')
    if entry:
        import json as _json
        print(_json.dumps(entry, indent=2))
    else:
        print('  No entry for $TARGET')
PY
  else
    echo "  No occurrences of $TARGET"
  fi
  echo
}

show_config "$HOME/.claude.json" "Global config"
show_config "$PWD/.claude.json" "Project config"
