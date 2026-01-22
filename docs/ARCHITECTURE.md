# Reasoner Architecture

Comprehensive technical documentation of the Reasoner system architecture.

## Table of Contents

1. [System Overview](#system-overview)
2. [Backend Architecture](#backend-architecture)
3. [Frontend Architecture](#frontend-architecture)
4. [Provider Layer](#provider-layer)
5. [Thinking System](#thinking-system)
6. [Agent Framework](#agent-framework)
7. [Storage Layer](#storage-layer)
8. [Configuration System](#configuration-system)

---

## System Overview

Reasoner is an AI chat application with multi-strategy reasoning capabilities. It consists of a FastAPI backend (orchestrator) and a React/Vite frontend (ui), connected to OpenAI-compatible LLM providers. Default configuration uses DeepInfra cloud, but supports local providers (llama-server, vLLM, Ollama) via environment variables.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    USER                                          │
│                               ┌──────────┐                                       │
│                               │ Browser  │                                       │
│                               └────┬─────┘                                       │
└────────────────────────────────────┼─────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼─────────────────────────────────────────────┐
│                         FRONTEND - React + Vite (:3000)                          │
│  ┌─────────────────┐   ┌─────────────────┐   ┌────────────────────────────────┐  │
│  │ Conversation    │───│  Zustand Store  │───│  SSE Hooks                     │  │
│  │ Views & UI      │   │  (app state)    │   │  (useSSE, useAgentSSE)         │  │
│  └─────────────────┘   └─────────────────┘   └─────────────┬──────────────────┘  │
└────────────────────────────────────────────────────────────┼─────────────────────┘
                                     │ REST API              │ SSE stream
                                     ▼                       ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          BACKEND - FastAPI (:9000)                               │
│  ┌──────────────┐   ┌────────────────────┐   ┌────────────────────────────────┐  │
│  │   Routes     │───│    ChatEngine      │───│    Provider Layer              │  │
│  │ /api/*       │   │  orchestration     │   │  LLMProvider protocol          │  │
│  └──────────────┘   └─────────┬──────────┘   └────────────────────────────────┘  │
│                               │                                                   │
│  ┌──────────────┐   ┌─────────▼──────────┐   ┌────────────────────────────────┐  │
│  │ Repositories │   │ ThinkingOrchestrator│   │      Agent Engine             │  │
│  │ SQLite DAOs  │   │  strategy routing   │   │  tool calling + synthesis     │  │
│  └──────────────┘   └────────────────────┘   └────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
                               │                              │
                               ▼                              ▼
┌──────────────────────────────────────────┐  ┌────────────────────────────────────┐
│   LLM Provider (DeepInfra / llama-server │  │   SQLite (var/traces.sqlite)       │
│   / vLLM / Ollama / OpenAI)              │  │ conversations | runs | trace_events│
│   OpenAI-compatible API                  │  │ agent_steps | agent_tool_calls     │
│   - /v1/chat/completions (default)       │  └────────────────────────────────────┘
│   - /v1/responses (gpt-oss native)       │
└──────────────────────────────────────────┘
```

### Key Features

- **Dual Mode Operation**: Chat mode (conversational) and Research mode (agent with tools)
- **Multi-Provider Support**: LM Studio, vLLM, Ollama, OpenAI, and any OpenAI-compatible API
- **Streaming-First**: Real-time token streaming via Server-Sent Events (SSE)
- **Thinking Strategies**: Direct strategy with native reasoning support (gpt-oss models)
- **Full Traceability**: Every LLM call, tool execution, and event is recorded in SQLite
- **Provider Failover**: Circuit breaker pattern with automatic provider switching

---

## Backend Architecture

### Directory Structure

```
orchestrator/
├── app.py                    # FastAPI entry point, middleware, routers
├── config.py                 # Configuration system (ChatConfig, ProviderConfig)
├── chat_config.yaml          # Runtime settings (single source of truth)
├── schemas.py                # Pydantic request/response models
├── logging_config.py         # Structured JSON logging
│
├── engine/
│   └── chat_engine.py        # Core chat orchestration
│
├── providers/
│   ├── base.py               # LLMProvider protocol, LLMResponse dataclass
│   ├── factory.py            # Provider factory (single or chained)
│   ├── openai_compat.py      # OpenAI-compatible client (~825 lines)
│   ├── chain.py              # Provider chain with failover
│   ├── circuit_breaker.py    # Circuit breaker implementation
│   ├── request_builders.py   # Build requests for different endpoints
│   └── response_parsers.py   # Parse responses from different endpoints
│
├── thinking/
│   ├── base.py               # ThinkingStrategy ABC, StreamParser, data models
│   ├── orchestrator.py       # Strategy registry and routing
│   └── strategies/
│       └── direct.py         # Single model call (fastest)
│
├── agent/
│   ├── agent_engine.py       # Agent loop with tool calling
│   ├── state_machine.py      # Agent state management
│   ├── context_pruner.py     # Token budget management
│   ├── query_classifier.py   # Query type classification
│   ├── recovery.py           # Crash recovery support
│   └── tools/
│       ├── base.py           # BaseTool protocol
│       ├── registry.py       # Tool registry
│       ├── web_search.py     # Parallel.ai web search
│       ├── web_extract.py    # Content extraction
│       ├── python_local.py   # Local Python execution
│       └── python_sandbox.py # E2B sandbox (optional)
│
├── routes/
│   ├── conversations.py      # Conversation CRUD
│   ├── runs.py               # Chat runs + SSE streaming
│   └── agent_runs.py         # Agent runs + SSE streaming
│
├── storage/
│   ├── db.py                 # Async SQLite wrapper
│   ├── schema.sql            # Database schema
│   └── repositories/
│       ├── conversation_repo.py  # Conversation data access
│       ├── trace_repo.py         # Runs and trace events
│       └── agent_repo.py         # Agent-specific tables
│
└── utils/
    ├── tokens.py             # Token counting (cl100k_base)
    ├── sanitize.py           # Response sanitization
    └── harmony_parser.py     # gpt-oss Harmony format parsing
```

### Application Entry Point (`app.py`)

The FastAPI application initializes with:

1. **Lifespan Management**: Startup loads config, initializes DB; shutdown handles cleanup
2. **Middleware**:
   - `RequestLoggingMiddleware`: Request ID correlation and timing
   - `CORSMiddleware`: Allows frontend at localhost:3000
3. **Routers**: `/api/conversations`, `/api/runs`, `/api/agent/runs`
4. **Health/Config Endpoints**: `/api/health`, `/api/config`

```python
app = FastAPI(title="Reasoner API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(conversations.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(agent_runs.router, prefix="/api")
```

### Chat Engine (`engine/chat_engine.py`)

The `ChatEngine` class orchestrates all chat interactions:

```
┌─────────────────────────────────────────────────────────────────────┐
│                           ChatEngine                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐ │
│  │  LLMProvider   │  │  Thinking      │  │  TraceRepo             │ │
│  │  (streaming)   │  │  Orchestrator  │  │  (persistence)         │ │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────────────┘ │
│          │                   │                   │                   │
│          ▼                   ▼                   ▼                   │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      chat() method                             │  │
│  │  1. Load conversation history from DB                          │  │
│  │  2. Build message list (system prompt + history + user msg)    │  │
│  │  3. Create run record with status="running"                    │  │
│  │  4. Execute thinking strategy with streaming                   │  │
│  │  5. Record trace events (llm_request, llm_response)            │  │
│  │  6. Update run with final_answer, status="succeeded"           │  │
│  │  7. Return ChatResult                                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Methods**:

| Method | Purpose |
|--------|---------|
| `chat()` | Main entry point for processing a message |
| `_build_messages()` | Constructs message list from history (respects max_messages) |
| `_call_model_streaming()` | Handles streaming with token callbacks via StreamParser |

**ChatResult Dataclass**:
```python
@dataclass
class ChatResult:
    run_id: str
    conversation_id: str
    message: str
    response: str
    status: str              # "succeeded" or "failed"
    error: Optional[str]
    timing_ms: int
    token_usage: Optional[dict]
    thinking_summary: str
```

---

## Frontend Architecture

### Directory Structure

```
ui/src/
├── main.tsx                  # React entry point
├── App.tsx                   # Main layout + routing
│
├── components/
│   ├── ConversationView.tsx  # Chat interface (dual mode: chat/research)
│   ├── ConversationList.tsx  # Sidebar with conversation list
│   ├── DetailPanel.tsx       # Debug trace viewer
│   ├── AgentRunMessage.tsx   # Research mode message display
│   ├── AgentStepsPanel.tsx   # Research progress timeline
│   ├── AnswerMarkdown.tsx    # Markdown + LaTeX rendering
│   ├── AnswerWithCitations.tsx  # Answer with source citations
│   ├── ThinkingPanel.tsx     # Collapsible thinking display
│   ├── ToolCallCard.tsx      # Tool execution card
│   ├── CitationInline.tsx    # Inline citation badge
│   └── ui/                   # Shadcn-style primitives
│       ├── button.tsx
│       ├── card.tsx
│       ├── badge.tsx
│       ├── input.tsx
│       ├── dialog.tsx
│       └── ...
│
├── hooks/
│   ├── useStore.ts           # Zustand store (state + actions)
│   ├── useSSE.ts             # Chat mode streaming hook
│   ├── useAgentSSE.ts        # Agent mode streaming hook
│   └── useAgentRunDetails.ts # Load agent trace data
│
├── api/
│   └── client.ts             # REST + SSE API client
│
├── types/
│   ├── index.ts              # Core types (Run, Conversation, Event)
│   └── agent.ts              # Agent-specific types
│
└── lib/
    ├── utils.ts              # Utility functions (cn, formatTimestamp)
    └── retry.ts              # Retry with exponential backoff
```

### Component Hierarchy

```
App.tsx
├── ConversationList.tsx (sidebar)
│   └── Conversation items with delete/multi-select
│
├── Routes
│   └── ConversationView.tsx (main content)
│       ├── Message history
│       │   ├── RunMessage (chat mode)
│       │   │   ├── User message bubble
│       │   │   ├── AI response bubble
│       │   │   ├── ThinkingPanel (collapsible)
│       │   │   └── AnswerMarkdown
│       │   │
│       │   └── AgentRunMessage (research mode)
│       │       ├── User query bubble
│       │       ├── AgentStepsPanel
│       │       │   └── ToolCallCard (per tool)
│       │       └── AnswerWithCitations
│       │           └── CitationInline
│       │
│       └── Input form with mode toggle
│
└── DetailPanel.tsx (right panel, debug)
    └── Raw trace JSON viewer
```

### State Management (Zustand)

The store (`useStore.ts`) manages all application state:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           Zustand Store                                   │
├──────────────────────────────────────────────────────────────────────────┤
│ CONVERSATIONS                          │ STREAMING                        │
│ ├─ conversations: Conversation[]       │ ├─ streamingRunId: string        │
│ ├─ selectedConversationId: string      │ ├─ streamingText: Record<id,str> │
│ └─ runsByConversation: Record<id,Run[]>│ └─ streamingThinking: Record<>   │
├────────────────────────────────────────┼──────────────────────────────────┤
│ AGENT STATE                            │ UI STATE                         │
│ ├─ agentRunState: Record<id,AgentUI>   │ ├─ detailPanelOpen: boolean      │
│ │   ├─ isActive                        │ ├─ selectedEventSeq: number      │
│ │   ├─ currentStep                     │ └─ sidebarCollapsed: boolean     │
│ │   ├─ thinkingBuffer                  │                                  │
│ │   ├─ answerBuffer                    │ CONNECTION                       │
│ │   ├─ steps[]                         │ ├─ isConnected: boolean          │
│ │   ├─ toolCalls[]                     │ ├─ isLoading: boolean            │
│ │   └─ citations[]                     │ └─ error: string                 │
└────────────────────────────────────────┴──────────────────────────────────┘
```

### SSE Streaming Hooks

**`useSSE.ts`** (Chat Mode):
- Subscribes to `/api/runs/{id}/stream`
- Routes `TOKEN` events to `streamingText`
- Routes `THINKING_TOKEN` events to `streamingThinking`
- Clears streaming state on completion

**`useAgentSSE.ts`** (Research Mode):
- Subscribes to `/api/agent/runs/{id}/stream`
- Processes events: `step_start`, `thinking`, `tool_start`, `tool_result`, `answer`, `complete`
- Supports resumption via `since_seq` parameter
- Updates `agentRunState` in store

---

## Provider Layer

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Provider Layer                                   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    LLMProvider Protocol                           │   │
│  │  - complete(messages, max_tokens, temperature, tools, ...)        │   │
│  │  - complete_streaming(messages, on_token, on_reasoning, ...)      │   │
│  │  - health_check()                                                 │   │
│  │  - close()                                                        │   │
│  └─────────────────────────────────┬────────────────────────────────┘   │
│                                    │                                     │
│              ┌─────────────────────┼─────────────────────┐               │
│              ▼                     ▼                     ▼               │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐    │
│  │ OpenAICompatProvider│ │  ProviderChain    │  │  (Future providers)│   │
│  │ - Single provider   │ │  - Failover       │  │                    │   │
│  │ - Dual endpoints    │ │  - Circuit breaker│  │                    │   │
│  │ - Retry logic       │ │  - Priority-based │  │                    │   │
│  └───────────────────┘  └───────────────────┘  └───────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Dual Endpoint Support

The provider supports two OpenAI endpoints with automatic fallback:

| Endpoint | Path | Use Case |
|----------|------|----------|
| `responses` | `/v1/responses` | gpt-oss models, full agent/tool support, native reasoning |
| `chat_completions` | `/v1/chat/completions` | Standard chat, wider compatibility |

**Fallback Logic**:
1. Try `/v1/responses` first
2. On 404/405, cache result and use `/v1/chat/completions`
3. Cached per `base_url` for session

### Provider Switching

Switch between cloud (DeepInfra) and local (llama-server) providers:

```bash
./dev.sh provider local      # Local llama-server on port 8080
./dev.sh provider deepinfra  # DeepInfra cloud (default)
./dev.sh restart             # Required after switching
```

**Supported Local Providers**:
- `llama-server` (llama.cpp) - Tested with Ministral-3-14B-Reasoning
- `vLLM` - OpenAI-compatible server
- `Ollama` - Via OpenAI compatibility mode

**Configuration** (`.env.provider`):
```bash
LLM_BASE_URL=http://localhost:8080/v1  # Local
LLM_ENDPOINT=chat_completions
LLM_MODEL=ministral-14b-reasoning
```

**URL Building**: Handles base URLs that already contain `/v1` (e.g., llama-server) to avoid double `/v1/v1/...` paths.

**Message Alternation**: Some models (Mistral family) require strict user/assistant message alternation. The provider layer ensures:
- Plan is appended to system message (not as separate message)
- Incomplete conversation history runs are skipped
- No duplicate user messages

### Circuit Breaker Pattern

```
                    ┌─────────────────┐
                    │     CLOSED      │
                    │   (healthy)     │
                    └────────┬────────┘
                             │
         failure_threshold   │   request succeeds
         failures reached    │
                             │
                    ┌────────▼────────┐
                    │      OPEN       │
                    │   (unhealthy)   │◄──────────────┐
                    └────────┬────────┘               │
                             │                        │
         recovery_timeout    │                        │ test request fails
         expires             │                        │
                             │                        │
                    ┌────────▼────────┐               │
                    │    HALF_OPEN    │───────────────┘
                    │   (testing)     │
                    └────────┬────────┘
                             │
         success_threshold   │
         successes reached   │
                             │
                    ┌────────▼────────┐
                    │     CLOSED      │
                    │   (healthy)     │
                    └─────────────────┘
```

**Configuration**:
- `failure_threshold`: 5 failures to open circuit
- `recovery_timeout_seconds`: 30s before testing again
- `success_threshold`: 2 successes to close circuit

### Retry Logic

Exponential backoff with jitter for transient failures:

```
delay = min(base_delay * 2^attempt, max_delay) + random(0, delay * 0.1)

Attempt 1: 1.0s + jitter
Attempt 2: 2.0s + jitter
Attempt 3: 4.0s + jitter
...max 30s
```

**Retryable Statuses**: 429, 500, 502, 503, 504

---

## Thinking System

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      ThinkingOrchestrator                                │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Strategy Registry                                                  │ │
│  │  ┌─────────────────┐                                               │ │
│  │  │  DirectStrategy │  (only registered strategy)                   │ │
│  │  │  (single call)  │                                               │ │
│  │  └─────────────────┘                                               │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                    │                                     │
│                                    ▼                                     │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                        StreamParser                                 │ │
│  │  Separates thinking tokens from answer tokens in real-time         │ │
│  │  Detects: [THINK]...[/THINK], <think>...</think>, Harmony format   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Available Strategy

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `direct` | Single model call, captures native reasoning | Fast responses, gpt-oss models |

### StreamParser

Real-time token routing during streaming:

```
Input tokens → StreamParser → (thinking_token, answer_token)
                    │
                    ├── Detects [THINK] or <think> opening
                    ├── Routes tokens to thinking buffer
                    ├── Detects [/THINK] or </think> closing
                    ├── Routes tokens to answer buffer
                    └── Handles native reasoning via [THINK_NATIVE] marker
```

### ThinkingResult

```python
@dataclass
class ThinkingResult:
    steps: List[ThinkingStep]    # Internal trace
    final_answer: str
    thinking_summary: str        # For UI display
    thinking_tokens: int
    answer_tokens: int
    metadata: dict
```

---

## Agent Framework

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AgentEngine                                    │
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────────┐ │
│  │ State Machine  │  │ Context Pruner │  │ Tool Registry              │ │
│  │ - PLANNING     │  │ - Token budget │  │ - web_search               │ │
│  │ - TOOL_CALLING │  │ - LLM-based    │  │ - web_extract              │ │
│  │ - SYNTHESIZING │  │   summarization│  │ - python_execute           │ │
│  │ - COMPLETE     │  │ - Query-aware  │  │                            │ │
│  │ - ERROR        │  │                │  │                            │ │
│  └────────┬───────┘  └────────────────┘  └────────────────────────────┘ │
│           │                                                              │
│           │          ┌────────────────┐                                  │
│           │          │ Findings       │ Tracks key findings from each   │
│           │          │ Accumulator    │ tool result for synthesis       │
│           │          └────────────────┘                                  │
│           ▼                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                        Agent Loop                                   │ │
│  │  while not (synthesis or max_steps):                                │ │
│  │    1. Prune context with LLM summarization (query-aware)            │ │
│  │    2. Call LLM with tool schemas                                    │ │
│  │    3. Parse response for tool calls or synthesis decision           │ │
│  │    4. Execute tools (with idempotency keys)                         │ │
│  │    5. Extract findings from tool results                            │ │
│  │    6. Record results in database, track tokens                      │ │
│  │    7. Emit SSE events for UI                                        │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Planning Step (Pre-Execution)

Before entering the main agent loop, the engine can optionally create a research plan:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Planning Step                                │
│                                                                      │
│  Input: User query + system prompt                                   │
│  Output: ResearchPlan with ordered steps                             │
│                                                                      │
│  1. Analyze query complexity                                         │
│  2. Generate plan with tool suggestions per step                     │
│  3. Inject plan into system message                                  │
│  4. Track plan progress during execution                             │
└─────────────────────────────────────────────────────────────────────┘
```

**Configuration** (`chat_config.yaml`):
```yaml
agent_planning:
  enabled: true           # Enable/disable planning step
  max_plan_steps: 5       # Maximum steps planner can create
```

**Plan Injection**: The plan is appended to the system message (not as a separate message) to maintain strict user/assistant message alternation required by some models (e.g., Mistral).

### Agent State Machine

```
┌─────────────┐
│   INIT      │
└──────┬──────┘
       │
       ▼
┌─────────────┐ (optional)
│  PLANNING   │─────────────────────────┐
│  (research  │                         │
│   plan)     │                         │
└──────┬──────┘                         │
       │                                │
       ▼                                ▼
┌─────────────┐     tool_calls     ┌─────────────┐
│ STEP_LOOP   │──────────────────►│ TOOL_CALLING│
└──────┬──────┘                    └──────┬──────┘
       │                                  │
       │ synthesize                       │ all tools done
       │                                  │
       ▼                                  ▼
┌─────────────┐                    ┌─────────────┐
│SYNTHESIZING │◄───────────────────│ STEP_LOOP   │
└──────┬──────┘                    └─────────────┘
       │
       ▼
┌─────────────┐
│  COMPLETE   │
└─────────────┘

Any state can transition to ERROR on failure
```

### Available Tools

| Tool | Description | Provider | Registration |
|------|-------------|----------|--------------|
| `python_execute` | Execute Python code | Local subprocess or Daytona | Always registered |
| `web_search` | Search the web for information | Parallel.ai | Requires `PARALLEL_API_KEY` |
| `web_extract` | Extract content from URLs | Parallel.ai | Requires `PARALLEL_API_KEY` |

**Python Execution Providers** (set via `PYTHON_PROVIDER` env var):
- `local` (default): Fast subprocess execution
- `daytona`: Secure cloud sandbox via Daytona SDK (~90ms startup)

### Crash Recovery

The agent supports crash recovery via:
- **Idempotency Keys**: Hash-based tool call deduplication
- **State Reconstruction**: Rebuild state from database on restart
- **Execution Attempts**: Track retry count per tool call

### Findings Accumulator

The agent tracks key findings from each tool result to improve synthesis quality:
- Extracts query-relevant facts from web search/extract results
- Stores findings with step number and source tool
- Includes accumulated findings in forced synthesis prompt
- Improves answer quality when hitting max steps

### LLM-Based Context Summarization

The `ContextPruner` uses LLM calls to create query-aware summaries:
- Summarizes tool results over 500 chars using LLM
- Prompt extracts only facts relevant to the user's query
- Results are cached to prevent duplicate LLM calls
- Falls back to basic truncation on error
- Python output keeps head/tail pattern (not LLM summarized)

### Token Tracking

The agent tracks total tokens used across all LLM calls:
- Accumulates tokens from each planning/tool-calling step
- Includes tokens from forced synthesis
- Returns `total_tokens` in `AgentResult`
- Displayed in UI alongside duration

---

## Storage Layer

### Database Schema Overview

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│  conversations  │       │      runs       │       │  trace_events   │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ conversation_id │──┐    │ run_id          │──┐    │ id              │
│ title           │  │    │ conversation_id │◄─┘    │ run_id          │◄─┐
│ summary         │  │    │ user_message    │       │ seq             │  │
│ status          │  │    │ final_answer    │       │ event_type      │  │
│ created_at      │  │    │ thinking_summary│       │ event_status    │  │
│ metadata_json   │  │    │ status          │       │ content_json    │  │
└─────────────────┘  │    │ usage_stats     │       │ duration_ms     │  │
                     │    └─────────────────┘       │ parent_event_id │──┘
                     │                              └─────────────────┘
                     │
                     │    ┌─────────────────┐       ┌─────────────────┐
                     │    │  agent_steps    │       │agent_tool_calls │
                     │    ├─────────────────┤       ├─────────────────┤
                     │    │ id              │──┐    │ id              │
                     │    │ run_id          │◄─┼────│ step_id         │
                     │    │ step_number     │  │    │ run_id          │
                     │    │ state           │  │    │ tool_name       │
                     │    │ thinking_text   │  │    │ arguments       │
                     │    │ decision        │  │    │ status          │
                     │    └─────────────────┘  │    │ result_summary  │
                     │                         │    │ idempotency_key │
                     │                         │    └─────────────────┘
                     │                         │
                     │                         │    ┌─────────────────┐
                     │                         │    │ agent_citations │
                     │                         │    ├─────────────────┤
                     │                         │    │ id              │
                     │                         └────│ tool_call_id    │
                     │                              │ run_id          │
                     │                              │ source_url      │
                     │                              │ snippet         │
                     │                              │ used_in_answer  │
                     │                              └─────────────────┘
                     │
                     └─── (1:N relationship)
```

### Repository Pattern

| Repository | Purpose | Key Methods |
|------------|---------|-------------|
| `ConversationRepo` | Conversation CRUD | `create`, `get`, `list`, `update`, `delete` |
| `TraceRepo` | Runs and trace events | `create_run`, `update_run`, `add_trace_event`, `get_run` |
| `AgentRepo` | Agent-specific data | `create_step`, `add_tool_call`, `set_citations` |

---

## Configuration System

### Configuration File (`chat_config.yaml`)

Single source of truth for all runtime settings:

```yaml
provider:
  # Default: DeepInfra cloud. Override with LLM_BASE_URL for local providers.
  base_url: ${LLM_BASE_URL:-https://api.deepinfra.com/v1/openai}
  api_key: ${DEEPINFRA_API_KEY:-}
  endpoint: ${LLM_ENDPOINT:-chat_completions}  # chat_completions | responses | auto
  fallback_on_404: true
  fail_on_tool_fallback: true   # Raise error if tools unavailable
  state_mode: "stateless"       # stateless | stateful_opt_in
  timeout: 120.0
  slow_response_threshold: 15.0 # Seconds before showing "taking longer" message
  max_retries: 3
  base_delay: 1.0
  max_delay: 30.0
  retryable_statuses: [429, 500, 502, 503, 504]
  extra_headers: {}             # Additional headers (e.g., api-version for Azure)

provider_chain:
  enabled: false              # Set true for multi-provider failover

model:
  name: ${LLM_MODEL:-openai/gpt-oss-120b}
  temperature: 1.0
  max_tokens: 4096
  reasoning_effort: "medium"  # For gpt-oss: low | medium | high

context:
  max_messages: 50
  max_tokens: 6000
  reserve_for_response: 2048
  truncation_strategy: "sliding_window"

thinking:
  mode_mapping:
    default: "direct"
    thinking: "direct"
  tracing:
    save_internal: true       # Save internal reasoning traces
    save_user_summary: true   # Save UI-friendly summaries
  ui:
    show_thinking: false      # Show thinking in UI by default
    collapsible: true         # Allow collapsing thinking sections

tracing:                      # Chat-level tracing (separate from thinking)
  enabled: true
  log_level: "info"           # debug | info | warn
  log_model_calls: true       # Log LLM requests/responses

query_classification:         # Query classification for tool selection
  enabled: true               # If false, skip classification
  min_confidence_for_enforcement: 2

parallel:                     # Web search/extract (Parallel.ai)
  api_key: ${PARALLEL_API_KEY:-}
  base_url: "https://api.parallel.ai/v1beta"
  search:
    max_results: 10
    timeout_ms: 15000
  extract:
    timeout_ms: 30000
    max_urls_per_request: 5

python:                       # Local Python execution
  timeout_seconds: 30

# NOTE: E2B sandbox is configured but not currently in use.
# Local Python execution is used instead.
sandbox:                      # Python sandbox (NOT CURRENTLY USED)
  provider: "e2b"
  e2b:
    api_key: ${E2B_API_KEY:-}
    template: "code-interpreter"
    timeout_seconds: 30
    cleanup_on_startup: true
    stale_session_minutes: 10
```

### Environment Variable Resolution

- `${VAR}` - Required, errors if not set
- `${VAR:-default}` - Optional with default value

Variables are resolved before Pydantic validation.

### Key Configuration Classes

| Class | Purpose |
|-------|---------|
| `ProviderConfig` | LLM endpoint, retry settings, state mode, `slow_response_threshold` |
| `ProviderChainConfig` | Multi-provider failover with circuit breakers |
| `ChatModelConfig` | Model name, temperature, max_tokens, reasoning_effort |
| `ChatContextConfig` | Conversation history limits, truncation |
| `ChatTracingConfig` | Chat-level tracing (enabled, log_level, log_model_calls) |
| `ThinkingConfig` | Mode mapping, ThinkingTracingConfig, ThinkingUIConfig |
| `QueryClassificationConfig` | Query classification settings for tool selection |
| `ParallelConfig` | Web search/extract with nested `ParallelSearchConfig`, `ParallelExtractConfig` |
| `PythonConfig` | Local Python execution settings |
| `SandboxConfig` | Python sandbox with `E2BConfig` (not currently used) |

---

## Related Documentation

- [Data Models](DATA_MODELS.md) - Complete data model reference
- [Data Flow](DATA_FLOW.md) - Request lifecycle and streaming
- [Components](COMPONENTS.md) - Detailed component documentation
- [API Reference](API_REFERENCE.md) - Complete API documentation
