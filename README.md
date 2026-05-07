# Fluxion

An AI agent application with browser-based chat and coding workflows, web search, Python execution, and reasoning capabilities. FastAPI backend + React/Vite frontend, backed by SQLite for full traceability.

## What It Does

- **Web UI + API**: React frontend with FastAPI backend APIs
- **Dual Mode**: Chat mode and browser coding-agent mode
- **10 Tools**: Web search, content extraction, Python execution, file read/write/edit, bash, grep, glob, directory listing
- **Model Registry**: ~25 presets across OpenRouter, DeepInfra, and local providers with hot-swap
- **Local Models**: Scan GGUF files, start/stop llama-server, runtime provider switching
- **ChatGPT OAuth**: Use ChatGPT Plus/Pro subscription as a provider (GPT-5.2 Codex, o4-mini, o3)
- **Streaming**: Real-time token streaming via Server-Sent Events (SSE) with auto-reconnect
- **Provider Abstraction**: OpenAI-compatible providers (DeepInfra, OpenRouter, llama-server, vLLM, Ollama, ChatGPT)
- **Provider Failover**: Circuit breaker pattern with automatic provider switching
- **Context Management**: Token-aware history pruning, turn summaries, provider-aware budgets
- **Tool Approval**: Permission-gated tool execution (strict/relaxed/yolo policies)
- **Full Traceability**: Every LLM call, tool execution, approval, and agent step recorded in SQLite
- **Benchmarks**: GAIA benchmark evaluation with results dashboard
- **Demo Mode**: Rate limiting, session isolation, and sidebar restrictions for public deployments
- **Mobile-Responsive**: Progressive enhancement from 320px phones to 1920px+ desktops

## Documentation

Comprehensive documentation is available in the `docs/` folder:

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture with diagrams |
| [COMPONENTS.md](docs/COMPONENTS.md) | Every backend and frontend component |
| [DATA_MODELS.md](docs/DATA_MODELS.md) | Database schema, Pydantic models, TypeScript types |
| [DATA_FLOW.md](docs/DATA_FLOW.md) | Request lifecycle, streaming, provider failover |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | Complete REST API and SSE documentation |
| [BENCHMARKS.md](docs/BENCHMARKS.md) | GAIA benchmark results and methodology |
| [IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md) | Feature tracking and change history |
| [WORKFLOW.md](docs/WORKFLOW.md) | Development process guide |
| [RAILWAY_CLI.md](docs/RAILWAY_CLI.md) | Railway deployment guide (staging/production) |
| [CHATGPT_OAUTH_INTEGRATION.md](docs/CHATGPT_OAUTH_INTEGRATION.md) | OAuth flow design |

## Architecture Snapshot

```
Browser (React + Vite)
  - Conversation list, chat view,
    agent steps panel, model picker
  - Zustand store, SSE hooks
        |
        | HTTP + SSE
        v
FastAPI Backend (:9000)
  - Routes: conversations, runs, agent/runs, models, auth, benchmarks
  - ChatEngine: model orchestration + streaming
  - AgentEngine: coding prompt, tool calling, approval, synthesis
  - ThinkingOrchestrator: strategy selection (direct)
  - Model Registry: ~25 presets, hot-swap, provider resolution
  - Provider layer: LLMProvider protocol + circuit breaker + ChatGPT OAuth
  - Context management: token budgets, turn summaries, history builder
  - Middleware: rate limiting, session isolation, security headers, request logging
  - SQLite repositories (conversations, runs, trace_events,
                         agent_steps, agent_tool_calls, chatgpt_tokens)
        |
        | OpenAI-compatible HTTP
        v
LLM Providers
  - DeepInfra (cloud default)
  - OpenRouter (Qwen, Llama, etc.)
  - ChatGPT (OAuth + Codex API)
  - llama-server / vLLM / Ollama (local)

        |
        | HTTP APIs
        v
External Tools
  - Parallel.ai (web search + content extraction)
  - Python execution (local subprocess, E2B sandbox, or Daytona)
```

## Quick Start

### 1) Install dependencies

```bash
# Python
uv sync

# UI
cd ui && pnpm install

# Or both:
just install
```

### 2) Configure environment

```bash
# Required for cloud deployment (DeepInfra)
export DEEPINFRA_API_KEY=your_key

# Required for agent web search
export PARALLEL_API_KEY=your_key

# Optional: OpenRouter models
export OPENROUTER_API_KEY=your_key

# Optional overrides
export LLM_BASE_URL=http://localhost:8080/v1  # For local llama-server
export LLM_MODEL=your-model-name
export LLM_ENDPOINT=chat_completions         # responses | chat_completions | auto
```

### 3) Run the app

```bash
# UI + API
just dev
# or
./dev.sh start
```

Or separately:

```bash
uv run uvicorn orchestrator.app:app --host 127.0.0.1 --port 9000 --reload
cd ui && pnpm dev
```

Open http://localhost:3000

### 4) CLI (optional)

```bash
# Install CLI entry point
uv pip install -e ".[cli]"

# Run
reasoner                          # Default (DeepInfra, agent mode)
reasoner --provider chatgpt       # ChatGPT via OAuth
reasoner --local                  # Interactive local model picker
reasoner --mode chat              # Chat mode (no tools)
reasoner --permission strict      # Require approval for all tools
reasoner --working-dir /path      # Set filesystem root
reasoner --max-steps 20           # Override max agent steps
```

**In-CLI commands**: `/login`, `/logout`, `/status`, `/switch`, `/model`, `/help`
**Keyboard shortcuts**: `Ctrl+M` (model picker), `Ctrl+K` (new chat), `Ctrl+C` (exit)

## Agent Framework

The agent operates as a state machine with planning, tool execution, and synthesis:

```
Query -> Profile Selection -> Plan -> Execute Tools (loop) -> Synthesize Answer
```

### Agent Profiles

| Profile | Tools | Use Case |
|---------|-------|----------|
| **Research** | web_search, web_extract, python_execute | Web research, data analysis, fact-finding |
| **Coding** | All research tools + read_file, write_file, edit_file, bash, grep, glob, list_directory | Code editing, debugging, file operations |

### Available Tools

| Tool | Description | Provider | Permission |
|------|-------------|----------|------------|
| `web_search` | Search the web for information | Parallel.ai | auto |
| `web_extract` | Extract content from URLs | Parallel.ai | auto |
| `python_execute` | Run Python code for calculations | Local / E2B / Daytona | auto |
| `read_file` | Read file contents with line numbers | Local filesystem | auto |
| `write_file` | Create or overwrite files | Local filesystem | confirm |
| `edit_file` | Exact string replacement in files | Local filesystem | confirm |
| `bash` | Execute shell commands | Local subprocess | dangerous |
| `grep` | Regex content search across files | Local filesystem | auto |
| `glob` | Pattern-based file matching | Local filesystem | auto |
| `list_directory` | Tree-style directory listing | Local filesystem | auto |

### Agent Features

- **Planning Step**: Generates a structured research/coding plan before executing (configurable)
- **Query Classification**: Detects query type (calculation, research, general) for tool selection
- **Context Pruning**: Smart token budget management with provider-aware limits (up to 250k)
- **Crash Recovery**: Idempotency keys and execution attempt tracking
- **Citation Tracking**: Sources from web search are linked in the final answer
- **Tool Approval**: Permission-gated execution (auto/confirm/dangerous per tool)
- **Parallel Execution**: Read-only tools can execute in parallel for faster results

## Model Registry

Hot-swap models without restart via the registry system:

```bash
# CLI: Ctrl+M or /model to open picker
# API: POST /api/models/select {"model": "qwen3-72b"}
# API: GET /api/models (list all presets)
```

Supports ~25 presets across providers:
- **OpenRouter**: Qwen 3, Llama 4, DeepSeek R1/V3, Gemma 3, Mistral, etc.
- **DeepInfra**: gpt-oss-120b, Llama 4 Scout/Maverick, etc.
- **Local**: Any GGUF model via llama-server

## Repository Layout

```
fluxion/
├── orchestrator/              # Backend (FastAPI)
│   ├── app.py                 # FastAPI entrypoint, middleware, routers
│   ├── config.py              # ChatConfig + loader for chat_config.yaml
│   ├── chat_config.yaml       # Runtime settings (single source of truth)
│   ├── schemas.py             # API request/response models
│   ├── logging_config.py      # Structured JSON logging
│   ├── engine/
│   │   └── chat_engine.py     # Orchestrates model calls + streaming
│   ├── agent/
│   │   ├── agent_engine.py    # Agent loop with tool calling + approval
│   │   ├── profile.py         # Agent profiles (research/coding) + system prompts
│   │   ├── factory.py         # AgentEngine factory with profile resolution
│   │   ├── planner.py         # Research/coding plan generation
│   │   ├── context.py         # Context strategies (research/coding)
│   │   ├── state_machine.py   # Agent state management
│   │   ├── context_pruner.py  # Token budget management
│   │   ├── query_classifier.py# Query type classification
│   │   ├── recovery.py        # Crash recovery support
│   │   └── tools/
│   │       ├── base.py        # BaseTool protocol
│   │       ├── registry.py    # Tool registry
│   │       ├── web_search.py  # Parallel.ai web search
│   │       ├── web_extract.py # Content extraction
│   │       ├── python_local.py    # Local Python execution
│   │       ├── python_daytona.py  # Daytona cloud sandbox
│   │       ├── python_sandbox.py  # E2B sandbox (optional)
│   │       ├── read_file.py       # File reading
│   │       ├── write_file.py      # File writing
│   │       ├── edit_file.py       # Exact string replacement
│   │       ├── bash_tool.py       # Shell command execution
│   │       ├── grep_tool.py       # Regex file search
│   │       ├── glob_tool.py       # Pattern-based file matching
│   │       └── list_directory.py  # Directory listing
│   ├── models/                # Model registry
│   │   └── registry.py        # ProviderDef, ModelPreset, ModelRegistry
│   ├── services/              # External service management
│   │   └── local_models.py    # GGUF scanning + llama-server lifecycle
│   ├── providers/             # LLM provider abstraction layer
│   │   ├── base.py            # LLMProvider protocol, LLMResponse
│   │   ├── factory.py         # Provider factory (single, chained, or registry)
│   │   ├── openai_compat.py   # OpenAI-compatible client
│   │   ├── chatgpt.py         # ChatGPT OAuth provider (Codex Responses API)
│   │   ├── chain.py           # Provider chain with failover
│   │   ├── circuit_breaker.py # Circuit breaker implementation
│   │   ├── request_builders.py
│   │   └── response_parsers.py
│   ├── thinking/              # Thinking strategies + orchestrator
│   │   ├── base.py            # ThinkingStrategy, StreamParser, data models
│   │   ├── orchestrator.py    # Strategy registry and routing
│   │   └── strategies/
│   │       └── direct.py      # Single model call (fastest)
│   ├── context/               # Token-aware context management
│   │   ├── budget.py          # ContextBudget tracking
│   │   ├── history_builder.py # Budget-aware conversation history
│   │   └── turn_summary.py    # Compact turn summaries (50-150 tokens)
│   ├── middleware/
│   │   ├── rate_limit.py      # IP-based rate limiting for demo mode
│   │   └── session.py         # Cookie-based session isolation
│   ├── routes/
│   │   ├── conversations.py   # Conversation CRUD
│   │   ├── runs.py            # Chat runs + SSE streaming
│   │   ├── agent_runs.py      # Agent runs + SSE streaming + tool approval
│   │   ├── models.py          # Model registry + local model management
│   │   ├── auth.py            # ChatGPT OAuth endpoints
│   │   └── benchmarks.py      # GAIA benchmark results
│   ├── storage/               # SQLite schema + repositories
│   │   ├── db.py
│   │   ├── schema.sql
│   │   └── repositories/
│   │       ├── conversation_repo.py
│   │       ├── trace_repo.py
│   │       └── agent_repo.py
│   ├── reporting/             # Report builder for runs
│   └── utils/                 # Token counting, sanitization, parsing
├── ui/                        # Frontend (React + Vite)
│   └── src/
│       ├── App.tsx                    # Main layout + routing
│       ├── components/
│       │   ├── ConversationView.tsx   # Chat interface + agent mode
│       │   ├── ConversationList.tsx   # Sidebar conversation list
│       │   ├── AgentRunMessage.tsx    # Agent run display
│       │   ├── AgentStepsPanel.tsx    # Agent steps visualization
│       │   ├── ToolCallCard.tsx       # Tool execution display
│       │   ├── AnswerMarkdown.tsx     # Markdown + LaTeX rendering
│       │   ├── AnswerWithCitations.tsx# Answer with source citations
│       │   ├── ThinkingPanel.tsx      # Thinking display (sanitized)
│       │   ├── DetailPanel.tsx        # Debug trace viewer
│       │   ├── BenchmarksPage.tsx     # GAIA benchmark results
│       │   ├── TracesModal.tsx        # Evaluation traces viewer
│       │   └── CitationInline.tsx     # Inline citation badge
│       ├── hooks/             # Zustand store, SSE hooks
│       ├── api/               # REST + SSE client
│       ├── types/             # Shared TS types
│       └── lib/               # Utilities, retry logic
├── docs/                      # Comprehensive documentation
├── tests/                     # Unit + integration tests
├── scripts/                   # Dev and test scripts
│   ├── sanity_test.sh         # Browser coding smoke test with a real provider
│   ├── test_loop.sh           # Watch mode for tests
│   └── gaia/                  # GAIA benchmark runner
├── justfile                   # Dev tasks
├── dev.sh                     # Development control script
├── Procfile.dev               # Process manager config
└── var/                       # SQLite DB and runtime artifacts
```

## Thinking System

The backend supports reasoning strategies under `orchestrator/thinking/strategies/`:

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `direct` | Single model call, no explicit reasoning | Fast responses, models with native reasoning |

**Native Reasoning (gpt-oss)**: When using gpt-oss models, set `reasoning_effort` (low/medium/high) in config. The model's native reasoning is captured and displayed as `thinking_summary`.

## Provider Abstraction

All LLM interactions go through the provider layer (`orchestrator/providers/`):

- **Dual endpoint support**: Tries `/v1/responses` first, falls back to `/v1/chat/completions`
- **Retry logic**: Exponential backoff with jitter for transient failures
- **Circuit breaker**: Tracks provider health, auto-switches on repeated failures
- **Provider chain**: Priority-based failover across multiple providers (e.g., DeepInfra -> Together AI)
- **ChatGPT OAuth**: Direct access to ChatGPT Plus/Pro models via Codex Responses API
- **OpenRouter**: Auto-detected via base URL, supports reasoning params
- **Model registry**: Resolve aliases to full provider configs, hot-swap at runtime
- **Native reasoning**: Captures gpt-oss reasoning via separate callback
- **Tool support**: Structured tool calls with compatible models

## Data & Tracing

SQLite stores these core entities:

| Table | Description |
|-------|-------------|
| `conversations` | Chat sessions with title, summary, status |
| `runs` | One run per user message, stores final answer + thinking summary |
| `trace_events` | Granular timeline of LLM requests/responses/errors/thinking steps |
| `agent_steps` | Agent execution steps (plan, search, extract, synthesize) |
| `agent_tool_calls` | Individual tool call results with idempotency keys |
| `agent_citations` | Source citations from web research |
| `run_events` | SSE event persistence for replay |
| `run_artifacts` | Generated files/artifacts |
| `chatgpt_tokens` | OAuth token storage |

## API Summary

### Conversations

- `POST /api/conversations` - Create conversation
- `GET /api/conversations` - List conversations
- `GET /api/conversations/{id}` - Get conversation + runs
- `PATCH /api/conversations/{id}` - Update (title, summary, status)
- `DELETE /api/conversations/{id}` - Delete conversation
- `GET /api/conversations/{id}/traces` - Get all conversation traces

### Runs

- `POST /api/conversations/{id}/runs` - Send message (returns stream URL)
- `POST /api/runs` - Create standalone run
- `GET /api/runs` - List runs (paginated)
- `GET /api/runs/{id}` - Get run details
- `GET /api/runs/{id}/stream` - SSE stream (tokens, events)
- `GET /api/runs/{id}/events` - Get model call events
- `GET /api/runs/{id}/timeline` - Get trace event timeline
- `GET /api/runs/{id}/report` - Get markdown report
- `GET /api/runs/{id}/thinking` - Get thinking traces
- `POST /api/runs/{id}/abort` - Cancel run

### Agent Runs

- `POST /api/agent/runs` - Create agent run (query, max_steps, profile)
- `GET /api/agent/runs/{id}` - Get agent run status + steps
- `GET /api/agent/runs/{id}/trace` - Get full agent trace
- `GET /api/agent/runs/{id}/stream` - SSE stream (agent events)
- `POST /api/agent/runs/{id}/cancel` - Cancel agent run
- `POST /api/agent/runs/{id}/approve/{tool_call_id}` - Approve tool execution
- `POST /api/agent/runs/{id}/deny/{tool_call_id}` - Deny tool execution

### Models

- `GET /api/models` - List model registry presets (grouped by provider)
- `POST /api/models/select` - Hot-swap active model
- `GET /api/models/status` - Current provider info
- `GET /api/models/local` - Scan available GGUF models
- `POST /api/models/local/start` - Start llama-server
- `POST /api/models/local/stop` - Stop llama-server

### Auth

- `GET /api/auth/chatgpt/login` - Initiate ChatGPT OAuth
- `GET /api/auth/chatgpt/callback` - OAuth callback
- `GET /api/auth/chatgpt/status` - Check auth status
- `POST /api/auth/chatgpt/logout` - Clear tokens
- `POST /api/auth/chatgpt/refresh` - Force token refresh
- `GET /api/auth/chatgpt/export` - Export tokens for CLI backup
- `POST /api/auth/chatgpt/restore` - Restore tokens from backup

### System

- `GET /api/health` - Health check
- `GET /api/config` - Get current configuration

## Configuration

All runtime settings live in `orchestrator/chat_config.yaml`:

```yaml
provider:
  base_url: ${LLM_BASE_URL:-https://api.deepinfra.com/v1/openai}
  api_key: ${LLM_API_KEY:-}
  endpoint: ${LLM_ENDPOINT:-chat_completions}
  fallback_on_404: true

model:
  name: ${LLM_MODEL:-openai/gpt-oss-120b}
  temperature: 1.0
  max_tokens: 16384
  reasoning_effort: "medium"    # For gpt-oss: low | medium | high

context:
  max_messages: 50
  max_tokens: 100000
  reserve_for_response: 16384

parallel:                       # Web search & extract (Parallel.ai)
  api_key: ${PARALLEL_API_KEY:-}

chatgpt:                        # ChatGPT OAuth integration
  enabled: ${CHATGPT_OAUTH_ENABLED:-true}
  default_model: "gpt-5.2-codex"

agent_planning:
  enabled: true
  max_plan_steps: 5

demo:
  enabled: ${DEMO_MODE:-false}
  rate_limit:
    max_agent_runs_per_hour: 10
    max_chat_runs_per_hour: 30
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_API_KEY` | LLM provider API key | (none) |
| `DEEPINFRA_API_KEY` | DeepInfra API key | (none) |
| `OPENROUTER_API_KEY` | OpenRouter API key | (none) |
| `PARALLEL_API_KEY` | Parallel.ai API key (web search) | (none) |
| `LLM_BASE_URL` | LLM provider base URL | `https://api.deepinfra.com/v1/openai` |
| `LLM_MODEL` | Model name | `openai/gpt-oss-120b` |
| `LLM_ENDPOINT` | Endpoint type | `chat_completions` |
| `DEMO_MODE` | Enable demo mode | `false` |
| `DEMO_OWNER_SECRET` | Owner bypass secret | (none) |
| `CHATGPT_OAUTH_ENABLED` | Enable ChatGPT OAuth | `true` |
| `DAYTONA_API_KEY` | Daytona sandbox API key | (none) |
| `REASONER_MODEL` | CLI model override | (none) |

Environment variable syntax in config:
- `${VAR}` - Required, errors if not set
- `${VAR:-default}` - Optional with default value

Changes require a backend restart.

## Deployment

Deployed on **Railway** with staging and production environments. See [docs/RAILWAY_CLI.md](docs/RAILWAY_CLI.md) for the complete CLI reference.

```bash
railway up --service backend --environment staging      # Deploy to staging
railway up --service backend --environment production   # Deploy to production
railway logs --service backend --environment production  # Check logs
```
