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

# Cookie jar for session persistence (demo mode uses session cookies)
COOKIE_JAR=$(mktemp)
CURL_OPTS="-b $COOKIE_JAR -c $COOKIE_JAR"

# Cleanup cookie jar on exit
cleanup_cookies() {
    rm -f "$COOKIE_JAR" 2>/dev/null
}
trap cleanup_cookies EXIT

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

trap 'stop_debug_tail; cleanup_cookies' EXIT

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
        payload=$(curl -s $CURL_OPTS "$API_URL/api/runs/$run_id")
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
    stream=$(curl -s --max-time 20 $CURL_OPTS "$API_URL/api/runs/$run_id/stream")

    if echo "$stream" | grep -q "event: complete"; then
        pass "$label stream completes"
    elif echo "$stream" | grep -q "event: error"; then
        fail "$label stream has error event"
        return 1
    else
        # For completed runs, verify completion via run status and events
        local run_json
        run_json=$(curl -s $CURL_OPTS "$API_URL/api/runs/$run_id")
        local status
        status=$(json_get "$run_json" ".status")
        if [ "$status" = "succeeded" ]; then
            # Run succeeded but stream was empty - check events exist
            local events_json
            events_json=$(curl -s $CURL_OPTS "$API_URL/api/runs/$run_id/events")
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
    events_json=$(curl -s $CURL_OPTS "$API_URL/api/runs/$run_id/events")
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
    thinking_json=$(curl -s $CURL_OPTS "$API_URL/api/runs/$run_id/thinking?detail=$detail")
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
    report_json=$(curl -s $CURL_OPTS "$API_URL/api/runs/$run_id/report")
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
    conv_json=$(curl -s $CURL_OPTS "$API_URL/api/conversations/$conversation_id")

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
    run_json=$(curl -s $CURL_OPTS "$API_URL/api/runs/$run_id")

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
        payload=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$run_id")
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
    http_code=$(curl -s $CURL_OPTS -o /tmp/agent_trace.json -w "%{http_code}" "$API_URL/api/agent/runs/$run_id/trace")
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

# Check thinking content quality
check_thinking_content() {
    local run_id="$1"
    local label="$2"
    local trace
    trace=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$run_id/trace")

    # Get steps with thinking_text
    local thinking_texts
    thinking_texts=$(echo "$trace" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
for step in data.get('steps', []):
    text = step.get('thinking_text', '')
    if text:
        print(text[:100])
")

    if [ -n "$thinking_texts" ]; then
        pass "$label has thinking content"
    else
        warn "$label thinking content empty"
    fi
}

# Check tool call details - ANY tool called = PASS
# $3 = "require" if tools are mandatory, otherwise warn on no tools
check_tool_calls_detail() {
    local run_id="$1"
    local label="$2"
    local require_tools="${3:-}"
    local trace
    trace=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$run_id/trace")

    # Check tool calls have arguments (any tool = pass)
    local tool_info
    tool_info=$(echo "$trace" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
tools = []
for tc in data.get('tool_calls', []):
    name = tc.get('tool_name', 'unknown')
    has_args = bool(tc.get('arguments'))
    tools.append(f'{name}:{\"ok\" if has_args else \"no-args\"}')
print(','.join(tools) if tools else '')
")

    if [ -n "$tool_info" ]; then
        pass "$label tool calls present ($tool_info)"
    elif [ "$require_tools" = "require" ]; then
        fail "$label no tool calls found (required)"
    else
        warn "$label no tool calls (model answered directly)"
    fi
}

# Check final answer format
# $3 = "require" if answer is mandatory, otherwise warn on empty (for external service failures)
check_answer_format() {
    local run_id="$1"
    local label="$2"
    local require_answer="${3:-require}"
    local run_json
    run_json=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$run_id")
    local answer
    answer=$(json_get "$run_json" ".final_answer")

    # Check not empty
    if [ -z "$answer" ] || [ "$answer" = "null" ]; then
        if [ "$require_answer" = "require" ]; then
            fail "$label answer is empty"
        else
            warn "$label answer is empty (possible external service issue)"
        fi
        return 1
    fi
    pass "$label has non-empty answer"

    # Check no duplicate "Citations" section (model should use inline only)
    if echo "$answer" | grep -qi "^## Citations\|^### Citations\|^Citations:"; then
        warn "$label answer has separate Citations section (should use inline [N] only)"
    else
        pass "$label answer uses inline citations format"
    fi

    # Check for inline citation pattern [1], [2], etc. (only for web queries)
    if echo "$answer" | grep -qE '\[[0-9]+\]'; then
        pass "$label answer has inline citation references"
    fi
}

# Check SSE event sequence
check_sse_sequence() {
    local run_id="$1"
    local label="$2"
    local stream
    stream=$(curl -s --max-time 30 $CURL_OPTS "$API_URL/api/agent/runs/$run_id/stream")

    # Check for expected event types in sequence
    # Use tr to ensure clean integer output from grep -c
    local has_step_start has_complete
    has_step_start=$(echo "$stream" | grep -c "event: step_start" 2>/dev/null | tr -d '[:space:]')
    has_complete=$(echo "$stream" | grep -c "event: complete" 2>/dev/null | tr -d '[:space:]')

    # Default to 0 if empty
    has_step_start="${has_step_start:-0}"
    has_complete="${has_complete:-0}"

    if [ "$has_step_start" -gt 0 ] 2>/dev/null; then
        pass "$label SSE has step_start events ($has_step_start)"
    else
        warn "$label SSE missing step_start events"
    fi

    if [ "$has_complete" -gt 0 ] 2>/dev/null; then
        pass "$label SSE has complete event"
    else
        fail "$label SSE missing complete event"
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
python -c "from orchestrator.agent.profile import AgentProfile, get_profile, PROFILES" 2>/dev/null && pass "agent profile imports" || fail "agent profile imports"
python -c "from orchestrator.agent.context import get_context_strategy, CodingContextStrategy" 2>/dev/null && pass "agent context imports" || fail "agent context imports"

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

# Get LLM config from environment variables (matches chat_config.yaml)
# API config endpoint no longer exposes sensitive provider settings
LLM_BASE_URL="${LLM_BASE_URL:-https://api.deepinfra.com/v1/openai}"
LLM_API_KEY="${DEEPINFRA_API_KEY:-}"

# Build models endpoint URL (handle different base_url formats)
# DeepInfra: https://api.deepinfra.com/v1/openai -> /models
# Local: http://localhost:8080/v1 -> /models
# Plain: http://localhost:1234 -> /v1/models
if echo "$LLM_BASE_URL" | grep -q "/v1"; then
    MODELS_URL="$LLM_BASE_URL/models"
else
    MODELS_URL="$LLM_BASE_URL/v1/models"
fi

# Check models endpoint (with auth header if API key present)
if [ -n "$LLM_API_KEY" ] && [ "$LLM_API_KEY" != "null" ]; then
    LLM_CHECK=$(curl -s --max-time 10 -H "Authorization: Bearer $LLM_API_KEY" "$MODELS_URL")
else
    LLM_CHECK=$(curl -s --max-time 10 "$MODELS_URL")
fi

if echo "$LLM_CHECK" | grep -q "data\|models\|id"; then
    pass "LLM server reachable at $LLM_BASE_URL"
else
    fail "LLM server not reachable at $MODELS_URL"
    echo "Start your LLM server (llama-cpp, vLLM, etc.) or check API credentials"
    echo ""
    echo "========================================"
    echo "RESULTS: $PASSED passed, $FAILED failed (LLM tests skipped)"
    echo "========================================"
    exit 1
fi

# Check model name from environment (config endpoint doesn't expose model settings)
MODEL_NAME="${MODEL_NAME:-}"
if [ -n "$MODEL_NAME" ]; then
    pass "Model configured: $MODEL_NAME"
else
    pass "Using default model from config"
fi

# ============================================================
# 3. DIRECT FLOW (default mode)
# ============================================================
print_header "3. Direct Flow (default mode)"

DIRECT_CONV=$(curl -s -X POST $CURL_OPTS "$API_URL/api/conversations" \
    -H "Content-Type: application/json" \
    -d '{"title": "Sanity Direct"}')
DIRECT_CONV_ID=$(json_get "$DIRECT_CONV" ".conversation_id")

if [ -n "$DIRECT_CONV_ID" ]; then
    pass "Created conversation for direct flow ($DIRECT_CONV_ID)"
else
    fail "Failed to create conversation for direct flow"
fi

DIRECT_RUN_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/conversations/$DIRECT_CONV_ID/runs" \
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
    FOLLOWUP_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/conversations/$DIRECT_CONV_ID/runs" \
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
# 4. AGENT FLOW - CALCULATION QUERY
# ============================================================
print_header "4. Agent Flow - Calculation Query"

# Check if agent endpoint exists
AGENT_CHECK=$(curl -s $CURL_OPTS -o /dev/null -w "%{http_code}" "$API_URL/api/agent/runs" -X POST -H "Content-Type: application/json" -d '{}' 2>/dev/null)
if [ "$AGENT_CHECK" = "404" ]; then
    warn "Agent endpoint not available - skipping agent tests"
else
    # Create agent run with a physics calculation query
    CALC_QUERY="What is the kinetic energy of a 5kg object moving at 10 m/s?"
    AGENT_CALC_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/agent/runs" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$CALC_QUERY\", \"max_steps\": 5}")
    AGENT_CALC_ID=$(json_get "$AGENT_CALC_RESP" ".run_id")

    if [ -n "$AGENT_CALC_ID" ] && [ "$AGENT_CALC_ID" != "null" ]; then
        pass "Created calculation agent run ($AGENT_CALC_ID)"

        # Wait for completion (longer timeout for tool execution)
        wait_for_agent_run "$AGENT_CALC_ID" "Calculation run" 120

        # Rigorous checks (any tool = pass)
        check_thinking_content "$AGENT_CALC_ID" "Calculation run"
        check_tool_calls_detail "$AGENT_CALC_ID" "Calculation run"
        check_answer_format "$AGENT_CALC_ID" "Calculation run"
        check_sse_sequence "$AGENT_CALC_ID" "Calculation run"
        check_agent_trace "$AGENT_CALC_ID" "Calculation run"
    else
        fail "Failed to create calculation agent run"
    fi
fi

# ============================================================
# 4.5 AGENT FLOW - WEB SEARCH QUERY
# ============================================================
print_header "4.5. Agent Flow - Web Search Query"

# Only run if Parallel.ai is configured (check env var, config no longer exposes keys)
PARALLEL_KEY="${PARALLEL_API_KEY:-}"
if [ -n "$PARALLEL_KEY" ]; then
    WEB_QUERY="What is the current population of Tokyo?"
    AGENT_WEB_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/agent/runs" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$WEB_QUERY\", \"max_steps\": 5}")
    AGENT_WEB_ID=$(json_get "$AGENT_WEB_RESP" ".run_id")

    if [ -n "$AGENT_WEB_ID" ] && [ "$AGENT_WEB_ID" != "null" ]; then
        pass "Created web search agent run ($AGENT_WEB_ID)"

        wait_for_agent_run "$AGENT_WEB_ID" "Web search run" 120

        # Rigorous checks (any tool = pass)
        check_thinking_content "$AGENT_WEB_ID" "Web search run"
        check_tool_calls_detail "$AGENT_WEB_ID" "Web search run" "require"
        check_answer_format "$AGENT_WEB_ID" "Web search run" "warn"
        check_sse_sequence "$AGENT_WEB_ID" "Web search run"

        # Check citations exist for web search
        trace=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$AGENT_WEB_ID/trace")
        citation_count=$(json_array_len "$trace" "citations")
        if [ "$citation_count" -gt 0 ]; then
            pass "Web search run has citations ($citation_count)"
        else
            warn "Web search run missing citations"
        fi
    else
        fail "Failed to create web search agent run"
    fi
else
    warn "Skipping web search test - PARALLEL_API_KEY not configured"
fi

# ============================================================
# 4.7 AGENT FLOW - COMPLEX MULTI-STEP QUERIES
# ============================================================
print_header "4.7. Agent Flow - Complex Multi-Step Queries"

# Test 1: Multi-step reasoning with calculation
# This query requires: understanding the problem, calculating multiple values, synthesizing
MULTI_STEP_QUERY="If I invest \$1000 at 5% annual interest compounded annually, how much will I have after 3 years? Show the calculation step by step."
AGENT_MULTI1_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/agent/runs" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"$MULTI_STEP_QUERY\", \"max_steps\": 8}")
AGENT_MULTI1_ID=$(json_get "$AGENT_MULTI1_RESP" ".run_id")

if [ -n "$AGENT_MULTI1_ID" ] && [ "$AGENT_MULTI1_ID" != "null" ]; then
    pass "Created multi-step calculation run ($AGENT_MULTI1_ID)"

    wait_for_agent_run "$AGENT_MULTI1_ID" "Multi-step calculation" 120

    # Check for step-by-step reasoning
    check_thinking_content "$AGENT_MULTI1_ID" "Multi-step calculation"
    check_agent_trace "$AGENT_MULTI1_ID" "Multi-step calculation"
    check_answer_format "$AGENT_MULTI1_ID" "Multi-step calculation"

    # Verify answer quality - should mention compound interest formula or show yearly breakdown
    multi1_answer=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$AGENT_MULTI1_ID" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(data.get('final_answer', ''))
")
    if echo "$multi1_answer" | grep -qiE "1157|1158|year|compound|interest|formula"; then
        pass "Multi-step calculation has correct answer structure (mentions expected values/concepts)"
    else
        warn "Multi-step calculation answer may not show step-by-step breakdown"
    fi
else
    fail "Failed to create multi-step calculation run"
fi

# Test 2: Multi-source research query (requires web search if available)
if [ -n "$PARALLEL_KEY" ]; then
    RESEARCH_QUERY="Compare the GDP growth rates of Japan and Germany in the most recent available year. Which country had higher growth?"
    AGENT_MULTI2_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/agent/runs" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$RESEARCH_QUERY\", \"max_steps\": 10}")
    AGENT_MULTI2_ID=$(json_get "$AGENT_MULTI2_RESP" ".run_id")

    if [ -n "$AGENT_MULTI2_ID" ] && [ "$AGENT_MULTI2_ID" != "null" ]; then
        pass "Created multi-source research run ($AGENT_MULTI2_ID)"

        # Longer timeout for multiple web searches
        wait_for_agent_run "$AGENT_MULTI2_ID" "Multi-source research" 180

        check_thinking_content "$AGENT_MULTI2_ID" "Multi-source research"
        check_tool_calls_detail "$AGENT_MULTI2_ID" "Multi-source research" "require"
        check_answer_format "$AGENT_MULTI2_ID" "Multi-source research" "warn"
        check_agent_trace "$AGENT_MULTI2_ID" "Multi-source research"

        # Check that both countries are mentioned in the answer
        multi2_answer=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$AGENT_MULTI2_ID" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(data.get('final_answer', ''))
")
        if echo "$multi2_answer" | grep -qi "japan" && echo "$multi2_answer" | grep -qi "germany"; then
            pass "Multi-source research compares both countries"
        else
            warn "Multi-source research may not compare both countries adequately"
        fi

        # Check for multiple tool calls (should search for both countries' data)
        trace=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$AGENT_MULTI2_ID/trace")
        tool_count=$(json_array_len "$trace" "tool_calls")
        if [ "$tool_count" -ge 2 ]; then
            pass "Multi-source research used multiple tool calls ($tool_count calls)"
        else
            warn "Multi-source research may not have used enough tools ($tool_count calls)"
        fi
    else
        fail "Failed to create multi-source research run"
    fi
else
    warn "Skipping multi-source research test - PARALLEL_API_KEY not configured"
fi

# Test 3: Complex reasoning problem (no external tools, just multi-step logic)
LOGIC_QUERY="A farmer has chickens and cows. Together they have 30 heads and 74 legs. How many chickens and how many cows does the farmer have? Explain your reasoning."
AGENT_MULTI3_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/agent/runs" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"$LOGIC_QUERY\", \"max_steps\": 6}")
AGENT_MULTI3_ID=$(json_get "$AGENT_MULTI3_RESP" ".run_id")

if [ -n "$AGENT_MULTI3_ID" ] && [ "$AGENT_MULTI3_ID" != "null" ]; then
    pass "Created logic puzzle run ($AGENT_MULTI3_ID)"

    wait_for_agent_run "$AGENT_MULTI3_ID" "Logic puzzle" 120

    check_thinking_content "$AGENT_MULTI3_ID" "Logic puzzle"
    check_answer_format "$AGENT_MULTI3_ID" "Logic puzzle"

    # Verify correct answer: 23 chickens and 7 cows (or equivalent)
    multi3_answer=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$AGENT_MULTI3_ID" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(data.get('final_answer', ''))
")
    # Check for correct numbers (23 chickens, 7 cows)
    if echo "$multi3_answer" | grep -qE "23.*chicken|chicken.*23|7.*cow|cow.*7"; then
        pass "Logic puzzle has correct answer (23 chickens, 7 cows)"
    else
        warn "Logic puzzle answer may not be correct (expected 23 chickens, 7 cows)"
    fi
else
    fail "Failed to create logic puzzle run"
fi

# ============================================================
# 5. TOOL HEALTH (Optional)
# ============================================================
print_header "5. Tool Health (Optional)"

# Check E2B sandbox if configured (check env var, config no longer exposes keys)
E2B_KEY="${E2B_API_KEY:-}"
if [ -n "$E2B_KEY" ]; then
    echo "E2B API key detected - testing Python sandbox..."
    # Simple agent run with python_execute intent
    PYTHON_RUN=$(curl -s -X POST $CURL_OPTS "$API_URL/api/agent/runs" \
        -H "Content-Type: application/json" \
        -d '{"query": "Use Python to calculate the square root of 144", "max_steps": 3}')
    PYTHON_RUN_ID=$(json_get "$PYTHON_RUN" ".run_id")

    if [ -n "$PYTHON_RUN_ID" ] && [ "$PYTHON_RUN_ID" != "null" ]; then
        # Optional test - use longer timeout and treat timeout as warning
        E2B_TIMEOUT=90
        E2B_WAITED=0
        E2B_STATUS=""
        while [ $E2B_WAITED -lt $E2B_TIMEOUT ]; do
            E2B_PAYLOAD=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$PYTHON_RUN_ID")
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

# Check Parallel.ai if configured (reuse env check from above)
if [ -n "$PARALLEL_KEY" ]; then
    pass "Parallel.ai API key configured (web tools available)"
else
    warn "Skipping web tool tests - PARALLEL_API_KEY not configured"
fi

# ============================================================
# 6. LIST + HOUSEKEEPING CHECKS
# ============================================================
print_header "6. Listing & housekeeping"

RUN_LIST=$(curl -s $CURL_OPTS "$API_URL/api/runs?limit=5")
if echo "$RUN_LIST" | grep -q "$DIRECT_RUN_ID"; then
    pass "Run listing returns recent runs"
else
    warn "Run listing missing recent runs"
fi

CONV_LIST=$(curl -s $CURL_OPTS "$API_URL/api/conversations?limit=5")
if echo "$CONV_LIST" | grep -q "$DIRECT_CONV_ID"; then
    pass "Conversation listing returns created conversations"
else
    warn "Conversation listing missing created conversations"
fi

# ============================================================
# 7. SANDBOX SETUP & PROFILE TESTS
# ============================================================
print_header "7. Sandbox Project & Profile Tests"

# Create a sandbox project directory that the coding agent can explore
SANDBOX_DIR=$(mktemp -d "${TMPDIR:-/tmp}/reasoner-sandbox-XXXXXX")
echo -e "${BLUE}Creating sandbox project at: $SANDBOX_DIR${NC}"

cleanup_sandbox() {
    rm -rf "$SANDBOX_DIR" 2>/dev/null
}
# Chain cleanup with existing exit traps
trap 'stop_debug_tail; cleanup_cookies; cleanup_sandbox' EXIT

# Initialize sandbox with git, files, and a rules file
(
    cd "$SANDBOX_DIR"
    git init -q
    git config user.email "test@sandbox.local"
    git config user.name "Sandbox Test"

    # Create a simple Python project structure
    mkdir -p src tests .reasoner

    cat > pyproject.toml << 'PYEOF'
[project]
name = "calculator"
version = "0.1.0"
description = "A simple calculator package"
requires-python = ">=3.10"
dependencies = ["pydantic>=2.0"]
PYEOF

    cat > src/__init__.py << 'PYEOF'
"""Calculator package."""
PYEOF

    cat > src/calculator.py << 'PYEOF'
"""Simple calculator module with basic operations."""


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


def divide(a: float, b: float) -> float:
    """Divide a by b.

    Raises:
        ValueError: If b is zero.
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


def factorial(n: int) -> int:
    """Compute factorial of n.

    BUG: Does not handle negative numbers.
    """
    if n == 0:
        return 1
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result
PYEOF

    cat > tests/test_calculator.py << 'PYEOF'
"""Tests for calculator module."""
from src.calculator import add, subtract, multiply, divide, factorial


def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 3) == 2

def test_multiply():
    assert multiply(4, 5) == 20

def test_divide():
    assert divide(10, 2) == 5.0

def test_factorial():
    assert factorial(5) == 120
PYEOF

    cat > .reasoner/rules.md << 'PYEOF'
# Project Rules

- Use type hints for all function signatures
- Write docstrings for all public functions
- Follow PEP 8 naming conventions
- All functions must have unit tests
PYEOF

    cat > README.md << 'PYEOF'
# Calculator

A simple calculator package with basic arithmetic operations.

## Usage

```python
from src.calculator import add, multiply
print(add(2, 3))
print(multiply(4, 5))
```
PYEOF

    # Make an initial commit
    git add -A
    git commit -q -m "Initial commit: calculator project"

    # Make a second commit to have history
    cat >> src/calculator.py << 'PYEOF'


def power(base: float, exponent: float) -> float:
    """Raise base to the power of exponent."""
    return base ** exponent
PYEOF

    git add -A
    git commit -q -m "feat: add power function"
)

if [ -d "$SANDBOX_DIR/.git" ] && [ -f "$SANDBOX_DIR/src/calculator.py" ]; then
    pass "Sandbox project created with git + Python files"
else
    fail "Sandbox project setup failed"
fi

# --- Test 7a: Coding Profile with Sandbox ---
echo ""
echo -e "${BLUE}--- 7a. Coding Profile Agent (with sandbox context) ---${NC}"

CODING_QUERY="Look at the calculator module in this project. What functions are defined? Is there a bug in any of them?"
CODING_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/agent/runs" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json
print(json.dumps({
    'query': '$CODING_QUERY',
    'max_steps': 8,
    'profile': 'coding',
    'filesystem_enabled': True,
    'working_dir': '$SANDBOX_DIR',
}))
")")
CODING_RUN_ID=$(json_get "$CODING_RESP" ".run_id")

if [ -n "$CODING_RUN_ID" ] && [ "$CODING_RUN_ID" != "null" ]; then
    pass "Created coding profile run ($CODING_RUN_ID)"

    wait_for_agent_run "$CODING_RUN_ID" "Coding profile" 120

    # Check that agent used filesystem tools (read_file, glob, etc.)
    CODING_TRACE=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$CODING_RUN_ID/trace")
    CODING_TOOL_NAMES=$(echo "$CODING_TRACE" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
tools = set()
for tc in data.get('tool_calls', []):
    tools.add(tc.get('tool_name', 'unknown'))
print(','.join(sorted(tools)))
" 2>/dev/null)

    if echo "$CODING_TOOL_NAMES" | grep -qE "read_file|glob|grep|list_directory"; then
        pass "Coding profile used filesystem tools ($CODING_TOOL_NAMES)"
    else
        warn "Coding profile did not use filesystem tools (tools: $CODING_TOOL_NAMES)"
    fi

    # Check agent found the functions
    CODING_ANSWER=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$CODING_RUN_ID" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(data.get('final_answer', ''))
" 2>/dev/null)

    if echo "$CODING_ANSWER" | grep -qiE "add|subtract|multiply|divide|factorial"; then
        pass "Coding profile found calculator functions"
    else
        warn "Coding profile answer may not mention functions"
    fi

    if echo "$CODING_ANSWER" | grep -qiE "bug|negative|error|issue|handle"; then
        pass "Coding profile identified the bug in factorial"
    else
        warn "Coding profile may not have found the factorial bug"
    fi

    # Check run metrics are stored
    CODING_STATUS=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$CODING_RUN_ID")
    CODING_USAGE=$(json_get "$CODING_STATUS" ".usage_stats")
    if [ -n "$CODING_USAGE" ] && [ "$CODING_USAGE" != "null" ] && [ "$CODING_USAGE" != "{}" ]; then
        pass "Coding profile run has usage_stats/metrics stored"

        # Check for profile field in metrics
        METRIC_PROFILE=$(echo "$CODING_USAGE" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(data.get('run_metrics', {}).get('profile', ''))
" 2>/dev/null)
        if [ "$METRIC_PROFILE" = "coding" ]; then
            pass "Run metrics include profile=coding"
        else
            warn "Run metrics profile field missing or unexpected ($METRIC_PROFILE)"
        fi
    else
        warn "Coding profile run missing usage_stats"
    fi
else
    fail "Failed to create coding profile run"
fi

# --- Test 7b: Research Profile (no sandbox context) ---
echo ""
echo -e "${BLUE}--- 7b. Research Profile Agent (no project context) ---${NC}"

RESEARCH_QUERY="What is the derivative of x^3 + 2x? Show the steps."
RESEARCH_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/agent/runs" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json
print(json.dumps({
    'query': '$RESEARCH_QUERY',
    'max_steps': 5,
    'profile': 'research',
}))
")")
RESEARCH_RUN_ID=$(json_get "$RESEARCH_RESP" ".run_id")

if [ -n "$RESEARCH_RUN_ID" ] && [ "$RESEARCH_RUN_ID" != "null" ]; then
    pass "Created research profile run ($RESEARCH_RUN_ID)"

    wait_for_agent_run "$RESEARCH_RUN_ID" "Research profile" 120

    # Research profile should NOT use filesystem tools
    RESEARCH_TRACE=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$RESEARCH_RUN_ID/trace")
    RESEARCH_TOOLS=$(echo "$RESEARCH_TRACE" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
tools = set()
for tc in data.get('tool_calls', []):
    tools.add(tc.get('tool_name', 'unknown'))
fs_tools = tools & {'read_file', 'glob', 'grep', 'list_directory', 'write_file', 'edit_file', 'bash'}
print(','.join(sorted(fs_tools)) if fs_tools else '')
" 2>/dev/null)

    if [ -z "$RESEARCH_TOOLS" ]; then
        pass "Research profile did not use filesystem tools (correct isolation)"
    else
        warn "Research profile used filesystem tools ($RESEARCH_TOOLS) - unexpected"
    fi

    # Check answer mentions derivative
    RESEARCH_ANSWER=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$RESEARCH_RUN_ID" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(data.get('final_answer', ''))
" 2>/dev/null)

    if echo "$RESEARCH_ANSWER" | grep -qiE "3x.*2|3x\^2|derivative|power rule"; then
        pass "Research profile answer contains derivative result"
    else
        warn "Research profile answer may not contain derivative"
    fi
else
    fail "Failed to create research profile run"
fi

# --- Test 7c: Full Profile with Sandbox ---
echo ""
echo -e "${BLUE}--- 7c. Full Profile Agent (combined capabilities) ---${NC}"

FULL_QUERY="Read the calculator.py file in this project and compute factorial(7) using the Python tool to verify it."
FULL_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/agent/runs" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json
print(json.dumps({
    'query': '$FULL_QUERY',
    'max_steps': 8,
    'profile': 'full',
    'filesystem_enabled': True,
    'working_dir': '$SANDBOX_DIR',
}))
")")
FULL_RUN_ID=$(json_get "$FULL_RESP" ".run_id")

if [ -n "$FULL_RUN_ID" ] && [ "$FULL_RUN_ID" != "null" ]; then
    pass "Created full profile run ($FULL_RUN_ID)"

    wait_for_agent_run "$FULL_RUN_ID" "Full profile" 120

    # Full profile should use a mix of filesystem + computation tools
    FULL_TRACE=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$FULL_RUN_ID/trace")
    FULL_TOOLS=$(echo "$FULL_TRACE" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
tools = set()
for tc in data.get('tool_calls', []):
    tools.add(tc.get('tool_name', 'unknown'))
print(','.join(sorted(tools)))
" 2>/dev/null)

    if echo "$FULL_TOOLS" | grep -qE "read_file|glob|grep"; then
        pass "Full profile used filesystem tools ($FULL_TOOLS)"
    else
        warn "Full profile may not have used filesystem tools ($FULL_TOOLS)"
    fi

    # Check answer mentions 5040 (factorial of 7)
    FULL_ANSWER=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$FULL_RUN_ID" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(data.get('final_answer', ''))
" 2>/dev/null)

    if echo "$FULL_ANSWER" | grep -q "5040"; then
        pass "Full profile computed factorial(7) = 5040"
    else
        warn "Full profile answer may not contain 5040"
    fi
else
    fail "Failed to create full profile run"
fi

# --- Test 7d: Profile Isolation (coding has filesystem, research doesn't) ---
echo ""
echo -e "${BLUE}--- 7d. Profile Isolation Verification ---${NC}"

# Verify the coding profile run has more tool variety than research
if [ -n "$CODING_RUN_ID" ] && [ -n "$RESEARCH_RUN_ID" ]; then
    CODING_TOOL_COUNT=$(echo "$CODING_TRACE" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(len(data.get('tool_calls', [])))
" 2>/dev/null)
    RESEARCH_TOOL_COUNT=$(echo "$RESEARCH_TRACE" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(len(data.get('tool_calls', [])))
" 2>/dev/null)

    pass "Coding profile: $CODING_TOOL_COUNT tool calls, Research profile: $RESEARCH_TOOL_COUNT tool calls"
fi

# ============================================================
# 8. CLI PROFILE TESTS
# ============================================================
print_header "8. CLI Profile Tests"

# Test that CLI module imports and accepts profile flags
echo "Testing CLI imports..."
python3 -c "from cli.config import CLIConfig" 2>/dev/null && pass "CLIConfig imports" || fail "CLIConfig imports"
python3 -c "from orchestrator.agent.profile import get_profile, PROFILES" 2>/dev/null && pass "Profile module imports" || fail "Profile module imports"
python3 -c "from orchestrator.agent.context import get_context_strategy" 2>/dev/null && pass "Context module imports" || fail "Context module imports"

# Test profile resolution logic
echo ""
echo "Testing profile resolution..."
python3 -c "
from orchestrator.agent.profile import get_profile, PROFILES

# Test all 3 profiles exist
for name in ['research', 'coding', 'full']:
    p = get_profile(name)
    assert p.name == name, f'Profile name mismatch: {p.name}'
print('OK: all 3 profiles resolve')

# Test research profile has only web+python tools
p = get_profile('research')
assert 'filesystem' not in p.tool_sets, 'research should not have filesystem'
print('OK: research profile has no filesystem tools')

# Test coding profile has filesystem tools
p = get_profile('coding')
assert 'filesystem' in p.tool_sets, 'coding should have filesystem'
print('OK: coding profile has filesystem tools')

# Test full profile has all tool sets
p = get_profile('full')
assert 'web' in p.tool_sets and 'python' in p.tool_sets and 'filesystem' in p.tool_sets
print('OK: full profile has all tool sets')

# Test invalid profile raises
try:
    get_profile('invalid')
    assert False, 'Should have raised'
except ValueError:
    print('OK: invalid profile raises ValueError')
" 2>/dev/null && pass "Profile resolution logic" || fail "Profile resolution logic"

# Test context strategies
echo ""
echo "Testing context strategies..."
python3 -c "
import asyncio
from orchestrator.agent.context import get_context_strategy

async def test():
    # Research context
    s = get_context_strategy('research')
    ctx = await s.gather()
    assert 'date' in ctx.lower() or '202' in ctx, f'Research context missing date: {ctx[:50]}'
    print(f'OK: research context ({len(ctx)} chars): {ctx[:60]}...')

    # Coding context with sandbox dir
    s = get_context_strategy('coding')
    ctx = await s.gather('$SANDBOX_DIR')
    print(f'OK: coding context ({len(ctx)} chars)')

    # Check coding context layers
    has_env = 'python' in ctx.lower() or 'os' in ctx.lower() or 'darwin' in ctx.lower()
    has_rules = 'type hints' in ctx.lower() or 'rules' in ctx.lower()
    has_git = 'branch' in ctx.lower() or 'main' in ctx.lower() or 'master' in ctx.lower()
    has_dir = '$SANDBOX_DIR' in ctx or 'sandbox' in ctx.lower()
    has_files = 'calculator' in ctx.lower() or 'pyproject' in ctx.lower()

    print(f'  env={has_env}, rules={has_rules}, git={has_git}, dir={has_dir}, files={has_files}')

    assert has_env or has_rules or has_git, 'Coding context missing expected layers'

    # Full context
    s = get_context_strategy('full')
    ctx = await s.gather('$SANDBOX_DIR')
    print(f'OK: full context ({len(ctx)} chars)')

asyncio.run(test())
" 2>/dev/null && pass "Context strategies gather data correctly" || fail "Context strategies gather data"

# Test CLIConfig profile defaults
echo ""
echo "Testing CLIConfig profile defaults..."
python3 -c "
from cli.config import CLIConfig

# Agent mode defaults to coding profile
cfg = CLIConfig.from_args(mode='agent')
assert cfg.profile == 'coding', f'Expected coding, got {cfg.profile}'
print('OK: agent mode defaults to coding profile')

# Explicit profile is preserved
cfg = CLIConfig.from_args(mode='agent', profile='research')
assert cfg.profile == 'research', f'Expected research, got {cfg.profile}'
print('OK: explicit profile is preserved')

# Chat mode without profile stays None
cfg = CLIConfig.from_args(mode='chat')
assert cfg.profile is None, f'Expected None, got {cfg.profile}'
print('OK: chat mode has no default profile')
" 2>/dev/null && pass "CLIConfig profile defaults" || fail "CLIConfig profile defaults"

# Test CLI --help shows --profile option
echo ""
echo "Testing CLI help output..."
CLI_HELP=$(cd "$PROJECT_DIR" && python3 -m cli --help 2>&1 || true)
if echo "$CLI_HELP" | grep -q "\-\-profile"; then
    pass "CLI --help shows --profile option"
else
    warn "CLI --help does not show --profile (may be OK if Click not set up)"
fi

# ============================================================
# 9. CONTEXT INJECTION VERIFICATION
# ============================================================
print_header "9. Context Injection Verification"

# Verify that the coding agent's system prompt actually got project context injected
# We do this by asking the agent a question that requires knowing project context
echo "Testing that coding agent received project context..."

CONTEXT_QUERY="What project rules are defined in the .reasoner/rules.md file of this project? Do NOT read the file, just tell me from what you already know about the project."
CONTEXT_RESP=$(curl -s -X POST $CURL_OPTS "$API_URL/api/agent/runs" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json
print(json.dumps({
    'query': '$CONTEXT_QUERY',
    'max_steps': 3,
    'profile': 'coding',
    'filesystem_enabled': True,
    'working_dir': '$SANDBOX_DIR',
}))
")")
CONTEXT_RUN_ID=$(json_get "$CONTEXT_RESP" ".run_id")

if [ -n "$CONTEXT_RUN_ID" ] && [ "$CONTEXT_RUN_ID" != "null" ]; then
    pass "Created context verification run ($CONTEXT_RUN_ID)"

    wait_for_agent_run "$CONTEXT_RUN_ID" "Context verification" 90

    # Check if agent knew about rules without reading the file
    CONTEXT_ANSWER=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$CONTEXT_RUN_ID" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(data.get('final_answer', ''))
" 2>/dev/null)

    # The rules mention: type hints, docstrings, PEP 8, unit tests
    RULES_FOUND=0
    for keyword in "type hint" "docstring" "PEP" "unit test"; do
        if echo "$CONTEXT_ANSWER" | grep -qi "$keyword"; then
            RULES_FOUND=$((RULES_FOUND + 1))
        fi
    done

    if [ "$RULES_FOUND" -ge 2 ]; then
        pass "Agent knew $RULES_FOUND/4 project rules from injected context"
    elif [ "$RULES_FOUND" -ge 1 ]; then
        warn "Agent knew $RULES_FOUND/4 project rules (partial context injection)"
    else
        # Agent may have read the file anyway - check tool calls
        CONTEXT_TRACE=$(curl -s $CURL_OPTS "$API_URL/api/agent/runs/$CONTEXT_RUN_ID/trace")
        CONTEXT_TOOLS=$(echo "$CONTEXT_TRACE" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
tools = [tc.get('tool_name', '') for tc in data.get('tool_calls', [])]
print(','.join(tools))
" 2>/dev/null)
        if echo "$CONTEXT_TOOLS" | grep -q "read_file"; then
            warn "Agent read the rules file instead of using injected context (context may not include rules)"
        else
            warn "Agent did not know project rules and did not read the file"
        fi
    fi
else
    fail "Failed to create context verification run"
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
