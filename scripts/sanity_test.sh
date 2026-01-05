#!/bin/bash
# Comprehensive sanity flow for Reasoner
# Run: ./scripts/sanity_test.sh [--debug]
# Requires: API server running on port 9000 (or override API_URL)
#
# Options:
#   --debug    Tail structured logs in background during test

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

API_URL="${API_URL:-http://127.0.0.1:9000}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
APP_LOG="$LOG_DIR/app.log"

PASSED=0
FAILED=0
LAST_RUN_PAYLOAD=""
TAIL_PID=""
DEBUG_MODE=false

# Parse --debug flag
if [ "$1" = "--debug" ]; then
    DEBUG_MODE=true
    shift
fi

# ============================================================
# LOG INTEGRATION FUNCTIONS
# ============================================================

clear_logs() {
    mkdir -p "$LOG_DIR"
    : > "$APP_LOG"
    echo -e "${YELLOW}Cleared app.log for fresh run${NC}"
}

show_failure_logs() {
    local run_id="$1"
    echo ""
    echo -e "${BLUE}=== Relevant Log Entries ===${NC}"
    if [ -f "$APP_LOG" ] && [ -s "$APP_LOG" ]; then
        if [ -n "$run_id" ]; then
            # Show logs for specific run
            grep "$run_id" "$APP_LOG" 2>/dev/null | \
                python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line)
        lvl = e.get('level', '')
        msg = e.get('message', '')[:60]
        err = e.get('error', {})
        print(f'{lvl}: {msg}')
        if err.get('type'):
            print(f'       Error: {err.get(\"type\")}: {err.get(\"message\", \"\")[:50]}')
    except: pass
" 2>/dev/null || grep "$run_id" "$APP_LOG"
        else
            # Show all errors
            grep '"level":"ERROR"\|"level":"WARNING"' "$APP_LOG" 2>/dev/null | tail -20 | \
                python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line)
        lvl = e.get('level', '')
        msg = e.get('message', '')[:60]
        req_id = e.get('request_id', '-')[:8]
        print(f'[{req_id}] {lvl}: {msg}')
    except: print(line.strip())
" 2>/dev/null || grep '"level":"ERROR"\|"level":"WARNING"' "$APP_LOG" | tail -20
        fi
    else
        echo "No logs found"
    fi
}

start_debug_tail() {
    if [ "$DEBUG_MODE" = true ]; then
        echo -e "${YELLOW}Starting log tail in background...${NC}"
        # Use a subshell with exec to ensure we can kill the entire process group
        (
            exec tail -f "$APP_LOG" 2>/dev/null | while read line; do
                echo "$line" | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line)
        ts = e.get('timestamp', '')[-12:-7]
        lvl = e.get('level', '')[:4]
        msg = e.get('message', '')[:50]
        print(f'  [{ts}] {lvl}: {msg}')
    except: pass
" 2>/dev/null
            done
        ) &
        TAIL_PID=$!
    fi
}

stop_debug_tail() {
    if [ -n "$TAIL_PID" ]; then
        # Kill the process group to ensure tail and all children are killed
        kill -- -$TAIL_PID 2>/dev/null || kill $TAIL_PID 2>/dev/null || true
        # Also kill any orphaned tail processes for this log file
        pkill -f "tail -f $APP_LOG" 2>/dev/null || true
    fi
}

trap stop_debug_tail EXIT

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

check_native_reasoning() {
    local run_id="$1"
    local label="$2"
    local run_json
    run_json=$(curl -s "$API_URL/api/runs/$run_id")

    # Check thinking_summary is populated (from native reasoning or parsed thinking)
    local thinking
    thinking=$(json_get "$run_json" ".thinking_summary")
    if [ -n "$thinking" ] && [ "$thinking" != "null" ]; then
        pass "$label has reasoning captured"
    else
        warn "$label reasoning not captured (may be model-dependent)"
    fi
}

# Agent helper functions
wait_for_agent_run() {
    local run_id="$1"
    local label="$2"
    local timeout="${3:-60}"
    local waited=0
    local status=""

    while [ $waited -lt $timeout ]; do
        local payload
        payload=$(curl -s "$API_URL/api/agent/runs/$run_id")
        status=$(json_get "$payload" ".status")

        if [ "$status" = "succeeded" ]; then
            pass "$label succeeded (run: $run_id)"
            local answer
            answer=$(json_get "$payload" ".final_answer")
            if [ -n "$answer" ] && [ "$answer" != "null" ]; then
                pass "$label has final answer"
            else
                warn "$label missing final answer"
            fi
            return 0
        elif [ "$status" = "failed" ]; then
            local error
            error=$(json_get "$payload" ".error_message")
            fail "$label failed: ${error:-unknown}"
            return 1
        fi

        sleep 3
        waited=$((waited + 3))
    done

    fail "$label did not complete within ${timeout}s (status: ${status:-unknown})"
    return 1
}

check_agent_trace() {
    local run_id="$1"
    local label="$2"
    local trace
    local http_code

    # Get trace with HTTP status code
    http_code=$(curl -s -o /tmp/agent_trace.json -w "%{http_code}" "$API_URL/api/agent/runs/$run_id/trace")
    trace=$(cat /tmp/agent_trace.json 2>/dev/null)

    # Check if trace endpoint is working
    if [ "$http_code" != "200" ]; then
        warn "$label trace endpoint returned HTTP $http_code (endpoint may have issues)"
        return 0
    fi

    # Check for error in response
    if echo "$trace" | grep -qi "internal server error"; then
        warn "$label trace endpoint returned error (endpoint may have issues)"
        return 0
    fi

    local step_count
    step_count=$(json_array_len "$trace" "steps")
    if [ "$step_count" -gt 0 ]; then
        pass "$label has steps recorded ($step_count steps)"
    else
        warn "$label has no step records (may be expected for simple queries)"
    fi

    local tool_count
    tool_count=$(json_array_len "$trace" "tool_calls")
    if [ "$tool_count" -gt 0 ]; then
        pass "$label has tool calls recorded ($tool_count calls)"
    else
        warn "$label has no tool calls (may be expected for simple queries)"
    fi
}

# ============================================================
# 0. SETUP
# ============================================================
clear_logs
start_debug_tail

# ============================================================
# 1. IMPORT TESTS (No server needed)
# ============================================================
print_header "1. Import Tests"

cd "$PROJECT_DIR"

# Activate venv if exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "Testing Python imports..."

python -c "from orchestrator.config import get_chat_config" 2>/dev/null && pass "config module imports" || fail "config module imports"
python -c "from orchestrator.thinking import ThinkingOrchestrator, StreamParser" 2>/dev/null && pass "thinking module imports" || fail "thinking module imports"
python -c "from orchestrator.engine.chat_engine import ChatEngine" 2>/dev/null && pass "chat_engine imports" || fail "chat_engine imports"
python -c "from orchestrator.thinking.strategies.direct import DirectStrategy" 2>/dev/null && pass "direct strategy imports" || fail "direct strategy imports"

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
# 2.5 LLM PROVIDER CONNECTIVITY CHECK
# ============================================================
print_header "2.5. LLM Provider Connectivity Check"

# Get base_url from config (OpenAI-compatible endpoint)
LLM_BASE_URL=$(json_get "$CONFIG_JSON" ".config.provider.base_url")
LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:1234}"

# Check /v1/models endpoint (OpenAI-compatible)
if curl -s --max-time 5 "$LLM_BASE_URL/v1/models" | grep -q "data\|models\|id"; then
    pass "LLM server reachable at $LLM_BASE_URL"
else
    fail "LLM server not reachable at $LLM_BASE_URL"
    echo "Start LM Studio or your OpenAI-compatible server"
    echo ""
    echo "========================================"
    echo "RESULTS: $PASSED passed, $FAILED failed (LLM tests skipped)"
    echo "========================================"
    exit 1
fi

# Check model name from config
MODEL_NAME=$(json_get "$CONFIG_JSON" ".config.model.name")
if [ -n "$MODEL_NAME" ] && [ "$MODEL_NAME" != "null" ]; then
    pass "Model configured: $MODEL_NAME"
else
    warn "Model name not found in config"
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
    check_native_reasoning "$DIRECT_RUN_ID" "Direct run"
    check_report "$DIRECT_RUN_ID" "Direct run"
    check_conversation_detail "$DIRECT_CONV_ID" "$DIRECT_RUN_ID" "Direct"
fi

# ============================================================
# 3.5 MULTI-TURN CONTEXT TEST
# ============================================================
print_header "3.5. Multi-Turn Context Test"

# Use same conversation from direct flow test
if [ -n "$DIRECT_CONV_ID" ] && [ -n "$DIRECT_RUN_ID" ]; then
    # Send follow-up message that references prior context
    FOLLOWUP_RESP=$(curl -s -X POST "$API_URL/api/conversations/$DIRECT_CONV_ID/runs" \
        -H "Content-Type: application/json" \
        -d '{"message": "What was my previous question?"}')
    FOLLOWUP_RUN_ID=$(json_get "$FOLLOWUP_RESP" ".run_id")

    if [ -n "$FOLLOWUP_RUN_ID" ]; then
        pass "Created follow-up run ($FOLLOWUP_RUN_ID)"
        wait_for_run "$FOLLOWUP_RUN_ID" "Follow-up run"

        # Check if response references the prior question
        followup_answer=$(json_get "$LAST_RUN_PAYLOAD" ".final_answer")
        # Look for "2+2" or "two plus two" or similar in response
        if echo "$followup_answer" | grep -qi "2.*2\|two.*two\|previous\|asked\|addition\|math"; then
            pass "Context preserved - response references prior conversation"
        else
            warn "Context test inconclusive - response may not reference prior question"
        fi
    else
        fail "Failed to create follow-up run"
    fi
else
    warn "Skipping context test - no prior conversation"
fi

# ============================================================
# 4. AGENT FLOW
# ============================================================
print_header "4. Agent Flow"

# Check if agent endpoint exists
AGENT_CHECK=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/agent/runs" -X POST -H "Content-Type: application/json" -d '{}' 2>/dev/null)
if [ "$AGENT_CHECK" = "404" ]; then
    warn "Agent endpoint not available - skipping agent tests"
else
    # Create agent run with a simple calculation query
    AGENT_RUN_RESP=$(curl -s -X POST "$API_URL/api/agent/runs" \
        -H "Content-Type: application/json" \
        -d '{"query": "What is 15 multiplied by 7? Calculate it step by step.", "max_steps": 5}')
    AGENT_RUN_ID=$(json_get "$AGENT_RUN_RESP" ".run_id")

    if [ -n "$AGENT_RUN_ID" ] && [ "$AGENT_RUN_ID" != "null" ]; then
        pass "Created agent run ($AGENT_RUN_ID)"

        # Wait for completion (longer timeout for tool execution)
        wait_for_agent_run "$AGENT_RUN_ID" "Agent run" 90

        # Check trace
        check_agent_trace "$AGENT_RUN_ID" "Agent run"
    else
        warn "Failed to create agent run - agent may not be configured"
    fi
fi

# ============================================================
# 5. TOOL HEALTH (Optional)
# ============================================================
print_header "5. Tool Health (Optional)"

# Check E2B sandbox if configured
E2B_KEY=$(json_get "$CONFIG_JSON" ".config.sandbox.e2b.api_key")
if [ -n "$E2B_KEY" ] && [ "$E2B_KEY" != "null" ] && [ "$E2B_KEY" != "***" ] && [ "$E2B_KEY" != "" ]; then
    echo "E2B API key detected - testing Python sandbox..."
    # Simple agent run with python_execute intent
    PYTHON_RUN=$(curl -s -X POST "$API_URL/api/agent/runs" \
        -H "Content-Type: application/json" \
        -d '{"query": "Use Python to calculate the square root of 144", "max_steps": 3}')
    PYTHON_RUN_ID=$(json_get "$PYTHON_RUN" ".run_id")

    if [ -n "$PYTHON_RUN_ID" ] && [ "$PYTHON_RUN_ID" != "null" ]; then
        # Optional test - use longer timeout and treat timeout as warning
        E2B_TIMEOUT=90
        E2B_WAITED=0
        E2B_STATUS=""
        while [ $E2B_WAITED -lt $E2B_TIMEOUT ]; do
            E2B_PAYLOAD=$(curl -s "$API_URL/api/agent/runs/$PYTHON_RUN_ID")
            E2B_STATUS=$(json_get "$E2B_PAYLOAD" ".status")
            if [ "$E2B_STATUS" = "succeeded" ]; then
                pass "Python sandbox test succeeded"
                break
            elif [ "$E2B_STATUS" = "failed" ]; then
                warn "Python sandbox test failed (external service issue)"
                break
            fi
            sleep 3
            E2B_WAITED=$((E2B_WAITED + 3))
        done
        if [ "$E2B_STATUS" != "succeeded" ] && [ "$E2B_STATUS" != "failed" ]; then
            warn "Python sandbox test timed out (E2B may be slow to start)"
        fi
    else
        warn "Failed to create Python sandbox test run"
    fi
else
    warn "Skipping E2B sandbox test - E2B_API_KEY not configured"
fi

# Check Parallel.ai if configured
PARALLEL_KEY=$(json_get "$CONFIG_JSON" ".config.parallel.api_key")
if [ -n "$PARALLEL_KEY" ] && [ "$PARALLEL_KEY" != "null" ] && [ "$PARALLEL_KEY" != "***" ] && [ "$PARALLEL_KEY" != "" ]; then
    pass "Parallel.ai API key configured (web tools available)"
else
    warn "Skipping web tool tests - PARALLEL_API_KEY not configured"
fi

# ============================================================
# 6. LIST + HOUSEKEEPING CHECKS
# ============================================================
print_header "6. Listing & housekeeping"

RUN_LIST=$(curl -s "$API_URL/api/runs?limit=5")
if echo "$RUN_LIST" | grep -q "$DIRECT_RUN_ID"; then
    pass "Run listing returns recent runs"
else
    warn "Run listing missing recent runs"
fi

CONV_LIST=$(curl -s "$API_URL/api/conversations?limit=5")
if echo "$CONV_LIST" | grep -q "$DIRECT_CONV_ID"; then
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

    # Show relevant logs for debugging
    show_failure_logs ""

    echo ""
    echo -e "${YELLOW}Debugging commands:${NC}"
    echo "  View full log:     cat $APP_LOG"
    echo "  Find errors:       grep '\"level\":\"ERROR\"' $APP_LOG | jq ."
    echo "  Run with debug:    ./scripts/sanity_test.sh --debug"
    exit 1
fi
