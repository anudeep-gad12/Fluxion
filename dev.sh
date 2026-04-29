#!/bin/bash
# Development script for Reasoning Runtime
# Usage: ./dev.sh [command]
#   start   - Start all services (default)
#   stop    - Stop all services
#   restart - Restart all services
#   logs    - View backend logs
#   traces  - View recent traces from SQLite
#   ui      - Start only the UI
#   api     - Start only the API

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/.pids"
DB_PATH="$PROJECT_DIR/var/traces.sqlite"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

mkdir -p "$LOG_DIR" "$PID_DIR"

log() {
    echo -e "${GREEN}[dev]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[dev]${NC} $1"
}

error() {
    echo -e "${RED}[dev]${NC} $1"
}

# Kill process on a port
kill_port() {
    local port=$1
    local pid=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$pid" ]; then
        kill -9 $pid 2>/dev/null || true
        log "Killed process on port $port"
    fi
}

# Start the API server
start_api() {
    log "Starting API server on port 9000..."
    kill_port 9000
    cd "$PROJECT_DIR"

    # Load main env (API keys: E2B_API_KEY, FIREWORKS_API_KEY, PARALLEL_API_KEY)
    if [ -f "$PROJECT_DIR/.env" ]; then
        set -a
        source "$PROJECT_DIR/.env"
        set +a
        log "Loaded .env"
    fi

    # Load provider env if set (overrides LLM settings from .env)
    if [ -f "$PROJECT_DIR/.env.provider" ]; then
        set -a
        source "$PROJECT_DIR/.env.provider"
        set +a
        log "Using provider: $(grep '^# Provider:' "$PROJECT_DIR/.env.provider" | cut -d: -f2)"
    fi

    nohup uv run uvicorn orchestrator.app:app --reload --reload-dir orchestrator --port 9000 --host 0.0.0.0 > "$LOG_DIR/api.log" 2>&1 &
    echo $! > "$PID_DIR/api.pid"
    sleep 2
    if curl -s http://localhost:9000/api/health > /dev/null 2>&1; then
        log "API server started: ${BLUE}http://localhost:9000${NC}"
    else
        warn "API server starting... (check logs/api.log)"
    fi
}

# Start the UI dev server
start_ui() {
    log "Starting UI dev server on port 3000..."
    kill_port 3000
    cd "$PROJECT_DIR/ui"
    nohup pnpm dev > "$LOG_DIR/ui.log" 2>&1 &
    echo $! > "$PID_DIR/ui.pid"
    sleep 2
    log "UI dev server started: ${BLUE}http://localhost:3000${NC}"
}

# Stop all services
stop_all() {
    log "Stopping all services..."
    kill_port 9000
    kill_port 3000

    # Kill by PID files
    for pidfile in "$PID_DIR"/*.pid; do
        if [ -f "$pidfile" ]; then
            pid=$(cat "$pidfile")
            kill -9 $pid 2>/dev/null || true
            rm "$pidfile"
        fi
    done

    log "All services stopped"
}

# View logs (combined view)
view_logs() {
    log "Showing recent logs then tailing app.log (Ctrl+C to exit)..."
    echo ""
    echo -e "${BLUE}=== Recent API Access Logs (api.log) ===${NC}"
    tail -10 "$LOG_DIR/api.log" 2>/dev/null || echo "No api.log yet"
    echo ""
    echo -e "${BLUE}=== Application Logs (app.log) ===${NC}"
    if [ -f "$LOG_DIR/app.log" ] && [ -s "$LOG_DIR/app.log" ]; then
        tail -f "$LOG_DIR/app.log" | while read line; do
            # Pretty print JSON if jq is available
            if command -v jq >/dev/null 2>&1; then
                echo "$line" | jq -c '{ts: .timestamp[-12:], lvl: .level, msg: .message[:60]}' 2>/dev/null || echo "$line"
            else
                echo "$line"
            fi
        done
    else
        echo "No app.log yet - start the server to generate logs"
    fi
}

# View structured application logs (JSON)
view_app_logs() {
    log "Tailing structured app logs (Ctrl+C to exit)..."
    if command -v jq >/dev/null 2>&1; then
        tail -f "$LOG_DIR/app.log" | jq .
    else
        tail -f "$LOG_DIR/app.log"
    fi
}

# Debug: show recent errors
show_debug() {
    echo -e "${BLUE}=== Recent Errors from app.log ===${NC}"
    if [ -f "$LOG_DIR/app.log" ]; then
        if command -v jq >/dev/null 2>&1; then
            grep '"level":"ERROR"\|"level":"WARNING"' "$LOG_DIR/app.log" 2>/dev/null | tail -20 | jq . || echo "No errors found"
        else
            grep '"level":"ERROR"\|"level":"WARNING"' "$LOG_DIR/app.log" 2>/dev/null | tail -20 || echo "No errors found"
        fi
    else
        echo "No app.log found"
    fi
    echo ""
    echo -e "${BLUE}=== Quick Commands ===${NC}"
    echo "  Find request ID:  grep -o '\"request_id\":\"[^\"]*\"' $LOG_DIR/app.log | sort -u"
    echo "  Trace request:    grep '<request_id>' $LOG_DIR/app.log | jq ."
    echo "  All errors:       grep '\"level\":\"ERROR\"' $LOG_DIR/app.log | jq ."
}

# View traces from SQLite
view_traces() {
    if [ ! -f "$DB_PATH" ]; then
        warn "No database found at $DB_PATH"
        warn "Run a query first to create traces"
        exit 1
    fi

    echo ""
    echo -e "${BLUE}=== Recent Runs ===${NC}"
    sqlite3 -header -column "$DB_PATH" "
        SELECT
            run_id,
            status,
            mode,
            profile_name,
            substr(user_message, 1, 40) as message,
            datetime(created_at) as created
        FROM runs
        ORDER BY created_at DESC
        LIMIT 10;
    "

    echo ""
    echo -e "${BLUE}=== Latest Run Events ===${NC}"
    local latest_run=$(sqlite3 "$DB_PATH" "SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1")
    if [ -n "$latest_run" ]; then
        echo "Run ID: $latest_run"
        echo ""
        sqlite3 -header -column "$DB_PATH" "
            SELECT
                seq,
                event_type as type,
                event_status as status,
                actor,
                substr(content_json, 1, 60) as content
            FROM trace_events
            WHERE run_id = '$latest_run'
            ORDER BY seq;
        "
    fi
}

# Interactive trace explorer
explore_trace() {
    local run_id=$1
    if [ -z "$run_id" ]; then
        echo "Usage: ./dev.sh explore <run_id>"
        echo ""
        echo "Recent runs:"
        sqlite3 -header -column "$DB_PATH" "SELECT run_id, status, substr(user_message, 1, 50) as message FROM runs ORDER BY created_at DESC LIMIT 5;"
        exit 1
    fi

    echo -e "${BLUE}=== Run Details ===${NC}"
    sqlite3 -header -column "$DB_PATH" "SELECT run_id, conversation_id, status, mode, profile_name, substr(user_message, 1, 60) as message, created_at FROM runs WHERE run_id = '$run_id';"

    echo ""
    echo -e "${BLUE}=== Events ===${NC}"
    sqlite3 -header -column "$DB_PATH" "
        SELECT seq, event_type as type, event_status as status, actor, substr(content_json, 1, 80) as content
        FROM trace_events WHERE run_id = '$run_id' ORDER BY seq;
    "

    echo ""
    echo -e "${BLUE}=== Final Answer ===${NC}"
    sqlite3 "$DB_PATH" "SELECT final_answer FROM runs WHERE run_id = '$run_id';"
}

# Switch provider (local llama-server or cloud providers)
switch_provider() {
    local provider=$1

    case "$provider" in
        local|llama)
            # Set for llama-server (local gpt-oss)
            # Start server first: llama-server -m ~/.lmstudio/models/lmstudio-community/gpt-oss-20b-GGUF/gpt-oss-20b-MXFP4.gguf --jinja --ctx-size 4096 -ub 512 -b 512 --port 8080
            cat > "$PROJECT_DIR/.env.provider" << 'EOF'
# Provider: llama-server (local gpt-oss)
LLM_BASE_URL=http://localhost:8080/v1
LLM_ENDPOINT=chat_completions
LLM_MODEL=gpt-oss-120b
EOF
            provider="local (llama-server + gpt-oss-20b)"
            ;;
        fireworks|cloud|fw)
            # Set for Fireworks (cloud)
            cat > "$PROJECT_DIR/.env.provider" << 'EOF'
# Provider: Fireworks (cloud Kimi K2.6)
LLM_BASE_URL=https://api.fireworks.ai/inference/v1
LLM_API_KEY=${FIREWORKS_API_KEY:-}
LLM_ENDPOINT=chat_completions
LLM_MODEL=accounts/fireworks/models/kimi-k2p6
EOF
            provider="fireworks (cloud Kimi K2.6)"
            ;;
        deepinfra|di)
            # Set for DeepInfra (cloud)
            cat > "$PROJECT_DIR/.env.provider" << 'EOF'
# Provider: DeepInfra (cloud)
LLM_BASE_URL=https://api.deepinfra.com/v1/openai
LLM_ENDPOINT=chat_completions
LLM_MODEL=openai/gpt-oss-120b
EOF
            provider="deepinfra (cloud)"
            ;;
        "")
            # Show current provider
            echo -e "${BLUE}=== Current Provider ===${NC}"
            if [ -f "$PROJECT_DIR/.env.provider" ]; then
                cat "$PROJECT_DIR/.env.provider"
            else
                echo "No provider set. Using config defaults (Fireworks Kimi K2.6)."
            fi
            echo ""
            echo "Usage: ./dev.sh provider [local|fireworks|deepinfra]"
            echo ""
            echo "  local     - llama-server @ localhost:8080 (gpt-oss-20b)"
            echo "  fireworks - Fireworks cloud API (Kimi K2.6)"
            echo "  deepinfra - DeepInfra cloud API (gpt-oss-120b)"
            return
            ;;
        *)
            error "Unknown provider: $provider"
            echo "Use: local, fireworks, deepinfra"
            exit 1
            ;;
    esac

    log "Switched to ${BLUE}$provider${NC}"
    cat "$PROJECT_DIR/.env.provider"
    echo ""
    warn "Restart required: ./dev.sh restart"
}

# Show status
show_status() {
    echo -e "${BLUE}=== Service Status ===${NC}"

    if curl -s http://localhost:9000/api/health > /dev/null 2>&1; then
        echo -e "API Server:  ${GREEN}Running${NC} on http://localhost:9000"
    else
        echo -e "API Server:  ${RED}Stopped${NC}"
    fi

    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo -e "UI Server:   ${GREEN}Running${NC} on http://localhost:3000"
    else
        echo -e "UI Server:   ${RED}Stopped${NC}"
    fi

    echo ""
    echo -e "${BLUE}=== Log Files ===${NC}"
    ls -la "$LOG_DIR"/*.log 2>/dev/null || echo "No logs yet"

    echo ""
    echo -e "${BLUE}=== Database ===${NC}"
    if [ -f "$DB_PATH" ]; then
        local run_count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM runs;" 2>/dev/null || echo "0")
        echo "Database: $DB_PATH"
        echo "Total runs: $run_count"
    else
        echo "No database yet"
    fi
}

# Main command handler
case "${1:-start}" in
    start)
        log "Starting Reasoning Runtime..."
        start_api
        start_ui
        echo ""
        show_status
        echo ""
        log "Ready! Open ${BLUE}http://localhost:3000${NC} in your browser"
        log "API docs at ${BLUE}http://localhost:9000/docs${NC}"
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 1
        start_api
        start_ui
        log "Restarted!"
        ;;
    api)
        start_api
        log "API only. View logs: ./dev.sh logs"
        ;;
    ui)
        start_ui
        ;;
    logs)
        view_logs
        ;;
    applogs)
        view_app_logs
        ;;
    debug)
        show_debug
        ;;
    traces)
        view_traces
        ;;
    explore)
        explore_trace "$2"
        ;;
    status)
        show_status
        ;;
    cli)
        # Install CLI deps if needed
        if ! uv run python -c "import textual" 2>/dev/null; then
            log "Installing CLI dependencies..."
            uv sync --extra cli
        fi
        # Launch CLI TUI, starting API if needed
        CLI_STARTED_API=false
        if ! curl -s http://localhost:9000/api/health > /dev/null 2>&1; then
            log "API not running — starting it first..."
            start_api
            CLI_STARTED_API=true
        fi
        shift
        # Trap: kill API on exit if we started it
        cleanup_cli() {
            if [ "$CLI_STARTED_API" = true ]; then
                log "Shutting down API server..."
                kill_port 9000
            fi
        }
        trap cleanup_cli EXIT INT TERM
        log "Launching CLI..."
        cd "$PROJECT_DIR"
        uv run python -m cli --working-dir "$(pwd)" "$@"
        ;;
    provider)
        switch_provider "$2"
        ;;
    *)
        echo "Usage: ./dev.sh [command]"
        echo ""
        echo "Commands:"
        echo "  start     Start all services (default)"
        echo "  stop      Stop all services"
        echo "  restart   Restart all services"
        echo "  api       Start only the API"
        echo "  ui        Start only the UI"
        echo "  cli       Launch CLI TUI (auto-starts API)"
        echo "  logs      Tail combined logs (api.log summary + app.log live)"
        echo "  applogs   Tail structured app logs (JSON, pretty-printed)"
        echo "  debug     Show recent errors and debugging commands"
        echo "  traces    View recent traces from database"
        echo "  explore   Explore a specific run: ./dev.sh explore <run_id>"
        echo "  status    Show service status"
        echo "  provider  Switch LLM provider: ./dev.sh provider [local|fireworks|deepinfra]"
        ;;
esac
