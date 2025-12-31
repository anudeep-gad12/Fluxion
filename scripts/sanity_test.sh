#!/bin/bash
# Comprehensive sanity flow for Reasoner
# Run: ./scripts/sanity_test.sh
# Requires: API server running on port 9000 (or override API_URL)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

API_URL="${API_URL:-http://127.0.0.1:9000}"
PASSED=0
FAILED=0
LAST_RUN_PAYLOAD=""

print_header() {
    echo ""
    echo "========================================"
    echo "$1"
    echo "========================================"
}

pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    FAILED=$((FAILED + 1))
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
}

# Simple JSON field reader (jq if available, else Python)
json_get() {
    local json="$1"
    local path="$2" # dot path e.g. .run_id

    if command -v jq >/dev/null 2>&1; then
        echo "$json" | jq -r "$path" 2>/dev/null
    else
        echo "$json" | python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read() or '{}')
    path = '$path'.lstrip('.').split('.')
    cur = data
    for p in path:
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            cur = None
            break
        if cur is None:
            break
    if cur is None:
        print('')
    elif isinstance(cur, bool):
        print('true' if cur else 'false')
    elif isinstance(cur, (dict, list)):
        print(json.dumps(cur))
    else:
        print(cur)
except Exception:
    print('')
"
    fi
}

json_array_len() {
    local json="$1"
    local key="$2"
    echo "$json" | python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read() or '{}')
    arr = data.get('$key')
    if arr is None:
        print(0)
    elif isinstance(arr, list):
        print(len(arr))
    else:
        print(0)
except Exception:
    print(0)
"
}

# Poll run status until done or timeout
wait_for_run() {
    local run_id="$1"
    local label="$2"
    local timeout="${3:-45}"
    local waited=0
    local status=""
    local payload=""

    while [ $waited -lt $timeout ]; do
        payload=$(curl -s "$API_URL/api/runs/$run_id")
        status=$(json_get "$payload" ".status")

        if [ "$status" = "succeeded" ]; then
            LAST_RUN_PAYLOAD="$payload"
            pass "$label succeeded (run: $run_id)"
            local answer
            answer=$(json_get "$payload" ".final_answer")
            if [ -n "$answer" ]; then
                pass "$label has final answer text"
            else
                warn "$label missing final answer text"
            fi
            return 0
        elif [ "$status" = "failed" ]; then
            LAST_RUN_PAYLOAD="$payload"
            local error_msg
            error_msg=$(json_get "$payload" ".error_message")
            fail "$label failed: ${error_msg:-unknown error}"
            return 1
        fi

        sleep 2
        waited=$((waited + 2))
    done

    LAST_RUN_PAYLOAD="$payload"
    fail "$label did not complete within ${timeout}s (last status: ${status:-unknown})"
    return 1
}

check_stream_complete() {
    local run_id="$1"
    local label="$2"
    local stream
    # Use longer timeout for completed runs to ensure we get the full response
    stream=$(curl -s --max-time 20 "$API_URL/api/runs/$run_id/stream")

    if echo "$stream" | grep -q "event: complete"; then
        pass "$label stream completes"
    elif echo "$stream" | grep -q "event: error"; then
        fail "$label stream has error event"
        return 1
    else
        # For completed runs, verify completion via run status and events
        local run_json
        run_json=$(curl -s "$API_URL/api/runs/$run_id")
        local status
        status=$(json_get "$run_json" ".status")
        if [ "$status" = "succeeded" ]; then
            # Run succeeded but stream was empty - check events exist
            local events_json
            events_json=$(curl -s "$API_URL/api/runs/$run_id/events")
            local event_count
            event_count=$(json_array_len "$events_json" "events")
            if [ "$event_count" -gt 0 ]; then
                pass "$label stream completes (verified via run status + events)"
            else
                fail "$label stream missing complete event"
                return 1
            fi
        else
            fail "$label stream missing complete event (status: $status)"
            return 1
        fi
    fi

    if echo "$stream" | grep -q "\"run_id\""; then
        pass "$label stream returns final payload"
    else
        warn "$label stream payload missing run_id"
    fi
}

check_events() {
    local run_id="$1"
    local label="$2"
    local events_json
    events_json=$(curl -s "$API_URL/api/runs/$run_id/events")
    local count
    count=$(json_array_len "$events_json" "events")
    if [ "$count" -gt 0 ]; then
        pass "$label events recorded ($count events)"
    else
        fail "$label events missing"
    fi
}

check_thinking() {
    local run_id="$1"
    local label="$2"
    local detail="$3"
    local expect_steps="${4:-true}"  # Default: expect steps (set to "false" for direct route)
    local thinking_json
    thinking_json=$(curl -s "$API_URL/api/runs/$run_id/thinking?detail=$detail")
    local summary
    summary=$(json_get "$thinking_json" ".thinking_summary")
    local steps
    steps=$(json_array_len "$thinking_json" "steps")

    if [ -n "$summary" ]; then
        pass "$label thinking summary ($detail) present"
    else
        warn "$label thinking summary ($detail) empty"
    fi

    if [ "$steps" -gt 0 ]; then
        pass "$label thinking steps ($detail) recorded ($steps steps)"
    elif [ "$expect_steps" = "true" ]; then
        fail "$label thinking steps ($detail) missing"
    else
        warn "$label thinking steps ($detail) empty (may be expected for direct route)"
    fi
}

check_report() {
    local run_id="$1"
    local label="$2"
    local report_json
    report_json=$(curl -s "$API_URL/api/runs/$run_id/report")
    local report_text
    report_text=$(json_get "$report_json" ".report")
    local timeline_len
    timeline_len=$(json_array_len "$report_json" "timeline")

    if [ -n "$report_text" ]; then
        pass "$label report available"
    else
        warn "$label report empty"
    fi

    if [ "$timeline_len" -gt 0 ]; then
        pass "$label timeline has entries ($timeline_len)"
    else
        fail "$label timeline missing"
    fi
}

check_conversation_detail() {
    local conversation_id="$1"
    local expected_run="$2"
    local label="$3"
    local conv_json
    conv_json=$(curl -s "$API_URL/api/conversations/$conversation_id")

    local summary
    summary=$(json_get "$conv_json" ".conversation.summary")
    if [ -n "$summary" ]; then
        pass "$label conversation summary updated"
    else
        warn "$label conversation summary empty"
    fi

    if echo "$conv_json" | grep -q "$expected_run"; then
        pass "$label conversation includes run $expected_run"
    else
        fail "$label conversation missing run $expected_run"
    fi
}

check_thinking_tokens() {
    local run_id="$1"
    local label="$2"
    local events_json
    events_json=$(curl -s "$API_URL/api/runs/$run_id/events")

    # Check for reasoning events (persisted events have type "reasoning", not "THINKING_TOKEN")
    # THINKING_TOKEN events only exist during live streaming and are not persisted
    if echo "$events_json" | grep -q '"type".*"reasoning"'; then
        pass "$label has reasoning events recorded"
    else
        fail "$label missing reasoning events"
    fi

    # Check if the thinking content contains [THINK] tags (validates streaming would have worked)
    local thinking_content
    thinking_content=$(echo "$events_json" | jq -r '.events[0].payload.internal.raw_content // empty' 2>/dev/null)
    if echo "$thinking_content" | grep -qi '\[THINK\]'; then
        pass "$label reasoning content has [THINK] tags (streaming UI compatible)"
    else
        warn "$label [THINK] tag not found in reasoning content"
    fi
}

check_think_tags() {
    local run_id="$1"
    local label="$2"
    local thinking_json
    thinking_json=$(curl -s "$API_URL/api/runs/$run_id/thinking?detail=internal")

    # Check if raw thinking contains [THINK] tag
    if echo "$thinking_json" | grep -qi '\[THINK\]'; then
        pass "$label response contains [THINK] tag"
    else
        warn "$label [THINK] tag not found in response (may affect streaming UI)"
    fi
}

# ============================================================
# 1. IMPORT TESTS (No server needed)
# ============================================================
print_header "1. Import Tests"

cd "$(dirname "$0")/.."

# Activate venv if exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "Testing Python imports..."

python -c "from orchestrator.config import get_chat_config" 2>/dev/null && pass "config module imports" || fail "config module imports"
python -c "from orchestrator.thinking import ThinkingOrchestrator, StreamParser" 2>/dev/null && pass "thinking module imports" || fail "thinking module imports"
python -c "from orchestrator.engine.chat_engine import ChatEngine" 2>/dev/null && pass "chat_engine imports" || fail "chat_engine imports"
python -c "from orchestrator.thinking.strategies.direct import DirectStrategy" 2>/dev/null && pass "direct strategy imports" || fail "direct strategy imports"
python -c "from orchestrator.thinking.strategies.cot import ChainOfThoughtStrategy" 2>/dev/null && pass "CoT strategy imports" || fail "CoT strategy imports"

# ============================================================
# 2. API HEALTH CHECK
# ============================================================
print_header "2. API Health Check"

if curl -s --max-time 3 "$API_URL/api/health" >/dev/null 2>&1; then
    pass "API health endpoint reachable"
else
    fail "API health check failed at $API_URL"
    echo "Start server with: ./dev.sh start"
    echo ""
    echo "========================================"
    echo "RESULTS: $PASSED passed, $FAILED failed (API tests skipped)"
    echo "========================================"
    exit 1
fi

CONFIG_JSON=$(curl -s --max-time 3 "$API_URL/api/config")
if [ -n "$CONFIG_JSON" ]; then
    pass "API config endpoint reachable"
else
    warn "API config endpoint empty"
fi

# ============================================================
# 2.5 OLLAMA CONNECTIVITY CHECK
# ============================================================
print_header "2.5. Ollama Connectivity Check"

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"

# Check Ollama is running
if curl -s --max-time 5 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    pass "Ollama server reachable at $OLLAMA_URL"
else
    fail "Ollama server not reachable at $OLLAMA_URL"
    echo "Start Ollama with: ollama serve"
    echo ""
    echo "========================================"
    echo "RESULTS: $PASSED passed, $FAILED failed (LLM tests skipped)"
    echo "========================================"
    exit 1
fi

# Check model is available
MODEL_NAME=$(json_get "$CONFIG_JSON" ".config.model.name")
MODEL_LIST=$(curl -s --max-time 5 "$OLLAMA_URL/api/tags")
if echo "$MODEL_LIST" | grep -q "$MODEL_NAME"; then
    pass "Model '$MODEL_NAME' is available in Ollama"
else
    warn "Model '$MODEL_NAME' not found - test may fail (pull with: ollama pull $MODEL_NAME)"
fi

# ============================================================
# 3. DIRECT FLOW (default mode)
# ============================================================
print_header "3. Direct Flow (default mode)"

DIRECT_CONV=$(curl -s -X POST "$API_URL/api/conversations" \
    -H "Content-Type: application/json" \
    -d '{"title": "Sanity Direct"}')
DIRECT_CONV_ID=$(json_get "$DIRECT_CONV" ".conversation_id")

if [ -n "$DIRECT_CONV_ID" ]; then
    pass "Created conversation for direct flow ($DIRECT_CONV_ID)"
else
    fail "Failed to create conversation for direct flow"
fi

DIRECT_RUN_RESP=$(curl -s -X POST "$API_URL/api/conversations/$DIRECT_CONV_ID/runs" \
    -H "Content-Type: application/json" \
    -d '{"message": "What is 2+2?"}')
DIRECT_RUN_ID=$(json_get "$DIRECT_RUN_RESP" ".run_id")

if [ -n "$DIRECT_RUN_ID" ]; then
    pass "Created direct/CAR run ($DIRECT_RUN_ID)"
else
    fail "Failed to create direct/CAR run"
fi

if [ -n "$DIRECT_RUN_ID" ]; then
    wait_for_run "$DIRECT_RUN_ID" "Direct run"
    check_stream_complete "$DIRECT_RUN_ID" "Direct run"
    check_events "$DIRECT_RUN_ID" "Direct run"
    check_thinking "$DIRECT_RUN_ID" "Direct run" "user" "false"
    check_thinking "$DIRECT_RUN_ID" "Direct run" "internal" "false"
    check_report "$DIRECT_RUN_ID" "Direct run"
    check_conversation_detail "$DIRECT_CONV_ID" "$DIRECT_RUN_ID" "Direct"
fi

# ============================================================
# 4. CoT FLOW (thinking mode)
# ============================================================
print_header "4. CoT Flow (thinking mode)"

COT_CONV=$(curl -s -X POST "$API_URL/api/conversations" \
    -H "Content-Type: application/json" \
    -d '{"title": "Sanity CoT"}')
COT_CONV_ID=$(json_get "$COT_CONV" ".conversation_id")

if [ -n "$COT_CONV_ID" ]; then
    pass "Created conversation for CoT flow ($COT_CONV_ID)"
else
    fail "Failed to create conversation for CoT flow"
fi

COT_RUN_RESP=$(curl -s -X POST "$API_URL/api/conversations/$COT_CONV_ID/runs" \
    -H "Content-Type: application/json" \
    -d '{"message": "Explain how the Pythagorean theorem works.", "thinking_mode": "thinking"}')
COT_RUN_ID=$(json_get "$COT_RUN_RESP" ".run_id")

if [ -n "$COT_RUN_ID" ]; then
    pass "Created CoT run ($COT_RUN_ID)"
else
    fail "Failed to create CoT run"
fi

if [ -n "$COT_RUN_ID" ]; then
    wait_for_run "$COT_RUN_ID" "CoT run" 75
    check_stream_complete "$COT_RUN_ID" "CoT run"
    check_events "$COT_RUN_ID" "CoT run"
    check_thinking_tokens "$COT_RUN_ID" "CoT run"
    check_think_tags "$COT_RUN_ID" "CoT run"
    check_thinking "$COT_RUN_ID" "CoT run" "user"
    check_thinking "$COT_RUN_ID" "CoT run" "internal"
    check_report "$COT_RUN_ID" "CoT run"
    check_conversation_detail "$COT_CONV_ID" "$COT_RUN_ID" "CoT"
fi

# ============================================================
# 5. LIST + HOUSEKEEPING CHECKS
# ============================================================
print_header "5. Listing & housekeeping"

RUN_LIST=$(curl -s "$API_URL/api/runs?limit=5")
if echo "$RUN_LIST" | grep -q "$DIRECT_RUN_ID" && echo "$RUN_LIST" | grep -q "$COT_RUN_ID"; then
    pass "Run listing returns recent runs"
else
    warn "Run listing missing recent runs"
fi

CONV_LIST=$(curl -s "$API_URL/api/conversations?limit=5")
if echo "$CONV_LIST" | grep -q "$DIRECT_CONV_ID" && echo "$CONV_LIST" | grep -q "$COT_CONV_ID"; then
    pass "Conversation listing returns created conversations"
else
    warn "Conversation listing missing created conversations"
fi

# ============================================================
# RESULTS
# ============================================================
print_header "RESULTS"

TOTAL=$((PASSED + FAILED))
echo "Passed: $PASSED / $TOTAL"
echo "Failed: $FAILED / $TOTAL"

if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "\n${RED}Some tests failed!${NC}"
    exit 1
fi
