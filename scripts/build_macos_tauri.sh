#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Fluxion"
TAURI_DIR="$ROOT_DIR/src-tauri"

if [[ -n "${FLUXION_APP_VERSION:-}" ]]; then
  VERSION="$FLUXION_APP_VERSION"
elif [[ -n "${GITHUB_REF_NAME:-}" && "${GITHUB_REF_NAME}" == v* ]]; then
  VERSION="${GITHUB_REF_NAME#v}"
elif TAG="$(cd "$ROOT_DIR" && git describe --tags --exact-match 2>/dev/null)" && [[ "$TAG" == v* ]]; then
  VERSION="${TAG#v}"
elif TAG="$(cd "$ROOT_DIR" && git describe --tags --match 'v*' --abbrev=0 2>/dev/null)" && [[ "$TAG" == v* ]]; then
  VERSION="${TAG#v}"
else
  VERSION="$(cd "$ROOT_DIR" && python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
fi

if [[ -n "${FLUXION_BUILD_ID:-}" ]]; then
  BUILD_ID="$FLUXION_BUILD_ID"
elif [[ -n "${GITHUB_SHA:-}" ]]; then
  BUILD_ID="${GITHUB_SHA:0:12}"
elif BUILD_ID="$(cd "$ROOT_DIR" && git rev-parse --short HEAD 2>/dev/null)"; then
  if ! (cd "$ROOT_DIR" && git diff --quiet && git diff --cached --quiet); then
    BUILD_ID="${BUILD_ID}-dirty-$(date -u +%Y%m%d%H%M%S)"
  fi
  :
else
  BUILD_ID="$(date -u +%Y%m%d%H%M%S)"
fi

if [[ -n "${FLUXION_BUILD_NUMBER:-}" ]]; then
  BUILD_NUMBER="$FLUXION_BUILD_NUMBER"
elif [[ -n "${GITHUB_RUN_NUMBER:-}" ]]; then
  BUILD_NUMBER="$GITHUB_RUN_NUMBER"
elif BUILD_NUMBER="$(cd "$ROOT_DIR" && git rev-list --count HEAD 2>/dev/null)"; then
  :
else
  BUILD_NUMBER="$(date -u +%Y%m%d%H%M%S)"
fi

ARCH="$(uname -m)"
if [[ "$ARCH" == "arm64" ]]; then
  RELEASE_ARCH="arm64"
  SIDEcar_TRIPLE="aarch64-apple-darwin"
elif [[ "$ARCH" == "x86_64" ]]; then
  RELEASE_ARCH="x64"
  SIDEcar_TRIPLE="x86_64-apple-darwin"
else
  RELEASE_ARCH="$ARCH"
  SIDEcar_TRIPLE="${ARCH}-apple-darwin"
fi

BUILD_ROOT="$ROOT_DIR/build/macos"
DIST_ROOT="$ROOT_DIR/dist/macos"
ZIP_PATH="$DIST_ROOT/${APP_NAME}-macos-${RELEASE_ARCH}.zip"
DMG_PATH="$DIST_ROOT/${APP_NAME}-macos-${RELEASE_ARCH}.dmg"
LOCAL_BUNDLE_ID="io.fluxion.local.dev"
LOCAL_BUILD=false

log() { echo "[build-macos-tauri] $*"; }

export FLUXION_APP_VERSION="$VERSION"
export FLUXION_BUILD_ID="$BUILD_ID"
export FLUXION_BUILD_NUMBER="$BUILD_NUMBER"
export CI="${CI:-true}"

TAURI_BUILD_CONFIG=()
if [[ -z "${APPLE_SIGNING_IDENTITY:-}" ]]; then
  LOCAL_BUILD=true
  LOCAL_CONFIG_PATH="$BUILD_ROOT/tauri.local.conf.json"
  mkdir -p "$BUILD_ROOT"
  cat > "$LOCAL_CONFIG_PATH" <<EOF
{
  "identifier": "$LOCAL_BUNDLE_ID"
}
EOF
  TAURI_BUILD_CONFIG=(--config "$LOCAL_CONFIG_PATH")
fi

log "Version $VERSION build $BUILD_ID bundle $BUILD_NUMBER"

if [[ -n "${FLUXION_SPARKLE_PUBLIC_ED_KEY:-}" ]]; then
  "$ROOT_DIR/scripts/patch_sparkle_public_key.sh" "$FLUXION_SPARKLE_PUBLIC_ED_KEY"
fi

log "Building frontend"
(
  cd "$ROOT_DIR/ui"
  if [[ -x node_modules/.bin/tsc && -x node_modules/.bin/vite ]]; then
    log "Using existing UI dependencies"
  else
    pnpm install --frozen-lockfile
  fi
  pnpm build
)

log "Packaging backend with PyInstaller"
rm -rf "$BUILD_ROOT/pyinstaller-dist" "$BUILD_ROOT/pyinstaller-work"
mkdir -p "$BUILD_ROOT" "$TAURI_DIR/binaries"
(
  cd "$ROOT_DIR"
  uv run --with pyinstaller pyinstaller \
    --noconfirm \
    --clean \
    --onefile \
    --name fluxion-server \
    --distpath "$BUILD_ROOT/pyinstaller-dist" \
    --workpath "$BUILD_ROOT/pyinstaller-work" \
    --specpath "$BUILD_ROOT" \
    --collect-submodules "orchestrator" \
    --add-data "$ROOT_DIR/orchestrator/chat_config.yaml:orchestrator" \
    --add-data "$ROOT_DIR/orchestrator/storage/schema.sql:orchestrator/storage" \
    orchestrator/launcher.py
)

cp "$BUILD_ROOT/pyinstaller-dist/fluxion-server" \
  "$TAURI_DIR/binaries/fluxion-server-${SIDEcar_TRIPLE}"
chmod +x "$TAURI_DIR/binaries/fluxion-server-${SIDEcar_TRIPLE}"

if [[ ! -f "$TAURI_DIR/icons/icon.icns" ]]; then
  log "Generating Tauri icons from assets/macos/Fluxion.svg"
  if command -v cargo >/dev/null 2>&1 && cargo tauri --version >/dev/null 2>&1; then
    mkdir -p "$TAURI_DIR/icons"
    (cd "$TAURI_DIR" && cargo tauri icon "$ROOT_DIR/assets/macos/Fluxion.svg") || true
  fi
fi

bash "$ROOT_DIR/scripts/ensure_sparkle_framework.sh"
export SPARKLE_FRAMEWORK_PATH="$ROOT_DIR/src-tauri/Frameworks"

log "Building Tauri app bundle"
(
  cd "$TAURI_DIR"
  export SPARKLE_FRAMEWORK_PATH
  if [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
    cargo tauri build --bundles app,dmg
  else
    cargo tauri build "${TAURI_BUILD_CONFIG[@]}" --bundles app
  fi
)

APP_BUNDLE="$(find "$TAURI_DIR/target/release/bundle/macos" -maxdepth 1 -name "${APP_NAME}.app" -print -quit)"
if [[ -z "$APP_BUNDLE" ]]; then
  echo "::error::${APP_NAME}.app not found under src-tauri/target/release/bundle/macos"
  exit 1
fi

mkdir -p "$DIST_ROOT"
rm -rf "$DIST_ROOT/${APP_NAME}.app"
cp -R "$APP_BUNDLE" "$DIST_ROOT/${APP_NAME}.app"

INFO_PLIST="$DIST_ROOT/${APP_NAME}.app/Contents/Info.plist"
if [[ -f "$INFO_PLIST" ]]; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$INFO_PLIST"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NUMBER" "$INFO_PLIST"
  if [[ "$LOCAL_BUILD" == true ]]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName Fluxion Local" "$INFO_PLIST"
    /usr/libexec/PlistBuddy -c "Set :CFBundleName Fluxion Local" "$INFO_PLIST"
  fi
fi

# PlistBuddy writes happen after Tauri's bundle signing pass. Re-seal the app
# so macOS TCC sees a valid code identity when remembering Screen Recording
# consent. A Developer ID / Apple Development identity is stable across builds;
# ad-hoc signatures change every build, which invalidates the TCC grant.
if [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
  codesign --force --options runtime --entitlements "$TAURI_DIR/entitlements.plist" \
    --sign "$APPLE_SIGNING_IDENTITY" "$DIST_ROOT/${APP_NAME}.app"
else
  LOCAL_SIGNING_IDENTITY="${FLUXION_LOCAL_SIGNING_IDENTITY:-}"
  if [[ -z "$LOCAL_SIGNING_IDENTITY" ]]; then
    LOCAL_SIGNING_IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null \
      | awk -F'"' '/Developer ID Application/ {print $2; exit}')"
  fi
  if [[ -z "$LOCAL_SIGNING_IDENTITY" ]]; then
    LOCAL_SIGNING_IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null \
      | awk -F'"' '/Apple Development/ {print $2; exit}')"
  fi
  if [[ -n "$LOCAL_SIGNING_IDENTITY" ]]; then
    codesign --force --entitlements "$TAURI_DIR/entitlements.plist" \
      --sign "$LOCAL_SIGNING_IDENTITY" "$DIST_ROOT/${APP_NAME}.app"
    log "Signed local build ($LOCAL_BUNDLE_ID) with '$LOCAL_SIGNING_IDENTITY'"
    log "Screen Recording consent will persist across rebuilds"
  else
    codesign --force --entitlements "$TAURI_DIR/entitlements.plist" \
      --sign - "$DIST_ROOT/${APP_NAME}.app"
    log "Ad-hoc signed local build as $LOCAL_BUNDLE_ID"
    log "Reset only its Screen Recording consent with: tccutil reset ScreenCapture $LOCAL_BUNDLE_ID"
  fi
fi
codesign --verify --deep --strict "$DIST_ROOT/${APP_NAME}.app"

if [[ -f "$TAURI_DIR/target/release/bundle/dmg/${APP_NAME}_${VERSION}_${SIDEcar_TRIPLE}.dmg" ]]; then
  cp "$TAURI_DIR/target/release/bundle/dmg/${APP_NAME}_${VERSION}_${SIDEcar_TRIPLE}.dmg" "$DMG_PATH"
elif compgen -G "$TAURI_DIR/target/release/bundle/dmg/"*.dmg > /dev/null; then
  cp "$(ls -1 "$TAURI_DIR/target/release/bundle/dmg/"*.dmg | head -n 1)" "$DMG_PATH"
fi

log "Creating zip for Sparkle/Homebrew"
rm -f "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "$DIST_ROOT/${APP_NAME}.app" "$ZIP_PATH"
(
  cd "$DIST_ROOT"
  shasum -a 256 "$(basename "$ZIP_PATH")" > SHA256SUMS
  if [[ -f "$(basename "$DMG_PATH")" ]]; then
    shasum -a 256 "$(basename "$DMG_PATH")" >> SHA256SUMS
  fi
)

log "Built $DIST_ROOT/${APP_NAME}.app"
if [[ -f "$ZIP_PATH" ]]; then
  log "Built $ZIP_PATH"
fi
if [[ -f "$DMG_PATH" ]]; then
  log "Built $DMG_PATH"
fi
