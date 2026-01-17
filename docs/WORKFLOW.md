# Development Workflow

> Quick reference for feature development with Claude Code.

---

## TL;DR - Quick Commands

```bash
# Start work
git checkout test && git pull && git checkout -b feature/xxx

# During development
uv run pytest tests/xxx/ -v           # Unit tests for module
./dev.sh debug                         # Check for errors
./dev.sh traces                        # View recent runs

# Before merge
uv run pytest                          # Full test suite
./scripts/sanity_test.sh --debug       # E2E tests (actual flow)

# Merge
git checkout test && git merge feature/xxx
# Update docs/IMPLEMENTATION_LOG.md
```

---

## Feature Development Flow

### Step 1: Branch Setup

```bash
git checkout test
git pull origin test
git checkout -b feature/<name>
```

### Step 2: Implement Feature

- Write code following patterns in existing files
- Reference `docs/COMPONENTS.md` for architecture
- Check `docs/DATA_MODELS.md` for schemas

### Step 3: Write Tests

```bash
# Create test file mirroring source structure
# tests/<module>/test_<file>.py

# Run tests incrementally
uv run pytest tests/<module>/test_<file>.py -v -x
```

### Step 4: Validate with Traces

```bash
# Start services
./dev.sh start

# Make test requests via UI or API
curl -X POST http://localhost:9000/api/conversations \
  -H "Content-Type: application/json" \
  -d '{"title": "Test"}'

# Check traces for errors
./dev.sh traces                        # Recent runs
./dev.sh explore <run_id>              # Specific run detail
```

### Step 5: Check Logs for Errors

```bash
./dev.sh debug                         # Recent errors/warnings
grep '"level":"ERROR"' logs/app.log | jq .
```

### Step 6: Full Test Suite

```bash
uv run pytest                          # All unit tests
./scripts/sanity_test.sh --debug       # E2E with live logs (actual flow)
```

### Step 7: Commit and Merge

```bash
git add .
git commit -m "feat(<scope>): <description>

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Merge to test
git checkout test
git merge feature/<name>
git push origin test
```

### Step 8: Update Implementation Log

Add entry to `docs/IMPLEMENTATION_LOG.md`:
- Branch name
- Files changed
- Tests added
- Issues found/fixed
- Trace verification

---

## PR Workflow (Every Few Features)

After several features merged to `test`:

```bash
# Ensure test is up to date
git checkout test
git push origin test

# Create PR via gh CLI
gh pr create --base main --head test \
  --title "Feature batch: X, Y, Z" \
  --body "## Summary
- Feature X: description
- Feature Y: description
- Feature Z: description

## Verification
- All tests pass
- E2E sanity tests pass
- Manual testing completed"

# Request Claude Code review
/code-review
```

---

## Error Investigation

### Trace Error Pattern

```bash
# Find failed runs
sqlite3 var/traces.sqlite "
  SELECT run_id, status, error_message
  FROM runs
  WHERE status='failed'
  ORDER BY created_at DESC
  LIMIT 10;
"

# Explore failed run
./dev.sh explore <run_id>

# Find error events
sqlite3 var/traces.sqlite "
  SELECT * FROM trace_events
  WHERE run_id='<id>'
  AND event_status='error';
"
```

### Log Error Pattern

```bash
# Recent errors
./dev.sh debug

# Find by request ID
grep '<request_id>' logs/app.log | jq .

# All errors with context
grep '"level":"ERROR"' logs/app.log | tail -20 | jq '{ts: .timestamp, msg: .message, err: .error}'
```

---

## Quick Reference

### Key Files by Task

| Task | Files to Read |
|------|---------------|
| New feature | `docs/COMPONENTS.md`, similar existing feature |
| Bug fix | `logs/app.log`, `./dev.sh traces`, error location |
| API change | `orchestrator/routes/`, `orchestrator/schemas.py` |
| Agent change | `orchestrator/agent/agent_engine.py`, `orchestrator/agent/tools/` |
| UI change | `ui/src/components/`, `ui/src/hooks/` |
| Config change | `orchestrator/chat_config.yaml`, `orchestrator/config.py` |

### Service Commands

| Command | Purpose |
|---------|---------|
| `./dev.sh start` | Start API + UI |
| `./dev.sh stop` | Stop all services |
| `./dev.sh debug` | Show recent errors |
| `./dev.sh traces` | View SQLite traces |
| `./dev.sh explore <id>` | Explore specific run |
