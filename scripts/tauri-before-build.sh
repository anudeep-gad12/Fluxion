#!/usr/bin/env bash
# Run before `cargo tauri build` — always produce a fresh production UI bundle.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "[tauri] Building UI into ui/dist..."
(cd "$ROOT/ui" && pnpm build)
