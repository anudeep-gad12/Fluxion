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
DB_PATH="$PROJECT_DIR/data/runs.db"

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
    nohup uv run uvicorn orchestrator.app:app --reload --port 9000 --host 0.0.0.0 > "$LOG_DIR/api.log" 2>&1 &
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

# View logs
view_logs() {
    log "Tailing API logs (Ctrl+C to exit)..."
    tail -f "$LOG_DIR/api.log"
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
            profile,
            substr(prompt, 1, 40) as prompt,
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
                type,
                json_extract(display, '$.title') as title,
                substr(json_extract(display, '$.summary'), 1, 60) as summary
            FROM events
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
        sqlite3 -header -column "$DB_PATH" "SELECT run_id, status, substr(prompt, 1, 50) as prompt FROM runs ORDER BY created_at DESC LIMIT 5;"
        exit 1
    fi

    echo -e "${BLUE}=== Run Details ===${NC}"
    sqlite3 -header -column "$DB_PATH" "SELECT * FROM runs WHERE run_id = '$run_id';"

    echo ""
    echo -e "${BLUE}=== Events ===${NC}"
    sqlite3 -header -column "$DB_PATH" "
        SELECT seq, type, display, substr(payload, 1, 100) as payload_preview
        FROM events WHERE run_id = '$run_id' ORDER BY seq;
    "

    echo ""
    echo -e "${BLUE}=== Final Answer ===${NC}"
    sqlite3 "$DB_PATH" "SELECT final_answer FROM runs WHERE run_id = '$run_id';"
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
    traces)
        view_traces
        ;;
    explore)
        explore_trace "$2"
        ;;
    status)
        show_status
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
        echo "  logs      Tail API logs"
        echo "  traces    View recent traces from database"
        echo "  explore   Explore a specific run: ./dev.sh explore <run_id>"
        echo "  status    Show service status"
        ;;
esac
