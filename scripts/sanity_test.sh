#!/bin/bash
# Sanity Test Script for Reasoner
# Run: ./scripts/sanity_test.sh
# Requires: Server running on port 9000 (except for import tests)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

API_URL="${API_URL:-http://127.0.0.1:9000}"
PASSED=0
FAILED=0

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
python -c "from orchestrator.thinking.strategies.car import CARStrategy" 2>/dev/null && pass "CAR strategy imports" || fail "CAR strategy imports"
python -c "from orchestrator.thinking.strategies.cot import ChainOfThoughtStrategy" 2>/dev/null && pass "CoT strategy imports" || fail "CoT strategy imports"

# ============================================================
# 2. API HEALTH CHECK
# ============================================================
print_header "2. API Health Check"

# Check if server is running
if curl -s --max-time 2 "$API_URL/api/runs" > /dev/null 2>&1; then
    pass "API server is reachable"
else
    fail "API server not reachable at $API_URL"
    echo "Start server with: ./dev.sh start"
    echo ""
    echo "========================================"
    echo "RESULTS: $PASSED passed, $FAILED failed (API tests skipped)"
    echo "========================================"
    exit 1
fi

# ============================================================
# 3. CAR STRATEGY TEST (Default Mode)
# ============================================================
print_header "3. CAR Strategy Test (Default Mode)"

# Create a simple run
RESPONSE=$(curl -s -X POST "$API_URL/api/runs" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "What is 2+2?"}')

RUN_ID=$(echo "$RESPONSE" | grep -o '"run_id":"[^"]*"' | cut -d'"' -f4)

if [ -n "$RUN_ID" ]; then
    pass "Created run: $RUN_ID"
else
    fail "Failed to create run"
fi

# Wait for completion
echo "Waiting for CAR response..."
sleep 4

# Check result
RESULT=$(curl -s "$API_URL/api/runs/$RUN_ID")
STATUS=$(echo "$RESULT" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ "$STATUS" = "succeeded" ]; then
    pass "CAR strategy completed"
else
    fail "CAR strategy failed (status: $STATUS)"
fi

# ============================================================
# 4. COT STRATEGY TEST (Thinking Mode)
# ============================================================
print_header "4. CoT Strategy Test (Thinking Mode)"

# Create conversation
CONV_RESPONSE=$(curl -s -X POST "$API_URL/api/conversations" \
    -H "Content-Type: application/json" \
    -d '{}')

CONV_ID=$(echo "$CONV_RESPONSE" | grep -o '"conversation_id":"[^"]*"' | cut -d'"' -f4)

if [ -n "$CONV_ID" ]; then
    pass "Created conversation"
else
    fail "Failed to create conversation"
fi

# Send message with thinking mode
COT_RESPONSE=$(curl -s -X POST "$API_URL/api/conversations/$CONV_ID/runs" \
    -H "Content-Type: application/json" \
    -d '{"message": "What is 3+5?", "thinking_mode": "thinking"}')

COT_RUN_ID=$(echo "$COT_RESPONSE" | grep -o '"run_id":"[^"]*"' | cut -d'"' -f4)

if [ -n "$COT_RUN_ID" ]; then
    pass "Created CoT run: $COT_RUN_ID"
else
    fail "Failed to create CoT run"
fi

# Wait for completion (CoT takes longer)
echo "Waiting for CoT response (may take 10-15s)..."
sleep 12

# Check result
COT_RESULT=$(curl -s "$API_URL/api/runs/$COT_RUN_ID")
COT_STATUS=$(echo "$COT_RESULT" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ "$COT_STATUS" = "succeeded" ]; then
    pass "CoT strategy completed"
else
    fail "CoT strategy failed (status: $COT_STATUS)"
fi

# Check thinking trace
THINKING=$(curl -s "$API_URL/api/runs/$COT_RUN_ID/thinking?detail=user")
if echo "$THINKING" | grep -q "thinking_summary"; then
    pass "Thinking trace available"
else
    fail "No thinking trace found"
fi

# ============================================================
# 5. CONVERSATION FLOW TEST
# ============================================================
print_header "5. Conversation Flow Test"

# List conversations
CONV_LIST=$(curl -s "$API_URL/api/conversations")
if echo "$CONV_LIST" | grep -q "conversations"; then
    pass "Can list conversations"
else
    fail "Cannot list conversations"
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
