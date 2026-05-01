# Data Models

Complete reference for all data structures in the Fluxion system.

## Table of Contents

1. [Database Schema (SQLite)](#database-schema-sqlite)
2. [Backend Models (Python/Pydantic)](#backend-models-pythonpydantic)
3. [Frontend Types (TypeScript)](#frontend-types-typescript)
4. [Type Mapping Between Layers](#type-mapping-between-layers)

---

## Database Schema (SQLite)

Location: `orchestrator/storage/schema.sql`

### Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DATABASE SCHEMA                                     │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐
│    conversations    │
├─────────────────────┤
│ PK conversation_id  │──────────────────────────────────────┐
│    title            │                                      │
│    summary          │                                      │
│    status           │                                      │
│    created_at       │                                      │
│    metadata_json    │                                      │
│    session_id       │ (demo mode isolation)                │
└─────────────────────┘                                      │
         │                                                   │
         │ 1:N                                               │
         ▼                                                   │
┌─────────────────────┐                                      │
│       runs          │                                      │
├─────────────────────┤                                      │
│ PK run_id           │──────────────────────┐               │
│ FK conversation_id  │◄─────────────────────┼───────────────┘
│    user_message     │                      │
│    system_prompt_   │                      │
│      snapshot       │                      │
│    profile_name     │                      │
│    mode             │                      │
│    model_config_    │                      │
│      snapshot       │                      │
│    final_answer     │                      │
│    thinking_summary │                      │
│    error_message    │                      │
│    status           │                      │
│    last_response_id │                      │
│    usage_stats      │                      │
│    agent_state      │                      │
│    current_step     │                      │
│    max_steps        │                      │
│    session_id       │ (demo mode isolation)│
│    created_at       │                      │
│    updated_at       │                      │
└─────────────────────┘                      │
         │                                   │
         │ 1:N                               │
         ▼                                   │
┌─────────────────────┐                      │
│   trace_events      │                      │
├─────────────────────┤                      │
│ PK id               │◄─────────────────────┼─────┐
│ FK run_id           │◄─────────────────────┘     │
│    seq              │ (UNIQUE with run_id)       │
│    created_at       │                            │
│    event_type       │                            │
│    event_status     │                            │
│    actor            │                            │
│    endpoint         │                            │
│    attempt          │                            │
│    content_json     │                            │
│ FK parent_event_id  │────────────────────────────┘
│    step_number      │
│    duration_ms      │
│    token_count      │
│    error_message    │
└─────────────────────┘

                    ┌─────────────────────────────────────────────┐
                    │              AGENT TABLES                    │
                    └─────────────────────────────────────────────┘

┌─────────────────────┐
│    agent_steps      │
├─────────────────────┤
│ PK id               │──────────────────────┐
│ FK run_id           │◄─ (from runs table)  │
│    step_number      │ (UNIQUE with run_id) │
│    state            │                      │
│    thinking_text    │                      │
│    decision         │                      │
│    error_message    │                      │
│    created_at       │                      │
│    completed_at     │                      │
└─────────────────────┘                      │
         │                                   │
         │ 1:N                               │
         ▼                                   │
┌─────────────────────┐                      │
│  agent_tool_calls   │                      │
├─────────────────────┤                      │
│ PK id               │──────────────────────┼───┐
│ FK run_id           │                      │   │
│ FK step_id          │◄─────────────────────┘   │
│    tool_name        │                          │
│    arguments        │ (JSON)                   │
│    status           │                          │
│    started_at       │                          │
│    completed_at     │                          │
│    duration_ms      │                          │
│    idempotency_key  │                          │
│    execution_attempt│                          │
│    result_summary   │                          │
│    result_detail    │ (full output)            │
│    approval_decision│ (approved/denied/auto)   │
│    approval_policy  │ (strict/relaxed/yolo)    │
│    error_message    │                          │
│    created_at       │                          │
└─────────────────────┘                          │
         │                                       │
         │ 1:N                                   │
         ▼                                       │
┌─────────────────────┐                          │
│  agent_citations    │                          │
├─────────────────────┤                          │
│ PK id               │                          │
│ FK run_id           │                          │
│ FK tool_call_id     │◄─────────────────────────┘
│    source_url       │
│    title            │
│    snippet          │
│    used_in_answer   │ (boolean)
│    created_at       │
└─────────────────────┘
```

### Core Tables

#### conversations

Stores conversation metadata.

| Column | Type | Description |
|--------|------|-------------|
| `conversation_id` | TEXT PK | UUID identifier |
| `title` | TEXT | Auto-generated from first message |
| `summary` | TEXT | Conversation summary |
| `status` | TEXT | `active`, `archived`, `closed` |
| `created_at` | TEXT | ISO 8601 timestamp |
| `updated_at` | TEXT | ISO 8601 timestamp (Migration 7) |
| `metadata_json` | TEXT | Additional metadata (JSON) |
| `session_id` | TEXT | Session UUID for demo mode isolation (Migration 4) |

#### runs

One record per user message/response exchange.

| Column | Type | Description |
|--------|------|-------------|
| `run_id` | TEXT PK | UUID identifier |
| `conversation_id` | TEXT FK | Reference to conversations |
| `user_message` | TEXT | User's input message |
| `system_prompt_snapshot` | TEXT | System prompt at execution time |
| `profile_name` | TEXT | Profile used |
| `mode` | TEXT | Execution mode |
| `model_config_snapshot` | TEXT | Model config (JSON) |
| `final_answer` | TEXT | Model's response |
| `thinking_summary` | TEXT | Cleaned thinking for UI |
| `error_message` | TEXT | Error details if failed |
| `status` | TEXT | `running`, `succeeded`, `failed` |
| `last_response_id` | TEXT | For stateful mode chaining |
| `usage_stats` | TEXT | Token usage (JSON) |
| `agent_state` | TEXT | Agent prompt scaffold/debug snapshot for tracing/debugging; not the primary cross-turn continuation source |
| `current_step` | INTEGER | Current agent step |
| `max_steps` | INTEGER | Maximum agent steps |
| `turn_summary` | TEXT | Compact context string for cross-turn history (Migration 9) |
| `created_at` | TEXT | ISO 8601 timestamp |
| `session_id` | TEXT | Session UUID for demo mode isolation (Migration 4) |
| `updated_at` | TEXT | ISO 8601 timestamp |

**Turn Summary**: After each run completes, a `TurnSummarizer` generates a compact context string from the user message and final answer. This `turn_summary` is still used by `HistoryBuilder` for compact background history. Coding-profile continuation now prefers persisted `coding_session_entries` transcript replay plus lightweight `coding_sessions` metadata, while non-coding runs continue to rely on summary-oriented history.

#### trace_events

Granular timeline of all events in a run.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID identifier |
| `run_id` | TEXT FK | Reference to runs |
| `seq` | INTEGER | Sequence number (UNIQUE with run_id) |
| `created_at` | TEXT | ISO 8601 timestamp |
| `event_type` | TEXT | `llm_request`, `llm_response`, `thinking`, `error`, `retry` |
| `event_status` | TEXT | `pending`, `success`, `error`, `skipped` |
| `actor` | TEXT | `model`, `system`, `tool:<name>` |
| `endpoint` | TEXT | `/v1/responses` or `/v1/chat/completions` |
| `attempt` | INTEGER | Retry attempt number (default 1) |
| `content_json` | TEXT | Event-specific data (JSON) |
| `parent_event_id` | TEXT FK | Reference to parent event |
| `step_number` | INTEGER | Step in thinking process |
| `duration_ms` | INTEGER | Execution duration |
| `token_count` | INTEGER | Tokens used |
| `error_message` | TEXT | Error details if failed |

### Agent Tables

#### terminal_sessions

Persists lightweight browser-terminal metadata per conversation. The live PTY process itself stays in memory.

| Column | Type | Description |
|--------|------|-------------|
| `session_id` | TEXT PK | Current terminal session identifier |
| `conversation_id` | TEXT FK UNIQUE | One browser terminal per conversation |
| `workspace_path` | TEXT | Workspace/cwd used when this shell was started |
| `shell` | TEXT | Executable launched (`/bin/zsh`, `/bin/sh`, etc.) |
| `status` | TEXT | `running`, `closed`, or `stale` |
| `cols` | INTEGER | Last known terminal column count |
| `rows` | INTEGER | Last known terminal row count |
| `session_owner` | TEXT | Demo-mode owner/session binding |
| `created_at` | TEXT | ISO 8601 timestamp |
| `updated_at` | TEXT | ISO 8601 timestamp |
| `last_activity_at` | TEXT | Last input/output timestamp |

#### coding_sessions

Persists durable coding-session state per conversation for coding-profile continuity across turns.

| Column | Type | Description |
|--------|------|-------------|
| `conversation_id` | TEXT PK/FK | Conversation this coding session belongs to |
| `state_json` | TEXT | Structured coding-session bookkeeping state (objective, files, file evidence, recent commands) |
| `last_run_id` | TEXT | Most recent run that updated this session |
| `created_at` | TEXT | ISO 8601 timestamp |
| `updated_at` | TEXT | ISO 8601 timestamp |

**Coding Session State**: The JSON payload is metadata-only bookkeeping. It stores neutral fields such as `objective`, `read_files`, `modified_files`, `recent_commands`, and per-file evidence with stored line spans and freshness hashes. It does **not** act as a natural-language truth layer for “what was fixed”, “root cause”, “next steps”, or checkpoint summaries. `AgentEngine` may use it to decide whether rereads are needed and to render a tiny neutral metadata block, but coding prompt continuity comes from transcript replay.

#### coding_session_entries

Replayable coding-session transcript entries for coding-profile conversations. These rows are the canonical natural-language continuity source for future coding prompts.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID identifier |
| `conversation_id` | TEXT FK | Conversation this entry belongs to |
| `seq` | INTEGER | Monotonic per-conversation sequence number |
| `run_id` | TEXT | Run that produced the entry |
| `step_number` | INTEGER | Agent step that produced the entry, if any |
| `entry_type` | TEXT | `user`, `assistant`, `assistant_tool_calls`, `tool_result`, or replayable synthetic `compaction_summary` |
| `role` | TEXT | Prompt role to reconstruct (`user`, `assistant`, `tool`) |
| `content_json` | TEXT | Canonical replay payload (JSON) |
| `token_estimate` | INTEGER | Estimated token cost of the stored entry |
| `compacted_at` | TEXT | ISO 8601 timestamp when this entry was compacted out of active replay |
| `created_at` | TEXT | ISO 8601 timestamp |

**Coding Session Replay**:
- `CodingSessionContextBuilder` rebuilds coding prompts as `system prompt + optional checkpoint summary + optional neutral metadata + restored file evidence + preserved raw tail`
- transcript entries are replayed in persisted `seq` order, with `compaction_summary` inserted at the compaction boundary so the next turn still feels like one continuous conversation
- only replay-eligible entries are included
- entries marked compacted are excluded from active replay once a newer checkpoint replaces them
- assistant/tool replay stays canonicalized from parsed tool-call arguments and stable tool-result payloads
- structurally bad assistant fallback turns can remain stored with `replay_eligible=false` for debugging while being excluded from continuation prompts

#### agent_steps

Tracks each step in agent execution.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID identifier |
| `run_id` | TEXT FK | Reference to runs |
| `step_number` | INTEGER | Step index (UNIQUE with run_id) |
| `state` | TEXT | `planning`, `tool_calling`, `synthesizing`, `complete`, `error` |
| `thinking_text` | TEXT | Agent's thinking for this step |
| `decision` | TEXT | `call_tool`, `synthesize`, `error` |
| `error_message` | TEXT | Error details if failed |
| `created_at` | TEXT | ISO 8601 timestamp |
| `completed_at` | TEXT | ISO 8601 timestamp |
| `updated_at` | TEXT | ISO 8601 timestamp (Migration 7) |

#### agent_tool_calls

Records individual tool executions, including approval decisions for permission-gated tools.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID identifier |
| `run_id` | TEXT FK | Reference to runs |
| `step_id` | TEXT FK | Reference to agent_steps |
| `tool_name` | TEXT | Tool identifier |
| `arguments` | TEXT | Tool arguments (JSON) |
| `status` | TEXT | `pending`, `running`, `success`, `error`, `timeout`, `interrupted` |
| `started_at` | TEXT | ISO 8601 timestamp |
| `completed_at` | TEXT | ISO 8601 timestamp |
| `duration_ms` | INTEGER | Execution duration |
| `idempotency_key` | TEXT | Hash for crash recovery |
| `execution_attempt` | INTEGER | Retry count |
| `result_summary` | TEXT | Brief result (not full output) |
| `result_detail` | TEXT | Full result (up to 10k chars) for write/edit/bash tools |
| `approval_decision` | TEXT | `approved`, `denied`, `auto`, `timeout` |
| `approval_policy` | TEXT | `strict`, `relaxed`, `yolo` — policy in effect |
| `approval_decided_at` | TEXT | ISO 8601 timestamp of approval/denial |
| `error_message` | TEXT | Error details if failed |
| `created_at` | TEXT | ISO 8601 timestamp |

**Approval Flow**: When a tool's `permission_level` requires user consent (based on the active `approval_policy`), the tool call is created with `status=pending` and `approval_decision=NULL`. The backend emits a `tool_approval_required` SSE event and waits for the user to approve or deny via the API. The `approval_decision` is set when the user responds (or `timeout` after 5 minutes).

#### agent_citations

Stores evidence sources for agent answers.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID identifier |
| `run_id` | TEXT FK | Reference to runs |
| `tool_call_id` | TEXT FK | Reference to agent_tool_calls |
| `source_url` | TEXT | Source URL |
| `title` | TEXT | Source title |
| `snippet` | TEXT | Relevant text snippet |
| `used_in_answer` | INTEGER | Boolean (0/1) |
| `created_at` | TEXT | ISO 8601 timestamp |

#### run_events

Persisted SSE events that survive in-memory cleanup. Provides durable event history for reconnection and debugging.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID identifier |
| `run_id` | TEXT FK | Reference to runs |
| `seq` | INTEGER | Sequence number (UNIQUE with run_id) |
| `event_type` | TEXT | SSE event type (e.g., `step_start`, `tool_start`, `complete`) |
| `event_data` | TEXT | Full event payload (JSON) |
| `created_at` | TEXT | ISO 8601 timestamp |

**Purpose**: While the backend keeps SSE events in-memory (`_event_history`) for active runs, `run_events` provides persistent storage so events survive server restarts and in-memory cleanup.

#### run_artifacts

Tracks file changes and command executions made by agent tools. Enables auditing of what the agent modified.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID identifier |
| `run_id` | TEXT FK | Reference to runs |
| `artifact_type` | TEXT | `file_write`, `file_edit`, `command_run` |
| `file_path` | TEXT | Path of affected file (NULL for commands) |
| `action` | TEXT | Tool that created this: `write_file`, `edit_file`, `bash_tool` |
| `detail` | TEXT | Change summary (diff for edits, output for commands) |
| `tool_call_id` | TEXT FK | Reference to agent_tool_calls |
| `created_at` | TEXT | ISO 8601 timestamp |

#### chatgpt_tokens

Stores ChatGPT OAuth tokens per CLI session. Created via migration (not in schema.sql).

| Column | Type | Description |
|--------|------|-------------|
| `session_id` | TEXT PK | CLI session identifier |
| `access_token` | TEXT | OAuth access token |
| `refresh_token` | TEXT | OAuth refresh token |
| `account_id` | TEXT | OpenAI account ID |
| `expires_at` | INTEGER | Token expiry timestamp |
| `created_at` | TEXT | ISO 8601 timestamp |

### Evaluation Tables

#### eval_runs

Benchmark execution sessions for model evaluation.

| Column | Type | Description |
|--------|------|-------------|
| `eval_run_id` | TEXT PK | UUID identifier |
| `created_at` | TEXT | ISO 8601 timestamp |
| `benchmark_name` | TEXT | Benchmark identifier (e.g., "gpqa_diamond", "mmlu_pro") |
| `model_id` | TEXT | Model being evaluated |
| `policy_name` | TEXT | Strategy: `direct`, `vote`, `cot`, `solve_verify` |
| `policy_config_json` | TEXT | Full policy configuration snapshot |
| `status` | TEXT | `running`, `completed`, `failed`, `cancelled` |
| `total_samples` | INT | Total samples in benchmark |
| `completed_samples` | INT | Samples completed so far |
| `accuracy` | REAL | Final accuracy (0.0 - 1.0) |
| `avg_tokens_per_sample` | REAL | Average token usage |
| `total_duration_ms` | INT | Total execution time |
| `results_json` | TEXT | Detailed aggregate results |
| `error_message` | TEXT | Error details if failed |

#### eval_samples

Individual evaluation samples linked to full traces.

| Column | Type | Description |
|--------|------|-------------|
| `sample_id` | TEXT PK | UUID identifier |
| `eval_run_id` | TEXT FK | Reference to eval_runs |
| `created_at` | TEXT | ISO 8601 timestamp |
| `question_id` | TEXT | ID from benchmark dataset |
| `question_text` | TEXT | The evaluation question |
| `correct_answer` | TEXT | Expected correct answer |
| `model_answer` | TEXT | Model's response |
| `is_correct` | BOOLEAN | Whether answer matches correct answer |
| `run_id` | TEXT FK | Reference to runs table for full trace |
| `thinking_tokens` | INT | Tokens used for thinking |
| `answer_tokens` | INT | Tokens used for answer |
| `total_tokens` | INT | Total tokens used |
| `duration_ms` | INT | Execution duration |
| `status` | TEXT | `pending`, `running`, `completed`, `failed` |
| `error_message` | TEXT | Error details if failed |

### Database Indexes

Indexes are created for performance optimization on frequently queried columns:

| Table | Index Name | Columns | Purpose |
|-------|------------|---------|---------|
| `conversations` | `idx_conversations_created_at` | `created_at` | Sort by creation date |
| `coding_sessions` | `idx_coding_sessions_updated_at` | `updated_at` | Find latest persisted coding sessions |
| `coding_session_entries` | `idx_coding_session_entries_conversation_seq` | `conversation_id, seq` | Replay coding-session history in order |
| `coding_session_entries` | `idx_coding_session_entries_compacted` | `conversation_id, compacted_at, seq` | Find active replay entries efficiently |
| `runs` | `idx_runs_conversation_id` | `conversation_id` | Filter runs by conversation |
| `eval_runs` | `idx_eval_runs_created_at` | `created_at` | Sort by creation date |
| `eval_runs` | `idx_eval_runs_benchmark` | `benchmark_name` | Filter by benchmark |
| `eval_samples` | `idx_eval_samples_eval_run_id` | `eval_run_id` | Filter samples by eval run |
| `eval_samples` | `idx_eval_samples_run_id` | `run_id` | Link to trace data |
| `trace_events` | `idx_trace_events_run_seq` | `run_id, seq` | Ordered event retrieval |
| `trace_events` | `idx_trace_events_type` | `event_type` | Filter by event type |
| `trace_events` | `idx_trace_events_step` | `run_id, step_number` | Filter by step |
| `trace_events` | `idx_trace_events_parent` | `parent_event_id` | Parent-child linking |
| `agent_steps` | `idx_agent_steps_run` | `run_id` | Filter steps by run |
| `agent_steps` | `idx_agent_steps_state` | `state` | Filter by state |
| `agent_tool_calls` | `idx_agent_tool_calls_run` | `run_id` | Filter calls by run |
| `agent_tool_calls` | `idx_agent_tool_calls_step` | `step_id` | Filter calls by step |
| `agent_tool_calls` | `idx_agent_tool_calls_status` | `status` | Filter by status |
| `agent_citations` | `idx_agent_citations_run` | `run_id` | Filter citations by run |
| `run_events` | `idx_run_events_run_seq` | `run_id, seq` | Ordered event retrieval |
| `run_artifacts` | `idx_run_artifacts_run` | `run_id` | Filter artifacts by run |

### Referential Integrity (CASCADE Deletes)

The schema uses `ON DELETE CASCADE` for automatic cleanup when parent records are deleted:

| Child Table | Parent Table | FK Column | Behavior |
|-------------|--------------|-----------|----------|
| `trace_events` | `runs` | `run_id` | Delete events when run deleted |
| `trace_events` | `trace_events` | `parent_event_id` | Delete children when parent deleted |
| `coding_sessions` | `conversations` | `conversation_id` | Delete coding continuity state when conversation deleted |
| `coding_session_entries` | `conversations` | `conversation_id` | Delete coding transcript replay history when conversation deleted |
| `agent_steps` | `runs` | `run_id` | Delete steps when run deleted |
| `agent_tool_calls` | `runs` | `run_id` | Delete calls when run deleted |
| `agent_tool_calls` | `agent_steps` | `step_id` | Delete calls when step deleted |
| `agent_citations` | `runs` | `run_id` | Delete citations when run deleted |
| `agent_citations` | `agent_tool_calls` | `tool_call_id` | Delete citations when call deleted |
| `eval_samples` | `eval_runs` | `eval_run_id` | Delete samples when eval run deleted |
| `eval_samples` | `runs` | `run_id` | Delete samples when run deleted |
| `run_events` | `runs` | `run_id` | Delete events when run deleted |
| `run_artifacts` | `runs` | `run_id` | Delete artifacts when run deleted |
| `run_artifacts` | `agent_tool_calls` | `tool_call_id` | Delete artifacts when call deleted |

**Note**: Deleting a `conversation` record will automatically cascade to remove its persisted `coding_sessions` row and `coding_session_entries`. Deleting a `runs` record will automatically cascade to remove all related `trace_events`, `agent_steps`, `agent_tool_calls`, `agent_citations`, `run_events`, and `run_artifacts`.

---

## Backend Models (Python/Pydantic)

### API Schemas (`orchestrator/schemas.py`)

#### Request Models

```python
class CreateConversationRequest(BaseModel):
    title: Optional[str] = None

class CreateConversationRunRequest(BaseModel):
    message: str
    thinking_mode: Optional[str] = "default"  # "default" or "thinking"
    reasoning_effort: Optional[str] = None    # "low", "medium", "high"

class CreateRunRequest(BaseModel):
    prompt: str
    mode: Optional[str] = "default"
    profile: Optional[str] = "default"

class CreateAgentRunRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None
    max_steps: int = 10

class CreateAgentRunResponse(BaseModel):
    run_id: str
    status: str
    stream_url: str        # Includes token query param
    stream_token: str      # Per-run secret for SSE auth
```

#### Response Models

```python
class ConversationResponse(BaseModel):
    conversation_id: str
    title: Optional[str]
    summary: Optional[str]
    status: str
    created_at: str
    metadata: Optional[dict]

class ConversationDetailResponse(BaseModel):
    conversation: ConversationResponse
    runs: List[RunResponse]

class RunResponse(BaseModel):
    run_id: str
    created_at: str
    status: str
    mode: str = "chat"
    profile: str = "chat"
    prompt: str = ""
    user_message: Optional[str] = None
    conversation_id: Optional[str] = None
    conversation_summary: Optional[str] = None
    final_answer: Optional[str] = None
    final_report: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    thinking_summary: Optional[str] = None

class EventResponse(BaseModel):
    run_id: str
    seq: int
    ts: str
    type: str
    display: dict  # {title, summary, status?, result_preview?}
    payload: dict
```

#### Trace/Timeline Models

```python
class TraceEventResponse(BaseModel):
    id: str
    run_id: str
    seq: int
    created_at: str
    event_type: str      # llm_request, llm_response, thinking, error, retry
    event_status: str    # pending, success, error, skipped
    actor: str           # model, system, tool:<name>
    endpoint: Optional[str]
    attempt: int
    content: dict
    parent_event_id: Optional[str]
    step_number: Optional[int]
    duration_ms: Optional[int]
    token_count: Optional[int]
    error_message: Optional[str]

class RunTimelineResponse(BaseModel):
    run_id: str
    status: str
    created_at: str
    events: List[TraceEventResponse]
    total_events: int
```

#### Agent Models

```python
class AgentStepState(str, Enum):
    PLANNING = "planning"
    TOOL_CALLING = "tool_calling"
    SYNTHESIZING = "synthesizing"
    PAUSED = "paused"
    COMPLETE = "complete"
    ERROR = "error"

class AgentToolCallStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"

class AgentStepResponse(BaseModel):
    id: str
    run_id: str
    step_number: int
    state: AgentStepState
    thinking_text: Optional[str]
    decision: Optional[str]
    created_at: str
    completed_at: Optional[str]
    error_message: Optional[str]

class AgentToolCallResponse(BaseModel):
    id: str
    run_id: str
    step_id: str
    tool_name: str
    arguments: dict
    status: AgentToolCallStatus
    result_summary: Optional[str]
    result_detail: Optional[str]          # Full output for write/edit/bash tools
    approval_decision: Optional[str]      # approved | denied | auto | timeout
    approval_policy: Optional[str]        # strict | relaxed | yolo
    approval_decided_at: Optional[str]    # ISO 8601 timestamp
    error_message: Optional[str]
    duration_ms: Optional[int]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    idempotency_key: str
    execution_attempt: int

class AgentCitationResponse(BaseModel):
    id: str
    run_id: str
    tool_call_id: str
    source_url: str
    title: Optional[str]
    snippet: str
    used_in_answer: bool
    created_at: str

class AgentRunStatusResponse(BaseModel):
    run_id: str
    status: str
    agent_state: Optional[str]
    current_step: Optional[int]
    max_steps: Optional[int]
    final_answer: Optional[str]
    created_at: str
    updated_at: Optional[str]

class RunArtifactResponse(BaseModel):
    id: str
    run_id: str
    artifact_type: str       # file_write | file_edit | command_run
    file_path: Optional[str]
    action: str              # write_file | edit_file | bash_tool
    detail: Optional[str]
    tool_call_id: Optional[str]
    created_at: str

class AgentRunTraceResponse(BaseModel):
    run_id: str
    status: str
    steps: List[AgentStepResponse]
    tool_calls: List[AgentToolCallResponse]
    citations: List[AgentCitationResponse]
    artifacts: List[RunArtifactResponse]     # File changes and commands
    final_answer: Optional[str]
    agent_state: Optional[str]
```

#### Local Model Schemas

```python
class LocalModelSchema(BaseModel):
    """A GGUF model available on disk."""
    path: str              # Full filesystem path to .gguf file
    name: str              # Display name (derived from filename)
    size_bytes: int        # File size in bytes
    size_display: str      # Human-readable size ("35.0 GB")

class StartModelRequest(BaseModel):
    """Request to start llama-server with a local model."""
    model_path: str                    # Path to GGUF file
    ctx_size: Optional[int] = None     # Context window (None = use config default)

class ModelStatusResponse(BaseModel):
    """Current provider status."""
    provider: str              # "local" or "cloud"
    model_name: Optional[str]  # Active model name
    base_url: Optional[str]    # Active provider URL
    local_running: bool        # Whether llama-server is running
    context_window: int
    max_output_tokens: int
    effective_input_budget: int
    supports_tools: bool
    supports_reasoning: bool
    source: str
```

#### Normalized Context Profile (`orchestrator/context/context_profile.py`)

```python
@dataclass
class ModelContextProfile:
    provider_name: str
    model_id: str
    display_name: str
    context_window: int
    max_output_tokens: int
    supports_tools: bool
    supports_reasoning: bool
    pricing: dict[str, Optional[float]]
    source: str

    @property
    def effective_input_budget(self) -> int: ...
```

#### Tool Models

```python
class ToolCall(BaseModel):
    """OpenAI-compatible tool call format."""
    id: str
    type: str = "function"
    function: dict  # {name: str, arguments: str (JSON)}

class ToolResponse(BaseModel):
    tool_call_id: str
    output: str

class ToolDefinition(BaseModel):
    """OpenAI-compatible tool definition."""
    type: str = "function"
    function: dict  # {name, description, parameters (JSON Schema)}
```

### Configuration Models (`orchestrator/config.py`)

```python
class ProviderConfig(BaseModel):
    # Note: Class defaults shown. This repo's YAML currently defaults to Fireworks.
    base_url: str = "http://127.0.0.1:1234"  # YAML default: ${LLM_BASE_URL:-https://api.fireworks.ai/inference/v1}
    api_key: Optional[str] = None            # YAML default: ${LLM_API_KEY:-}
    endpoint: str = "responses"              # YAML default: chat_completions
    fallback_on_404: bool = True
    fail_on_tool_fallback: bool = True
    timeout: float = 120.0
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    retryable_statuses: List[int] = [429, 500, 502, 503, 504]
    state_mode: str = "stateless"    # stateless | stateful_opt_in
    extra_headers: dict = {}

class ChatModelConfig(BaseModel):
    # Note: YAML config currently sets name to accounts/fireworks/models/kimi-k2p6 by default
    name: str = "openai/gpt-oss-20b"  # YAML default: ${LLM_MODEL:-accounts/fireworks/models/kimi-k2p6}
    temperature: float = 0.7          # YAML override: 1.0
    max_tokens: int = 4096            # YAML override: 32768
    seed: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    reasoning_effort: Optional[str] = None  # low | medium | high (YAML: "medium")

class ChatContextConfig(BaseModel):
    max_messages: int = 50
    max_tokens: int = 6000            # YAML override: 100000 fallback context budget
    reserve_for_response: int = 2048  # YAML override: 16384 fallback reserve
    truncation_strategy: str = "sliding_window"  # sliding_window | oldest_first

class ThinkingConfig(BaseModel):
    mode_mapping: dict = {"default": "direct", "thinking": "direct"}
    tracing: dict = {"save_internal": True, "save_user_summary": True}
    ui: dict = {"show_thinking": False, "collapsible": True}

class CircuitBreakerConfig(BaseModel):
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    success_threshold: int = 2

class ChatConfig(BaseModel):
    provider: ProviderConfig
    model: ChatModelConfig
    context: ChatContextConfig
    thinking: ThinkingConfig
    system_prompt: str
    # ... tool configs (parallel, sandbox, etc.)
```

### Provider Models (`orchestrator/providers/base.py`)

```python
@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    text: str
    tool_calls: Optional[List[Dict]] = None
    reasoning: Optional[str] = None           # Native reasoning (gpt-oss)
    response_id: Optional[str] = None         # For stateful mode
    endpoint_used: str = ""                   # Which endpoint was used
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"

class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    async def complete(
        self,
        messages: List[Dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
        tools: Optional[List[Dict]] = None,
        reasoning_effort: Optional[str] = None,
    ) -> LLMResponse: ...

    async def complete_streaming(
        self,
        messages: List[Dict],
        on_token: Optional[Callable[[str], None]] = None,
        on_reasoning: Optional[Callable[[str], None]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
        reasoning_effort: Optional[str] = None,
    ) -> LLMResponse: ...

    async def health_check(self) -> bool: ...
    async def close(self) -> None: ...
```

### Thinking Models (`orchestrator/thinking/base.py`)

```python
@dataclass
class ThinkingStep:
    """One step in the thinking process."""
    seq: int
    step_type: str              # "reasoning", "critique", "verification"
    raw_content: str            # Full unfiltered output
    messages_sent: List[dict]   # Messages sent to model
    tokens: Dict[str, int]      # {"input": N, "output": N}
    timing_ms: int
    metadata: dict
    # User-facing
    ui_summary: str             # Clean summary for UI
    ui_status: str              # "thinking", "verifying", "done"

@dataclass
class ThinkingResult:
    """Final result from a thinking strategy."""
    steps: List[ThinkingStep]   # Internal trace
    final_answer: str
    thinking_summary: str       # For UI display
    thinking_tokens: int
    answer_tokens: int
    metadata: dict

class ThinkingStrategy(ABC):
    """Abstract base for thinking strategies."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def think(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable] = None,
    ) -> ThinkingResult: ...
```

### Context Budget (`orchestrator/context/budget.py`)

```python
@dataclass
class ContextBudget:
    """Token budget for a single agent turn."""
    max_tokens: int                        # Total context window
    reserve_for_response: int              # Held back for generation
    system_prompt_tokens: int = 0          # System prompt cost
    plan_tokens: int = 0                   # Plan / scratchpad cost
    current_query_tokens: int = 0          # Current user query cost
    history_tokens: int = 0                # Cross-turn history cost

    # Properties
    available_for_history: int             # max_tokens - reserve - system - plan - query
    total_used: int                        # Sum of all non-reserve buckets
    utilization_pct: float                 # total_used / max_tokens * 100
```

**Current Agent Usage Accounting**:
- `context_usage` reports current-call prompt accounting: `context_window`, `reserved_output_tokens`, `effective_input_budget`, `prompt_tokens_current_call`, `remaining_tokens`, utilization, and compaction counters
- `stored_context` reports replayable stored coding context: `stored_tokens`, `context_window`, `utilization_pct`, and `replayable_entry_count`
- browser footer `raw` is derived by summing normalized provider `usage.total_tokens` across runs in the conversation

### Turn Summary (`orchestrator/context/turn_summary.py`)

```python
@dataclass
class TurnSummary:
    """Compact record of a completed turn for cross-turn history."""
    run_id: str                            # Owning run
    mode: str                              # "chat" | "agent"
    query_brief: str                       # ~120 chars, user intent
    answer_brief: str                      # ~200-300 chars, key outcome
    tools_used: list[str]                  # Tool names invoked
    files_touched: list[str]               # Paths read/written
    key_findings: str                      # Most important result
    token_cost: int                        # Tokens this summary consumes
```

`TurnSummarizer` no longer falls back to historical thinking text when generating stored cross-turn summaries.

### Agent Models (`orchestrator/agent/agent_engine.py`)

```python
@dataclass
class AgentResult:
    """Final result from agent execution."""
    run_id: str
    success: bool
    final_answer: Optional[str] = None
    citations: List[Dict[str, Any]] = field(default_factory=list)
    total_steps: int = 0
    error_message: Optional[str] = None
    timing_ms: int = 0           # Total execution duration
    total_tokens: int = 0        # Total LLM tokens used across all steps
```

---

## Frontend Types (TypeScript)

### Core Types (`ui/src/types/index.ts`)

```typescript
interface ThinkingStep {
  seq: number;
  step_type: string;
  summary: string;
  status: string;
}

interface Run {
  run_id: string;
  created_at: string;
  status: 'running' | 'succeeded' | 'failed';
  mode: string;
  profile: string;
  prompt: string;
  user_message?: string;
  conversation_id?: string;
  conversation_summary?: string;
  final_answer?: string;
  final_report?: string;
  thinking_summary?: string;
  error_code?: string;
  error_detail?: string;
}

interface Event {
  run_id: string;
  seq: number;
  ts: string;
  type: string;
  display: {
    title: string;
    summary: string;
    status?: string;
    result_preview?: string;
  };
  payload: Record<string, unknown>;
}

interface Conversation {
  conversation_id: string;
  created_at: string;
  title?: string;
  summary?: string;
  status: string;
  metadata?: Record<string, unknown>;
}

interface CreateRunRequest {
  prompt: string;
  mode?: string;
  profile?: string;
}

interface CreateRunResponse {
  run_id: string;
  stream_url: string;
}

interface CreateConversationRunRequest {
  message: string;
  thinking_mode?: string;
  reasoning_effort?: string;
}
```

### Agent Types (`ui/src/types/agent.ts`)

```typescript
// Enums (mirror backend)
type AgentStepState =
  | 'planning'
  | 'tool_calling'
  | 'synthesizing'
  | 'complete'
  | 'error';

type AgentToolCallStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'error'
  | 'timeout'
  | 'interrupted';

type AgentSSEEventType =
  | 'agent_state'
  | 'step_start'
  | 'thinking'
  | 'tool_start'
  | 'tool_result'
  | 'answer'
  | 'complete'
  | 'error'
  | 'paused'
  | 'resumed'
  | 'steer'
  | 'cancelled'
  | 'heartbeat';

// Data Models
interface AgentStep {
  id: string;
  run_id: string;
  step_number: number;
  state: AgentStepState;
  thinking_text?: string;
  decision?: string;
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

interface AgentToolCall {
  id: string;
  run_id: string;
  step_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: AgentToolCallStatus;
  result_summary?: string;
  error_message?: string;
  duration_ms?: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  idempotency_key: string;
  execution_attempt: number;
}

interface AgentCitation {
  id: string;
  run_id: string;
  tool_call_id: string;
  source_url: string;
  title?: string;
  snippet: string;
  used_in_answer: boolean;
  created_at: string;
}

interface AgentRunStatus {
  run_id: string;
  status: string;
  agent_state?: string;
  current_step?: number;
  max_steps?: number;
  final_answer?: string;
  created_at: string;
  updated_at?: string;
}

interface AgentRunTrace {
  run_id: string;
  status: string;
  steps: AgentStep[];
  tool_calls: AgentToolCall[];
  citations: AgentCitation[];
  final_answer?: string;
  agent_state?: string;
}

// UI State
interface AgentUIState {
  isActive: boolean;
  currentStep: number;
  maxSteps: number;
  agentState: string;
  thinkingBuffer: string;
  answerBuffer: string;
  steps: AgentStep[];
  toolCalls: AgentToolCall[];
  citations: AgentCitation[];
  lastSeq: number;
  timing_ms?: number;           // Total execution duration
  total_tokens?: number;        // Total LLM tokens used
  context_tokens?: number;      // Tokens used in current context
  context_remaining?: number;   // Tokens remaining in budget
  isPaused?: boolean;           // Whether the run is currently paused
  injectedSteers?: string[];   // Steering messages injected into the run
}

// SSE Event Types (discriminated union)
interface AgentStateEvent {
  type: 'agent_state';
  state: string;
  current_step: number;
  max_steps: number;
}

interface StepStartEvent {
  type: 'step_start';
  step_number: number;
  steps_remaining: number;
  context_tokens?: number;
  context_remaining?: number;
}

interface ThinkingEvent {
  type: 'thinking';
  content: string;
}

interface ToolStartEvent {
  type: 'tool_start';
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
}

interface ToolResultEvent {
  type: 'tool_result';
  tool_call_id: string;
  success: boolean;
  result_summary?: string;
  error_message?: string;
  duration_ms?: number;
}

interface AnswerEvent {
  type: 'answer';
  content: string;
}

interface CompleteEvent {
  type: 'complete';
  success: boolean;
  final_answer?: string;
  citations: AgentCitation[];
  total_steps: number;
  timing_ms: number;
  total_tokens?: number;   // Total LLM tokens used across all steps
}

interface PausedEvent {
  type: 'paused';
  step: number;
}

interface ResumedEvent {
  type: 'resumed';
  step: number;
}

interface SteerEvent {
  type: 'steer';
  message: string;
}

type AgentSSEEvent =
  | AgentStateEvent
  | StepStartEvent
  | ThinkingEvent
  | ToolStartEvent
  | ToolResultEvent
  | AnswerEvent
  | CompleteEvent
  | PausedEvent
  | ResumedEvent
  | SteerEvent;
```

### Store State Types

```typescript
interface AppState {
  // Conversations
  conversations: Conversation[];
  selectedConversationId: string | null;

  // Runs
  runsByConversation: Record<string, Run[]>;
  selectedRunId: string | null;

  // Events
  eventsByRun: Record<string, Event[]>;

  // Streaming
  streamingRunId: string | null;
  streamingText: Record<string, string>;      // runId → partial response
  streamingThinking: Record<string, string>;  // runId → partial thinking

  // Agent State
  agentRunState: Record<string, AgentUIState>;

  // UI
  detailPanelOpen: boolean;
  selectedEventSeq: number | null;

  // Connection
  isConnected: boolean;
  isLoading: boolean;
  error: string | null;
  fetchingRuns: Set<string>;
}
```

---

## Type Mapping Between Layers

### Backend → Frontend Mapping

| Backend (Python) | Frontend (TypeScript) | Notes |
|-----------------|----------------------|-------|
| `ConversationResponse` | `Conversation` | Direct mapping |
| `RunResponse` | `Run` | Direct mapping |
| `EventResponse` | `Event` | Direct mapping |
| `AgentStepResponse` | `AgentStep` | Direct mapping |
| `AgentToolCallResponse` | `AgentToolCall` | Direct mapping |
| `AgentCitationResponse` | `AgentCitation` | Direct mapping |
| `AgentRunStatusResponse` | `AgentRunStatus` | Direct mapping |
| `AgentRunTraceResponse` | `AgentRunTrace` | Direct mapping |

### Database → Backend Mapping

| Database Column | Backend Type | Transformation |
|----------------|--------------|----------------|
| `TEXT` (JSON) | `dict`, `List[T]` | `json.loads()` |
| `TEXT` (timestamp) | `str` | ISO 8601 format |
| `INTEGER` (boolean) | `bool` | 0/1 → False/True |
| `TEXT` (enum) | `str` or `Enum` | String value |

### SSE Event Mapping

| Backend Event | Frontend Event Type | Notes |
|--------------|---------------------|-------|
| `agent_started` | `agent_state` | Mapped via `_EVENT_TYPE_MAP` |
| `step_started` | `step_start` | |
| `thinking` | `thinking` | |
| `tool_start` | `tool_start` | |
| `tool_result` | `tool_result` | |
| `synthesizing` | `agent_state` | |
| `answer_token` | `answer` | |
| `agent_complete` | `complete` | |
| `agent_error` | `error` | |
| `paused` | `paused` | Agent blocked between steps |
| `resumed` | `resumed` | Agent unblocked |
| `steer_injected` | `steer` | Steering message added to context |
| `agent_cancelled` | `cancelled` | |

---

## Related Documentation

- [Architecture](ARCHITECTURE.md) - System architecture overview
- [Data Flow](DATA_FLOW.md) - Request lifecycle and streaming
- [Components](COMPONENTS.md) - Detailed component documentation
- [API Reference](API_REFERENCE.md) - Complete API documentation
