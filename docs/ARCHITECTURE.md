# Fluxion Architecture

Comprehensive technical documentation of the Fluxion system architecture.

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

Fluxion is a macOS coding-agent application. A Tauri desktop shell hosts the React/Vite UI, app-managed browser tabs, and integrated terminals; the FastAPI backend (`orchestrator/`) runs chat, coding-agent, model/provider, auth, workspace, and terminal APIs. The repo default cloud provider is Fireworks/Kimi via OpenAI-compatible chat completions, with registry support for OpenAI API, ChatGPT/Codex OAuth, Grok OAuth, xAI, OpenRouter, DeepInfra, and managed local GGUF/MLX launches.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    USER                                          │
│                      ┌──────────┐                                            │
│                      │ Tauri app │                                            │
│                      └────┬─────┘                                            │
└───────────────────────────┼───────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────────────────────┐
│  FRONTEND - React + Vite (:3000 dev, bundled in Tauri desktop)               │
│  ┌─────────────┐  ┌─────────────┐                                            │
│  │ Conversation │──│ Zustand     │                                            │
│  │ Views & UI   │  │ Store       │                                            │
│  └─────────────┘  └──────┬──────┘                                            │
│                   SSE Hooks                                                │
└────────────────────┬──────────────────────────────────────────────────────────┘
                     │ REST API + SSE
                     ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          BACKEND - FastAPI (:9000)                               │
│  ┌──────────────┐   ┌────────────────────┐   ┌────────────────────────────────┐  │
│  │   Routes     │───│    ChatEngine      │───│    Provider Layer              │  │
│  │ /api/*       │   │  orchestration     │   │  OpenAI-compat + ChatGPT      │  │
│  └──────────────┘   └─────────┬──────────┘   └────────────────────────────────┘  │
│                               │                                                   │
│  ┌──────────────┐   ┌─────────▼──────────┐   ┌────────────────────────────────┐  │
│  │ Repositories │   │ ThinkingOrchestrator│   │      Agent Engine             │  │
│  │ SQLite DAOs  │   │  strategy routing   │   │  coding context + tools       │  │
│  └──────────────┘   └────────────────────┘   └────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
                               │                              │
                               ▼                              ▼
┌──────────────────────────────────────────┐  ┌────────────────────────────────────┐
│   LLM Provider                           │  │   SQLite (var/traces.sqlite)       │
│   - Fireworks / OpenAI / OpenRouter     │  │ conversations | runs | trace_events│
│   - ChatGPT/Grok OAuth, xAI, DeepInfra   │  │ coding_sessions | coding_session_  │
│   - /v1/chat/completions (default)       │  │ entries | agent_steps              │
│   - /v1/responses (gpt-oss native)       │  │ agent_tool_calls | run_events      │
│                                           │  │ run_artifacts                      │
│                                           │  └────────────────────────────────────┘
└──────────────────────────────────────────┘
```

### Key Features

- **macOS Desktop + REST API**: Tauri desktop surface, app-managed browser tabs, integrated terminals, plus backend APIs
- **Chat + Coding Agent**: Plain chat runs and workspace-bound coding-agent runs
- **Filesystem Tools**: apply_patch, exec_command/write_stdin, bash, glob, grep, read_file, edit_file, write_file, list_directory
- **Tool Approval Flow**: Permission-gated tool execution (strict/relaxed/yolo policies)
- **Multi-Provider Support**: Fireworks, OpenAI API, ChatGPT/Codex OAuth, Grok OAuth, xAI, OpenRouter, DeepInfra, and local GGUF/MLX
- **Streaming-First**: Real-time token streaming via Server-Sent Events (SSE)
- **Context Management**: Model-aware context profiles, threshold-based conversation compaction, bounded tool-result history, turn summaries, transcript-first coding-session replay for coding-profile follow-ups, metadata-only coding session state, stored-context telemetry, per-file freshness/reread tracking for coding continuity, and project context injection
- **Full Traceability**: Every LLM call, tool execution, approval, and file change is recorded
- **Provider Failover**: Circuit breaker pattern with automatic provider switching
- **Plan/Approve + Pause/Resume/Steer**: Plan Mode proposals, durable plan docs, plan approval/rejection, pause/resume, and mid-run steering
- **Per-Session Message Limits**: Configurable usage caps with owner bypass for demo deployments

---

## Backend Architecture

### Directory Structure

```
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
│   ├── profile.py                # Coding-agent config + system prompt
│   ├── context.py                # Coding workspace context strategy
│   ├── state_machine.py          # Agent state management
│   ├── context_pruner.py         # Token estimation for prompt budgeting
│   ├── recovery.py               # Crash recovery support
│   └── tools/
│       ├── base.py               # BaseTool protocol, ToolResult, ToolSchema
│       ├── registry.py           # Tool registry
│       ├── apply_patch_tool.py   # Atomic Codex-style patches (confirm)
│       ├── command_session.py    # exec_command/write_stdin sessions (dangerous)
│       ├── bash_tool.py          # Legacy shell command execution (dangerous)
│       ├── read_file.py          # File reading with line numbers (auto)
│       ├── write_file.py         # File creation/overwrite (confirm)
│       ├── edit_file.py          # Exact string replacement fallback (confirm)
│       ├── glob_tool.py          # File pattern matching (auto)
│       ├── grep_tool.py          # Regex content search (auto)
│       ├── list_directory.py     # Tree-style directory listing (auto)
│       ├── web_search.py         # Parallel.ai web search
│       ├── web_extract.py        # Content extraction
│       ├── command_session.py    # exec_command/write_stdin shell sessions
│       ├── run_artifacts.py      # Read/list persisted run output artifacts
│       ├── request_user_input.py # Plan Mode/user input bridge
│       ├── update_plan_doc.py    # Plan Mode durable plan updates
│       └── view_image.py         # Local image inspection
│
├── models/
│   └── registry.py              # ProviderDef, ModelPreset, ModelRegistry (~25 presets)
│
├── services/
│   ├── browser_terminal.py      # PTY-backed terminal manager
│   ├── conversation_rewind.py   # Workspace rewind capture/restore
│   ├── grok_auth.py             # Grok CLI/OAuth integration
│   ├── local_models.py          # GGUF/MLX scanning + local server lifecycle
│   ├── model_catalog.py         # Live/curated provider catalog helpers
│   ├── provider_keys.py         # DB-backed provider key storage
│   └── reasoning_settings.py    # Runtime reasoning settings persistence
│
├── context/
│   ├── budget.py                # ContextBudget tracking and utilization
│   ├── context_profile.py       # Normalized active-model context profile
│   ├── history_builder.py       # Budget-aware conversation history builder
│   └── turn_summary.py          # Compact turn summaries (50-150 tokens)
│
├── routes/
│   ├── conversations.py          # Conversation CRUD
│   ├── runs.py                   # Chat runs + SSE streaming
│   ├── agent_runs.py             # Agent runs + SSE + tool approval endpoints
│   ├── models.py                 # Model registry + custom/local runtime management
│   ├── auth.py                   # ChatGPT OAuth PKCE flow
│   ├── grok_auth.py              # Grok OAuth/fallback-code routes
│   ├── models.py                 # Model registry/provider keys/local runtime
│   ├── terminal.py               # PTY terminal sessions + websocket attach
│   ├── workspaces.py             # Workspace browse/search/gitignore APIs
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
3. **Routers**: `/api/conversations`, `/api/runs`, `/api/agent/runs`, `/api/models`, `/api/auth/chatgpt`, `/api/auth/grok`, `/api/workspaces`, `/api/terminal`, `/api/benchmarks`
4. **Health/Config Endpoints**: `/api/health`, `/api/config`

```python
app = FastAPI(title="Fluxion API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(conversations.router)
app.include_router(runs.router)
app.include_router(agent_runs.router)
app.include_router(benchmarks.router)
app.include_router(auth.router)
app.include_router(grok_auth.router)
app.include_router(models.router)
app.include_router(workspaces.router)
app.include_router(terminal.router)
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
├── api/client.ts             # REST + SSE API client
├── assets/                   # UI assets
├── components/
│   ├── ConversationView.tsx  # Browser/desktop conversation surface
│   ├── ConversationList.tsx  # Workspace-grouped sidebar
│   ├── AgentLiveHUD.tsx      # Active agent/Plan Mode HUD
│   ├── AgentRunMessage.tsx   # Agent run transcript rendering
│   ├── AgentStepsPanel.tsx   # Agent progress timeline
│   ├── ToolCallCard.tsx      # Tool approval/result cards
│   ├── IntegratedTerminal.tsx# xterm terminal surface
│   ├── WorkspacePickerDialog.tsx
│   ├── desktop/              # Tauri titlebar, browser pane, terminal panel, composer, status bar
│   └── ui/                   # Shared primitives
├── hooks/
│   ├── useStore.ts           # Zustand store
│   ├── useSSE.ts             # Chat SSE
│   ├── useAgentSSE.ts        # Agent SSE + replay/token auth
│   └── useAgentRunDetails.ts # Trace/artifact loading
├── lib/                      # platform, retry, live agent state, usage metrics
├── styles/                   # Global/theme styles
└── types/                    # Core + agent TypeScript types
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
│       │   └── AgentRunMessage (agent mode)
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

**`useAgentSSE.ts`** (Agent Mode):
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

- **Auth**: OAuth PKCE flow initiated from the desktop/web model picker or API routes
- **API**: Translates to ChatGPT's Codex Responses API (`chatgpt.com/backend-api/codex/responses`)
- **Translation**: Converts chat completions format → Codex format, maps streaming deltas back
- **Models**: current registry allowlist in `orchestrator/models/registry.py` and `chat_config.yaml` (currently GPT-5.5/5.4 family for ChatGPT/Codex)
- **Token refresh**: Supports `update_token()` for session management
- **Retry**: Exponential backoff (3 attempts max)

### Local Model Service

The local model service (`orchestrator/services/local_models.py`) manages GGUF/MLX discovery and local server lifecycle:

**Model Scanning**: Searches these LM Studio directories for local models:
- `~/.lmstudio/models`
- `~/.cache/lm-studio/models`

Ollama subfolders under those roots are intentionally excluded from discovery. GGUF files and MLX model directories are both supported.

**llama-server Management**:
- Start with selected GGUF model on port 8080
- Health check polling during startup
- Graceful shutdown via SIGTERM
- Default GGUF launch context: 131k tokens; MLX launches use larger prefill/prompt-cache defaults. API callers can override `ctx_size`.

**API Endpoints** (`orchestrator/routes/models.py`):
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/models/local` | GET | Scan and list available GGUF/MLX models |
| `/api/models/local/start` | POST | Start `llama-server` or `mlx_lm.server` with selected model |
| `/api/models/local/stop` | POST | Stop llama-server, revert to cloud |
| `/api/models/status` | GET | Current provider info (local vs cloud) |
| `/api/models/provider-keys` | GET | List persisted provider-key availability/status |
| `/api/models/provider-keys/{provider}` | PUT/DELETE | Save or clear a persisted provider API key |
| `/api/models/reasoning-settings` | GET/PUT | Global runtime reasoning controls |

**Provider Override**: Starting a local model sets a runtime provider override via `set_provider_override()` in `factory.py`. The override pins the active local model id into request construction so later agent/chat continuations keep sending the real local model name instead of a stale cloud preset. Stopping clears the override, reverting to the configured cloud provider.

**Launch Logging**: Local launches append to `logs/llama.log` or `logs/mlx.log`, rotate oversized active logs into `*.wal.*` segments, and preserve per-start headers with model path, context size, and command line.

### OpenRouter Support

OpenRouter-hosted models (e.g., `qwen/qwen3.5-35b-a3b`) are auto-detected via base URL containing `openrouter.ai`:

- Sends `reasoning: {"effort": "medium"}` parameter (OpenRouter-specific)
- Parses `reasoning_details` array from response (OpenRouter wraps reasoning in `[{type: "thinking", thinking: "..."}]`)
- Falls back to `reasoning_content` field for standard providers
- XML tool call parsing from reasoning tokens when `api_tool_calls=0` (Qwen puts tool calls in `<think>` output)

### Provider Switching

Switch providers/models at runtime through the model picker or API:

```http
POST /api/models/select
GET  /api/models/provider-keys
PUT  /api/models/provider-keys/{provider}
POST /api/models/local/start
POST /api/models/local/stop
GET  /api/models/status
GET  /api/models/reasoning-settings
PUT  /api/models/reasoning-settings
```

Environment fallback remains available for development:

```bash
LLM_BASE_URL=https://api.fireworks.ai/inference/v1 # Fireworks repo default
LLM_BASE_URL=https://api.deepinfra.com/v1/openai   # DeepInfra
LLM_BASE_URL=https://openrouter.ai/api/v1           # OpenRouter
LLM_BASE_URL=http://localhost:8080/v1               # Existing local OpenAI-compatible server
LLM_MODEL=accounts/fireworks/models/kimi-k2p6
```

Supported provider families in the registry: Fireworks, OpenAI API, ChatGPT/Codex OAuth, Grok OAuth, xAI, OpenRouter, DeepInfra, and local GGUF/MLX. Explicit provider selections fail visibly when credentials are missing; they do not silently fall back to another configured provider.

**URL Building**: Handles base URLs that already contain `/v1` to avoid double `/v1/v1/...` paths.

**Message Alternation**: Some models require strict user/assistant alternation. Provider/request builders normalize message layout and avoid duplicate user messages.

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

Fluxion has one live browser/desktop agent runtime: a workspace-bound coding agent. It is capability-driven per run (`web`, `filesystem`, `bash`, `python`) and uses permission policies (`strict`, `relaxed`, `yolo`) to decide whether tools need approval. Historical research-profile/planner code has been removed from the live path.

### Runtime Loop

```text
Create agent run
  -> resolve conversation/workspace/capabilities/provider/context profile
  -> load coding-session replay + project context
  -> call model with canonical tool schemas
  -> canonicalize tool names and parse native/function tool calls
  -> gate approvals for confirm/dangerous tools
  -> execute tools, persist steps/tool calls/events/artifacts
  -> compact replay context under pressure
  -> accept final assistant text when no tools are pending
```

Completion is evidence-aware but tool-call based: no-tool assistant text can be final, while missing required command/filesystem/web evidence is traced for debugging. Synthetic nudge loops and prose-pattern progress detection are not part of the current completion path.

### Plan Mode

Plan Mode is a collaboration mode for workspace runs. Planning runs create `.fluxion/plans/<run_id>.md`, can update that file through `update_plan_doc`, emit `plan_doc_updated` SSE/artifact events, and wait for explicit approval or rejection through `/api/agent/runs/{run_id}/plan/approve` or `/plan/reject`. Approved implementation runs are linked back to the plan and append progress journal updates.

### State Machine

Live states are `init`, `planning`, `tool_calling`, `synthesizing`, `paused`, `complete`, and `error`. `pause`, `resume`, `steer`, `cancel`, tool approval/denial, user-input responses, and Plan Mode approval/rejection are all exposed as agent routes and SSE events.

### Available Tools

| Tool | Description | Permission | Notes |
|------|-------------|------------|-------|
| `apply_patch` | Atomic add/update/delete/move patches | `confirm` | Workspace-safe; preferred for code edits |
| `exec_command` | Resumable shell command session | `dangerous` | Returns `session_id` for long-running commands |
| `write_stdin` | Poll/write to running command | `dangerous` | Paired with `exec_command` |
| `exec_command`/`write_stdin` | Codex-style local command sessions | `dangerous` | Primary shell/script interface |
| `bash` | Legacy single-shot shell command | `dangerous` | Kept for direct compatibility tests, not live-registered |
| `read_file` | Read files with line numbers/pagination | `auto` | Tracks read spans/freshness |
| `write_file` | Create/overwrite files | `confirm` | Overwrites require explicit argument |
| `edit_file` | Exact string replacement fallback | `confirm` | Returns diffs |
| `glob` | File pattern search | `auto` | Read-only |
| `grep` | Regex content search | `auto` | Uses ripgrep when available |
| `list_directory` | Bounded tree listing | `auto` | Read-only |
| `web_search` | Parallel.ai search | `auto` | Requires `PARALLEL_API_KEY` |
| `web_extract` | Parallel.ai extraction | `auto` | Persists large extracts as artifacts |
| `view_image` | Inspect local image files | `auto` | Vision-capable model support |
| `list_run_artifacts`/`read_artifact` | Read persisted run outputs | `auto` | Exposes `.fluxion/runs/<run_id>/` outputs |
| `request_user_input` | Ask structured user input | `auto` | Plan/collaboration support |
| `update_plan_doc` | Update durable plan markdown | `auto` | Plan Mode only |

### Context Management

Agent prompts are assembled from the system prompt, project context, model context profile, coding-session replay, neutral file/command metadata, and recent raw tool results. `coding_session_entries` are the canonical replay source; `coding_sessions.state_json` is metadata only. When prompt pressure crosses the compaction threshold, the backend writes a visible compaction entry and future prompts use the checkpoint summary plus raw post-compaction history.

Agent SSE/status payloads expose both `context_usage` (current assembled provider prompt) and `stored_context` (replayable persisted conversation context). The desktop composer footer uses `stored_context` for ctx utilization and raw provider usage for lifetime token totals.

### Recovery and Artifacts

Startup cleanup marks orphaned running runs interrupted/failed and persists terminal `_STREAM_END` events for replay. Tool calls have idempotency keys and approval audit fields. Command output, raw web extracts, and other large outputs are written under `.fluxion/runs/<run_id>/` with DB rows in `run_artifacts`; source reads/edits are not dumped wholesale into scratch artifacts.

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
| `AgentRepo` | Agent-specific data | `create_step`, `add_tool_call`, `set_citations`, `get_coding_session_state`, `upsert_coding_session_state`, `append_coding_session_entries`, `list_coding_session_entries`, `mark_coding_session_entries_compacted` |

---

## Configuration System

### Configuration File (`chat_config.yaml`)

Single source of truth for runtime defaults. Current important defaults:

```yaml
provider:
  base_url: ${LLM_BASE_URL:-https://api.fireworks.ai/inference/v1}
  api_key: ${FIREWORKS_API_KEY:-}
  endpoint: ${LLM_ENDPOINT:-chat_completions}
  timeout: 120.0
  slow_response_threshold: 15.0
  max_retries: 3

model:
  name: ${LLM_MODEL:-accounts/fireworks/models/kimi-k2p6}
  temperature: 0.7
  max_tokens: 32768
  reasoning_effort: "medium"

reasoning_controls:
  max_output_tokens: null   # null = selected model max
  reasoning_effort: "medium"

context:
  max_messages: 50
  max_tokens: 100000        # fallback when registry has no profile
  reserve_for_response: 16384

parallel:
  api_key: ${PARALLEL_API_KEY:-}
  search.max_results: 10
  extract.max_urls_per_request: 3

terminal:
  max_sessions_per_conversation: 10
  max_browser_tabs_per_conversation: 10

chatgpt:
  enabled: ${CHATGPT_OAUTH_ENABLED:-true}
  default_model: "gpt-5.5"

demo:
  enabled: ${DEMO_MODE:-false}
  message_limit: ${DEMO_MESSAGE_LIMIT:-10}
```

`provider_chain` remains available but disabled by default. `query_classification` is disabled by default so the model decides tool usage. Live command execution is handled by local `exec_command`/`write_stdin` sessions; Python work uses `python3` through that shell surface.

### Environment Variable Resolution

- `${VAR}` - Required, errors if not set
- `${VAR:-default}` - Optional with default value

Variables are resolved before Pydantic validation.

### Key Configuration Classes

| Class | Purpose |
|-------|---------|
| `ProviderConfig` | LLM endpoint, retry settings, fallback policy, `slow_response_threshold` |
| `ProviderChainConfig` | Multi-provider failover with circuit breakers |
| `ChatModelConfig` | Model name, temperature, max_tokens, reasoning_effort and sampling controls |
| `ChatContextConfig` | Conversation history limits, truncation |
| `ChatTracingConfig` | Chat-level tracing (enabled, log_level, log_model_calls) |
| `ThinkingConfig` | Mode mapping, ThinkingTracingConfig, ThinkingUIConfig |
| `QueryClassificationConfig` | Legacy keyword enforcement controls; disabled by default |
| `ParallelConfig` | Web search/extract with nested `ParallelSearchConfig`, `ParallelExtractConfig` |
| `SandboxConfig` | Legacy sandbox config retained for compatibility; not used by default |
| `DemoConfig` | Demo mode with `RateLimitConfig`, owner bypass, and per-session message limits |

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
