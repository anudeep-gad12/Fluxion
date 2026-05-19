#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Fluxion"
VERSION="${FLUXION_APP_VERSION:-$(cd "$ROOT_DIR" && python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')}"
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
export CI="${CI:-true}"
ARCH="$(uname -m)"
if [[ "$ARCH" == "arm64" ]]; then
  RELEASE_ARCH="arm64"
elif [[ "$ARCH" == "x86_64" ]]; then
  RELEASE_ARCH="x64"
else
  RELEASE_ARCH="$ARCH"
fi

BUILD_ROOT="$ROOT_DIR/build/macos"
DIST_ROOT="$ROOT_DIR/dist/macos"
APP_DIR="$DIST_ROOT/${APP_NAME}.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
ZIP_PATH="$DIST_ROOT/${APP_NAME}-macos-${RELEASE_ARCH}.zip"

log() { echo "[build-macos] $*"; }

log "Version $VERSION build $BUILD_ID"

log "Building frontend"
(
  cd "$ROOT_DIR/ui"
  pnpm install --frozen-lockfile
  pnpm build
)

log "Packaging backend with PyInstaller"
rm -rf "$BUILD_ROOT" "$DIST_ROOT"
mkdir -p "$BUILD_ROOT" "$DIST_ROOT"
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

log "Assembling ${APP_NAME}.app"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR/ui"
cp "$BUILD_ROOT/pyinstaller-dist/fluxion-server" "$RESOURCES_DIR/fluxion-server"
cp -R "$ROOT_DIR/ui/dist" "$RESOURCES_DIR/ui/dist"
cp "$ROOT_DIR/assets/macos/Fluxion.icns" "$RESOURCES_DIR/Fluxion.icns"

cat > "$MACOS_DIR/$APP_NAME" <<LAUNCHER
#!/usr/bin/env bash
set -euo pipefail
APP_BUNDLE="\$(cd "\$(dirname "\$0")/../.." && pwd)"
export FLUXION_APP_BUNDLE="\$APP_BUNDLE"
export FLUXION_LAUNCHER_PATH="\$APP_BUNDLE/Contents/MacOS/Fluxion"
export FLUXION_STATIC_DIR="\$APP_BUNDLE/Contents/Resources/ui/dist"
export FLUXION_APP_VERSION="$VERSION"
export FLUXION_BUILD_ID="$BUILD_ID"
if [[ "\$#" -eq 0 ]]; then
  exec "\$APP_BUNDLE/Contents/Resources/fluxion-server" open
fi
exec "\$APP_BUNDLE/Contents/Resources/fluxion-server" "\$@"
LAUNCHER
chmod +x "$MACOS_DIR/$APP_NAME" "$RESOURCES_DIR/fluxion-server"

cat > "$CONTENTS_DIR/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>$APP_NAME</string>
  <key>CFBundleIdentifier</key>
  <string>io.fluxion.local</string>
  <key>CFBundleName</key>
  <string>$APP_NAME</string>
  <key>CFBundleDisplayName</key>
  <string>$APP_NAME</string>
  <key>CFBundleIconFile</key>
  <string>Fluxion</string>
  <key>CFBundleVersion</key>
  <string>$VERSION</string>
  <key>CFBundleShortVersionString</key>
  <string>$VERSION</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSUIElement</key>
  <true/>
</dict>
</plist>
PLIST

log "Creating release archive"
rm -f "$ZIP_PATH" "$DIST_ROOT/SHA256SUMS"
(
  cd "$DIST_ROOT"
  ditto -c -k --sequesterRsrc --keepParent "${APP_NAME}.app" "$(basename "$ZIP_PATH")"
  shasum -a 256 "$(basename "$ZIP_PATH")" > SHA256SUMS
)

log "Built $ZIP_PATH"
