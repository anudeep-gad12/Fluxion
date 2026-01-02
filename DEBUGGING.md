# Debugging Guide for Reasoner

This guide covers the edit-test-read logs-patch-repeat workflow for debugging the Reasoner application.

## Quick Start

```bash
# Run unit tests with log analysis
just test-loop

# Run integration (sanity) tests with log analysis
just sanity

# Run sanity tests with live log tailing
just sanity-debug

# View live logs during development
./dev.sh applogs

# Quick error analysis
./dev.sh debug
```

## Development Scripts

### dev.sh Commands

| Command | Description |
|---------|-------------|
| `./dev.sh start` | Start API + UI servers |
| `./dev.sh logs` | Show api.log summary + tail app.log |
| `./dev.sh applogs` | Tail structured JSON logs (pretty-printed) |
| `./dev.sh debug` | Show recent errors + debugging commands |
| `./dev.sh traces` | View traces from SQLite database |
| `./dev.sh status` | Show service status |

### just Commands

| Command | Description |
|---------|-------------|
| `just test-loop` | Unit tests with log analysis |
| `just sanity` | Integration tests with log analysis |
| `just sanity-debug` | Integration tests with live log tailing |

## Log Files

| File | Format | Purpose |
|------|--------|---------|
| `logs/app.log` | JSON | Application logs (rotating, 10MB max) |
| `logs/app.log.1` - `.5` | JSON | Rotated log backups |
| `logs/test_run.log` | Text | Latest test run output |

## Log Structure

Each JSON log entry contains:

```json
{
  "timestamp": "2024-01-15T10:30:45.123456+00:00",
  "level": "INFO",
  "message": "Model call completed",
  "logger": "orchestrator.engine.chat_engine",
  "request_id": "abc12345-6789-...",
  "component": "chat_engine",
  "duration_ms": 1234,
  "extra_field": "value"
}
```

### Key Fields

- `timestamp`: ISO 8601 timestamp in UTC
- `level`: DEBUG, INFO, WARNING, ERROR
- `message`: Human-readable description
- `request_id`: UUID for tracing requests across components
- `component`: Which part of the system (http, sse, chat_engine, etc.)
- `duration_ms`: Operation timing when available
- `error`: Nested object with `type`, `message`, `traceback` on errors

## Finding and Tracing Requests

### Find all unique request IDs
```bash
grep -o '"request_id":"[^"]*"' logs/app.log | sort -u
```

### Trace a specific request
```bash
grep '"request_id":"abc12345"' logs/app.log | jq .
```

### Find errors
```bash
grep '"level":"ERROR"' logs/app.log | jq .
```

### Find slow requests (>1000ms)
```bash
grep -E '"duration_ms":[0-9]{4,}' logs/app.log | jq .
```

### Find by component
```bash
grep '"component":"sse"' logs/app.log | jq .
grep '"component":"chat_engine"' logs/app.log | jq .
```

## Stack Traces

When errors occur with stack traces:

```bash
# Find errors with tracebacks
grep '"error":{' logs/app.log | jq '.error.traceback'

# Pretty print full error details
grep '"error":{' logs/app.log | jq '.error'
```

## Debugging Workflow

### 1. Edit-Test-Debug Loop

```bash
# Terminal 1: Watch logs
tail -f logs/app.log | jq -c 'select(.level == "ERROR" or .level == "WARNING")'

# Terminal 2: Run test loop
just test-loop
```

### 2. Triage a Test Failure

1. **Run the failing test**:
   ```bash
   just test-loop tests/path/to/test.py::test_name -v
   ```

2. **Find the request ID** from test output or logs:
   ```bash
   tail -20 logs/app.log | jq -r '.request_id' | sort -u
   ```

3. **Trace the full request**:
   ```bash
   grep '"request_id":"<ID>"' logs/app.log | jq .
   ```

4. **Check for errors**:
   ```bash
   grep '"request_id":"<ID>"' logs/app.log | jq 'select(.error)'
   ```

### 3. SSE Stream Issues

For SSE streaming problems:

```bash
# Find stream lifecycle events
grep '"component":"sse"' logs/app.log | jq -c '{run_id, message, chunk_count}'

# Find aborted streams
grep 'stream aborted\|client disconnected' logs/app.log | jq .

# Find stream errors
grep 'SSE stream error' logs/app.log | jq .
```

### 4. Model Call Issues

```bash
# Find model call timing
grep '"component":"chat_engine"' logs/app.log | jq -c '{message, duration_ms}'

# Find retries
grep 'Retrying request' logs/app.log | jq .

# Find timeout errors
grep 'Request timeout' logs/app.log | jq .
```

## Failure Triage Checklist

When investigating a test failure:

- [ ] **Reproduce**: Can you reproduce with `just test-loop tests/... -v`?
- [ ] **Request ID**: What's the request ID for the failing request?
- [ ] **Timeline**: What events occurred? Trace with `grep request_id logs/app.log`
- [ ] **Error Type**: Is there an exception? Check `jq '.error.type'`
- [ ] **Duration**: Was it slow? Check `duration_ms` fields
- [ ] **Model Response**: Did the model call succeed? Look for `llm_response` events
- [ ] **SSE Stream**: Did the stream complete? Look for `SSE stream completed`
- [ ] **Retries**: Were there retries? Look for `Retrying request` logs

## Self-Heal Loop (for AI Assistants)

When running the edit-test-read logs-patch-repeat loop:

### Step 1: Run Tests
```bash
just test-loop
```

### Step 2: On Failure, Analyze Logs
```bash
# Get the error summary
grep '"level":"ERROR"' logs/app.log | jq -c '{message, error: .error.type}'

# Find the request ID
grep '"level":"ERROR"' logs/app.log | jq -r '.request_id' | head -1

# Trace the full request timeline
REQUEST_ID="<from above>"
grep "$REQUEST_ID" logs/app.log | jq -c '{timestamp, level, component, message}'
```

### Step 3: Identify Root Cause
- Check the error type and message
- Look at the stack trace: `jq '.error.traceback'`
- Review the request timeline for the sequence of events

### Step 4: Patch and Repeat
- Make the fix
- Run `just test-loop` again
- Continue until green

## Configuration

Logging is configured in `orchestrator/logging_config.py`:

- **Log level**: Set via `setup_logging(log_level="DEBUG")`
- **Rotation**: 10MB max file size, 5 backup files
- **Secret redaction**: API keys, tokens, emails are automatically redacted

### Changing Log Level

Edit `orchestrator/app.py` in the `lifespan()` function:
```python
setup_logging(
    log_level="INFO",  # Change to DEBUG for more detail
    log_dir="./logs",
    log_file="app.log",
)
```

## Tips

1. **Use `jq` for JSON parsing** - Install with `brew install jq`
2. **Watch mode** - Use `tail -f logs/app.log | jq .` during development
3. **Time-based filtering** - Logs include ISO timestamps for correlation
4. **Request correlation** - Every log entry includes `request_id` for tracing
5. **Clear logs before test** - `just test-loop` does this automatically

## Debugging Integration Tests (Sanity)

### Running with Log Analysis
```bash
# Basic run - shows errors on failure
just sanity

# With live log tailing - see logs as tests run
just sanity-debug

# Or directly
./scripts/sanity_test.sh --debug
```

### On Failure
The sanity test will automatically:
1. Show all ERROR/WARNING log entries
2. Print debugging commands

### Debugging a Specific Run
```bash
# Find the run ID from test output or logs
grep '"run_id"' logs/app.log | tail -5

# Trace that run
grep '<run_id>' logs/app.log | jq .

# Check run status via API
curl http://localhost:9000/api/runs/<run_id> | jq .

# View run timeline
curl http://localhost:9000/api/runs/<run_id>/timeline | jq .
```

## Common Issues

### No logs appearing
- Check that `setup_logging()` is called in app startup
- Verify `logs/` directory exists and is writable

### Logs too verbose
- Adjust log level: `setup_logging(log_level="WARNING")`
- Third-party loggers (uvicorn, httpx) are silenced by default

### Secrets in logs
- Secrets should be automatically redacted
- If you see a secret, add a pattern to `SECRET_PATTERNS` in `logging_config.py`

### Missing request_id
- Ensure the request went through the `RequestLoggingMiddleware`
- Background tasks may not have request context - check component field

## Example Debug Session

```bash
$ just test-loop tests/engine/test_chat_engine.py -v

=== Reasoner Test Loop ===

Clearing logs...
Running tests...
...
FAILED tests/engine/test_chat_engine.py::test_chat_basic

=== TESTS FAILED ===

=== Relevant Log Entries ===
[abc12345] ERROR: Model call failed
         Type: ConnectionError
         Message: Cannot connect to host

=== Test Failure Summary ===
FAILED tests/engine/test_chat_engine.py::test_chat_basic

Commands for debugging:
  View full test log:  cat logs/test_run.log
  View app log:        cat logs/app.log
  Find request IDs:    grep -o '"request_id":"[^"]*"' logs/app.log | sort -u
  Trace a request:     grep '<request_id>' logs/app.log | jq .
```

From here:
1. The error is `ConnectionError` - model server isn't running
2. Fix: Start the model server or mock it in tests
3. Run `just test-loop` again to verify
