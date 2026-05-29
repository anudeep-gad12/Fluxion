#!/usr/bin/env bash
# Run before `cargo tauri dev` — rebuild ui/dist only when sources changed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UI_DIR="$ROOT/ui"
DIST_INDEX="$UI_DIR/dist/index.html"

needs_build=0
if [ "${FORCE_UI_BUILD:-}" = "1" ]; then
  needs_build=1
elif [ ! -f "$DIST_INDEX" ]; then
  needs_build=1
elif find "$UI_DIR/src" -type f -newer "$DIST_INDEX" -print -quit 2>/dev/null | grep -q .; then
  needs_build=1
elif find "$UI_DIR/index.html" -newer "$DIST_INDEX" -print -quit 2>/dev/null | grep -q .; then
  needs_build=1
fi

if [ "$needs_build" -eq 0 ]; then
  echo "[tauri] ui/dist is up to date — skipping build (set FORCE_UI_BUILD=1 to rebuild)"
  exit 0
fi

echo "[tauri] Building UI into ui/dist..."
(cd "$UI_DIR" && pnpm build)
