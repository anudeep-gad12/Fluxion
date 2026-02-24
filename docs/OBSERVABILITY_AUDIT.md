# Observability Audit

**Date:** 2026-02-24
**Status:** Audit complete, fixes planned

---

## Summary

The system has **solid foundational tracing** (conversations, runs, steps, tool calls, citations, LLM traces all in SQLite) but **5 critical gaps** that lose data.

---

## What IS Tracked (Green)

| Data | Storage | Fidelity |
|------|---------|----------|
| Conversations | `conversations` table | Full (title, summary, status, created_at) |
| User messages | `runs.user_message` | Full text |
| Final answers | `runs.final_answer` | Full text |
| Token usage | `runs.usage_stats` JSON | input/output/thinking/answer tokens, latency_ms |
| Model config | `runs.model_config_snapshot` | Temperature, max_tokens, model name |
| System prompt | `runs.system_prompt_snapshot` | Exact prompt used |
| Run status | `runs.status` | running/succeeded/failed/cancelled |
| Error messages | `runs.error_message` | Full error text |
| Agent steps | `agent_steps` table | Step #, state, thinking, decision, timing |
| Tool calls (meta) | `agent_tool_calls` table | Name, arguments JSON, status, duration_ms |
| Tool idempotency | `agent_tool_calls.idempotency_key` | Crash recovery support |
| Citations | `agent_citations` table | URL, title, snippet, linked to tool call |
| LLM call traces | `trace_events` table | Token count, duration, endpoint, attempt # |
| Structured logs | `logs/app.log` (JSON) | Request ID correlation, secret redaction |

---

## What's NOT Tracked (Gaps)

### Gap 1: Tool Approval Decisions — NO AUDIT TRAIL
- User presses Y/N -> in-memory future resolves -> gone
- No record of who approved what, when
- **Risk:** For a CLI running bash commands, can't answer "did I approve that `rm -rf`?"
- **Fix:** Add `approval_decision` + `approval_timestamp` columns to `agent_tool_calls`

### Gap 2: Full Tool Results — TRUNCATED
- `agent_tool_calls.result_summary` stores ~300-500 chars only
- `read_file` on 500 lines -> summary says "Read 500 lines from src/main.py", content gone
- Bash output capped at summary level, grep results truncated
- **Risk:** Can't replay what the agent saw. Debugging requires re-running
- **Fix:** Add `result_detail` TEXT column for full results on important operations

### Gap 3: SSE Events — EPHEMERAL (5 min)
- `_event_history[run_id]` lives in memory, cleaned up 5 min after run
- Can't replay a session post-mortem
- **Risk:** If something goes wrong, the real-time event stream is gone
- **Fix:** Persist events to `run_events` table alongside in-memory buffer

### Gap 4: Raw LLM Request/Response — NOT PERSISTED
- Messages array sent to LLM: not in DB
- Raw streaming response: parsed into thinking/answer, full stream not saved
- Only available in app.log if debug logging enabled
- **Risk:** Can't audit "what exactly did we ask the model?"
- **Trade-off:** Intentional for space/privacy. Optional opt-in recommended

### Gap 5: File Change Tracking — NONEXISTENT
- No record of which files were created/modified/deleted across a run
- Can piece together from `agent_tool_calls.arguments` JSON but no aggregate view
- No before/after state, no diffs
- **Risk:** Agent modifies 10 files, you see tool calls but no "here's what changed" summary
- **Fix:** Add `run_artifacts` table tracking file paths + action type per run

---

## Silent Failures (Errors Swallowed)

| Location | What Happens | Severity |
|----------|-------------|----------|
| `agent_engine.py:910` | Trace event write fails -> `logger.warning()`, run continues without full traces | Medium |
| `agent_runs.py:248` | Tool approval timeout (5 min) -> silently returns False, no log | High |
| `agent_engine.py:1972` | Citation fetch fails -> debug log only, not persisted | Low |
| `chat_engine.py:371` | Trace recording fails -> WARNING only, doesn't block response | Medium |

---

## Missing Infrastructure

| Feature | Current State | Production Need |
|---------|--------------|-----------------|
| Distributed tracing | SQLite correlation IDs | OpenTelemetry spans |
| Metrics export | JSON logs only | Prometheus + Grafana |
| Cost tracking | Token counts stored | Dollar amounts per model |
| Event sourcing | Ephemeral (5 min) | Persistent event log |
| Schema versioning | Manual migrations | Alembic or similar |
| Multi-worker support | In-memory state (single process) | Redis pub/sub |
| `updated_at` timestamps | Only `created_at` exists | All mutable tables |

---

## Fix Priority

### Tier 1 — Do Now (data loss prevention)
1. **Persist approval decisions** on `agent_tool_calls`
2. **Add `run_events` table** for SSE event persistence
3. **Add `run_artifacts` table** for file change tracking
4. **Add `updated_at`** to all mutable tables
5. **Increase tool result storage** (result_detail column)

### Tier 2 — Before Production
1. Opt-in raw LLM request/response logging
2. Cost tracking (token counts -> dollar amounts)
3. Fix silent failures (log approval timeouts, escalate trace write failures)
4. Add `/metrics` endpoint (Prometheus-compatible)

### Tier 3 — Scale
1. OpenTelemetry integration
2. Redis pub/sub for multi-worker
3. Schema versioning (Alembic)
4. Data retention policy + GDPR deletion support

---

## Current Schema (for reference)

```
conversations    -> id, title, summary, created_at, status, metadata_json, session_id
runs             -> run_id, conversation_id, user_message, final_answer, status,
                    usage_stats, thinking_summary, model_config_snapshot,
                    system_prompt_snapshot, error_message, mode, session_id
trace_events     -> id, run_id, event_type, event_status, content_json, actor,
                    duration_ms, token_count, parent_event_id, step_number
agent_steps      -> id, run_id, step_number, state, thinking_text, decision,
                    error_message, created_at, completed_at
agent_tool_calls -> id, run_id, step_id, tool_name, arguments, status,
                    result_summary, error_message, duration_ms, execution_attempt,
                    idempotency_key, started_at, completed_at
agent_citations  -> id, run_id, tool_call_id, source_url, title, snippet,
                    used_in_answer
```

### Proposed Schema Additions

```sql
-- Gap 1: Approval audit trail
ALTER TABLE agent_tool_calls ADD COLUMN approval_decision TEXT;    -- approved/denied/auto/timeout
ALTER TABLE agent_tool_calls ADD COLUMN approval_timestamp TEXT;
ALTER TABLE agent_tool_calls ADD COLUMN approval_policy TEXT;      -- strict/relaxed/yolo

-- Gap 2: Full tool results
ALTER TABLE agent_tool_calls ADD COLUMN result_detail TEXT;        -- full result (opt-in, large)

-- Gap 3: Event persistence
CREATE TABLE run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT NOT NULL,                                      -- JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    UNIQUE(run_id, seq)
);

-- Gap 5: File change tracking
CREATE TABLE run_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,                                   -- file_created/file_modified/file_deleted/command_run
    file_path TEXT,
    action TEXT,                                                   -- write/edit/delete/bash
    detail TEXT,                                                   -- diff summary, command output, etc.
    tool_call_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (tool_call_id) REFERENCES agent_tool_calls(id)
);

-- Infrastructure: updated_at on mutable tables
ALTER TABLE conversations ADD COLUMN updated_at TEXT;
ALTER TABLE runs ADD COLUMN updated_at TEXT;
ALTER TABLE agent_steps ADD COLUMN updated_at TEXT;
```
