# API Reference

Complete documentation of all API endpoints in the Fluxion system.

## Table of Contents

1. [Overview](#overview)
2. [Conversations](#conversations)
3. [Runs](#runs)
4. [Agent Runs](#agent-runs)
5. [ChatGPT Auth](#chatgpt-auth-cli)
6. [Models](#models)
7. [Browser Terminal](#browser-terminal)
8. [Benchmarks](#benchmarks)
9. [System](#system)
10. [Rate Limiting](#rate-limiting)
11. [SSE Streaming](#sse-streaming)
12. [Error Handling](#error-handling)

---

## Overview

### Base URL

```
http://127.0.0.1:9000/api
```

### Authentication

No authentication required for local development.

### Content Type

All requests and responses use `application/json` unless otherwise specified.

### Common Response Format

**Success Response**:
```json
{
  "field": "value",
  ...
}
```

**Error Response**:
```json
{
  "detail": "Error message"
}
```

---

## Conversations

### Create Conversation

Create a new conversation.

**Request**:
```
POST /api/conversations
```

**Body**:
```json
{
  "title": "Optional conversation title"
}
```

**Response** (201 Created):
```json
{
  "conversation_id": "abc12345"
}
```

---

### List Conversations

Get all conversations with optional filtering.

**Request**:
```
GET /api/conversations?status=active&limit=50&offset=0
```

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | - | Filter by status: `active`, `archived`, `closed` |
| `limit` | int | 50 | Maximum results |
| `offset` | int | 0 | Pagination offset |

**Response** (200 OK):
```json
[
  {
    "conversation_id": "abc12345",
    "title": "Math questions",
    "summary": "Discussion about calculus",
    "status": "active",
    "created_at": "2024-01-15T10:30:00Z",
    "metadata": null
  },
  ...
]
```

---

### Get Conversation

Get conversation details including all runs.

**Request**:
```
GET /api/conversations/{conversation_id}
```

**Response** (200 OK):
```json
{
  "conversation": {
    "conversation_id": "abc12345",
    "title": "Math questions",
    "summary": "Discussion about calculus",
    "status": "active",
    "created_at": "2024-01-15T10:30:00Z",
    "metadata": null
  },
  "runs": [
    {
      "run_id": "run_001",
      "created_at": "2024-01-15T10:31:00Z",
      "status": "succeeded",
      "mode": "chat",
      "profile": "chat",
      "prompt": "What is 2+2?",
      "user_message": "What is 2+2?",
      "conversation_id": "abc12345",
      "final_answer": "2+2 equals 4.",
      "thinking_summary": null,
      "error_code": null,
      "error_detail": null
    }
  ]
}
```

**Error** (404 Not Found):
```json
{
  "detail": "Conversation not found"
}
```

---

### Update Conversation

Update conversation fields.

**Request**:
```
PATCH /api/conversations/{conversation_id}
```

**Body**:
```json
{
  "title": "New title",
  "summary": "Updated summary",
  "status": "archived"
}
```

All fields are optional.

**Response** (200 OK):
```json
{
  "conversation_id": "abc12345",
  "title": "New title",
  "summary": "Updated summary",
  "status": "archived",
  "created_at": "2024-01-15T10:30:00Z",
  "metadata": null
}
```

---

### Delete Conversation

Delete a conversation and all associated runs.

**Request**:
```
DELETE /api/conversations/{conversation_id}
```

**Response** (200 OK):
```json
{
  "status": "deleted",
  "conversation_id": "abc12345"
}
```

---

### Get Conversation Traces

Get all trace events for all runs in a conversation.

**Request**:
```
GET /api/conversations/{conversation_id}/traces
```

**Response** (200 OK):
```json
{
  "conversation_id": "abc12345",
  "events": [
    {
      "id": "evt_001",
      "run_id": "run_001",
      "seq": 1,
      "created_at": "2024-01-15T10:31:00Z",
      "event_type": "llm_request",
      "event_status": "pending",
      "actor": "system",
      "endpoint": "/v1/responses",
      "attempt": 1,
      "content": { ... },
      "parent_event_id": null,
      "step_number": 1,
      "duration_ms": null,
      "token_count": null,
      "error_message": null
    },
    ...
  ],
  "total_events": 10
}
```

---

## Runs

### Create Conversation Run

Send a message in a conversation. Returns immediately with stream URL.

**Request**:
```
POST /api/conversations/{conversation_id}/runs
```

**Body**:
```json
{
  "message": "What is the capital of France?",
  "thinking_mode": "default",
  "reasoning_effort": "medium"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | User message |
| `thinking_mode` | string | No | `"default"` or `"thinking"` |
| `reasoning_effort` | string | No | `"low"`, `"medium"`, `"high"` (gpt-oss) |

**Response** (200 OK):
```json
{
  "run_id": "run_001",
  "stream_url": "/api/runs/run_001/stream"
}
```

---

### Create Standalone Run

Create a run without a conversation.

**Request**:
```
POST /api/runs
```

**Body**:
```json
{
  "prompt": "What is 2+2?",
  "mode": "default",
  "profile": "default"
}
```

**Response** (200 OK):
```json
{
  "run_id": "run_001",
  "stream_url": "/api/runs/run_001/stream"
}
```

---

### List Runs

Get all runs with optional filtering.

**Request**:
```
GET /api/runs?status=succeeded&limit=50&offset=0
```

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | - | Filter by status |
| `conversation_id` | string | - | Filter by conversation |
| `limit` | int | 50 | Maximum results |
| `offset` | int | 0 | Pagination offset |

**Response** (200 OK):
```json
{
  "runs": [
    {
      "run_id": "run_001",
      "created_at": "2024-01-15T10:31:00Z",
      "status": "succeeded",
      "mode": "default",
      "profile": "default",
      "prompt": "What is 2+2?",
      "final_answer": "4",
      ...
    }
  ],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

---

### Get Run

Get run details.

**Request**:
```
GET /api/runs/{run_id}
```

**Response** (200 OK):
```json
{
  "run_id": "run_001",
  "created_at": "2024-01-15T10:31:00Z",
  "status": "succeeded",
  "mode": "chat",
  "profile": "chat",
  "prompt": "What is 2+2?",
  "user_message": "What is 2+2?",
  "conversation_id": "abc12345",
  "final_answer": "2+2 equals 4.",
  "thinking_summary": "I need to add 2 and 2...",
  "error_code": null,
  "error_detail": null
}
```

---

### Get Run Timeline

Get detailed trace event timeline for a run.

**Request**:
```
GET /api/runs/{run_id}/timeline
```

**Response** (200 OK):
```json
{
  "run_id": "run_001",
  "status": "succeeded",
  "created_at": "2024-01-15T10:31:00Z",
  "events": [
    {
      "id": "evt_001",
      "run_id": "run_001",
      "seq": 1,
      "created_at": "2024-01-15T10:31:00Z",
      "event_type": "llm_request",
      "event_status": "pending",
      "actor": "system",
      "endpoint": "/v1/responses",
      "attempt": 1,
      "content": {
        "messages": [...],
        "model": "gpt-oss-20b",
        "max_tokens": 4096,
        "temperature": 1.0
      },
      "parent_event_id": null,
      "step_number": 1,
      "duration_ms": null,
      "token_count": null,
      "error_message": null
    },
    {
      "id": "evt_002",
      "run_id": "run_001",
      "seq": 2,
      "created_at": "2024-01-15T10:31:01Z",
      "event_type": "llm_response",
      "event_status": "success",
      "actor": "model",
      "endpoint": "/v1/responses",
      "attempt": 1,
      "content": {
        "response_length": 256,
        "usage": {
          "prompt_tokens": 50,
          "completion_tokens": 20,
          "total_tokens": 70
        },
        "finish_reason": "stop"
      },
      "parent_event_id": "evt_001",
      "step_number": 1,
      "duration_ms": 1234,
      "token_count": 70,
      "error_message": null
    }
  ],
  "total_events": 2
}
```

---

### Abort Run

Cancel a running execution.

**Request**:
```
POST /api/runs/{run_id}/abort
```

**Response** (200 OK):
```json
{
  "status": "aborted",
  "run_id": "run_001"
}
```

**Error** (400 Bad Request):
```json
{
  "detail": "Run not found or not running"
}
```

---

### Stream Run (SSE)

Subscribe to real-time events for a run.

**Request**:
```
GET /api/runs/{run_id}/stream
```

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `since_seq` | int | Resume from sequence number |

**Response**: Server-Sent Events stream

See [SSE Streaming](#sse-streaming) for event format.

---

### Get Run Events

Get events for a run with optional sequence filtering.

**Request**:
```
GET /api/runs/{run_id}/events
```

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `since_seq` | int | null | Get events after this sequence number |

**Response** (200 OK):
```json
{
  "events": [
    {
      "run_id": "run_001",
      "seq": 1,
      "ts": "2024-01-15T10:30:00Z",
      "type": "llm_request",
      "display": { ... },
      "payload": { ... }
    },
    {
      "run_id": "run_001",
      "seq": 2,
      "ts": "2024-01-15T10:30:01Z",
      "type": "llm_response",
      "display": { ... },
      "payload": { ... }
    }
  ]
}
```

**Event Types**:
- `llm_request` - Request sent to LLM
- `llm_response` - Response received from LLM
- `reasoning` - Thinking/reasoning step
- `tool_call` - Tool invocation
- `tool_response` - Tool result
- `error` - Error occurred
- `retry` - Retry attempt

**Error** (404 Not Found):
```json
{
  "detail": "Run not found"
}
```

---

### Get Run Report

Get a human-readable markdown report for a run.

**Request**:
```
GET /api/runs/{run_id}/report
```

**Response** (200 OK):
```json
{
  "run_id": "run_001",
  "report": "# Chat Report\n\n**Run ID**: run_001\n**Status**: succeeded\n",
  "timeline": [
    {
      "seq": 1,
      "type": "llm_request",
      "duration_ms": null
    },
    {
      "seq": 2,
      "type": "llm_response",
      "duration_ms": 1234
    }
  ]
}
```

**Error** (404 Not Found):
```json
{
  "detail": "Run not found"
}
```

---

### Get Run Thinking

Get thinking trace for a run with configurable detail level.

**Request**:
```
GET /api/runs/{run_id}/thinking?detail=user
```

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `detail` | string | `user` | Detail level: `user`, `internal`, or `full` |

**Detail Levels**:
- `user` - Clean, UI-friendly summaries (default)
- `internal` - Full raw traces with tokens, timing, messages
- `full` - Both internal and UI data

**Response** (200 OK):
```json
{
  "run_id": "run_001",
  "thinking_summary": "I need to calculate 2+2...",
  "strategy": "direct",
  "steps": [
    {
      "seq": 1,
      "step_type": "reasoning",
      "summary": "Adding numbers",
      "status": "done"
    }
  ],
  "detail_level": "user"
}
```

**Error** (404 Not Found):
```json
{
  "detail": "Run not found"
}
```

**Error** (400 Bad Request):
```json
{
  "detail": "Invalid detail level. Use 'user', 'internal', or 'full'"
}
```

---

## Agent Runs

### Create Agent Run

Start an agent research query.

**Request**:
```
POST /api/agent/runs
```

**Body**:
```json
{
  "query": "What are the latest developments in quantum computing?",
  "conversation_id": "abc12345",
  "max_steps": 10,
  "profile": "coding",
  "permission_policy": "relaxed",
  "working_dir": "/path/to/project",
  "filesystem_enabled": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | Yes | - | Research query |
| `conversation_id` | string | No | null | Optional conversation |
| `max_steps` | int | No | 10 | Maximum agent steps |
| `profile` | string | No | `"research"` | Agent profile: `"research"` or `"coding"` |
| `permission_policy` | string | No | `"relaxed"` | Tool approval: `"strict"`, `"relaxed"`, `"yolo"` |
| `working_dir` | string | No | null | Filesystem root for coding tools |
| `filesystem_enabled` | bool | No | false | Enable filesystem tools |

**Response** (200 OK):
```json
{
  "run_id": "agent_001",
  "status": "running",
  "stream_url": "/api/agent/runs/agent_001/stream?token=abc123...",
  "stream_token": "abc123..."
}
```

The `stream_token` is a per-run secret (`secrets.token_urlsafe(16)`) used to authenticate SSE stream connections. Pass it as the `token` query parameter when connecting to the stream endpoint.

---

### Get Agent Run Status

Get current status of an agent run.

**Request**:
```
GET /api/agent/runs/{run_id}
```

**Response** (200 OK):
```json
{
  "run_id": "agent_001",
  "status": "running",
  "agent_state": "tool_calling",
  "current_step": 2,
  "max_steps": 10,
  "final_answer": null,
  "usage": {
    "input_tokens": 18420,
    "output_tokens": 2687,
    "reasoning_tokens": 0,
    "cached_tokens": 0,
    "total_tokens": 21107
  },
  "context_usage": {
    "context_window": 262144,
    "reserved_output_tokens": 32768,
    "effective_input_budget": 229376,
    "prompt_tokens_current_call": 21107,
    "conversation_tokens_active_history": 21107,
    "remaining_tokens": 208269,
    "utilization_pct_effective": 9.2,
    "compaction_threshold_pct": 90,
    "next_compaction_at_tokens": 206438,
    "compaction_count": 0,
    "last_compacted_at_step": null
  },
  "stored_context": {
    "context_window": 262144,
    "stored_tokens": 6123,
    "utilization_pct": 2.3,
    "replayable_entry_count": 14
  },
  "context_profile": {
    "provider_name": "fireworks",
    "model_id": "accounts/fireworks/models/kimi-k2p6",
    "display_name": "Kimi K2.6",
    "context_window": 262144,
    "max_output_tokens": 32768,
    "effective_input_budget": 229376,
    "supports_tools": true,
    "supports_reasoning": false,
    "pricing": {
      "input_cost_per_million": null,
      "cached_input_cost_per_million": null,
      "output_cost_per_million": null
    },
    "source": "registry"
  },
  "compaction_count": 0,
  "last_compacted_at_step": null,
  "created_at": "2024-01-15T10:31:00Z",
  "updated_at": "2024-01-15T10:31:30Z"
}
```

`context_usage` is the current assembled provider prompt for the active call. `stored_context` is the replayable conversation context currently persisted for future coding turns.

**Status Values**:
- `running` - Agent is executing
- `succeeded` - Agent finished successfully
- `failed` - Agent encountered an error
- `cancelled` - User cancelled

**Agent State Values**:
- `init` - Starting
- `planning` - Deciding action
- `tool_calling` - Executing tools
- `synthesizing` - Generating answer
- `paused` - Blocked between steps (via pause endpoint)
- `complete` - Done
- `error` - Failed

---

### Get Agent Run Trace

Get complete trace of agent execution.

**Request**:
```
GET /api/agent/runs/{run_id}/trace
```

**Response** (200 OK):
```json
{
  "run_id": "agent_001",
  "status": "complete",
  "agent_state": "complete",
  "final_answer": "Based on my research...",
  "steps": [
    {
      "id": "step_001",
      "run_id": "agent_001",
      "step_number": 1,
      "state": "complete",
      "thinking_text": "I need to search for quantum computing news...",
      "decision": "call_tool",
      "created_at": "2024-01-15T10:31:00Z",
      "completed_at": "2024-01-15T10:31:05Z",
      "error_message": null
    },
    {
      "id": "step_002",
      "run_id": "agent_001",
      "step_number": 2,
      "state": "complete",
      "thinking_text": "Found useful information, let me synthesize...",
      "decision": "synthesize",
      "created_at": "2024-01-15T10:31:06Z",
      "completed_at": "2024-01-15T10:31:15Z",
      "error_message": null
    }
  ],
  "tool_calls": [
    {
      "id": "tc_001",
      "run_id": "agent_001",
      "step_id": "step_001",
      "tool_name": "web_search",
      "arguments": {
        "query": "latest quantum computing developments 2024"
      },
      "status": "success",
      "result_summary": "Found 5 relevant articles about quantum computing breakthroughs...",
      "result_detail": null,
      "approval_decision": "auto",
      "approval_policy": "relaxed",
      "approval_decided_at": null,
      "error_message": null,
      "duration_ms": 2500,
      "created_at": "2024-01-15T10:31:01Z",
      "started_at": "2024-01-15T10:31:01Z",
      "completed_at": "2024-01-15T10:31:03Z",
      "idempotency_key": "abc123def456",
      "execution_attempt": 1
    }
  ],
  "artifacts": [
    {
      "id": "art_001",
      "run_id": "agent_001",
      "artifact_type": "file_edit",
      "file_path": "src/main.py",
      "action": "edit_file",
      "detail": "Changed function name from foo to bar",
      "tool_call_id": "tc_002",
      "created_at": "2024-01-15T10:31:05Z"
    }
  ],
  "system_events": [
    {
      "event_type": "conversation_compacted",
      "message": "Conversation compacted to preserve context window",
      "step_number": 6,
      "seq": 42,
      "created_at": "2024-01-15T10:31:12Z"
    }
  ],
  "context_profile": {
    "provider_name": "fireworks",
    "model_id": "accounts/fireworks/models/kimi-k2p6",
    "display_name": "Kimi K2.6",
    "context_window": 262144,
    "max_output_tokens": 32768,
    "effective_input_budget": 229376,
    "supports_tools": true,
    "supports_reasoning": false,
    "pricing": {
      "input_cost_per_million": null,
      "cached_input_cost_per_million": null,
      "output_cost_per_million": null
    },
    "source": "registry"
  },
  "context_usage": {
    "context_window": 262144,
    "reserved_output_tokens": 32768,
    "effective_input_budget": 229376,
    "prompt_tokens_current_call": 21107,
    "conversation_tokens_active_history": 21107,
    "remaining_tokens": 208269,
    "utilization_pct_effective": 9.2,
    "compaction_threshold_pct": 90,
    "next_compaction_at_tokens": 206438,
    "compaction_count": 0,
    "last_compacted_at_step": null
  },
  "stored_context": {
    "context_window": 262144,
    "stored_tokens": 6123,
    "utilization_pct": 2.3,
    "replayable_entry_count": 14
  },
  "compaction_count": 0,
  "last_compacted_at_step": null,
  "citations": [
    {
      "id": "cit_001",
      "run_id": "agent_001",
      "tool_call_id": "tc_001",
      "source_url": "https://example.com/quantum-article",
      "title": "Breakthrough in Quantum Error Correction",
      "snippet": "Researchers have achieved a new milestone in quantum error correction...",
      "used_in_answer": true,
      "created_at": "2024-01-15T10:31:10Z"
    }
  ]
}
```

---

### Approve Tool Execution

Approve a pending tool call that requires user consent.

**Request**:
```
POST /api/agent/runs/{run_id}/approve/{tool_call_id}
```

**Response** (200 OK):
```json
{
  "status": "approved",
  "tool_call_id": "tc_001"
}
```

**Error** (404 Not Found):
```json
{
  "detail": "No pending approval for this tool call"
}
```

**Notes**:
- Only works when a `tool_approval_required` SSE event has been emitted for this tool_call_id
- The agent engine is blocked waiting for this response
- After approval, the tool executes and a `tool_result` event follows

---

### Deny Tool Execution

Deny a pending tool call. The tool is skipped and the agent continues.

**Request**:
```
POST /api/agent/runs/{run_id}/deny/{tool_call_id}
```

**Response** (200 OK):
```json
{
  "status": "denied",
  "tool_call_id": "tc_001"
}
```

**Error** (404 Not Found):
```json
{
  "detail": "No pending approval for this tool call"
}
```

**Notes**:
- The denied tool is recorded with `approval_decision: "denied"` and `status: "interrupted"`
- The agent continues execution (may call other tools or synthesize)

---

### Pause Agent Run

Pause an active agent run between steps. The agent blocks at the next step boundary.

**Request**:
```
POST /api/agent/runs/{run_id}/pause
```

**Response** (200 OK):
```json
{
  "run_id": "agent_001",
  "status": "paused"
}
```

**Error** (400 Bad Request):
```json
{
  "detail": "Run is not active"
}
```

**Notes**:
- Emits a `paused` SSE event
- Agent state transitions to `PAUSED`
- The agent loop blocks between steps until resumed or cancelled

---

### Resume Agent Run

Resume a paused agent run.

**Request**:
```
POST /api/agent/runs/{run_id}/resume
```

**Response** (200 OK):
```json
{
  "run_id": "agent_001",
  "status": "running"
}
```

**Error** (400 Bad Request):
```json
{
  "detail": "Run is not paused"
}
```

**Notes**:
- Emits a `resumed` SSE event
- Agent state transitions back from `PAUSED` and continues the step loop

---

### Steer Agent Run

Inject a steering message into an active agent run. The message is queued and injected as a user-role message before the next LLM call.

**Request**:
```
POST /api/agent/runs/{run_id}/steer
```

**Body**:
```json
{
  "message": "Focus on the performance comparison, not the architecture."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | Steering message to inject |

**Response** (200 OK):
```json
{
  "run_id": "agent_001",
  "status": "queued"
}
```

**Notes**:
- Emits a `steer` (steer_injected) SSE event
- The message is injected as a user-role message before the next LLM call
- Multiple messages can be queued; all are injected and cleared on the next step
- Works on both running and paused runs (injected when the run proceeds)

---

### Cancel Agent Run

Stop an agent execution.

**Request**:
```
POST /api/agent/runs/{run_id}/cancel
```

**Response** (200 OK):
```json
{
  "run_id": "agent_001",
  "status": "cancelled"
}
```

---

### Stream Agent Run (SSE)

Subscribe to real-time agent events.

**Request**:
```
GET /api/agent/runs/{run_id}/stream?token=abc123&since_seq=0
```

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `token` | string | Stream token from create response (recommended) |
| `since_seq` | int | Resume from sequence number |

**Response**: Server-Sent Events stream

**Authentication**: If a `token` is provided and it doesn't match the run's stream token, the server returns **403 Forbidden**. Omitting the token is allowed as a fallback (e.g., page reload before token is restored from localStorage).

**Reconnection**: On reconnect (e.g., page reload), the server creates a new SSE generator with its own read cursor into the append-only `_event_history` log. All past events are replayed from the cursor position, then the generator waits for new live events. Events with `seq <= since_seq` are skipped for deduplication. Multiple concurrent clients each maintain independent cursors, so they never interfere with each other.

See [SSE Streaming](#sse-streaming) for event format.

---

## ChatGPT Auth (CLI)

### Export Tokens

Export ChatGPT OAuth tokens for local backup.

**Request**:
```
GET /api/auth/chatgpt/export?cli_session={session_id}
```

**Response** (200 OK):
```json
{
  "session_id": "...",
  "refresh_token": "...",
  "account_id": "..."
}
```

Returns 404 if no valid tokens for the session.

---

### Restore Tokens

Restore ChatGPT auth from backed-up refresh token.

**Request**:
```
POST /api/auth/chatgpt/restore
Content-Type: application/json

{
  "session_id": "...",
  "refresh_token": "..."
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "model": "gpt-4o"
}
```

Returns `{"success": false, "error": "..."}` if refresh fails.

---

## Models

### List Model Presets

Get all available model presets grouped by provider, with API key availability.

**Request**:
```
GET /api/models
```

**Response** (200 OK):
```json
{
  "providers": {
    "openrouter": [...],
    "deepinfra": [...],
    "fireworks": [...],
    "local": [...]
  },
  "active_model": "qwen3-72b",
  "active_model_id": "qwen/qwen3-72b"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `providers` | object | Models grouped by provider name |
| `active_model` | string\|null | The last selected model string (alias/ID), or `null` if none |
| `active_model_id` | string\|null | ID of the currently active model, or `null` if none |

The `available` field on each model indicates whether the required API key is set.

---

### Select Model

Hot-swap the active model without restart. Resolves the model string through the registry (alias, prefix, or fallback).

**Request**:
```
POST /api/models/select
```

**Body**:
```json
{
  "model": "qwen3-72b"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Model alias, ID, or `provider:model_id` |

**Response** (200 OK):
```json
{
  "status": "ok",
  "model_id": "qwen/qwen3-72b",
  "display_name": "Qwen 3 72B",
  "provider": "openrouter",
  "context_window": 131072,
  "max_output_tokens": 8192,
  "effective_input_budget": 122880,
  "supports_tools": true,
  "supports_reasoning": false,
  "source": "registry"
}
```

**Error** (400 Bad Request):
```json
{
  "detail": "No API key for provider openrouter (set OPENROUTER_API_KEY)"
}
```

> **Note:** Disabled in production/staging (`SERVE_STATIC=true`). Returns 403 Forbidden.

---

### Get Model Status

Get current provider and model info.

Current status payload also includes:
- `context_window`
- `max_output_tokens`
- `effective_input_budget`
- `supports_tools`
- `supports_reasoning`
- `source`

**Request**:
```
GET /api/models/status
```

**Response** (200 OK):
```json
{
  "provider": "local",
  "model_name": "Qwen3.5-35B-A3B-Q8_0",
  "base_url": "http://localhost:8080/v1",
  "local_running": true
}
```

Provider is `"local"` when llama-server is active, `"cloud"` otherwise.

---

### List Local Models

Scan disk for available GGUF models.

**Request**:
```
GET /api/models/local
```

**Response** (200 OK):
```json
[
  {
    "path": "/Users/user/.lmstudio/models/Qwen3.5-35B-A3B-Q8_0.gguf",
    "name": "Qwen3.5-35B-A3B-Q8_0",
    "size_bytes": 37580963840,
    "size_display": "35.0 GB"
  }
]
```

Scans: `~/.lmstudio/models`, `~/.cache/lm-studio/models` (excluding Ollama subfolders)

---

### Start Local Model

Start llama-server with a GGUF model and switch provider.

**Request**:
```
POST /api/models/local/start
```

**Body**:
```json
{
  "model_path": "/path/to/model.gguf",
  "ctx_size": 100000
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `model_path` | string | Yes | - | Full path to GGUF file |
| `ctx_size` | int | No | config `context.max_tokens` | Context window size |

**Response** (200 OK):
```json
{
  "status": "ok",
  "model_name": "Qwen3.5-35B-A3B-Q8_0"
}
```

**Error** (404): Model file not found
**Error** (500): llama-server failed to start

---

### Stop Local Model

Stop llama-server and revert to cloud provider.

**Request**:
```
POST /api/models/local/stop
```

**Response** (200 OK):
```json
{
  "status": "ok",
  "provider": "cloud"
}
```

---

## Browser Terminal

Desktop agent mode exposes a per-conversation persistent terminal session backed by a PTY shell. The browser terminal is separate from the agent `bash` tool: it is user-driven, interactive, and long-lived until restarted or closed.

### Create or Reattach Terminal Session

**Request**:
```
POST /api/terminal/conversations/{conversation_id}/session
```

**Body**:
```json
{
  "workspace_path": "/Users/me/project",
  "cols": 120,
  "rows": 30
}
```

**Response** (200 OK):
```json
{
  "session_id": "6f1d...",
  "conversation_id": "abc123",
  "workspace_path": "/Users/me/project",
  "shell": "/bin/zsh",
  "status": "running",
  "cols": 120,
  "rows": 30,
  "created_at": "2026-04-28T12:00:00+00:00",
  "updated_at": "2026-04-28T12:00:00+00:00",
  "last_activity_at": "2026-04-28T12:00:00+00:00",
  "reconnect_supported": true,
  "replay_buffer": ""
}
```

If the conversation already has a live terminal session, this endpoint returns the existing session metadata instead of creating a new shell.

### Get Terminal Session Metadata

**Request**:
```
GET /api/terminal/conversations/{conversation_id}/session
```

Returns the persisted session metadata plus:
- `reconnect_supported=true` when the live PTY still exists in memory
- `status="stale"` when metadata exists but the server restart/loss killed the live shell
- `replay_buffer` containing bounded recent output for reconnect/reopen

### Restart Terminal Session

**Request**:
```
POST /api/terminal/conversations/{conversation_id}/session/restart
```

Same request body as create. This kills the old shell, starts a new PTY, and updates the session metadata to the current workspace path and terminal size.

### Close Terminal Session

**Request**:
```
POST /api/terminal/conversations/{conversation_id}/session/close
```

**Response**:
```json
{
  "status": "closed",
  "conversation_id": "abc123"
}
```

### WebSocket Attach Endpoint

**Request**:
```
GET /api/terminal/conversations/{conversation_id}/ws?session_id={session_id}
```

Protocol:
- browser → server:
  - `{"type":"input","data":"ls\r"}`
  - `{"type":"resize","cols":132,"rows":36}`
  - `{"type":"ping"}`
- server → browser:
  - `{"type":"status","status":"running"}`
  - `{"type":"replay","data":"..."}`
  - `{"type":"output","data":"..."}`
  - `{"type":"exit","exit_code":0}`
  - `{"type":"pong"}`

Notes:
- The terminal session is scoped per conversation, not per browser tab.
- Changing the conversation workspace path later does not automatically reset the running shell.
- WebSocket access follows the same owner/session isolation rules as the rest of the browser app.

---

## Benchmarks

### List Benchmark Traces

Get metadata for all GAIA evaluation traces.

**Request**:
```
GET /api/benchmarks/traces
```

**Response** (200 OK):
```json
[
  {
    "filename": "gpt5mini_level1_best_66.7pct.json",
    "timestamp": "2026-01-31T10:00:00Z",
    "level": "1",
    "model": "openai/gpt-5-mini",
    "total_questions": 42,
    "correct": 28,
    "accuracy": 66.7
  },
  ...
]
```

Traces are sorted by timestamp (newest first). Searches both `gaia_results/` and `gaia_results/best_runs/` directories.

---

### Get Benchmark Trace

Get full evaluation data for a specific trace file.

**Request**:
```
GET /api/benchmarks/traces/{filename}
```

**Response** (200 OK):
```json
{
  "metadata": {
    "timestamp": "2026-01-31T10:00:00Z",
    "level": "1",
    "model_name": "openai/gpt-5-mini",
    ...
  },
  "summary": {
    "total_questions": 42,
    "agent_correct": 28,
    "agent_accuracy": 66.7,
    ...
  },
  "results": [
    {
      "question": "...",
      "expected_answer": "...",
      "agent_answer": "...",
      "agent_correct": true,
      ...
    }
  ]
}
```

**Error** (400 Bad Request):
```json
{
  "detail": "Invalid filename"
}
```

**Error** (404 Not Found):
```json
{
  "detail": "Trace not found"
}
```

---

## System

### Health Check

Check API health.

**Request**:
```
GET /api/health
```

**Response** (200 OK):
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

---

### Get Usage

Get per-session message usage and limits. Only relevant when `demo.message_limit` is set.

**Request**:
```
GET /api/usage
```

**Response** (200 OK):
```json
{
  "limit": 10,
  "used": 3,
  "remaining": 7
}
```

**Notes**:
- Counting is session-based (via `demo_session` cookie), not IP-based
- Owner bypasses all limits (`remaining` is always large)
- When `demo.message_limit` is 0 or demo mode is disabled, `limit` is 0 and `remaining` is effectively unlimited
- Frontend shows "X left" counter; input is disabled at 0 remaining; 429 errors handled via toast

---

### Get Configuration

Get current runtime configuration.

**Request**:
```
GET /api/config
```

**Response** (200 OK):
```json
{
  "config": {
    "provider": {
      "base_url": "https://api.fireworks.ai/inference/v1",
      "endpoint": "chat_completions",
      "fallback_on_404": true,
      "timeout": 120.0
    },
    "model": {
      "name": "accounts/fireworks/models/kimi-k2p6",
      "temperature": 1.0,
      "max_tokens": 32768,
      "reasoning_effort": "medium"
    },
    "context": {
      "max_messages": 50,
      "max_tokens": 100000,
      "reserve_for_response": 16384,
      "truncation_strategy": "sliding_window"
    },
    "thinking": {
      "mode_mapping": {
        "default": "direct",
        "thinking": "direct"
      }
    }
  }
}
```

Note: The response is wrapped in a `config` key and shows values from `chat_config.yaml`. In this repo the current YAML defaults point at Fireworks with `accounts/fireworks/models/kimi-k2p6`; environment variables can override that at runtime.

---

## Rate Limiting

### Client IP Resolution

The rate limiter identifies clients by IP address. How the IP is determined depends on the deployment environment:

- **Production/staging** (`SERVE_STATIC=true`, i.e. behind Railway reverse proxy): The `X-Forwarded-For` header is trusted and used to extract the real client IP.
- **Development** (`SERVE_STATIC` unset or `false`): The `X-Forwarded-For` header is ignored. The direct connection IP from the transport socket is always used, preventing header spoofing by untrusted clients.

This ensures that rate limits cannot be bypassed by forging `X-Forwarded-For` headers in environments where the server is directly exposed.

---

## SSE Streaming

### Event Format

All SSE events follow this format:

```
event: <event_type>
data: <json_payload>

```

or for data-only events:

```
data: <json_payload>

```

### Chat Run Events

| Event | Type | Description |
|-------|------|-------------|
| `data` | - | Token or thinking token |
| `event: complete` | - | Stream complete |
| `event: error` | - | Error occurred |
| `event: aborted` | - | Run aborted |

**Token Event**:
```
data: {"type": "TOKEN", "content": "Hello"}

```

**Thinking Token Event**:
```
data: {"type": "THINKING_TOKEN", "content": "Let me think..."}

```

**Complete Event**:
```
event: complete
data: {"run_id": "run_001", "final_answer": "...", "status": "succeeded", ...}

```

**Error Event**:
```
event: error
data: {"error": "Connection failed", "code": "PROVIDER_ERROR"}

```

### Agent Run Events

| Event Type | Description | Payload |
|------------|-------------|---------|
| `agent_state` | State change | `{state, current_step, max_steps}` |
| `step_start` | New step | `{step_number, steps_remaining}` |
| `thinking` | Thinking token | `{content}` |
| `tool_start` | Tool starting | `{tool_call_id, tool_name, arguments}` |
| `tool_approval_required` | Approval needed | `{tool_call_id, tool_name, arguments}` |
| `tool_result` | Tool finished | `{tool_call_id, success, result_summary, duration_ms}` |
| `answer` | Answer token | `{content}` |
| `usage_update` | Live usage/context budget update | `{usage, cost, context_usage, stored_context, context_profile, compaction_count, last_compacted_at_step}` |
| `conversation_compacted` | Visible conversation compaction event | `{message, step_number, context_usage, stored_context, context_profile}` |
| `complete` | Agent done | `{success, final_answer, citations, total_steps, timing_ms, total_tokens, usage, cost, context_usage, stored_context, context_profile}` |
| `error` | Error | `{error, step}` |
| `paused` | Agent paused | `{step}` |
| `resumed` | Agent resumed | `{step}` |
| `steer` | Steering message injected | `{message}` |
| `cancelled` | Cancelled | `{message}` |
| `heartbeat` | Keep-alive | `{}` |

**Examples**:

```
data: {"seq": 1, "type": "agent_state", "state": "planning", "current_step": 1, "max_steps": 10}

data: {"seq": 2, "type": "step_start", "step_number": 1, "steps_remaining": 9, "context_usage": {"context_window": 262144, "reserved_output_tokens": 32768, "effective_input_budget": 229376, "prompt_tokens_current_call": 21107, "conversation_tokens_active_history": 21107, "remaining_tokens": 208269, "utilization_pct_effective": 9.2, "compaction_threshold_pct": 90, "next_compaction_at_tokens": 206438, "compaction_count": 0}, "stored_context": {"context_window": 262144, "stored_tokens": 6123, "utilization_pct": 2.3, "replayable_entry_count": 14}}

data: {"seq": 3, "type": "thinking", "content": "I need to search for..."}

data: {"seq": 4, "type": "tool_start", "tool_call_id": "tc_001", "tool_name": "web_search", "arguments": {"query": "..."}}

data: {"seq": 4, "type": "tool_approval_required", "tool_call_id": "tc_002", "tool_name": "bash", "arguments": {"command": "npm test"}}

data: {"seq": 5, "type": "tool_result", "tool_call_id": "tc_001", "success": true, "result_summary": "Found 5 results...", "duration_ms": 2500}

data: {"seq": 6, "type": "usage_update", "usage": {"input_tokens": 18420, "output_tokens": 2687, "reasoning_tokens": 0, "cached_tokens": 0, "total_tokens": 21107}, "context_usage": {"context_window": 262144, "reserved_output_tokens": 32768, "effective_input_budget": 229376, "prompt_tokens_current_call": 21107, "conversation_tokens_active_history": 21107, "remaining_tokens": 208269, "utilization_pct_effective": 9.2, "compaction_threshold_pct": 90, "next_compaction_at_tokens": 206438, "compaction_count": 0}, "stored_context": {"context_window": 262144, "stored_tokens": 6123, "utilization_pct": 2.3, "replayable_entry_count": 14}, "context_profile": {"provider_name": "fireworks", "model_id": "accounts/fireworks/models/kimi-k2p6", "display_name": "Kimi K2.6", "context_window": 262144, "max_output_tokens": 32768, "effective_input_budget": 229376, "supports_tools": true, "supports_reasoning": false, "pricing": {"input_cost_per_million": null, "cached_input_cost_per_million": null, "output_cost_per_million": null}, "source": "registry"}}

data: {"seq": 7, "type": "agent_state", "state": "synthesizing", "current_step": 2}

data: {"seq": 8, "type": "answer", "content": "Based on my research"}

data: {"seq": 9, "type": "complete", "success": true, "final_answer": "Based on my research...", "citations": [...], "total_steps": 2, "timing_ms": 15000, "total_tokens": 4250, "usage": {"input_tokens": 18420, "output_tokens": 2687, "reasoning_tokens": 0, "cached_tokens": 0, "total_tokens": 21107}, "stored_context": {"context_window": 262144, "stored_tokens": 6123, "utilization_pct": 2.3, "replayable_entry_count": 14}}

```

### SSE Resumption & Reconnection

Agent streams support resumption and reconnection:

```
GET /api/agent/runs/{run_id}/stream?token=abc123&since_seq=5
```

The server:
1. Replays events from the shared event history with `seq > since_seq`
2. Continues streaming live events from the append-only in-memory history
3. Restores persisted run-event history from SQLite if needed before replay
4. Deduplicates events by sequence number to prevent overlap

The `token` parameter authenticates the stream connection. If provided and invalid, the server returns 403. The token is optional to support reconnection after page reload (before localStorage token is restored).

---

## Error Handling

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - Invalid input |
| 404 | Not Found - Resource doesn't exist |
| 422 | Unprocessable Entity - Validation error |
| 403 | Forbidden - Invalid stream token |
| 429 | Too Many Requests - Rate limit or message limit exceeded |
| 500 | Internal Server Error |

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Validation Errors (422)

```json
{
  "detail": [
    {
      "loc": ["body", "message"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Conversation not found` | Invalid conversation_id | Check ID is correct |
| `Run not found` | Invalid run_id | Check ID is correct |
| `Run not running` | Abort on completed run | Only abort running runs |
| `Provider unavailable` | LLM server down | Start LM Studio/vLLM |
| `Max retries exceeded` | Repeated failures | Check LLM server health |

---

## Related Documentation

- [Architecture](ARCHITECTURE.md) - System architecture overview
- [Data Models](DATA_MODELS.md) - Complete data model reference
- [Data Flow](DATA_FLOW.md) - Request lifecycle and streaming
- [Components](COMPONENTS.md) - Detailed component documentation
