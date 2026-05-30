#!/usr/bin/env bash
# Sync macOS app icon SVG + raster exports to ui/ and site/ brand paths.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_SVG="$ROOT/assets/macos/Fluxion.svg"
TAURI_ICONS="$ROOT/src-tauri/icons"

if [[ ! -f "$SOURCE_SVG" ]]; then
  echo "Missing source icon: $SOURCE_SVG" >&2
  exit 1
fi

log() { echo "[sync-brand] $*"; }

log "Copying favicon SVG"
cp "$SOURCE_SVG" "$ROOT/ui/public/favicon.svg"
cp "$SOURCE_SVG" "$ROOT/ui/src/assets/favicon.svg"
cp "$SOURCE_SVG" "$ROOT/site/public/favicon.svg"
cp "$SOURCE_SVG" "$ROOT/site/public/logo.svg"

if [[ -d "$TAURI_ICONS" ]]; then
  log "Copying raster logo sizes from src-tauri/icons"
  cp "$TAURI_ICONS/32x32.png" "$ROOT/site/public/logo-32.png"
  cp "$TAURI_ICONS/128x128.png" "$ROOT/site/public/logo-128.png"
  cp "$TAURI_ICONS/128x128@2x.png" "$ROOT/site/public/logo-256.png"
  cp "$TAURI_ICONS/128x128@2x.png" "$ROOT/site/public/apple-touch-icon.png"
  cp "$TAURI_ICONS/128x128.png" "$ROOT/assets/brand/logo-128.png"
  cp "$TAURI_ICONS/128x128@2x.png" "$ROOT/ui/public/apple-touch-icon.png"
  cp "$TAURI_ICONS/128x128@2x.png" "$ROOT/ui/src/assets/app-icon.png"
else
  log "Warning: $TAURI_ICONS missing — run: cd src-tauri && cargo tauri icon ../assets/macos/Fluxion.svg"
fi

log "Done"
