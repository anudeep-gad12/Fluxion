#!/usr/bin/env bash
# Download Sparkle.framework for tauri-plugin-sparkle-updater and Tauri bundle.
# The plugin build.rs joins search_path/Sparkle.framework — set SPARKLE_FRAMEWORK_PATH
# to src-tauri/Frameworks (see tauri-before-build.sh / build_macos_tauri.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAURI_DIR="$ROOT/src-tauri"
FRAMEWORKS_DIR="$TAURI_DIR/Frameworks"
SPARKLE_FRAMEWORK="$FRAMEWORKS_DIR/Sparkle.framework"
SPARKLE_VERSION="${SPARKLE_VERSION:-2.9.2}"

log() { echo "[ensure-sparkle] $*"; }

if [[ ! -e "$SPARKLE_FRAMEWORK/Sparkle" ]]; then
  log "Downloading Sparkle $SPARKLE_VERSION"
  CACHE="$ROOT/build/macos/sparkle"
  mkdir -p "$CACHE/extract" "$FRAMEWORKS_DIR"
  curl -fsSL \
    "https://github.com/sparkle-project/Sparkle/releases/download/${SPARKLE_VERSION}/Sparkle-${SPARKLE_VERSION}.tar.xz" \
    -o "$CACHE/sparkle.tar.xz"
  rm -rf "$CACHE/extract"/*
  tar -xJf "$CACHE/sparkle.tar.xz" -C "$CACHE/extract"
  rm -rf "$SPARKLE_FRAMEWORK"
  cp -R "$CACHE/extract/Sparkle.framework" "$SPARKLE_FRAMEWORK"
  log "Installed $SPARKLE_FRAMEWORK"
else
  log "Using existing $SPARKLE_FRAMEWORK"
fi

LINK_PATH="$TAURI_DIR/Sparkle.framework"
if [[ ! -e "$LINK_PATH" ]]; then
  ln -sf "Frameworks/Sparkle.framework" "$LINK_PATH"
  log "Linked $LINK_PATH -> Frameworks/Sparkle.framework"
fi
