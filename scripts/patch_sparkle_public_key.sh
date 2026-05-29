#!/usr/bin/env bash
# Patch SUPublicEDKey in src-tauri/tauri.conf.json (used in release CI).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_KEY="${1:-${FLUXION_SPARKLE_PUBLIC_ED_KEY:-}}"

if [[ -z "$PUBLIC_KEY" ]]; then
  echo "Usage: $0 <sparkle-ed-public-key>" >&2
  exit 1
fi

python3 - <<'PY' "$ROOT_DIR/src-tauri/Info.extend.plist" "$PUBLIC_KEY"
import plistlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
public_key = sys.argv[2]
with path.open("rb") as handle:
    plist = plistlib.load(handle)
plist["SUPublicEDKey"] = public_key
with path.open("wb") as handle:
    plistlib.dump(plist, handle)
print(f"Patched SUPublicEDKey in {path}")
PY
