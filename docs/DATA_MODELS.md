# Data Models

Complete reference for all data structures in the Reasoner system.

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
| `metadata_json` | TEXT | Additional metadata (JSON) |

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
| `agent_state` | TEXT | Agent execution state |
| `current_step` | INTEGER | Current agent step |
| `max_steps` | INTEGER | Maximum agent steps |
| `created_at` | TEXT | ISO 8601 timestamp |
| `updated_at` | TEXT | ISO 8601 timestamp |

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

#### agent_tool_calls

Records individual tool executions.

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
| `error_message` | TEXT | Error details if failed |
| `created_at` | TEXT | ISO 8601 timestamp |

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

### Referential Integrity (CASCADE Deletes)

The schema uses `ON DELETE CASCADE` for automatic cleanup when parent records are deleted:

| Child Table | Parent Table | FK Column | Behavior |
|-------------|--------------|-----------|----------|
| `trace_events` | `runs` | `run_id` | Delete events when run deleted |
| `trace_events` | `trace_events` | `parent_event_id` | Delete children when parent deleted |
| `agent_steps` | `runs` | `run_id` | Delete steps when run deleted |
| `agent_tool_calls` | `runs` | `run_id` | Delete calls when run deleted |
| `agent_tool_calls` | `agent_steps` | `step_id` | Delete calls when step deleted |
| `agent_citations` | `runs` | `run_id` | Delete citations when run deleted |
| `agent_citations` | `agent_tool_calls` | `tool_call_id` | Delete citations when call deleted |
| `eval_samples` | `eval_runs` | `eval_run_id` | Delete samples when eval run deleted |
| `eval_samples` | `runs` | `run_id` | Delete samples when run deleted |

**Note**: Deleting a `runs` record will automatically cascade to remove all related `trace_events`, `agent_steps`, `agent_tool_calls`, and `agent_citations`.

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
    mode: str
    profile: str
    prompt: str
    user_message: Optional[str]
    conversation_id: Optional[str]
    final_answer: Optional[str]
    thinking_summary: Optional[str]
    thinking_steps: Optional[List[ThinkingStepResponse]]
    strategy: Optional[str]
    error_code: Optional[str]
    error_detail: Optional[str]

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

class AgentRunTraceResponse(BaseModel):
    run_id: str
    status: str
    steps: List[AgentStepResponse]
    tool_calls: List[AgentToolCallResponse]
    citations: List[AgentCitationResponse]
    final_answer: Optional[str]
    agent_state: Optional[str]
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
    # Note: Class defaults shown. YAML config overrides to DeepInfra by default.
    base_url: str = "http://127.0.0.1:1234"  # YAML default: https://api.deepinfra.com/v1/openai
    api_key: Optional[str] = None            # YAML default: ${DEEPINFRA_API_KEY:-}
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
    # Note: YAML config sets name to openai/gpt-oss-120b by default
    name: str = "openai/gpt-oss-20b"  # YAML default: ${LLM_MODEL:-openai/gpt-oss-120b}
    temperature: float = 0.7          # YAML override: 1.0
    max_tokens: int = 4096
    seed: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    reasoning_effort: Optional[str] = None  # low | medium | high (YAML: "medium")

class ChatContextConfig(BaseModel):
    max_messages: int = 50
    max_tokens: int = 6000
    reserve_for_response: int = 2048
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
  thinking_steps?: ThinkingStep[];
  error_code?: string;
  error_detail?: string;
  strategy?: string;
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
  final_answer?: string;
  citations: AgentCitation[];
  total_steps: number;
  timing_ms: number;
}

type AgentSSEEvent =
  | AgentStateEvent
  | StepStartEvent
  | ThinkingEvent
  | ToolStartEvent
  | ToolResultEvent
  | AnswerEvent
  | CompleteEvent;
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
| `agent_cancelled` | `cancelled` | |

---

## Related Documentation

- [Architecture](ARCHITECTURE.md) - System architecture overview
- [Data Flow](DATA_FLOW.md) - Request lifecycle and streaming
- [Components](COMPONENTS.md) - Detailed component documentation
- [API Reference](API_REFERENCE.md) - Complete API documentation
