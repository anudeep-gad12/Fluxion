#!/bin/bash
# Test loop harness for Reasoner
# Clears logs, runs tests, shows relevant errors on failure
# Usage: ./scripts/test_loop.sh [pytest args...]

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$PROJECT_DIR/logs/app.log"
TEST_LOG="$PROJECT_DIR/logs/test_run.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Reasoner Test Loop ===${NC}"
echo ""

# Step 1: Clear logs
echo -e "${YELLOW}Clearing logs...${NC}"
mkdir -p "$PROJECT_DIR/logs"
: > "$LOG_FILE"
: > "$TEST_LOG"
echo "Logs cleared at $(date)" > "$TEST_LOG"

# Step 2: Run tests
echo -e "${YELLOW}Running tests...${NC}"
cd "$PROJECT_DIR"

# Capture exit code
set +e
uv run pytest "$@" 2>&1 | tee -a "$TEST_LOG"
TEST_EXIT_CODE=${PIPESTATUS[0]}
set -e

echo "" >> "$TEST_LOG"
echo "Test completed at $(date) with exit code $TEST_EXIT_CODE" >> "$TEST_LOG"

# Step 3: Report results
echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}=== ALL TESTS PASSED ===${NC}"
else
    echo -e "${RED}=== TESTS FAILED ===${NC}"
    echo ""

    # Extract relevant errors from app.log
    if [ -f "$LOG_FILE" ] && [ -s "$LOG_FILE" ]; then
        echo -e "${YELLOW}=== Relevant Log Entries ===${NC}"

        # Show errors and warnings from the log
        grep -E '"level":\s*"(ERROR|WARNING)"' "$LOG_FILE" 2>/dev/null | \
            python3 -c "
import sys, json
for line in sys.stdin:
    try:
        entry = json.loads(line)
        level = entry.get('level', 'UNKNOWN')
        msg = entry.get('message', '')
        req_id = entry.get('request_id', '-')
        req_id_short = req_id[:8] if req_id != '-' else '-'
        print(f'[{req_id_short}] {level}: {msg}')
        if 'error' in entry:
            err = entry['error']
            print(f'         Type: {err.get(\"type\", \"Unknown\")}')
            if err.get('message'):
                print(f'         Message: {err.get(\"message\", \"\")}')
    except:
        print(line.strip())
" 2>/dev/null || cat "$LOG_FILE"

        echo ""
    fi

    # Show test failure summary
    echo -e "${YELLOW}=== Test Failure Summary ===${NC}"
    grep -E "^(FAILED|ERROR|E   )" "$TEST_LOG" 2>/dev/null | head -20 || true

    echo ""
    echo -e "${YELLOW}Commands for debugging:${NC}"
    echo "  View full test log:  cat $TEST_LOG"
    echo "  View app log:        cat $LOG_FILE"
    echo "  Find request IDs:    grep -o '\"request_id\":\"[^\"]*\"' $LOG_FILE | sort -u"
    echo "  Trace a request:     grep '<request_id>' $LOG_FILE | jq ."
    echo "  Find errors:         grep '\"level\":\"ERROR\"' $LOG_FILE | jq ."
fi

exit $TEST_EXIT_CODE
