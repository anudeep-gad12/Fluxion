#!/usr/bin/env bash
# Run before `cargo tauri build` — Sparkle framework + fresh production UI bundle.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$ROOT/scripts/ensure_sparkle_framework.sh"
export SPARKLE_FRAMEWORK_PATH="$ROOT/src-tauri/Frameworks"

echo "[tauri] Building UI into ui/dist..."
(cd "$ROOT/ui" && pnpm build)
