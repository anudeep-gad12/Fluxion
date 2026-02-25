#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="/usr/local/bin/reasoner"

cat > "$WRAPPER" << 'WRAPPER_EOF'
#!/bin/bash
REPO_DIR="REPO_DIR_PLACEHOLDER"
API_URL="${REASONER_API_URL:-http://127.0.0.1:9000}"
LLAMA_PORT=8080

# Search paths for GGUF models
MODEL_DIRS=(
    "$HOME/.lmstudio/models"
    "$HOME/models"
    "$HOME/.cache/huggingface"
    "$HOME/.cache/lm-studio/models"
)

# --- Parse --local before passing rest to CLI ---
LOCAL_MODE=false
CLI_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --local)
            LOCAL_MODE=true
            shift
            ;;
        *)
            CLI_ARGS+=("$1")
            shift
            ;;
    esac
done

# --- Pids we started (cleaned up on exit) ---
STARTED_LLAMA=false
LLAMA_PID=""
STARTED_API=false
API_PID=""

cleanup() {
    if [ "$STARTED_API" = true ] && [ -n "$API_PID" ]; then
        echo ""
        echo "[reasoner] Shutting down server (pid $API_PID)..."
        kill $API_PID 2>/dev/null || true
        wait $API_PID 2>/dev/null || true
    fi
    if [ "$STARTED_LLAMA" = true ] && [ -n "$LLAMA_PID" ]; then
        echo "[reasoner] Shutting down llama-server (pid $LLAMA_PID)..."
        kill $LLAMA_PID 2>/dev/null || true
        wait $LLAMA_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# =============================================================================
# Local mode: find models, let user pick, start llama-server
# =============================================================================
if [ "$LOCAL_MODE" = true ]; then

    # Check llama-server is installed
    if ! command -v llama-server &>/dev/null; then
        echo "[reasoner] Error: llama-server not found"
        echo "  Install: brew install llama.cpp"
        exit 1
    fi

    # Find all GGUF files (exclude mmproj vision files and split shards except first)
    MODELS=()
    for dir in "${MODEL_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            while IFS= read -r f; do
                MODELS+=("$f")
            done < <(find "$dir" -name "*.gguf" -type f 2>/dev/null \
                | grep -v "mmproj" \
                | grep -v '\-00002-of-' \
                | grep -v '\-00003-of-' \
                | sort)
        fi
    done

    if [ ${#MODELS[@]} -eq 0 ]; then
        echo "[reasoner] No GGUF models found in:"
        for dir in "${MODEL_DIRS[@]}"; do echo "  $dir"; done
        echo ""
        echo "Download a model and place it in one of these directories."
        exit 1
    fi

    # Display model picker
    echo ""
    echo "  Local models"
    echo "  ────────────"
    for i in "${!MODELS[@]}"; do
        # Show friendly name: parent-dir/filename
        path="${MODELS[$i]}"
        name="$(basename "$(dirname "$path")")/$(basename "$path")"
        # Show size
        if command -v numfmt &>/dev/null; then
            size=$(stat -f%z "$path" 2>/dev/null | numfmt --to=iec 2>/dev/null || echo "?")
        else
            bytes=$(stat -f%z "$path" 2>/dev/null || echo 0)
            size="$(( bytes / 1073741824 ))G"
        fi
        printf "  %2d) %-60s %s\n" $((i+1)) "$name" "$size"
    done
    echo ""

    # Read selection
    while true; do
        printf "  Select model [1-%d]: " ${#MODELS[@]}
        read -r choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le ${#MODELS[@]} ]; then
            break
        fi
        echo "  Invalid choice."
    done

    SELECTED="${MODELS[$((choice-1))]}"
    MODEL_NAME="$(basename "$SELECTED" .gguf)"
    echo ""
    echo "[reasoner] Starting llama-server with $MODEL_NAME..."

    # Kill anything on the llama port first
    lsof -ti:$LLAMA_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true

    # Start llama-server
    mkdir -p "$REPO_DIR/logs"
    llama-server \
        -m "$SELECTED" \
        --port $LLAMA_PORT \
        --jinja \
        --ctx-size 4096 \
        -ub 512 -b 512 \
        > "$REPO_DIR/logs/llama.log" 2>&1 &
    LLAMA_PID=$!
    STARTED_LLAMA=true

    # Wait for llama-server to be ready (up to 30s — model loading can be slow)
    printf "[reasoner] Loading model"
    for i in $(seq 1 60); do
        if curl -s "http://localhost:$LLAMA_PORT/health" 2>/dev/null | grep -q '"status":"ok"'; then
            echo " ready!"
            break
        fi
        # Check if process died
        if ! kill -0 $LLAMA_PID 2>/dev/null; then
            echo " failed!"
            echo "[reasoner] llama-server exited. Check $REPO_DIR/logs/llama.log"
            exit 1
        fi
        printf "."
        sleep 0.5
    done

    if ! curl -s "http://localhost:$LLAMA_PORT/health" 2>/dev/null | grep -q '"status":"ok"'; then
        echo " timeout!"
        echo "[reasoner] llama-server not ready after 30s. Check $REPO_DIR/logs/llama.log"
        exit 1
    fi

    # Configure backend to use local llama-server
    export LLM_BASE_URL="http://localhost:$LLAMA_PORT/v1"
    export LLM_ENDPOINT="chat_completions"
    export LLM_MODEL="$MODEL_NAME"
fi

# =============================================================================
# Auto-start API server if not running
# =============================================================================
if ! curl -s "$API_URL/api/health" > /dev/null 2>&1; then
    echo "[reasoner] Starting backend server..."

    # Load env files
    if [ -f "$REPO_DIR/.env" ]; then
        set -a; source "$REPO_DIR/.env"; set +a
    fi
    if [ "$LOCAL_MODE" = false ] && [ -f "$REPO_DIR/.env.provider" ]; then
        set -a; source "$REPO_DIR/.env.provider"; set +a
    fi

    # Re-export local mode vars (they may have been overwritten by .env)
    if [ "$LOCAL_MODE" = true ]; then
        export LLM_BASE_URL="http://localhost:$LLAMA_PORT/v1"
        export LLM_ENDPOINT="chat_completions"
        export LLM_MODEL="$MODEL_NAME"
    fi

    mkdir -p "$REPO_DIR/logs"
    nohup uv run --project "$REPO_DIR" uvicorn orchestrator.app:app --port 9000 --host 0.0.0.0 \
        > "$REPO_DIR/logs/api.log" 2>&1 &
    API_PID=$!
    STARTED_API=true

    # Wait up to 10s for the server to be ready
    for i in $(seq 1 20); do
        if curl -s "$API_URL/api/health" > /dev/null 2>&1; then
            echo "[reasoner] Server ready"
            break
        fi
        sleep 0.5
    done

    if ! curl -s "$API_URL/api/health" > /dev/null 2>&1; then
        echo "[reasoner] Warning: server may not be ready yet (check $REPO_DIR/logs/api.log)"
    fi
fi

# =============================================================================
# Launch CLI
# =============================================================================
uv run --project "$REPO_DIR" python -m cli "${CLI_ARGS[@]}"
WRAPPER_EOF

# Replace placeholder with actual repo directory
sed -i '' "s|REPO_DIR_PLACEHOLDER|$REPO_DIR|g" "$WRAPPER"

chmod +x "$WRAPPER"
echo "Installed: reasoner → $REPO_DIR"
echo ""
echo "Usage:"
echo "  reasoner            # cloud provider (use /login for ChatGPT auth)"
echo "  reasoner --local    # pick a local model, starts llama-server for you"
