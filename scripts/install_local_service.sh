#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Fluxion"
APP_SLUG="fluxion"
DEFAULT_REF="main"
REPO_ARCHIVE_URL="https://github.com/anudeep-gad12/Fluxion/archive/refs/heads/${FLUXION_REF:-$DEFAULT_REF}.tar.gz"
HOST="127.0.0.1"
PORT="${FLUXION_PORT:-9000}"
URL="http://${HOST}:${PORT}"

if [[ "$(uname -s)" == "Darwin" ]]; then
  PLATFORM="macos"
  APP_ROOT="${HOME}/Library/Application Support/Fluxion"
  SERVICE_DIR="${HOME}/Library/LaunchAgents"
  SERVICE_FILE="${SERVICE_DIR}/io.fluxion.local.plist"
elif [[ "$(uname -s)" == "Linux" ]]; then
  PLATFORM="linux"
  APP_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/fluxion"
  SERVICE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  SERVICE_FILE="${SERVICE_DIR}/fluxion.service"
else
  echo "Unsupported OS: $(uname -s)" >&2
  exit 1
fi

SRC_DIR="${APP_ROOT}/source"
VENV_DIR="${APP_ROOT}/.venv"
DATA_DIR="${APP_ROOT}/data"
LOG_DIR="${DATA_DIR}/logs"
DB_PATH="${DATA_DIR}/var/traces.sqlite"
BIN_DIR="${HOME}/.local/bin"
LAUNCHER_PATH="${BIN_DIR}/fluxion"

log() { echo "[fluxion-install] $*"; }
fail() { echo "[fluxion-install] $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

open_url() {
  if [[ "$PLATFORM" == "macos" ]]; then
    open "$URL"
  else
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
}

pnpm_cmd() {
  if command -v pnpm >/dev/null 2>&1; then
    pnpm "$@"
  elif command -v corepack >/dev/null 2>&1; then
    corepack pnpm "$@"
  else
    fail "Need pnpm or corepack to build the UI"
  fi
}

write_launcher() {
  mkdir -p "$BIN_DIR"
  cat > "$LAUNCHER_PATH" <<LAUNCHER
#!/usr/bin/env bash
set -euo pipefail
PLATFORM="$PLATFORM"
SERVICE_FILE="$SERVICE_FILE"
URL="$URL"

service_start() {
  if [[ "\$PLATFORM" == "macos" ]]; then
    launchctl bootout "gui/\$(id -u)" "\$SERVICE_FILE" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/\$(id -u)" "\$SERVICE_FILE"
  else
    systemctl --user daemon-reload
    systemctl --user enable --now fluxion.service >/dev/null
  fi
}

service_stop() {
  if [[ "\$PLATFORM" == "macos" ]]; then
    launchctl bootout "gui/\$(id -u)" "\$SERVICE_FILE" >/dev/null 2>&1 || true
  else
    systemctl --user disable --now fluxion.service >/dev/null 2>&1 || true
  fi
}

service_status() {
  if [[ "\$PLATFORM" == "macos" ]]; then
    launchctl print "gui/\$(id -u)/io.fluxion.local" >/dev/null 2>&1
  else
    systemctl --user is-active --quiet fluxion.service
  fi
}

case "\${1:-open}" in
  start)
    service_start
    ;;
  stop)
    service_stop
    ;;
  restart)
    service_stop || true
    service_start
    ;;
  status)
    if service_status; then
      echo "running"
    else
      echo "stopped"
      exit 1
    fi
    ;;
  open)
    if ! service_status; then
      service_start
      sleep 2
    fi
    if [[ "\$PLATFORM" == "macos" ]]; then
      open "\$URL"
    else
      xdg-open "\$URL" >/dev/null 2>&1 || true
    fi
    ;;
  *)
    echo "usage: fluxion [start|stop|restart|status|open]" >&2
    exit 1
    ;;
esac
LAUNCHER
  chmod +x "$LAUNCHER_PATH"
}

write_service() {
  mkdir -p "$SERVICE_DIR" "$LOG_DIR" "$(dirname "$DB_PATH")"
  if [[ "$PLATFORM" == "macos" ]]; then
    cat > "$SERVICE_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>io.fluxion.local</string>
  <key>WorkingDirectory</key>
  <string>$SRC_DIR</string>
  <key>ProgramArguments</key>
  <array>
    <string>$VENV_DIR/bin/python</string>
    <string>-m</string>
    <string>uvicorn</string>
    <string>orchestrator.app:app</string>
    <string>--host</string>
    <string>$HOST</string>
    <string>--port</string>
    <string>$PORT</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>SERVE_STATIC</key><string>true</string>
    <key>DATABASE_PATH</key><string>$DB_PATH</string>
    <key>LOG_DIR</key><string>$LOG_DIR</string>
    <key>LOG_TO_FILE</key><string>true</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/service.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/service.stderr.log</string>
</dict>
</plist>
PLIST
  else
    cat > "$SERVICE_FILE" <<UNIT
[Unit]
Description=Fluxion local browser app
After=network.target

[Service]
Type=simple
WorkingDirectory=$SRC_DIR
Environment=SERVE_STATIC=true
Environment=DATABASE_PATH=$DB_PATH
Environment=LOG_DIR=$LOG_DIR
Environment=LOG_TO_FILE=true
ExecStart=$VENV_DIR/bin/python -m uvicorn orchestrator.app:app --host $HOST --port $PORT
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
UNIT
  fi
}

start_service() {
  if [[ "$PLATFORM" == "macos" ]]; then
    launchctl bootout "gui/$(id -u)" "$SERVICE_FILE" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$SERVICE_FILE"
  else
    systemctl --user daemon-reload
    systemctl --user enable --now fluxion.service >/dev/null
  fi
}

wait_for_health() {
  for _ in $(seq 1 40); do
    if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  fail "Fluxion service did not become healthy at $URL"
}

require_cmd curl
require_cmd tar
require_cmd python3
if [[ "$PLATFORM" == "linux" ]]; then
  require_cmd systemctl
fi

log "Installing into $APP_ROOT"
rm -rf "$SRC_DIR"
mkdir -p "$SRC_DIR" "$DATA_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
curl -fsSL "$REPO_ARCHIVE_URL" | tar -xz -C "$TMP_DIR"
EXTRACTED_DIR="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
cp -R "$EXTRACTED_DIR"/. "$SRC_DIR"/

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -e "$SRC_DIR"
(
  cd "$SRC_DIR/ui"
  pnpm_cmd install --frozen-lockfile
  pnpm_cmd build
)

write_service
write_launcher
start_service
wait_for_health
open_url

log "Installed. Use 'fluxion open' or visit $URL"
