# API Reference

Complete documentation of all API endpoints in the Reasoner system.

## Table of Contents

1. [Overview](#overview)
2. [Conversations](#conversations)
3. [Runs](#runs)
4. [Agent Runs](#agent-runs)
5. [Benchmarks](#benchmarks)
6. [System](#system)
7. [SSE Streaming](#sse-streaming)
8. [Error Handling](#error-handling)

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
  "max_steps": 10
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | Yes | - | Research query |
| `conversation_id` | string | No | null | Optional conversation |
| `max_steps` | int | No | 10 | Maximum agent steps |

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
  "created_at": "2024-01-15T10:31:00Z",
  "updated_at": "2024-01-15T10:31:30Z"
}
```

**Status Values**:
- `running` - Agent is executing
- `complete` - Agent finished successfully
- `error` - Agent encountered an error
- `cancelled` - User cancelled

**Agent State Values**:
- `init` - Starting
- `planning` - Deciding action
- `tool_calling` - Executing tools
- `synthesizing` - Generating answer
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
      "error_message": null,
      "duration_ms": 2500,
      "created_at": "2024-01-15T10:31:01Z",
      "started_at": "2024-01-15T10:31:01Z",
      "completed_at": "2024-01-15T10:31:03Z",
      "idempotency_key": "abc123def456",
      "execution_attempt": 1
    }
  ],
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

**Reconnection**: On reconnect (e.g., page reload), the server replays all past events from in-memory history, then continues streaming live events. Events already replayed are deduplicated by sequence number.

See [SSE Streaming](#sse-streaming) for event format.

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
      "base_url": "https://api.deepinfra.com/v1/openai",
      "endpoint": "chat_completions",
      "fallback_on_404": true,
      "timeout": 120.0
    },
    "model": {
      "name": "openai/gpt-oss-120b",
      "temperature": 1.0,
      "max_tokens": 4096,
      "reasoning_effort": "medium"
    },
    "context": {
      "max_messages": 50,
      "max_tokens": 6000,
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

Note: The response is wrapped in a `config` key and shows values from `chat_config.yaml`. Default provider is DeepInfra cloud - override with `LLM_BASE_URL` environment variable for local providers.

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
| `tool_result` | Tool finished | `{tool_call_id, success, result_summary, duration_ms}` |
| `answer` | Answer token | `{content}` |
| `complete` | Agent done | `{success, final_answer, citations, total_steps, timing_ms, total_tokens}` |
| `error` | Error | `{error, step}` |
| `cancelled` | Cancelled | `{message}` |
| `heartbeat` | Keep-alive | `{}` |

**Examples**:

```
data: {"seq": 1, "type": "agent_state", "state": "planning", "current_step": 1, "max_steps": 10}

data: {"seq": 2, "type": "step_start", "step_number": 1, "steps_remaining": 9}

data: {"seq": 3, "type": "thinking", "content": "I need to search for..."}

data: {"seq": 4, "type": "tool_start", "tool_call_id": "tc_001", "tool_name": "web_search", "arguments": {"query": "..."}}

data: {"seq": 5, "type": "tool_result", "tool_call_id": "tc_001", "success": true, "result_summary": "Found 5 results...", "duration_ms": 2500}

data: {"seq": 6, "type": "agent_state", "state": "synthesizing", "current_step": 2}

data: {"seq": 7, "type": "answer", "content": "Based on my research"}

data: {"seq": 8, "type": "complete", "success": true, "final_answer": "Based on my research...", "citations": [...], "total_steps": 2, "timing_ms": 15000, "total_tokens": 4250}

```

### SSE Resumption & Reconnection

Agent streams support resumption and reconnection:

```
GET /api/agent/runs/{run_id}/stream?token=abc123&since_seq=5
```

The server:
1. Replays events from in-memory history with `seq > since_seq`
2. Continues streaming live events from the queue
3. Deduplicates events by sequence number to prevent overlap

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
