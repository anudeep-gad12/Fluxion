#!/bin/bash
# Browser coding smoke test for Fluxion
# Run: ./scripts/sanity_test.sh [--debug]
# Requires: API server running on port 9000 (or override API_URL)

set -u

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

API_URL="${API_URL:-http://localhost:9000}"
SANITY_MODEL="${SANITY_MODEL:-accounts/fireworks/models/minimax-m2p7}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
APP_LOG="$LOG_DIR/app.log"

COOKIE_JAR=$(mktemp)
CURL_OPTS=(-s -b "$COOKIE_JAR" -c "$COOKIE_JAR")
RUN_HEADERS=(-H "Content-Type: application/json")
if [ -n "$SANITY_MODEL" ]; then
    RUN_HEADERS+=(-H "x-model: $SANITY_MODEL")
fi

PASSED=0
FAILED=0
DEBUG_MODE=false
TAIL_PID=""
SANDBOX_DIR=""
LAST_RUN_PAYLOAD=""

if [ "${1:-}" = "--debug" ]; then
    DEBUG_MODE=true
    shift
fi

cleanup() {
    if [ -n "$TAIL_PID" ]; then
        kill -- -"$TAIL_PID" 2>/dev/null || kill "$TAIL_PID" 2>/dev/null || true
        pkill -f "tail -f $APP_LOG" 2>/dev/null || true
        wait "$TAIL_PID" 2>/dev/null || true
    fi
    rm -f "$COOKIE_JAR" 2>/dev/null || true
    if [ -n "$SANDBOX_DIR" ]; then
        rm -rf "$SANDBOX_DIR" 2>/dev/null || true
    fi
}
trap cleanup EXIT

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

json_get() {
    local json="$1"
    local path="$2"
    if command -v jq >/dev/null 2>&1; then
        echo "$json" | jq -r "$path // empty" 2>/dev/null
    else
        echo "$json" | python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read() or '{}')
    cur = data
    for part in '$path'.lstrip('.').split('.'):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = None
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
    print(len(arr) if isinstance(arr, list) else 0)
except Exception:
    print(0)
"
}

clear_logs() {
    mkdir -p "$LOG_DIR"
    : > "$APP_LOG"
}

start_debug_tail() {
    if [ "$DEBUG_MODE" != true ]; then
        return
    fi
    echo -e "${YELLOW}Starting app log tail...${NC}"
    (
        exec tail -f "$APP_LOG" 2>/dev/null | while read -r line; do
            echo "$line" | python3 -c "
import json, sys
for raw in sys.stdin:
    try:
        event = json.loads(raw)
        ts = str(event.get('timestamp', ''))[-12:-7]
        level = str(event.get('level', ''))[:4]
        msg = str(event.get('message', ''))[:70]
        print(f'  [{ts}] {level}: {msg}')
    except Exception:
        pass
"
        done
    ) &
    TAIL_PID=$!
}

show_failure_logs() {
    echo ""
    echo -e "${BLUE}=== Recent Errors / Warnings ===${NC}"
    if [ -f "$APP_LOG" ]; then
        grep '"level":"ERROR"\|"level":"WARNING"' "$APP_LOG" 2>/dev/null | tail -20 || true
    fi
}

wait_for_agent_run() {
    local run_id="$1"
    local label="$2"
    local timeout="${3:-180}"
    local waited=0

    while [ "$waited" -lt "$timeout" ]; do
        local payload
        payload=$(curl "${CURL_OPTS[@]}" "$API_URL/api/agent/runs/$run_id")
        local status
        status=$(json_get "$payload" ".status")

        if [ "$status" = "succeeded" ]; then
            pass "$label succeeded ($run_id)"
            local answer
            answer=$(json_get "$payload" ".final_answer")
            LAST_RUN_PAYLOAD="$payload"
            if [ -n "$answer" ]; then
                pass "$label has final answer"
            else
                fail "$label missing final answer"
            fi
            return 0
        fi

        if [ "$status" = "failed" ]; then
            local error
            error=$(json_get "$payload" ".error_message")
            LAST_RUN_PAYLOAD="$payload"
            fail "$label failed: ${error:-unknown error}"
            return 1
        fi

        sleep 3
        waited=$((waited + 3))
    done

    LAST_RUN_PAYLOAD=$(curl "${CURL_OPTS[@]}" "$API_URL/api/agent/runs/$run_id")
    fail "$label timed out after ${timeout}s"
    return 1
}

create_sandbox_project() {
    SANDBOX_DIR=$(mktemp -d "${TMPDIR:-/tmp}/fluxion-sanity-XXXXXX")
    mkdir -p "$SANDBOX_DIR/tests"

    cat > "$SANDBOX_DIR/calculator.py" <<'PYEOF'
"""Simple calculator helpers."""


def factorial(n: int) -> int:
    """Return factorial of n."""
    if n == 0:
        return 1
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result
PYEOF

    cat > "$SANDBOX_DIR/tests/test_calculator.py" <<'PYEOF'
import unittest

from calculator import factorial


class CalculatorTests(unittest.TestCase):
    def test_factorial_positive(self) -> None:
        self.assertEqual(factorial(5), 120)


if __name__ == "__main__":
    unittest.main()
PYEOF

    cat > "$SANDBOX_DIR/README.md" <<'MDEOF'
# Calculator sandbox

This repo is used by the Fluxion sanity test.
MDEOF

    (
        cd "$SANDBOX_DIR" || exit 1
        git init -q
        git config user.email "sanity@test.local"
        git config user.name "Fluxion Sanity"
        git add .
        git commit -q -m "Initial sandbox"
    )
}

tool_names_from_trace() {
    local trace_json="$1"
    echo "$trace_json" | python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read() or '{}')
    names = [tc.get('tool_name', '') for tc in data.get('tool_calls', [])]
    print(','.join(name for name in names if name))
except Exception:
    print('')
"
}

print_header "1. Setup"
cd "$PROJECT_DIR"
clear_logs
start_debug_tail
create_sandbox_project

if [ -f "$SANDBOX_DIR/calculator.py" ] && [ -f "$SANDBOX_DIR/tests/test_calculator.py" ]; then
    pass "Created temporary coding workspace at $SANDBOX_DIR"
else
    fail "Failed to create temporary coding workspace"
fi

print_header "2. API Health"
if curl -s --max-time 3 "$API_URL/api/health" >/dev/null 2>&1; then
    pass "API health endpoint reachable"
else
    fail "API health check failed at $API_URL"
    echo "Start server with: ./dev.sh start"
    echo ""
    echo "RESULTS: $PASSED passed, $FAILED failed"
    exit 1
fi

print_header "3. Create workspace-bound conversation"
CONV_RESP=$(curl "${CURL_OPTS[@]}" -X POST "$API_URL/api/conversations" \
    -H "Content-Type: application/json" \
    -d "{\"title\":\"Sanity Coding Smoke\",\"workspace_path\":\"$SANDBOX_DIR\"}")
CONV_ID=$(json_get "$CONV_RESP" ".conversation_id")

if [ -n "$CONV_ID" ]; then
    pass "Created conversation ($CONV_ID)"
else
    fail "Failed to create workspace-bound conversation"
fi

print_header "4. Coding run: inspect, fix, verify"
CODING_QUERY="Fix calculator.py so factorial rejects negative inputs by raising ValueError. Add a regression test in tests/test_calculator.py and run python -m unittest -q."
RUN1_RESP=$(curl "${CURL_OPTS[@]}" -X POST "$API_URL/api/agent/runs" \
    "${RUN_HEADERS[@]}" \
    -d "{\"query\":\"$CODING_QUERY\",\"conversation_id\":\"$CONV_ID\",\"profile\":\"coding\",\"filesystem_enabled\":true,\"working_dir\":\"$SANDBOX_DIR\",\"permission_policy\":\"yolo\",\"max_steps\":12,\"capabilities\":{\"web\":true,\"filesystem\":true,\"bash\":true,\"python\":false}}")
RUN1_ID=$(json_get "$RUN1_RESP" ".run_id")

if [ -n "$RUN1_ID" ]; then
    pass "Created coding run ($RUN1_ID)"
else
    fail "Failed to create coding run"
fi

if [ -n "$RUN1_ID" ]; then
    wait_for_agent_run "$RUN1_ID" "Coding run" 240
fi
RUN1_STATUS_JSON="$LAST_RUN_PAYLOAD"
RUN1_STATUS=$(json_get "$RUN1_STATUS_JSON" ".status")

if (cd "$SANDBOX_DIR" && python3 -m unittest discover -s tests -q) >/tmp/fluxion-sanity-test.log 2>&1; then
    pass "Workspace tests pass after coding run"
else
    fail "Workspace tests still fail after coding run"
    cat /tmp/fluxion-sanity-test.log
fi

TRACE1_JSON=$(curl "${CURL_OPTS[@]}" "$API_URL/api/agent/runs/$RUN1_ID/trace")
TOOL_NAMES=$(tool_names_from_trace "$TRACE1_JSON")
if echo "$TOOL_NAMES" | grep -qE "read_file|grep|list_directory|glob"; then
    pass "Coding run used filesystem inspection tools ($TOOL_NAMES)"
else
    fail "Coding run did not use filesystem inspection tools (tools: ${TOOL_NAMES:-none})"
fi

if echo "$TOOL_NAMES" | grep -qE "apply_patch|edit_file|write_file"; then
    pass "Coding run used edit/write tool ($TOOL_NAMES)"
else
    fail "Coding run did not use edit/write tool (tools: ${TOOL_NAMES:-none})"
fi

TRACE1_COMMAND_STATUS=$(echo "$TRACE1_JSON" | python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read() or '{}')
    calls = [
        tc for tc in data.get('tool_calls', [])
        if tc.get('tool_name') in ('exec_command', 'bash')
    ]
    print(calls[-1].get('status', '') if calls else '')
except Exception:
    print('')
")
if echo "$TOOL_NAMES" | grep -qE "exec_command|bash" && [ "$TRACE1_COMMAND_STATUS" = "success" ]; then
    pass "Coding run used command verification successfully ($TOOL_NAMES)"
else
    fail "Coding run did not use successful command verification (tools: ${TOOL_NAMES:-none}, command_status=${TRACE1_COMMAND_STATUS:-missing})"
fi

RUN1_STORED_CONTEXT=$(json_get "$RUN1_STATUS_JSON" ".stored_context")
if [ -n "$RUN1_STORED_CONTEXT" ] && [ "$RUN1_STORED_CONTEXT" != "null" ] && [ "$RUN1_STORED_CONTEXT" != "{}" ]; then
    pass "Coding run stored context metrics are present"
else
    warn "Coding run stored context metrics missing"
fi

RUN1_ANSWER=$(json_get "$RUN1_STATUS_JSON" ".final_answer")
if echo "$RUN1_ANSWER" | grep -qiE "factorial|negative|ValueError"; then
    pass "Coding run answer mentions the bug/fix"
else
    warn "Coding run answer does not clearly mention factorial negative handling"
fi

if grep -q "raise ValueError" "$SANDBOX_DIR/calculator.py"; then
    pass "calculator.py now raises ValueError for negative input"
else
    fail "calculator.py was not updated with negative-input guard"
fi

if grep -q "negative" "$SANDBOX_DIR/tests/test_calculator.py"; then
    pass "Regression test for negative input was added"
else
    fail "Regression test for negative input is missing"
fi

if PYTHONPATH="$SANDBOX_DIR" python3 - <<PYEOF >/tmp/fluxion-sanity-factorial.log 2>&1
from calculator import factorial
try:
    factorial(-1)
except ValueError:
    raise SystemExit(0)
raise SystemExit(1)
PYEOF
then
    pass "factorial(-1) now raises ValueError"
else
    fail "factorial(-1) still does not raise ValueError"
    cat /tmp/fluxion-sanity-factorial.log
fi

print_header "5. Follow-up run: conversation continuity"
if [ "$RUN1_STATUS" != "succeeded" ]; then
    warn "Skipping continuity run because the main coding run did not succeed"
else
    RUN2_QUERY="From this conversation context, what bug did you just fix and which test now covers it? Keep it short."
    RUN2_RESP=$(curl "${CURL_OPTS[@]}" -X POST "$API_URL/api/agent/runs" \
        "${RUN_HEADERS[@]}" \
        -d "{\"query\":\"$RUN2_QUERY\",\"conversation_id\":\"$CONV_ID\",\"profile\":\"coding\",\"filesystem_enabled\":true,\"working_dir\":\"$SANDBOX_DIR\",\"permission_policy\":\"yolo\",\"max_steps\":6,\"capabilities\":{\"web\":true,\"filesystem\":true,\"bash\":true,\"python\":false}}")
    RUN2_ID=$(json_get "$RUN2_RESP" ".run_id")

    if [ -n "$RUN2_ID" ]; then
        pass "Created continuity run ($RUN2_ID)"
    else
        fail "Failed to create continuity run"
    fi

    if [ -n "$RUN2_ID" ]; then
        wait_for_agent_run "$RUN2_ID" "Continuity run" 180
    fi
    RUN2_STATUS_JSON="$LAST_RUN_PAYLOAD"

    RUN2_ANSWER=$(json_get "$RUN2_STATUS_JSON" ".final_answer")
    if echo "$RUN2_ANSWER" | grep -qiE "factorial|negative|ValueError"; then
        pass "Continuity answer remembers the earlier bug"
    else
        fail "Continuity answer lost the earlier bug context"
    fi

    if echo "$RUN2_ANSWER" | grep -qiE "test_calculator|negative"; then
        pass "Continuity answer remembers the regression test"
    else
        warn "Continuity answer does not clearly mention the regression test"
    fi

    RUN2_STORED_CONTEXT=$(json_get "$RUN2_STATUS_JSON" ".stored_context")
    if [ -n "$RUN2_STORED_CONTEXT" ] && [ "$RUN2_STORED_CONTEXT" != "null" ] && [ "$RUN2_STORED_CONTEXT" != "{}" ]; then
        pass "Continuity run exposes stored context metrics"
    else
        warn "Continuity run stored context metrics missing"
    fi

    RUN2_CONTEXT_USAGE=$(json_get "$RUN2_STATUS_JSON" ".context_usage")
    if [ -n "$RUN2_CONTEXT_USAGE" ] && [ "$RUN2_CONTEXT_USAGE" != "null" ] && [ "$RUN2_CONTEXT_USAGE" != "{}" ]; then
        pass "Continuity run exposes context usage metrics"
    else
        warn "Continuity run context usage metrics missing"
    fi
fi

print_header "6. Conversation and listing checks"
CONV_DETAIL=$(curl "${CURL_OPTS[@]}" "$API_URL/api/conversations/$CONV_ID")
if echo "$CONV_DETAIL" | grep -q "$RUN1_ID" && { [ -z "${RUN2_ID:-}" ] || echo "$CONV_DETAIL" | grep -q "$RUN2_ID"; }; then
    pass "Conversation detail includes both coding runs"
else
    fail "Conversation detail missing one or both coding runs"
fi

RUN_LIST=$(curl "${CURL_OPTS[@]}" "$API_URL/api/runs?limit=10")
if echo "$RUN_LIST" | grep -q "$RUN1_ID"; then
    pass "Run listing includes the coding run"
else
    warn "Run listing does not include the coding run"
fi

print_header "RESULTS"
TOTAL=$((PASSED + FAILED))
echo "Passed: $PASSED / $TOTAL"
echo "Failed: $FAILED / $TOTAL"

if [ "$FAILED" -eq 0 ]; then
    echo -e "\n${GREEN}Browser coding smoke test passed.${NC}"
    exit 0
fi

echo -e "\n${RED}Browser coding smoke test failed.${NC}"
show_failure_logs
echo ""
echo "Run with debug: ./scripts/sanity_test.sh --debug"
exit 1
