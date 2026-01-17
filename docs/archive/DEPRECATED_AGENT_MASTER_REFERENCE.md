> **DEPRECATED**: This document is kept for historical reference. For current documentation, see:
> - [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
> - [COMPONENTS.md](./COMPONENTS.md) - Component documentation
> - [DATA_MODELS.md](./DATA_MODELS.md) - Data models
> - [DATA_FLOW.md](./DATA_FLOW.md) - Data flow diagrams
> - [API_REFERENCE.md](./API_REFERENCE.md) - API documentation

---

# Web Research Agent - Master Reference

> Quick reference for the web research agent implementation. For detailed design, see [AGENT_SYSTEM_DESIGN.md](./AGENT_SYSTEM_DESIGN.md).

---

## Quick Links

| What | Where |
|------|-------|
| Full Design Doc | [docs/AGENT_SYSTEM_DESIGN.md](./AGENT_SYSTEM_DESIGN.md) |
| Implementation Plan | [.claude/plans/lazy-purring-nygaard.md](../.claude/plans/lazy-purring-nygaard.md) |
| Agent Schema | [orchestrator/storage/schema.sql](../orchestrator/storage/schema.sql) |
| Config | [orchestrator/chat_config.yaml](../orchestrator/chat_config.yaml) |

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────────────────────────────┐
│   Frontend  │────▶│              Backend                │
│   (Vercel)  │ SSE │           (Railway)                 │
└─────────────┘◀────│  ┌─────────┐    ┌──────────────┐   │
                    │  │ Agent   │───▶│ Turso SQLite │   │
                    │  │ Engine  │    └──────────────┘   │
                    │  └────┬────┘                        │
                    └───────┼────────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
    ┌──────────┐     ┌───────────┐     ┌──────────┐
    │ DeepInfra│     │Parallel.ai│     │   E2B    │
    │(gpt-oss) │     │(search/   │     │(sandbox) │
    └──────────┘     │ extract)  │     └──────────┘
                     └───────────┘
```

---

## Critical Fixes (Must Remember)

| # | Problem | Solution |
|---|---------|----------|
| 1 | Docker won't run in Railway/Fly.io containers | Use E2B external sandbox API |
| 2 | Context blows up to 128k tokens | Context Pruner: summarize old tool results |
| 3 | Orphan E2B sessions after crash | Session cleanup on startup |
| 4 | python_execute crash loses result | Inject system hint: "re-run the code" |
| 5 | Together AI is 60% more expensive | DeepInfra primary ($0.09/1M tokens) |
| 6 | result_raw causes WAL bloat | Store only result_summary, no blobs |

---

## Environment Variables

```bash
# Required
DEEPINFRA_API_KEY=xxx     # Primary model provider
PARALLEL_API_KEY=xxx      # Web search/extract
E2B_API_KEY=xxx           # Python sandbox

# Optional
TOGETHER_API_KEY=xxx      # Fallback model provider
TURSO_DATABASE_URL=xxx    # Production database
TURSO_AUTH_TOKEN=xxx
```

---

## Database Schema (Agent Tables)

```sql
-- Runs: Add agent columns
ALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';
ALTER TABLE runs ADD COLUMN agent_state TEXT;
ALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;

-- Agent Steps
CREATE TABLE agent_steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    state TEXT NOT NULL,  -- planning | tool_calling | complete | error
    thinking_text TEXT,
    decision TEXT,        -- call_tool | synthesize | error
    UNIQUE(run_id, step_number)
);

-- Tool Calls (NO result_raw - prevents WAL bloat)
CREATE TABLE agent_tool_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted
    result_summary TEXT,   -- 1-line only
    idempotency_key TEXT NOT NULL
);

-- Citations
CREATE TABLE agent_citations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT,
    snippet TEXT NOT NULL,
    used_in_answer BOOLEAN DEFAULT FALSE
);
```

---

## Tools Reference

### web_search
```json
{
  "name": "web_search",
  "description": "Search the web for information",
  "parameters": {
    "query": "string (required)",
    "num_results": "integer (default: 10)"
  }
}
```
**Idempotent:** Yes (safe to retry)

### web_extract
```json
{
  "name": "web_extract",
  "description": "Extract content from URLs",
  "parameters": {
    "urls": "array of strings (required, max 5)"
  }
}
```
**Idempotent:** Yes (safe to retry)

### python_execute
```json
{
  "name": "python_execute",
  "description": "Execute Python code in sandbox",
  "parameters": {
    "code": "string (required)"
  }
}
```
**Idempotent:** NO (inject hint on recovery)

---

## SSE Event Types

| Event | When | Data |
|-------|------|------|
| `agent_state` | State transition | `{state: "planning"}` |
| `step_start` | New step | `{step_number: 1}` |
| `tool_start` | Tool executing | `{tool_name: "web_search"}` |
| `tool_result` | Tool done | `{summary: "Found 10 results"}` |
| `thinking` | Reasoning tokens | `{text: "..."}` |
| `answer` | Final answer tokens | `{text: "..."}` |
| `citation` | Citation added | `{url, title, snippet}` |
| `complete` | Run finished | `{final_answer: "..."}` |
| `error` | Run failed | `{message: "..."}` |
| `heartbeat` | Keep-alive | `{}` |

**Resumption:** Use `?since_seq=N` to resume from sequence N

---

## API Endpoints

```
POST   /api/agent/runs              # Start new agent run
GET    /api/agent/runs/{id}         # Get run status
GET    /api/agent/runs/{id}/stream  # SSE event stream
POST   /api/agent/runs/{id}/cancel  # Cancel run
GET    /api/agent/runs/{id}/trace   # Get full trace
```

---

## Phased Implementation Checklist

### Phase 1: Data Layer
- [ ] Add agent tables to schema.sql
- [ ] Create Pydantic models in schemas.py
- [ ] Create agent_repo.py with CRUD
- [ ] Write unit tests
- [ ] **Exit:** `sqlite3 data/reasoner.db ".schema agent_steps"` works

### Phase 2: Provider Chain
- [ ] Implement circuit_breaker.py
- [ ] Implement chain.py with failover
- [ ] Update config.py
- [ ] Write unit + integration tests
- [ ] **Exit:** Failover to Together works when DeepInfra fails

### Phase 3: Tool Layer
- [ ] Create base.py (BaseTool ABC)
- [ ] Create registry.py
- [ ] Implement web_search.py
- [ ] Implement web_extract.py
- [ ] Implement python_sandbox.py (E2B)
- [ ] Write tests for each tool
- [ ] **Exit:** Each tool works in isolation

### Phase 4: Context Pruner + State Machine
- [ ] Implement context_pruner.py
- [ ] Implement state_machine.py
- [ ] Write unit tests
- [ ] **Exit:** Pruner reduces token count, state transitions work

### Phase 5: Agent Engine
- [ ] Implement recovery.py (with hint injection)
- [ ] Implement agent_engine.py
- [ ] Write unit + E2E tests
- [ ] **Exit:** Agent answers "What is the population of Tokyo?"

### Phase 6: API Layer
- [ ] Create routes/agent.py
- [ ] Update app.py with startup recovery
- [ ] Write API + SSE tests
- [ ] **Exit:** curl can start run and stream events

### Phase 7: Frontend
- [ ] Create TypeScript types
- [ ] Create API client
- [ ] Create useAgentSSE hook
- [ ] Create UI components
- [ ] **Exit:** Full user flow works in browser

### Phase 8: Production
- [ ] Deploy to Railway
- [ ] Deploy to Vercel
- [ ] Configure Turso
- [ ] Test crash recovery
- [ ] **Exit:** Production deployment with <5s p95 latency

---

## Debugging Commands

```bash
# View agent traces
sqlite3 data/reasoner.db "SELECT * FROM agent_steps WHERE run_id='xxx'"

# View tool calls
sqlite3 data/reasoner.db "SELECT tool_name, status, result_summary FROM agent_tool_calls WHERE run_id='xxx'"

# Check circuit breaker state
grep "circuit_breaker" logs/app.log | jq .

# Check token usage
grep "context_pruner" logs/app.log | jq '{before: .tokens_before, after: .tokens_after}'

# Check recovery actions
grep "recovery" logs/app.log | jq .
```

---

## Common Issues

### "Docker daemon not found"
**Cause:** Trying to run Docker in Railway/Fly.io container
**Fix:** Use E2B sandbox API instead

### Context exceeds 128k tokens
**Cause:** Tool results not being pruned
**Fix:** Check context_pruner is being called before model calls

### Agent hallucinates after crash recovery
**Cause:** Non-idempotent tool (python_execute) crashed, result lost
**Fix:** Verify hint injection is working in recovery.py

### SSE disconnects and loses events
**Cause:** Client not using `since_seq` parameter
**Fix:** Frontend must track last seq and reconnect with `?since_seq=N`

### WAL file growing to gigabytes
**Cause:** Storing result_raw in agent_tool_calls
**Fix:** Only store result_summary, enable auto_vacuum

---

## Key Files Map

```
orchestrator/
├── agent/
│   ├── agent_engine.py      # Main agent loop
│   ├── context_pruner.py    # Token management
│   ├── recovery.py          # Crash recovery + hints
│   ├── state_machine.py     # State transitions
│   └── tools/
│       ├── base.py          # BaseTool ABC
│       ├── registry.py      # Tool registry
│       ├── web_search.py    # Parallel.ai search
│       ├── web_extract.py   # Parallel.ai extract
│       └── python_sandbox.py # E2B sandbox
├── providers/
│   ├── chain.py             # Provider failover
│   └── circuit_breaker.py   # Circuit breaker
├── routes/
│   └── agent.py             # HTTP + SSE endpoints
└── storage/
    └── repositories/
        └── agent_repo.py    # DB operations

ui/src/
├── components/
│   ├── AgentThinkingPanel.tsx
│   ├── ToolCallCard.tsx
│   ├── CitationInline.tsx
│   └── AnswerWithCitations.tsx
└── hooks/
    └── useAgentSSE.ts       # SSE with reconnection
```
