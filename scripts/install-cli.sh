#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="/usr/local/bin/reasoner"

cat > "$WRAPPER" << WRAPPER_EOF
#!/bin/bash
REPO_DIR="$REPO_DIR"
API_URL="\${REASONER_API_URL:-http://127.0.0.1:9000}"

# --- Auto-start API server if not running ---
STARTED_API=false

if ! curl -s "\$API_URL/api/health" > /dev/null 2>&1; then
    echo "[reasoner] API not running — starting server..."

    # Load env files
    if [ -f "\$REPO_DIR/.env" ]; then
        set -a; source "\$REPO_DIR/.env"; set +a
    fi
    if [ -f "\$REPO_DIR/.env.provider" ]; then
        set -a; source "\$REPO_DIR/.env.provider"; set +a
    fi

    mkdir -p "\$REPO_DIR/logs"
    nohup uv run --project "\$REPO_DIR" uvicorn orchestrator.app:app --port 9000 --host 0.0.0.0 \\
        > "\$REPO_DIR/logs/api.log" 2>&1 &
    API_PID=\$!

    # Wait up to 10s for the server to be ready
    for i in \$(seq 1 20); do
        if curl -s "\$API_URL/api/health" > /dev/null 2>&1; then
            echo "[reasoner] Server ready (pid \$API_PID)"
            break
        fi
        sleep 0.5
    done

    if ! curl -s "\$API_URL/api/health" > /dev/null 2>&1; then
        echo "[reasoner] Warning: server may not be ready yet (check \$REPO_DIR/logs/api.log)"
    fi

    STARTED_API=true
fi

# --- Cleanup: stop server on exit if we started it ---
cleanup() {
    if [ "\$STARTED_API" = true ] && [ -n "\$API_PID" ]; then
        echo ""
        echo "[reasoner] Shutting down server (pid \$API_PID)..."
        kill \$API_PID 2>/dev/null || true
        wait \$API_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# --- Launch CLI ---
exec uv run --project "\$REPO_DIR" python -m cli "\$@"
WRAPPER_EOF

chmod +x "$WRAPPER"
echo "Installed: reasoner → $REPO_DIR"
echo "Run 'reasoner' from any directory."
