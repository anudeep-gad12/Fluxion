# Reasoner Architecture

Comprehensive technical documentation of the Reasoner system architecture.

## Table of Contents

1. [System Overview](#system-overview)
2. [Backend Architecture](#backend-architecture)
3. [CLI/TUI System](#clitui-system)
4. [Frontend Architecture](#frontend-architecture)
5. [Provider Layer](#provider-layer)
6. [Thinking System](#thinking-system)
7. [Agent Framework](#agent-framework)
8. [Storage Layer](#storage-layer)
9. [Configuration System](#configuration-system)

---

## System Overview

Reasoner is an AI chat application with multi-strategy reasoning capabilities. It consists of a FastAPI backend (orchestrator), a React/Vite frontend (ui), and a Textual-based CLI/TUI (cli), connected to OpenAI-compatible LLM providers. Default configuration uses DeepInfra cloud, but supports local providers (llama-server, vLLM, Ollama) and ChatGPT (via OAuth) as providers.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    USER                                          │
│                      ┌──────────┐        ┌──────────┐                            │
│                      │ Browser  │        │ Terminal │                            │
│                      └────┬─────┘        └────┬─────┘                            │
└───────────────────────────┼───────────────────┼─────────────────────────────────┘
                            │                   │
┌───────────────────────────▼────────┐  ┌───────▼────────────────────────────────┐
│  FRONTEND - React + Vite (:3000)   │  │  CLI/TUI - Textual (reasoner command)  │
│  ┌─────────────┐  ┌─────────────┐  │  │  ┌─────────────┐  ┌────────────────┐  │
│  │ Conversation │──│ Zustand     │  │  │  │ ChatScreen  │──│ APIClient      │  │
│  │ Views & UI   │  │ Store       │  │  │  │ + Widgets   │  │ (HTTP + SSE)   │  │
│  └─────────────┘  └──────┬──────┘  │  │  └──────┬──────┘  └───────┬────────┘  │
│                   SSE Hooks        │  │         │ Textual msgs     │ REST/SSE  │
└────────────────────┬───────────────┘  └─────────┼─────────────────┼────────────┘
                     │ REST API + SSE             │                 │
                     ▼                            ▼                 ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          BACKEND - FastAPI (:9000)                               │
│  ┌──────────────┐   ┌────────────────────┐   ┌────────────────────────────────┐  │
│  │   Routes     │───│    ChatEngine      │───│    Provider Layer              │  │
│  │ /api/*       │   │  orchestration     │   │  OpenAI-compat + ChatGPT      │  │
│  └──────────────┘   └─────────┬──────────┘   └────────────────────────────────┘  │
│                               │                                                   │
│  ┌──────────────┐   ┌─────────▼──────────┐   ┌────────────────────────────────┐  │
│  │ Repositories │   │ ThinkingOrchestrator│   │      Agent Engine             │  │
│  │ SQLite DAOs  │   │  strategy routing   │   │  profiles + tools + approval  │  │
│  └──────────────┘   └────────────────────┘   └────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
                               │                              │
                               ▼                              ▼
┌──────────────────────────────────────────┐  ┌────────────────────────────────────┐
│   LLM Provider                           │  │   SQLite (var/traces.sqlite)       │
│   - DeepInfra / llama-server / vLLM      │  │ conversations | runs | trace_events│
│   - ChatGPT (OAuth + Codex API)          │  │ agent_steps | agent_tool_calls     │
│   - /v1/chat/completions (default)       │  │ run_events | run_artifacts         │
│   - /v1/responses (gpt-oss native)       │  └────────────────────────────────────┘
└──────────────────────────────────────────┘
```

### Key Features

- **Triple Interface**: Web UI (React), CLI/TUI (Textual), and REST API
- **Agent Profiles**: Research (web + python) and Coding (filesystem + web + python) modes
- **Filesystem Tools**: bash, glob, grep, read_file, edit_file, write_file, list_directory
- **Tool Approval Flow**: Permission-gated tool execution (strict/relaxed/yolo policies)
- **Multi-Provider Support**: DeepInfra, ChatGPT (OAuth), llama-server, vLLM, Ollama
- **Streaming-First**: Real-time token streaming via Server-Sent Events (SSE)
- **Context Management**: Token-aware history pruning, turn summaries, project context injection
- **Full Traceability**: Every LLM call, tool execution, approval, and file change is recorded
- **Provider Failover**: Circuit breaker pattern with automatic provider switching

---

## Backend Architecture

### Directory Structure

```
cli/                              # CLI/TUI (Textual framework)
├── __main__.py                   # Click entry point (reasoner command)
├── app.py                        # ReasonerApp (Textual App), custom theme
├── config.py                     # CLIConfig, session persistence (~/.config/reasoner/)
├── api_client.py                 # APIClient (HTTP + SSE streaming, tool approval)
├── auth.py                       # ChatGPT OAuth PKCE flow
├── events.py                     # Textual message classes for SSE→UI routing
├── screens/
│   └── chat_screen.py            # ChatScreen (main UI surface, event handlers, approval flow)
└── widgets/
    ├── input_area.py             # InputArea (multi-line, approval mode)
    ├── message_bubble.py         # MessageBubble (user/assistant containers)
    ├── message_list.py           # MessageList (scrollable, auto-scroll)
    ├── thinking_panel.py         # ThinkingPanel (expandable, ∴ symbol)
    ├── tool_call_panel.py        # ToolCallPanel (expandable, approval display)
    ├── streaming_markdown.py     # StreamingMarkdown (token accumulation)
    ├── status_bar.py             # StatusBar (mode, model, step, context usage)
    └── agent_progress.py         # AgentProgress indicator

orchestrator/                     # Backend (FastAPI)
├── app.py                        # FastAPI entry point, middleware, routers
├── config.py                     # Configuration system (ChatConfig, ProviderConfig)
├── chat_config.yaml              # Runtime settings (single source of truth)
├── schemas.py                    # Pydantic request/response models
├── logging_config.py             # Structured JSON logging
│
├── engine/
│   └── chat_engine.py            # Core chat orchestration
│
├── providers/
│   ├── base.py                   # LLMProvider protocol, LLMResponse dataclass
│   ├── factory.py                # Provider factory (single or chained)
│   ├── openai_compat.py          # OpenAI-compatible client
│   ├── chatgpt.py                # ChatGPT OAuth provider (Codex Responses API)
│   ├── chain.py                  # Provider chain with failover
│   ├── circuit_breaker.py        # Circuit breaker implementation
│   ├── request_builders.py       # Build requests for different endpoints
│   └── response_parsers.py       # Parse responses from different endpoints
│
├── thinking/
│   ├── base.py                   # ThinkingStrategy ABC, StreamParser, data models
│   ├── orchestrator.py           # Strategy registry and routing
│   └── strategies/
│       └── direct.py             # Single model call (fastest)
│
├── agent/
│   ├── agent_engine.py           # Agent loop with tool calling + approval
│   ├── profile.py                # AgentProfile (research/coding), system prompts
│   ├── context.py                # Context strategies (research/coding)
│   ├── planner.py                # Research plan generation
│   ├── state_machine.py          # Agent state management
│   ├── context_pruner.py         # Token budget management
│   ├── query_classifier.py       # Query type classification
│   ├── recovery.py               # Crash recovery support
│   └── tools/
│       ├── base.py               # BaseTool protocol, ToolResult, ToolSchema
│       ├── registry.py           # Tool registry
│       ├── bash_tool.py          # Shell command execution (dangerous)
│       ├── read_file.py          # File reading with line numbers (auto)
│       ├── write_file.py         # File creation/overwrite (confirm)
│       ├── edit_file.py          # Exact string replacement (confirm)
│       ├── glob_tool.py          # File pattern matching (auto)
│       ├── grep_tool.py          # Regex content search (auto)
│       ├── list_directory.py     # Tree-style directory listing (auto)
│       ├── web_search.py         # Parallel.ai web search
│       ├── web_extract.py        # Content extraction
│       ├── python_local.py       # Local Python execution
│       ├── python_daytona.py     # Daytona cloud sandbox
│       └── python_sandbox.py     # E2B sandbox (deprecated)
│
├── models/
│   └── registry.py              # ProviderDef, ModelPreset, ModelRegistry (~25 presets)
│
├── services/
│   └── local_models.py          # GGUF scanning + llama-server lifecycle
│
├── context/
│   ├── budget.py                # ContextBudget tracking and utilization
│   ├── history_builder.py       # Budget-aware conversation history builder
│   └── turn_summary.py          # Compact turn summaries (50-150 tokens)
│
├── routes/
│   ├── conversations.py          # Conversation CRUD
│   ├── runs.py                   # Chat runs + SSE streaming
│   ├── agent_runs.py             # Agent runs + SSE + tool approval endpoints
│   ├── models.py                 # Model registry + local model management
│   ├── auth.py                   # ChatGPT OAuth PKCE flow
│   └── benchmarks.py             # GAIA benchmark traces API
│
├── storage/
│   ├── db.py                     # Async SQLite wrapper
│   ├── schema.sql                # Database schema
│   └── repositories/
│       ├── conversation_repo.py  # Conversation data access
│       ├── trace_repo.py         # Runs and trace events
│       └── agent_repo.py         # Agent-specific tables
│
└── utils/
    ├── tokens.py                 # Token counting (cl100k_base)
    ├── sanitize.py               # Response sanitization
    └── harmony_parser.py         # gpt-oss Harmony format parsing
```

### Application Entry Point (`app.py`)

The FastAPI application initializes with:

1. **Lifespan Management**: Startup loads config, initializes DB; shutdown handles cleanup
2. **Middleware**:
   - `SessionMiddleware`: Cookie-based session isolation for demo mode (mints `demo_session` cookie, sets `request.state.session_id` and `request.state.is_owner`)
   - `RequestLoggingMiddleware`: Request ID correlation and timing (redacts owner tokens from logs)
   - `SecurityHeadersMiddleware`: Security headers (X-Frame-Options, X-Content-Type-Options, Content-Security-Policy, etc.)
   - `RateLimitMiddleware`: IP-based rate limiting for demo mode
   - `CORSMiddleware`: Allows frontend at localhost:3000
3. **Routers**: `/api/conversations`, `/api/runs`, `/api/agent/runs`, `/api/models`, `/api/auth/chatgpt`, `/api/benchmarks`
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
app.include_router(benchmarks.router)  # prefix="/api/benchmarks" in router
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

## CLI/TUI System

The CLI provides a terminal-based interface to the Reasoner agent, built with the [Textual](https://textual.textualize.io/) framework.

### Installation & Invocation

```bash
# Installed via pyproject.toml entry point
reasoner                          # Default (DeepInfra, agent mode)
reasoner --provider chatgpt       # ChatGPT OAuth provider
reasoner --local                  # Interactive local model picker
reasoner --mode chat              # Chat mode (no tools)
reasoner --permission strict      # Require approval for all tools
reasoner --working-dir /path      # Set filesystem root
reasoner --max-steps 20           # Override max agent steps
```

### Screen Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Header (mode + provider/model info)                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  MessageList (scrollable, auto-scroll)                            │
│  ├── MessageBubble (user)                                        │
│  │   └── "What files handle routing?"                            │
│  ├── MessageBubble (assistant)                                   │
│  │   ├── ThinkingPanel (expandable, ∴ symbol)                    │
│  │   ├── ToolCallPanel (expandable, ▸/▾ toggle)                  │
│  │   │   └── "read_file(path=orchestrator/routes/runs.py)"       │
│  │   ├── ToolCallPanel (approval mode)                           │
│  │   │   └── "[y/n] bash(command=grep -r 'router' ...)"         │
│  │   └── StreamingMarkdown (answer tokens)                       │
│  └── ...                                                         │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│  InputArea (multi-line, Enter to submit, Shift+Enter newline)    │
│  [Approval mode: read-only, shows full args, y/n to decide]     │
├─────────────────────────────────────────────────────────────────┤
│  StatusBar (mode | model | step N/M | ctx 15% (14.8k))           │
└─────────────────────────────────────────────────────────────────┘
```

### Tool Approval Flow

The CLI implements a permission-gated approval system for dangerous tool operations:

```
Agent wants to run bash("rm -rf /tmp/old")
        │
        ▼
┌─────────────────────┐
│ Check permission     │
│ policy               │
└──────────┬──────────┘
           │
    ┌──────┴──────┬──────────────┐
    ▼             ▼              ▼
 "yolo"       "relaxed"      "strict"
 (auto)    (auto for read,  (approve all)
           confirm writes)
    │             │              │
    │      ┌──────┴──────┐      │
    │      │ permission  │      │
    │      │ = "auto"?   │      │
    │      └──┬──────┬───┘      │
    │     yes │      │ no       │
    │         │      ▼          │
    │         │  ┌──────────┐   │
    │         │  │ Require  │◄──┘
    │         │  │ approval │
    │         │  └────┬─────┘
    │         │       │
    │         │       ▼
    │         │  SSE: tool_approval_required
    │         │       │
    │         │       ▼
    │         │  InputArea switches to approval mode
    │         │  User presses y (approve) or n (deny)
    │         │       │
    │         │       ▼
    │         │  POST /api/agent/runs/{id}/approve/{tool_call_id}
    │         │  POST /api/agent/runs/{id}/deny/{tool_call_id}
    │         │       │
    ▼         ▼       ▼
       Tool executes (or skipped if denied)
```

**Permission Levels** (per tool):
- `auto` — Read-only tools (read_file, glob, grep, list_directory). Always execute.
- `confirm` — Write tools (edit_file, write_file). Require approval in strict/relaxed.
- `dangerous` — Shell execution (bash). Require approval unless yolo.

**Approval Timeout**: 5 minutes. Tool is denied if no response.

**Resilience**:
- If the server restarts mid-approval (POST returns 404), the CLI shows "Run was interrupted (server restarted)" and resets.
- SSE connection loss (closed/reset/refused) is detected and surfaced as "Connection lost — server may have restarted."
- After approval, the status bar shows "executing tool…" until the tool result arrives.
- `_force_reset_run()` cancels the backend run and resets all UI state on unrecoverable failures.

### Slash Commands

| Command | Description |
|---------|-------------|
| `/login` | Initiate ChatGPT OAuth (opens browser) |
| `/logout` | Clear session, revert to default provider |
| `/status` | Show auth status, provider, and model info |
| `/switch [provider]` | Switch provider mid-session (default, chatgpt) |
| `/help` | Show available commands |

### Event System

The CLI uses Textual message classes to bridge SSE events to widget updates:

| SSE Event | Textual Message | Widget Handler |
|-----------|-----------------|----------------|
| `step_start` | `StepStartEvent` | StatusBar step counter |
| `thinking` | `ThinkingEvent` | ThinkingPanel.append_token() |
| `tool_start` | `ToolStartEvent` | Creates ToolCallPanel |
| `tool_approval_required` | `ToolApprovalRequiredEvent` | InputArea → approval mode |
| `tool_result` | `ToolResultEvent` | ToolCallPanel.set_result() |
| `answer` | `AnswerTokenEvent` | StreamingMarkdown.append_token() |
| `complete` | `AgentCompleteEvent` | Finalize run, show context usage |
| `error` | `AgentErrorEvent` | Display error message |

### Configuration

CLI config is stored at `~/.config/reasoner/`:
- `config.json` — Session cookie, CLI session ID
- `provider` — Persisted provider preference (survives restarts)
- `chatgpt_auth.json` — Backed-up ChatGPT OAuth tokens (survives DB wipes/reinstalls)
- Provider/model selection via CLI flags, `/login`, or `/switch` command
- Profile is always `coding` for CLI usage

**ChatGPT Auth Persistence**: On login, tokens are backed up to `~/.config/reasoner/chatgpt_auth.json`. On startup, the CLI auto-checks saved auth against the backend. If the session expired but backup tokens exist, it attempts a restore via refresh token.

---

## Frontend Architecture

### Directory Structure

```
ui/src/
├── main.tsx                  # React entry point
├── App.tsx                   # Main layout + routing
│
├── components/
│   ├── ConversationView.tsx  # Chat interface (dual mode: chat/agent)
│   ├── ConversationList.tsx  # Sidebar with conversation list
│   ├── DetailPanel.tsx       # Debug trace viewer
│   ├── BenchmarksPage.tsx    # GAIA benchmark results page
│   ├── TracesModal.tsx       # Evaluation trace browser modal
│   ├── AgentRunMessage.tsx   # Agent mode message display
│   ├── AgentStepsPanel.tsx   # Agent progress timeline
│   ├── AnswerMarkdown.tsx    # Markdown + LaTeX rendering + copy button
│   ├── AnswerWithCitations.tsx  # Answer with source citations
│   ├── ThinkingPanel.tsx     # Collapsible thinking display (animated)
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
- Subscribes to `/api/agent/runs/{id}/stream` with per-run stream token
- Processes events: `step_start`, `thinking`, `tool_start`, `tool_result`, `answer`, `complete`
- Supports resumption via `since_seq` parameter and token-authenticated reconnection
- Persists stream token in `localStorage` for page reload recovery
- Updates `agentRunState` in store
- Uses `connectionIdRef` guard to drop events from stale EventSource connections (prevents duplicate processing on reconnect or React StrictMode double-mount)
- Backend uses **cursor-based pub/sub**: events append to `_event_history[run_id]`, each SSE generator tracks its own read cursor, so multiple clients each receive ALL events without interference

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

### ChatGPT Provider

The `ChatGPTProvider` (`orchestrator/providers/chatgpt.py`) enables direct access to ChatGPT models via OAuth:

- **Auth**: OAuth PKCE flow initiated from CLI (`/login` command) or web UI
- **API**: Translates to ChatGPT's Codex Responses API (`chatgpt.com/backend-api/codex/responses`)
- **Translation**: Converts chat completions format → Codex format, maps streaming deltas back
- **Models**: gpt-5.2-codex, o4-mini, gpt-4o, o3
- **Token refresh**: Supports `update_token()` for session management
- **Retry**: Exponential backoff (3 attempts max)

### Local Model Service

The local model service (`orchestrator/services/local_models.py`) manages GGUF models and llama-server lifecycle:

**Model Scanning**: Searches these directories for `.gguf` files:
- `~/.lmstudio/models`
- `~/models`
- `~/.cache/huggingface`
- `~/.cache/lm-studio/models`

**llama-server Management**:
- Start with selected GGUF model on port 8080
- Health check polling during startup
- Graceful shutdown via SIGTERM
- Default context size: 100,000 tokens

**API Endpoints** (`orchestrator/routes/models.py`):
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/models/local` | GET | Scan and list available GGUF models |
| `/api/models/local/start` | POST | Start llama-server with selected model |
| `/api/models/local/stop` | POST | Stop llama-server, revert to cloud |
| `/api/models/status` | GET | Current provider info (local vs cloud) |

**Provider Override**: Starting a local model sets a runtime provider override via `set_provider_override()` in `factory.py`. All subsequent LLM calls route to `localhost:8080`. Stopping clears the override, reverting to the configured cloud provider.

### OpenRouter Support

OpenRouter-hosted models (e.g., `qwen/qwen3.5-35b-a3b`) are auto-detected via base URL containing `openrouter.ai`:

- Sends `reasoning: {"effort": "medium"}` parameter (OpenRouter-specific)
- Parses `reasoning_details` array from response (OpenRouter wraps reasoning in `[{type: "thinking", thinking: "..."}]`)
- Falls back to `reasoning_content` field for standard providers
- XML tool call parsing from reasoning tokens when `api_tool_calls=0` (Qwen puts tool calls in `<think>` output)

### Provider Switching

Switch between providers at runtime:

**Via API** (local models):
```
POST /api/models/local/start  {"model_path": "/path/to/model.gguf"}
POST /api/models/local/stop
```

**Via CLI** (`/switch` command):
```
/switch chatgpt    # Switch to ChatGPT (requires /login first)
/switch default    # Switch to cloud provider (DeepInfra)
```

**Via environment** (`.env`):
```bash
LLM_BASE_URL=http://localhost:8080/v1              # Local llama-server
LLM_BASE_URL=https://api.deepinfra.com/v1/openai   # DeepInfra (default)
LLM_BASE_URL=https://openrouter.ai/api/v1           # OpenRouter
LLM_MODEL=qwen/qwen3.5-35b-a3b
```

**Supported Providers**:
- DeepInfra (cloud, default)
- OpenRouter (cloud, reasoning model support)
- llama-server (local, GGUF models)
- vLLM (local, OpenAI-compatible)
- Ollama (local, via OpenAI compatibility mode)
- ChatGPT (via OAuth, CLI only)

**URL Building**: Handles base URLs that already contain `/v1` to avoid double `/v1/v1/...` paths.

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

### Agent Profiles

Profiles configure the agent's tool set, system prompt, and context strategy:

| Profile | Tools | Context | Max Steps | Use Case |
|---------|-------|---------|-----------|----------|
| `research` | web_search, web_extract, python_execute | Date + knowledge cutoff | 25 | Web UI research mode |
| `coding` | All filesystem + web + python (10 tools) | 5-layer project context | 30 | CLI coding assistant |

**System Prompt Architecture**:
- **UNDERSTAND INTENT**: Focus on what users want, not literal words
- **STEP BACK WHEN STUCK**: If 2 attempts fail, reconsider approach
- **STAY ON TASK**: Track back to original question
- **BEFORE EACH TOOL CALL**: State why (1 sentence max)
- **STOPPING CRITERIA**: Profile-specific rules for when to synthesize
- Forced synthesis at max steps includes accumulated findings

### Available Tools

| Tool | Description | Permission | Idempotent | Profile |
|------|-------------|------------|------------|---------|
| `bash` | Shell command execution | `dangerous` | No | coding |
| `read_file` | Read file with line numbers | `auto` | Yes | coding |
| `write_file` | Create/overwrite file | `confirm` | No | coding |
| `edit_file` | Exact string replacement | `confirm` | No | coding |
| `glob` | File pattern matching | `auto` | Yes | coding |
| `grep` | Regex content search (uses ripgrep if available) | `auto` | Yes | coding |
| `list_directory` | Tree-style directory listing | `auto` | Yes | coding |
| `web_search` | Search the web for information | `auto` | Yes | research, coding |
| `web_extract` | Extract content from URLs | `auto` | Yes | research, coding |
| `python_execute` | Execute Python code | `auto` | No | research, coding |

**Python Execution Providers** (set via `PYTHON_PROVIDER` env var):
- `local` (default): Fast subprocess execution
- `daytona`: Secure cloud sandbox via Daytona SDK (~90ms startup)

### Context Management

The context system prevents token blowout while maintaining relevant information:

```
┌─────────────────────────────────────────────────────────┐
│                  Context Pipeline                         │
│                                                           │
│  1. Context Strategy (profile-dependent)                  │
│     ├─ Research: date + knowledge cutoff                  │
│     └─ Coding: 5-layer project context                    │
│        ├─ Environment (OS, Python/Node versions)          │
│        ├─ Project rules (.reasoner/rules.md, CLAUDE.md)   │
│        ├─ Structure (file tree, dependencies)             │
│        ├─ Git state (branch, status, last 3 commits)      │
│        └─ Working directory                               │
│                                                           │
│  2. History Builder (conversation turns → messages)       │
│                                                           │
│  3. Context Pruner (token-aware)                          │
│     ├─ Keep last 2 steps detailed                         │
│     ├─ Summarize older tool results via LLM               │
│     ├─ Python output: head/tail pattern (not LLM)         │
│     ├─ Cache summaries to prevent duplicates              │
│     └─ Fallback to basic truncation on error              │
└─────────────────────────────────────────────────────────┘
```

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
│ session_id      │  │    │ usage_stats     │       │ duration_ms     │  │
└─────────────────┘  │    │ session_id      │       │ parent_event_id │──┘
                     │    └─────────────────┘       └─────────────────┘
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
                     │                         │    │ approval_decision│ (NEW)
                     │                         │    │ approval_policy │ (NEW)
                     │                         │    │ result_detail   │ (NEW)
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
                     │    ┌─────────────────┐       ┌─────────────────┐
                     │    │   run_events    │ (NEW) │  run_artifacts  │ (NEW)
                     │    ├─────────────────┤       ├─────────────────┤
                     │    │ id              │       │ id              │
                     │    │ run_id          │       │ run_id          │
                     │    │ seq             │       │ artifact_type   │
                     │    │ event_type      │       │ file_path       │
                     │    │ event_data      │       │ action          │
                     │    │ created_at      │       │ detail          │
                     │    └─────────────────┘       │ tool_call_id    │
                     │                              │ created_at      │
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
  api_key: ${LLM_API_KEY:-}
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

# Demo mode for showcase deployments
demo:
  enabled: ${DEMO_MODE:-false}
  owner_secret: ${DEMO_OWNER_SECRET:-}  # Long random string for owner access
  rate_limit:
    max_agent_runs_per_hour: 10    # Agent runs are expensive
    max_chat_runs_per_hour: 30     # Chat runs are cheaper
    window_seconds: 3600           # 1 hour window
  whitelist_ips:                   # IPs that bypass rate limiting
    - "127.0.0.1"
    - "::1"
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
| `DemoConfig` | Demo mode with `RateLimitConfig` for rate limiting and sidebar lock |

---

## Session Isolation (Demo Mode)

When demo mode is enabled, each user gets isolated data via cookie-based sessions.

### How It Works

1. **SessionMiddleware** (`orchestrator/middleware/session.py`) runs on every request:
   - Reads or mints a `demo_session` cookie (UUID, 30-day TTL, httponly)
   - Sets `request.state.session_id` and `request.state.is_owner`
2. **Database scoping**: `session_id` column on `conversations` and `runs` tables (Migration 4)
   - All list/get queries filter by `session_id`
   - Unknown `conversation_id` returns 404 (no existence leak)
3. **Owner bypass**: Owner authenticates via `?owner=<secret>` query param or `X-Owner-Token` header
   - Uses `secrets.compare_digest()` for timing-safe comparison
   - Owner sees all conversations/runs across sessions
   - Owner token is redacted from request logs by `RequestLoggingMiddleware`

### Security Properties

- Identity without authentication (cookie-based, not signed)
- Session cookie: `httponly`, `samesite=lax`, `secure` in production
- SSE streams validate session ownership via in-memory `_run_sessions` dict
- When demo mode is disabled, all requests get `is_owner=True` (full access)

---

## Related Documentation

- [Data Models](DATA_MODELS.md) - Complete data model reference
- [Data Flow](DATA_FLOW.md) - Request lifecycle and streaming
- [Components](COMPONENTS.md) - Detailed component documentation
- [API Reference](API_REFERENCE.md) - Complete API documentation
