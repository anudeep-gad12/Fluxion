# Web Research Agent - Complete System Design

> **Last Updated:** 2026-01-04
> **Status:** Authoritative design document

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Critical Fixes](#2-critical-fixes)
3. [Architecture](#3-architecture)
4. [Model & Provider Layer](#4-model--provider-layer)
5. [Tool System](#5-tool-system)
6. [Agent Engine](#6-agent-engine)
7. [Data Model](#7-data-model)
8. [API Design](#8-api-design)
9. [SSE & Streaming](#9-sse--streaming)
10. [Failure Scenarios & Recovery](#10-failure-scenarios--recovery)
11. [Deployment](#11-deployment)
12. [Configuration](#12-configuration)

---

## 1. System Overview

### What We're Building

A production-grade web research agent that:
- Searches the web using Parallel.ai APIs
- Extracts and summarizes content from web pages
- Executes Python code in E2B sandbox
- Provides evidence-grounded answers with citations
- Recovers from crashes gracefully
- Streams real-time progress to the UI

### Core Capabilities

| Capability | Implementation |
|------------|----------------|
| Web Search | Parallel.ai Search API |
| Content Extraction | Parallel.ai Extract API |
| Computation | **E2B sandbox** (not Docker) |
| Reasoning | gpt-oss-120b with Harmony format |
| Primary Provider | **DeepInfra** ($0.09/1M tokens) |
| Fallback Provider | Together AI ($0.15/1M tokens) |
| Streaming | Server-Sent Events (SSE) |
| Durability | SQLite with Turso (production) |

### Non-Negotiables

1. **Evidence-grounded answers** - Every claim backed by citations
2. **Durable runs** - Crash recovery, cancel works, retries recorded
3. **Full trace system** - Complete trace of all events
4. **Thinking UI = trace projection** - Visualization of actual events
5. **Answer accuracy** - Correctness over speed

---

## 2. Critical Fixes

These are production failure modes that MUST be addressed:

| # | Problem | Why It Fails | Solution |
|---|---------|--------------|----------|
| 1 | **Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon inside | Use **E2B external sandbox API** |
| 2 | **Token Blowout** | Tool results accumulate, context exceeds 128k tokens | **Context Pruner**: summarize old results to 1-line |
| 3 | **Zombie Sessions** | Backend crash leaves orphan E2B sessions | **Session cleanup on startup** |
| 4 | **Non-Idempotent Recovery** | python_execute crash loses result, model hallucinates | **Inject system hint**: "execution interrupted, re-run" |
| 5 | **Provider Economics** | Together AI is 60% more expensive | **DeepInfra primary** ($0.09 vs $0.15) |
| 6 | **WAL Bloat** | Storing result_raw causes gigabyte WAL files | **Store only result_summary**, no blobs |

---

## 3. Architecture

```
┌─────────────────┐         HTTPS/SSE          ┌──────────────────────────────────┐
│    FRONTEND     │◄──────────────────────────▶│            BACKEND               │
│    (Vercel)     │                            │        (Railway/Fly.io)          │
│                 │                            │                                  │
│  • React/Vite   │                            │  ┌────────────────────────────┐  │
│  • Zustand      │                            │  │      FastAPI Server        │  │
│  • SSE Client   │                            │  └────────────┬───────────────┘  │
└─────────────────┘                            │               │                  │
                                               │               ▼                  │
                                               │  ┌────────────────────────────┐  │
                                               │  │      Agent Engine          │  │
                                               │  │  • State Machine           │  │
                                               │  │  • Context Pruner          │  │
                                               │  │  • Recovery Logic          │  │
                                               │  └────────────┬───────────────┘  │
                                               │               │                  │
                                               │  ┌────────────┴───────────────┐  │
                                               │  │      Tool Registry         │  │
                                               │  │  • web_search              │  │
                                               │  │  • web_extract             │  │
                                               │  │  • python_execute          │  │
                                               │  └────────────────────────────┘  │
                                               │               │                  │
                                               │  ┌────────────┴───────────────┐  │
                                               │  │    Provider Chain          │  │
                                               │  │  • DeepInfra (primary)     │  │
                                               │  │  • Together AI (fallback)  │  │
                                               │  │  • Circuit Breaker         │  │
                                               │  └────────────────────────────┘  │
                                               │               │                  │
                                               │  ┌────────────┴───────────────┐  │
                                               │  │    Turso SQLite            │  │
                                               │  └────────────────────────────┘  │
                                               └──────────────────────────────────┘
                                                              │
                    ┌─────────────────────────────────────────┼─────────────────────────────────────────┐
                    │                                         │                                         │
                    ▼                                         ▼                                         ▼
           ┌───────────────┐                         ┌───────────────┐                         ┌───────────────┐
           │   DeepInfra   │                         │  Parallel.ai  │                         │     E2B       │
           │  (gpt-oss)    │                         │ (search/ext)  │                         │  (sandbox)    │
           └───────────────┘                         └───────────────┘                         └───────────────┘
```

---

## 4. Model & Provider Layer

### Provider Selection

| Provider | Price (per 1M tokens) | Role | SLA |
|----------|----------------------|------|-----|
| **DeepInfra** | $0.09 input / $0.36 output | Primary | 99.5% |
| Together AI | $0.15 input / $0.60 output | Fallback | 99.9% |

**DeepInfra is primary because:**
- 40% cheaper for same open-weights model
- Native Harmony format support
- OpenAI-compatible API

### Failover Strategy

```
Request → DeepInfra
  ↓ (if 5xx or timeout > 30s)
  → Together AI
  ↓ (if also fails)
  → Error with retry option
```

### Circuit Breaker

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=30):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = "closed"  # closed | open | half-open
        self.last_failure_time = None

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"

    def record_success(self):
        self.failure_count = 0
        self.state = "closed"

    @property
    def is_open(self) -> bool:
        if self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
                return False
            return True
        return False
```

---

## 5. Tool System

### Tool Definitions

#### web_search
```json
{
  "name": "web_search",
  "description": "Search the web for information",
  "parameters": {
    "query": {"type": "string", "required": true},
    "num_results": {"type": "integer", "default": 10}
  }
}
```
**Idempotent:** Yes (safe to retry)

#### web_extract
```json
{
  "name": "web_extract",
  "description": "Extract content from URLs",
  "parameters": {
    "urls": {"type": "array", "items": "string", "maxItems": 5}
  }
}
```
**Idempotent:** Yes (safe to retry)

#### python_execute
```json
{
  "name": "python_execute",
  "description": "Execute Python code in sandbox",
  "parameters": {
    "code": {"type": "string", "required": true}
  }
}
```
**Idempotent:** NO (inject hint on recovery)

### E2B Sandbox Integration

```python
from e2b import Sandbox

class PythonSandboxTool(BaseTool):
    name = "python_execute"

    async def execute(self, code: str) -> ToolResult:
        sandbox = None
        try:
            sandbox = await Sandbox.create(
                template="python3",
                timeout=30,
                metadata={"app": "reasoner"}
            )

            result = await sandbox.run_code(code)

            return ToolResult(
                success=True,
                output=result.stdout,
                error=result.stderr if result.stderr else None
            )
        except TimeoutError:
            return ToolResult(success=False, error="Execution timed out")
        finally:
            if sandbox:
                await sandbox.kill()
```

### E2B Session Cleanup on Startup

```python
async def cleanup_stale_e2b_sessions():
    """Called on server startup."""
    from e2b import Sandbox

    try:
        sessions = await Sandbox.list()
        for session in sessions:
            if session.metadata.get("app") == "reasoner":
                age_minutes = (datetime.now() - session.created_at).total_seconds() / 60
                if age_minutes > 10:
                    logger.info(f"Cleaning up stale session: {session.id}")
                    await session.kill()
    except Exception as e:
        logger.warning(f"E2B cleanup failed (non-fatal): {e}")
```

---

## 6. Agent Engine

### State Machine

```
     ┌─────────┐
     │  INIT   │
     └────┬────┘
          │
          ▼
     ┌─────────┐
     │PLANNING │◄─────────────────────┐
     └────┬────┘                      │
          │                           │
          ▼                           │
  ┌───────────────┐                   │
  │ TOOL_CALLING  │───────────────────┘
  └───────┬───────┘
          │ (no more tools)
          ▼
  ┌───────────────┐
  │ SYNTHESIZING  │
  └───────┬───────┘
          │
          ▼
     ┌─────────┐
     │COMPLETE │
     └─────────┘
```

### Context Pruner (Critical)

```python
class ContextPruner:
    """Prevents token blowout by summarizing old tool results."""

    KEEP_FULL_STEPS = 2  # Keep last 2 steps detailed

    def prune(self, messages: list[dict], current_step: int) -> list[dict]:
        pruned = []
        for msg in messages:
            if msg["role"] == "tool":
                step = self._get_step_number(msg)
                if step is not None and step < current_step - self.KEEP_FULL_STEPS:
                    pruned.append(self._summarize_tool_result(msg))
                else:
                    pruned.append(msg)
            else:
                pruned.append(msg)
        return pruned

    def _summarize_tool_result(self, msg: dict) -> dict:
        content = msg.get("content", "")
        tool_name = msg.get("name", "unknown")

        if tool_name == "web_extract":
            summary = f"[Extracted content - {len(content)} chars]"
        elif tool_name == "web_search":
            summary = f"[Search results - {len(content)} chars]"
        elif tool_name == "python_execute":
            if len(content) > 500:
                summary = f"[Output: {content[:200]}...{content[-200:]}]"
            else:
                return msg
        else:
            summary = f"[Tool result - {len(content)} chars]"

        return {**msg, "content": summary, "_pruned": True}
```

### Non-Idempotent Recovery (Hint Injection)

```python
async def _recover_non_idempotent_tool(self, context, tool_call) -> None:
    """Handle recovery for python_execute crashes."""

    await self._update_tool_status(tool_call.id, "interrupted")

    hint = {
        "role": "system",
        "content": (
            f"IMPORTANT: The previous {tool_call.tool_name} execution was "
            f"interrupted by a system restart. The result was lost. "
            f"Please regenerate and re-run the code to get the result."
        )
    }
    context.messages.append(hint)
```

---

## 7. Data Model

### Agent Tables

```sql
-- Extend runs table
ALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';
ALTER TABLE runs ADD COLUMN agent_state TEXT;
ALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;
ALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;
ALTER TABLE runs ADD COLUMN updated_at TEXT;

-- Agent steps
CREATE TABLE agent_steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    state TEXT NOT NULL,  -- planning | tool_calling | complete | error
    thinking_text TEXT,
    decision TEXT,        -- call_tool | synthesize | error
    error_message TEXT,
    UNIQUE(run_id, step_number),
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

-- Tool calls (NO result_raw - prevents WAL bloat)
CREATE TABLE agent_tool_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    idempotency_key TEXT NOT NULL,
    execution_attempt INTEGER DEFAULT 1,
    result_summary TEXT,   -- 1-line only, no blobs
    error_message TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE
);

-- Citations
CREATE TABLE agent_citations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT,
    snippet TEXT NOT NULL,
    used_in_answer BOOLEAN DEFAULT FALSE,
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_agent_steps_run ON agent_steps(run_id);
CREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);
CREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);
CREATE INDEX idx_citations_run ON agent_citations(run_id);
```

---

## 8. API Design

### Endpoints

```
POST   /api/agent/runs              # Start new agent run
GET    /api/agent/runs/{id}         # Get run status
GET    /api/agent/runs/{id}/stream  # SSE event stream
POST   /api/agent/runs/{id}/cancel  # Cancel run
GET    /api/agent/runs/{id}/trace   # Get full trace
```

### Start Run Request

```json
POST /api/agent/runs
{
  "query": "What is the population of Tokyo?",
  "conversation_id": "optional-uuid"
}
```

### Response

```json
{
  "run_id": "uuid",
  "status": "running",
  "stream_url": "/api/agent/runs/{id}/stream"
}
```

---

## 9. SSE & Streaming

### Event Types

| Event | When | Data |
|-------|------|------|
| `agent_state` | State transition | `{state: "planning"}` |
| `step_start` | New step | `{step_number: 1}` |
| `tool_start` | Tool executing | `{tool_name: "web_search"}` |
| `tool_result` | Tool done | `{summary: "Found 10 results"}` |
| `thinking` | Reasoning tokens | `{text: "..."}` |
| `answer` | Final answer | `{text: "..."}` |
| `citation` | Citation added | `{url, title, snippet}` |
| `complete` | Run finished | `{final_answer: "..."}` |
| `error` | Run failed | `{message: "..."}` |
| `heartbeat` | Keep-alive | `{}` |

### Resumption Support

```
GET /api/agent/runs/{id}/stream?since_seq=42
```

Frontend tracks `lastSeq` and reconnects with this parameter.

---

## 10. Failure Scenarios & Recovery

### Model API Failures

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries |
| Timeout (>30s) | Request timeout | Failover to Together AI |
| 5xx error | HTTP status | Retry once, then failover |
| All providers down | Both fail | Mark run as error |

### Tool Failures

| Tool | Failure | Recovery |
|------|---------|----------|
| web_search | API error | Retry 3x, then error |
| web_extract | URL unreachable | Skip URL, continue |
| python_execute | Timeout | Return timeout error to model |
| python_execute | Crash mid-execution | **Inject hint, re-run** |

### Crash Recovery

| Crash Point | Recovery Action |
|-------------|-----------------|
| Before step created | Create step, continue |
| After step, before model call | Redo model call |
| During tool execution (idempotent) | Retry tool |
| During tool execution (python_execute) | Inject hint |
| After tool result | Mark step complete |

---

## 11. Deployment

### Hosting

| Component | Platform | Rationale |
|-----------|----------|-----------|
| Frontend | Vercel | Free tier, global CDN |
| Backend | Railway | Docker support, easy SQLite |
| Database | Turso | Distributed SQLite |
| Sandbox | E2B | External API, 100 free credits |

### Environment Variables

```bash
# Required
DEEPINFRA_API_KEY=xxx     # Primary model provider
PARALLEL_API_KEY=xxx      # Web search/extract
E2B_API_KEY=xxx           # Python sandbox

# Optional (for failover)
TOGETHER_API_KEY=xxx      # Fallback model provider

# Database (production)
TURSO_DATABASE_URL=xxx
TURSO_AUTH_TOKEN=xxx
```

---

## 12. Configuration

### chat_config.yaml additions

```yaml
# Model providers
model_providers:
  primary:
    name: deepinfra
    base_url: "https://api.deepinfra.com/v1/openai"
    api_key: ${DEEPINFRA_API_KEY}
    model: "openai/gpt-oss-120b"
    timeout_ms: 60000
  fallback:
    name: together_ai
    base_url: "https://api.together.xyz/v1"
    api_key: ${TOGETHER_API_KEY}
    model: "openai/gpt-oss-120b"
    timeout_ms: 60000

# Agent settings
agent:
  enabled: true
  max_steps: 10
  circuit_breaker:
    failure_threshold: 5
    recovery_timeout_seconds: 30

# Parallel.ai
parallel:
  base_url: "https://api.parallel.ai/v1beta"
  api_key: ${PARALLEL_API_KEY}
  search:
    max_results: 10
    timeout_ms: 15000
  extract:
    timeout_ms: 30000
    max_urls_per_request: 5

# Sandbox (E2B)
sandbox:
  provider: e2b
  e2b:
    api_key: ${E2B_API_KEY}
    template: "python3"
    timeout_seconds: 30
    metadata:
      app: "reasoner"
```
