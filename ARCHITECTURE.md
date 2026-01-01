# Reasoner Architecture

This document provides comprehensive technical documentation of the Reasoner system, including code examples, data flows, and API specifications.

## Table of Contents

1. [System Overview](#system-overview)
2. [Backend Architecture](#backend-architecture)
3. [Provider Abstraction](#provider-abstraction)
4. [Thinking System](#thinking-system)
5. [Trace Events System](#trace-events-system)
6. [Data Flow](#data-flow)
7. [Data Model](#data-model)
8. [API Surface](#api-surface)
9. [Frontend Architecture](#frontend-architecture)
10. [Configuration](#configuration)

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                   USER                                       │
│                              ┌───────────┐                                  │
│                              │  Browser  │                                  │
│                              └─────┬─────┘                                  │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────────────────┐
│                        FRONTEND - React + Vite (:3000)                       │
│  ┌─────────────────┐   ┌─────────────────┐   ┌──────────────────────────┐   │
│  │  Conversation    │───│  Zustand Store  │───│      SSE Hook            │   │
│  │  Views & UI      │   │  (app state)    │   │  (stream tokens/events)  │   │
│  └─────────────────┘   └─────────────────┘   └───────────┬──────────────┘   │
└──────────────────────────────────────────────────────────┼──────────────────┘
                                     │ REST API            │ SSE stream
                                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKEND - FastAPI (:9000)                            │
│  ┌──────────────┐   ┌────────────────────┐   ┌──────────────────────────┐   │
│  │   Routes     │───│    ChatEngine      │───│    Provider Layer        │   │
│  │ /api/*       │   │  orchestration     │   │  LLMProvider protocol    │   │
│  └──────────────┘   └─────────┬──────────┘   └──────────────────────────┘   │
│                               │                                              │
│  ┌──────────────┐   ┌─────────▼──────────┐   ┌──────────────────────────┐   │
│  │ Repositories │   │ ThinkingOrchestrator│   │      Trace Events       │   │
│  │ SQLite DAOs  │   │  strategy routing   │   │  timeline recording     │   │
│  └──────────────┘   └────────────────────┘   └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────┐  ┌─────────────────────────────────┐
│    LLM Server (LM Studio / vLLM)       │  │      SQLite (var/traces.sqlite) │
│    OpenAI-compatible API               │  │  conversations | runs | events  │
└────────────────────────────────────────┘  └─────────────────────────────────┘
```

---

## Backend Architecture

### Entry Point (`orchestrator/app.py`)

FastAPI application with CORS, routers, and lifespan hook.

```python
app = FastAPI(title="Reasoner API", lifespan=lifespan)

# CORS for UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(conversations.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
```

### Core Orchestration (`orchestrator/engine/chat_engine.py`)

The `ChatEngine` coordinates model calls, thinking strategies, and trace recording.

```python
class ChatEngine:
    def __init__(self, config: ChatConfig, trace_repo: TraceRepo):
        self.config = config
        self.trace_repo = trace_repo
        self.provider = create_provider(config.provider, config.model)
        self.thinking_orchestrator = ThinkingOrchestrator(default_strategy="direct")

    async def chat(
        self,
        conversation_id: str,
        message: str,
        run_id: str,
        event_callback: Optional[Callable] = None,
        thinking_strategy: str = "direct",
        reasoning_effort: Optional[str] = None,
    ) -> dict:
        # 1. Load conversation history
        # 2. Build message list
        # 3. Create run record
        # 4. Execute thinking strategy
        # 5. Record trace events
        # 6. Return result
```

**Key Methods**:

- `chat()` - Main entry point for processing a message
- `_call_model_streaming()` - Handles streaming with token callbacks
- `_build_messages()` - Constructs message list from history

---

## Provider Abstraction

The provider layer (`orchestrator/providers/`) abstracts all LLM interactions.

### LLMProvider Protocol (`base.py`)

```python
from typing import Protocol, Optional, Callable, List, Dict
from dataclasses import dataclass

@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    text: str
    tool_calls: Optional[List[Dict]] = None
    reasoning: Optional[str] = None          # Native reasoning (gpt-oss)
    endpoint_used: str = ""                   # /v1/responses or /v1/chat/completions
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    response_id: Optional[str] = None        # For stateful mode chaining

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
    ) -> LLMResponse:
        """Non-streaming completion."""
        ...

    async def complete_streaming(
        self,
        messages: List[Dict],
        on_token: Optional[Callable[[str], None]] = None,
        on_reasoning: Optional[Callable[[str], None]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
        reasoning_effort: Optional[str] = None,
    ) -> LLMResponse:
        """Streaming completion with token callbacks."""
        ...
```

### OpenAI-Compatible Client (`openai_compat.py`)

```python
class OpenAICompatProvider:
    """OpenAI-compatible provider for LM Studio, vLLM, Ollama, etc."""

    def __init__(self, config: ProviderConfig, model_config: ModelConfig):
        self.base_url = config.base_url
        self.api_key = config.api_key
        self.endpoint = config.endpoint  # "responses" | "chat_completions" | "auto"
        self.fallback_on_404 = config.fallback_on_404
        self.model = model_config.name
        # Retry configuration
        self.max_retries = config.max_retries
        self.base_delay = config.base_delay
        self.max_delay = config.max_delay
```

### Dual Endpoint Support

The provider supports two OpenAI endpoints:

| Endpoint | Path | Features |
|----------|------|----------|
| `responses` | `/v1/responses` | Full agent/tool support, native reasoning |
| `chat_completions` | `/v1/chat/completions` | Standard chat, wider compatibility |

**Fallback Logic**:
1. If `endpoint: "responses"` and `fallback_on_404: true`:
   - Try `/v1/responses` first
   - On 404/405, fall back to `/v1/chat/completions`
2. Result is cached for the session

### Retry Logic

Exponential backoff with jitter for transient failures:

```python
async def _retry_request(self, request_fn):
    for attempt in range(self.max_retries):
        try:
            return await request_fn()
        except HTTPStatusError as e:
            if e.response.status_code in self.retryable_statuses:
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                jitter = random.uniform(0, delay * 0.1)
                await asyncio.sleep(delay + jitter)
            else:
                raise
    raise MaxRetriesExceeded()
```

### Native Reasoning (gpt-oss)

For gpt-oss models, reasoning is captured via a separate callback:

```python
async def complete_streaming(
    self,
    messages,
    on_token=None,
    on_reasoning=None,  # Receives reasoning tokens separately
    reasoning_effort="medium",
    ...
) -> LLMResponse:
    # Response includes reasoning field
    # on_reasoning called with reasoning tokens during streaming
```

---

## Thinking System

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     ThinkingOrchestrator                         │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │  DirectStrategy │  │  CoTStrategy    │                       │
│  │  (single call)  │  │  (two-phase)    │                       │
│  └─────────────────┘  └─────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        StreamParser                              │
│  Separates [THINK]...[/THINK] from answer tokens                │
└─────────────────────────────────────────────────────────────────┘
```

### ThinkingOrchestrator (`thinking/orchestrator.py`)

Registry for thinking strategies:

```python
class ThinkingOrchestrator:
    _default_strategies = {
        "direct": DirectStrategy,
        "cot": ChainOfThoughtStrategy,
        "chain_of_thought": ChainOfThoughtStrategy,  # Alias
    }

    def get_strategy(self, name: str = None, **kwargs) -> ThinkingStrategy:
        strategy_name = name or self.default_strategy
        return self._strategies[strategy_name](**kwargs)
```

### Base Classes (`thinking/base.py`)

```python
@dataclass
class ThinkingStep:
    """One step in the thinking process."""
    seq: int
    step_type: str          # "reasoning", "critique", "verification"
    raw_content: str        # Full unfiltered output
    messages_sent: List[dict]
    tokens: Dict[str, int]  # {"input": N, "output": N}
    timing_ms: int
    ui_summary: str         # Clean summary for UI
    ui_status: str          # "thinking", "verifying", "done"

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
    @abstractmethod
    async def think(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable] = None,
    ) -> ThinkingResult:
        pass
```

### StreamParser

Separates thinking from answer tokens in real-time:

```python
class StreamParser:
    """Parse streaming tokens, separating thinking from answer."""

    def feed(self, token: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Feed a token and get back (thinking_token, answer_token).

        Handles:
        - [THINK]...[/THINK] tags
        - <think>...</think> tags
        - Harmony format: <|channel|>final<|message|>
        """
```

### Direct Strategy (`thinking/strategies/direct.py`)

Single model call, no explicit reasoning:

```python
class DirectStrategy(ThinkingStrategy):
    name = "direct"

    async def think(self, messages, model_call, event_callback=None) -> ThinkingResult:
        result = await model_call(messages)
        response_text, usage, reasoning = result  # reasoning from gpt-oss

        return ThinkingResult(
            steps=[],
            final_answer=response_text,
            thinking_summary=reasoning or "",  # Native reasoning captured here
            thinking_tokens=len(reasoning) // 4 if reasoning else 0,
            answer_tokens=usage.get("completion_tokens", 0),
            metadata={"strategy": "direct", "usage": usage},
        )
```

### Chain-of-Thought Strategy (`thinking/strategies/cot.py`)

Two-phase reasoning with token budgets (TALE-EP approach):

```python
class ChainOfThoughtStrategy(ThinkingStrategy):
    name = "cot"

    STOP_SEQUENCES = ["[/THINK]", "</think>", "\n</think>\n", "\n[/THINK]\n"]

    def __init__(self, thinking_budget: int = 512, answer_budget: int = 256):
        self.thinking_budget = thinking_budget
        self.answer_budget = answer_budget

    async def think(self, messages, model_call, event_callback=None) -> ThinkingResult:
        # Phase 1: Generate thinking
        thinking_prompt = f"""Think through your reasoning step by step.
Use [THINK][/THINK] tags to wrap your thinking.
Budget: {self.thinking_budget} tokens for thinking."""

        thinking_messages = messages + [{"role": "user", "content": thinking_prompt}]
        raw_response, thinking_usage, _ = await model_call(
            thinking_messages,
            max_tokens=self.thinking_budget,
            stop=self.STOP_SEQUENCES
        )
        thinking_content = self._extract_thinking(raw_response)

        # Phase 2: Generate answer
        answer_prompt = "Based on your reasoning above, provide your final answer."
        answer_messages = messages + [
            {"role": "assistant", "content": f"[THINK]{thinking_content}[/THINK]"},
            {"role": "user", "content": answer_prompt}
        ]
        answer_text, answer_usage, _ = await model_call(
            answer_messages,
            max_tokens=self.answer_budget
        )

        return ThinkingResult(
            steps=[...],
            final_answer=answer_text,
            thinking_summary=thinking_content,
            thinking_tokens=thinking_usage.get("completion_tokens", 0),
            answer_tokens=answer_usage.get("completion_tokens", 0),
            metadata={"strategy": "cot"},
        )
```

**TALE-EP Token Budgeting**:
- Research from ACL 2025: Token-Budget-Aware LLM Reasoning
- Telling the model its budget makes it naturally conclude within it
- Achieves 67% token reduction while maintaining accuracy
- Stop sequences ensure clean tag closure

---

## Trace Events System

### Overview

The trace events system provides granular observability into LLM interactions.

```
┌─────────────────────────────────────────────────────────────────┐
│                           Run                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    trace_events                           │   │
│  │  ┌─────────┐  ┌─────────────┐  ┌─────────────┐           │   │
│  │  │llm_req  │──│ llm_resp    │  │   error     │           │   │
│  │  │(pending)│  │ (success)   │  │  (if any)   │           │   │
│  │  └─────────┘  └─────────────┘  └─────────────┘           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Event Types

| Type | Description |
|------|-------------|
| `llm_request` | Request sent to LLM (messages, params) |
| `llm_response` | Response received (text, usage, timing) |
| `error` | Error during processing |
| `retry` | Retry attempt for transient failure |

### Event Recording

In `ChatEngine`, events are recorded via `TraceRepo`:

```python
# Record request event
request_event_id = await self.trace_repo.add_trace_event(
    run_id=run_id,
    event_type="llm_request",
    event_status="pending",
    actor="system",
    endpoint=endpoint_used,
    step_number=model_call_count,
    content={
        "messages": messages,
        "model": self.config.model.name,
        "max_tokens": max_tokens,
        "temperature": self.config.model.temperature,
    },
)

# Record response event
await self.trace_repo.add_trace_event(
    run_id=run_id,
    event_type="llm_response",
    event_status="success",
    actor="model",
    parent_event_id=request_event_id,
    duration_ms=duration_ms,
    token_count=total_tokens,
    content={
        "response_length": len(response_text),
        "usage": usage,
        "finish_reason": finish_reason,
    },
)

# Record error if any
await self.trace_repo.add_trace_event(
    run_id=run_id,
    event_type="error",
    event_status="error",
    actor="system",
    parent_event_id=request_event_id,
    error_message=str(e),
    content={"exception_type": type(e).__name__},
)
```

### Timeline API

```python
@router.get("/runs/{run_id}/timeline")
async def get_run_timeline(run_id: str):
    """Get trace event timeline for a run."""
    events = await trace_repo.get_trace_events(run_id)
    run = await trace_repo.get_run(run_id)

    return {
        "run_id": run_id,
        "status": run["status"],
        "created_at": run["created_at"],
        "events": events,
        "total_events": len(events),
    }
```

---

## Data Flow

### Request Lifecycle

#### 1. User Sends Message

```
UI (React)
  └─> POST /api/conversations/{id}/runs
      {
        message: "What is 2+2?",
        thinking_mode: "default",
        reasoning_effort: "medium"
      }
```

#### 2. Backend Creates Run

```python
# routes/runs.py
@router.post("/conversations/{conversation_id}/runs")
async def create_conversation_run(conversation_id: str, request: CreateRunRequest):
    run_id = str(uuid.uuid4())[:8]

    # Create event queue for SSE
    _active_runs[run_id] = asyncio.Queue()

    # Start background task
    asyncio.create_task(run_chat(run_id, conversation_id, request))

    return {"run_id": run_id, "stream_url": f"/api/runs/{run_id}/stream"}
```

#### 3. Chat Execution

```python
async def run_chat(run_id, conversation_id, request):
    engine = ChatEngine(config, trace_repo)

    async def event_callback(event):
        await _active_runs[run_id].put(event)

    result = await engine.chat(
        conversation_id=conversation_id,
        message=request.message,
        run_id=run_id,
        event_callback=event_callback,
        thinking_strategy=_mode_to_strategy(request.thinking_mode),
        reasoning_effort=request.reasoning_effort,
    )

    # Signal completion
    await _active_runs[run_id].put({"type": "_STREAM_END", "result": result})
```

#### 4. Streaming Tokens

```
Provider (streaming)
  └─> on_token(token)
      └─> StreamParser.feed(token)
          ├─> thinking_token → event_callback({type: "THINKING_TOKEN", content: ...})
          └─> answer_token → event_callback({type: "TOKEN", content: ...})

on_reasoning(token)  # gpt-oss native reasoning
  └─> event_callback({type: "THINKING_TOKEN", content: ...})
```

#### 5. SSE Event Stream

```python
@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str):
    async def event_generator():
        queue = _active_runs.get(run_id)
        while True:
            event = await queue.get()
            if event["type"] == "_STREAM_END":
                yield f"event: complete\ndata: {json.dumps(event['result'])}\n\n"
                break
            yield f"data: {json.dumps(event)}\n\n"

    return EventSourceResponse(event_generator())
```

#### 6. Frontend Receives Stream

```typescript
// hooks/useSSE.ts
export function useSSE(runId: string | null) {
  useEffect(() => {
    if (!runId) return;

    const unsubscribe = subscribeToRun(runId,
      (event) => {
        if (event.type === "TOKEN") {
          appendStreamingText(runId, event.content);
        } else if (event.type === "THINKING_TOKEN") {
          appendStreamingThinking(runId, event.content);
        }
        addEvent(runId, event);
      },
      (result) => {
        // Stream complete
        clearStreamingText(runId);
        updateRun(runId, result);
      },
      (error) => {
        setError(error.message);
      }
    );

    return unsubscribe;
  }, [runId]);
}
```

### SSE Event Types

| Event | Description |
|-------|-------------|
| `TOKEN` | Answer token for display |
| `THINKING_TOKEN` | Thinking token (inside tags or native reasoning) |
| `CHAT_STARTED` | Chat processing began |
| `CHAT_COMPLETED` | Chat finished successfully |
| `CHAT_FAILED` | Chat failed with error |
| `complete` (SSE event) | Stream end with final result |

---

## Data Model

### Database Schema (`storage/schema.sql`)

#### conversations

```sql
CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,  -- active, archived, closed
    metadata_json TEXT
);
```

#### runs

```sql
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    conversation_id TEXT,
    created_at TEXT NOT NULL,
    user_message TEXT,
    system_prompt_snapshot TEXT,
    profile_name TEXT NOT NULL,
    mode TEXT NOT NULL,
    model_config_snapshot TEXT,
    final_answer TEXT,
    thinking_summary TEXT,
    error_message TEXT,
    status TEXT NOT NULL,  -- running, succeeded, failed
    last_response_id TEXT,  -- Response ID from /v1/responses for stateful chaining
    usage_stats TEXT,
    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
);
```

#### trace_events

Stores all trace events including thinking steps (with `event_type="thinking"`).

```sql
CREATE TABLE trace_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,     -- llm_request | llm_response | thinking | error | retry
    event_status TEXT NOT NULL,   -- pending | success | error | skipped
    actor TEXT NOT NULL,          -- model | system | tool:<name>
    endpoint TEXT,                -- /v1/responses | /v1/chat/completions
    attempt INTEGER DEFAULT 1,
    content_json TEXT NOT NULL,
    parent_event_id TEXT,
    step_number INTEGER,
    duration_ms INTEGER,
    token_count INTEGER,
    error_message TEXT,
    UNIQUE(run_id, seq),
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(parent_event_id) REFERENCES trace_events(id) ON DELETE CASCADE
);
```

#### Evaluation Tables (not yet wired)

```sql
CREATE TABLE eval_runs (
    eval_run_id TEXT PRIMARY KEY,
    run_id TEXT,
    dataset_name TEXT,
    metrics_json TEXT,
    status TEXT
);

CREATE TABLE eval_samples (
    sample_id TEXT PRIMARY KEY,
    eval_run_id TEXT,
    input TEXT,
    expected_output TEXT,
    actual_output TEXT,
    score REAL
);
```

---

## API Surface

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/conversations` | Create conversation |
| GET | `/api/conversations` | List conversations |
| GET | `/api/conversations/{id}` | Get conversation + runs |
| GET | `/api/conversations/{id}/traces` | Get all trace events for all runs |
| PATCH | `/api/conversations/{id}` | Update (title, summary, status) |
| DELETE | `/api/conversations/{id}` | Delete conversation |

### Runs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/conversations/{id}/runs` | Send message (returns stream URL) |
| POST | `/api/runs` | Create standalone run |
| GET | `/api/runs` | List runs (paginated) |
| GET | `/api/runs/{id}` | Get run details |
| GET | `/api/runs/{id}/stream` | SSE stream (tokens, events) |
| GET | `/api/runs/{id}/events` | Get model call events |
| GET | `/api/runs/{id}/timeline` | Get trace event timeline |
| GET | `/api/runs/{id}/report` | Get markdown report |
| GET | `/api/runs/{id}/thinking` | Get thinking traces |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/config` | Get current configuration |

### Response Examples

#### POST /api/conversations/{id}/runs

Request:
```json
{
  "message": "What is 2+2?",
  "thinking_mode": "default",
  "reasoning_effort": "medium"
}
```

Response:
```json
{
  "run_id": "abc12345",
  "stream_url": "/api/runs/abc12345/stream"
}
```

#### GET /api/runs/{id}/timeline

Response:
```json
{
  "run_id": "abc12345",
  "status": "succeeded",
  "created_at": "2024-01-01T12:00:00Z",
  "events": [
    {
      "id": "evt_001",
      "run_id": "abc12345",
      "seq": 1,
      "created_at": "2024-01-01T12:00:00Z",
      "event_type": "llm_request",
      "event_status": "pending",
      "actor": "system",
      "endpoint": "/v1/responses",
      "step_number": 1,
      "content": {"messages": [...], "model": "gpt-oss-20b"}
    },
    {
      "id": "evt_002",
      "run_id": "abc12345",
      "seq": 2,
      "created_at": "2024-01-01T12:00:01Z",
      "event_type": "llm_response",
      "event_status": "success",
      "actor": "model",
      "parent_event_id": "evt_001",
      "duration_ms": 1234,
      "token_count": 150,
      "content": {"response_length": 256, "usage": {...}}
    }
  ],
  "total_events": 2
}
```

---

## Frontend Architecture

### Technology Stack

- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **State Management**: Zustand
- **UI Components**: Shadcn UI
- **Markdown**: React-markdown with GFM and KaTeX

### App Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Sidebar (Conversation List) │ Main Chat │ Trace Panel      │
│                              │ (Details) │                  │
│ - Conversations              │           │ Raw events       │
│ - Active: selected           │           │ & timeline       │
│ - Resizable width            │           │                  │
└─────────────────────────────────────────────────────────────┘
```

### State Management (`hooks/useStore.ts`)

```typescript
interface AppState {
  // Data
  conversations: Conversation[]
  selectedConversationId: string | null
  runsByConversation: Record<string, Run[]>
  selectedRunId: string | null
  eventsByRun: Record<string, Event[]>

  // Streaming
  streamingRunId: string | null
  streamingText: Record<string, string>
  streamingThinking: Record<string, string>

  // UI State
  detailPanelOpen: boolean
  selectedEventSeq: number | null

  // Connection
  isConnected: boolean
  isLoading: boolean
  error: string | null
}
```

### Components

| Component | Purpose |
|-----------|---------|
| `App.tsx` | Main layout with sidebar and panels |
| `ConversationList.tsx` | Conversation list with selection |
| `ConversationView.tsx` | Chat interface with message history |
| `ThinkingPanel.tsx` | Collapsible thinking/reasoning display |
| `DetailPanel.tsx` | Raw trace event inspection |
| `AnswerMarkdown.tsx` | Markdown rendering with LaTeX |

### SSE Hook (`hooks/useSSE.ts`)

```typescript
export function useSSE(runId: string | null) {
  useEffect(() => {
    if (!runId) return;

    const unsubscribe = subscribeToRun(
      runId,
      handleEvent,    // TOKEN, THINKING_TOKEN, status events
      handleComplete, // Stream end
      handleError     // Connection error
    );

    return unsubscribe;
  }, [runId]);
}
```

### API Client (`api/client.ts`)

```typescript
// REST endpoints
export async function createConversation(request: CreateConversationRequest): Promise<Conversation>
export async function listConversations(status?: string, limit?: number): Promise<Conversation[]>
export async function getRun(runId: string): Promise<Run>
export async function getRunTimeline(runId: string): Promise<RunTimeline>

// SSE subscription
export function subscribeToRun(
  runId: string,
  onEvent: (event: StreamEvent) => void,
  onComplete: (result: RunResult) => void,
  onError: (error: Error) => void
): () => void
```

---

## Configuration

### Configuration File (`orchestrator/chat_config.yaml`)

```yaml
# Provider Configuration
provider:
  base_url: ${LLM_BASE_URL:-http://127.0.0.1:1234}
  api_key: ${LLM_API_KEY:-}
  endpoint: "responses"       # responses | chat_completions | auto
  fallback_on_404: true
  timeout: 120.0
  max_retries: 3
  base_delay: 1.0
  max_delay: 30.0
  retryable_statuses: [429, 500, 502, 503, 504]
  extra_headers: {}

# Model Configuration
model:
  name: "openai/gpt-oss-20b"
  temperature: 1.0
  max_tokens: 4096
  seed: null
  top_p: null
  frequency_penalty: null
  presence_penalty: null
  reasoning_effort: "medium"  # low | medium | high (gpt-oss)

# Context Management
context:
  max_messages: 50
  max_tokens: 6000
  reserve_for_response: 2048
  truncation_strategy: "sliding_window"

# System Prompt
system_prompt: |
  You are a helpful AI assistant. Answer directly and clearly.

# Tracing & Observability
tracing:
  enabled: true
  log_level: "debug"
  log_model_calls: true

# Thinking/Reasoning Strategies
thinking:
  mode_mapping:
    default: "direct"
    thinking: "direct"  # Use "cot" for non-gpt-oss models
  cot:
    thinking_budget: 512
    answer_budget: 256
  tracing:
    save_internal: true
    save_user_summary: true
  ui:
    show_thinking: false
    collapsible: true
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_BASE_URL` | LLM server URL | `http://127.0.0.1:1234` |
| `LLM_API_KEY` | API key (empty for local) | (empty) |

**Syntax**:
- `${VAR}` - Required, errors if not set
- `${VAR:-default}` - Optional with default value

### Loading (`orchestrator/config.py`)

```python
def load_config() -> ChatConfig:
    """Load configuration from chat_config.yaml."""
    config_path = Path(__file__).parent / "chat_config.yaml"
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    # Resolve environment variables
    resolved = _resolve_env_vars(raw)

    return ChatConfig(**resolved)
```

---

## Component Summary

| Component | Purpose | Key Files |
|-----------|---------|-----------|
| **Backend** | | |
| FastAPI App | Entry point, routing | `app.py` |
| Config System | Settings management | `config.py`, `chat_config.yaml` |
| ChatEngine | Core orchestration | `engine/chat_engine.py` |
| Providers | LLM abstraction | `providers/*.py` |
| Thinking | Reasoning strategies | `thinking/*.py`, `thinking/strategies/*.py` |
| Routes | API endpoints | `routes/*.py` |
| Storage | Data persistence | `storage/*.py` |
| **Frontend** | | |
| React App | UI framework | `App.tsx` |
| Zustand Store | State management | `hooks/useStore.ts` |
| SSE Hook | Real-time events | `hooks/useSSE.ts` |
| API Client | REST + SSE | `api/client.ts` |

---

## Deployment Notes

- Backend: `127.0.0.1:9000` (default)
- Frontend: `127.0.0.1:3000` (default)
- LLM endpoint: `http://127.0.0.1:1234` (configurable)
- Database: `var/traces.sqlite` (auto-created)

For development, use `honcho start` with the provided `Procfile`.
