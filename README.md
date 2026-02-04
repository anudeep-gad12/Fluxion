# Is It Frontier?

An AI agent application with multi-step research, web search, Python execution, and reasoning capabilities. FastAPI backend + React/Vite frontend, backed by SQLite for full traceability.

## What It Does

- **Dual Mode**: Chat mode (conversational AI) and Agent mode (multi-step research with tools)
- **Agent Framework**: Planning, web search, content extraction, Python execution, findings synthesis
- **Streaming**: Real-time token streaming via Server-Sent Events (SSE) with auto-reconnect
- **Provider Abstraction**: OpenAI-compatible providers (DeepInfra cloud default, supports local llama-server, vLLM, Ollama)
- **Provider Failover**: Circuit breaker pattern with automatic provider switching
- **Full Traceability**: Every LLM call, tool execution, and agent step recorded in SQLite
- **Benchmarks**: GAIA benchmark evaluation with results dashboard
- **Demo Mode**: Rate limiting, session isolation, and sidebar restrictions for public deployments
- **Mobile-Responsive**: Progressive enhancement from 320px phones to 1920px+ desktops

## Documentation

Comprehensive documentation is available in the `docs/` folder:

| Document | Description |
|----------|-------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture with diagrams |
| [docs/COMPONENTS.md](docs/COMPONENTS.md) | Every backend and frontend component |
| [docs/DATA_MODELS.md](docs/DATA_MODELS.md) | Database schema, Pydantic models, TypeScript types |
| [docs/DATA_FLOW.md](docs/DATA_FLOW.md) | Request lifecycle, streaming, provider failover |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Complete REST API and SSE documentation |
| [docs/BENCHMARKS.md](docs/BENCHMARKS.md) | GAIA benchmark results and methodology |
| [docs/IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md) | Feature tracking and change history |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Development process guide |

## Architecture Snapshot

```
Browser (React + Vite)
  - Conversation list, chat view, agent steps panel
  - Zustand store, SSE hooks (useSSE, useAgentSSE)
        |
        | HTTP + SSE
        v
FastAPI Backend
  - Routes: conversations, runs, agent/runs, benchmarks
  - ChatEngine: model orchestration + streaming
  - AgentEngine: planning, tool calling, synthesis
  - ThinkingOrchestrator: strategy selection (direct)
  - Provider layer: LLMProvider protocol + circuit breaker
  - Middleware: rate limiting, session isolation, security headers, request logging
  - SQLite repositories (conversations, runs, trace_events,
                         agent_steps, agent_tool_calls)
        |
        | OpenAI-compatible HTTP
        v
LLM Provider (DeepInfra / llama-server / vLLM / Ollama)

        |
        | HTTP APIs
        v
External Tools
  - Parallel.ai (web search + content extraction)
  - Python execution (local subprocess or Daytona sandbox)
```

## Quick Start

### 1) Install dependencies

```bash
# Python
uv sync
```

```bash
# UI
cd ui && pnpm install
```

Or:

```bash
just install
```

### 2) Configure environment

```bash
# Required for cloud deployment (DeepInfra)
export DEEPINFRA_API_KEY=your_key

# Required for agent web search
export PARALLEL_API_KEY=your_key

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

## Agent Framework

The agent operates as a state machine with planning, tool execution, and synthesis:

```
Query -> Plan -> Execute Tools (loop) -> Synthesize Answer
```

### Available Tools

| Tool | Description | Provider |
|------|-------------|----------|
| `web_search` | Search the web for information | Parallel.ai |
| `web_extract` | Extract content from URLs | Parallel.ai |
| `python_execute` | Run Python code for calculations | Local subprocess or Daytona |

### Agent Features

- **Planning Step**: Generates a structured research plan before executing (configurable)
- **Query Classification**: Detects query type (calculation, research, general) for tool selection
- **Findings Accumulator**: Extracts and tracks key findings across tool executions
- **Context Pruning**: LLM-based summarization to stay within token budgets
- **Crash Recovery**: Idempotency keys and execution attempt tracking
- **Citation Tracking**: Sources from web search are linked in the final answer

## Repository Layout

```
reasoner/
├── orchestrator/              # Backend (FastAPI)
│   ├── app.py                 # FastAPI entrypoint, middleware, routers
│   ├── config.py              # ChatConfig + loader for chat_config.yaml
│   ├── chat_config.yaml       # Runtime settings (single source of truth)
│   ├── schemas.py             # API request/response models
│   ├── logging_config.py      # Structured JSON logging
│   ├── engine/
│   │   └── chat_engine.py     # Orchestrates model calls + streaming
│   ├── agent/
│   │   ├── agent_engine.py    # Agent loop with tool calling
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
│   │       └── python_sandbox.py  # E2B sandbox (optional)
│   ├── providers/             # LLM provider abstraction layer
│   │   ├── base.py            # LLMProvider protocol, LLMResponse
│   │   ├── factory.py         # Provider factory (single or chained)
│   │   ├── openai_compat.py   # OpenAI-compatible client
│   │   ├── chain.py           # Provider chain with failover
│   │   ├── circuit_breaker.py # Circuit breaker implementation
│   │   ├── request_builders.py
│   │   └── response_parsers.py
│   ├── thinking/              # Thinking strategies + orchestrator
│   │   ├── base.py            # ThinkingStrategy, StreamParser, data models
│   │   ├── orchestrator.py    # Strategy registry and routing
│   │   └── strategies/
│   │       └── direct.py      # Single model call (fastest)
│   ├── middleware/
│   │   ├── rate_limit.py      # IP-based rate limiting for demo mode
│   │   └── session.py         # Cookie-based session isolation
│   ├── routes/
│   │   ├── conversations.py   # Conversation CRUD
│   │   ├── runs.py            # Chat runs + SSE streaming
│   │   ├── agent_runs.py      # Agent runs + SSE streaming
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
│       ├── components/
│       │   ├── ConversationView.tsx  # Chat interface + agent mode
│       │   ├── ConversationList.tsx  # Sidebar conversation list
│       │   ├── AgentRunMessage.tsx   # Agent run display
│       │   ├── AgentStepsPanel.tsx   # Agent steps visualization
│       │   ├── ToolCallCard.tsx      # Tool execution display
│       │   ├── BenchmarksPage.tsx    # GAIA benchmark results
│       │   ├── TracesModal.tsx       # Evaluation traces viewer
│       │   ├── DetailPanel.tsx       # Trace/event inspector
│       │   ├── ThinkingPanel.tsx     # Thinking display
│       │   └── AnswerMarkdown.tsx    # Markdown rendering
│       ├── hooks/             # Zustand store, SSE hooks
│       ├── api/               # REST + SSE client
│       └── types/             # Shared TS types
├── docs/                      # Comprehensive documentation
├── tests/                     # Unit + integration tests
├── scripts/                   # Dev and test scripts
├── Procfile                   # Dev process manager
├── justfile                   # Dev tasks
└── var/                       # SQLite DB and runtime artifacts
```

## Thinking System

The backend supports reasoning strategies under `orchestrator/thinking/strategies/`:

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `direct` | Single model call, no explicit reasoning | Fast responses, gpt-oss with native reasoning |

**Native Reasoning (gpt-oss)**: When using gpt-oss models, set `reasoning_effort` (low/medium/high) in config. The model's native reasoning is captured and displayed as `thinking_summary`.

## Provider Abstraction

All LLM interactions go through the provider layer (`orchestrator/providers/`):

- **Dual endpoint support**: Tries `/v1/responses` first, falls back to `/v1/chat/completions`
- **Retry logic**: Exponential backoff with jitter for transient failures
- **Circuit breaker**: Tracks provider health, auto-switches on repeated failures
- **Provider chain**: Priority-based failover across multiple providers (e.g., DeepInfra -> Together AI)
- **Native reasoning**: Captures gpt-oss reasoning via separate callback
- **Tool support**: Structured tool calls with gpt-oss models

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

- `POST /api/agent/runs` - Create agent run (query, max_steps)
- `GET /api/agent/runs/{id}` - Get agent run status + steps
- `GET /api/agent/runs/{id}/trace` - Get full agent trace
- `GET /api/agent/runs/{id}/stream` - SSE stream (agent events)
- `POST /api/agent/runs/{id}/cancel` - Cancel agent run

### System

- `GET /api/health` - Health check
- `GET /api/config` - Get current configuration

## Configuration

All runtime settings live in `orchestrator/chat_config.yaml`:

```yaml
provider:
  base_url: ${LLM_BASE_URL:-https://api.deepinfra.com/v1/openai}
  api_key: ${DEEPINFRA_API_KEY:-}
  endpoint: ${LLM_ENDPOINT:-chat_completions}
  fallback_on_404: true

model:
  name: ${LLM_MODEL:-openai/gpt-oss-120b}
  temperature: 1.0
  max_tokens: 4096
  reasoning_effort: "medium"    # For gpt-oss: low | medium | high

context:
  max_messages: 50
  max_tokens: 100000

parallel:                       # Web search & extract (Parallel.ai)
  api_key: ${PARALLEL_API_KEY:-}

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
| `DEEPINFRA_API_KEY` | DeepInfra API key | (none) |
| `PARALLEL_API_KEY` | Parallel.ai API key (web search) | (none) |
| `LLM_BASE_URL` | LLM provider base URL | `https://api.deepinfra.com/v1/openai` |
| `LLM_MODEL` | Model name | `openai/gpt-oss-120b` |
| `LLM_ENDPOINT` | Endpoint type | `chat_completions` |
| `DEMO_MODE` | Enable demo mode | `false` |
| `DEMO_OWNER_SECRET` | Owner bypass secret | (none) |
| `DAYTONA_API_KEY` | Daytona sandbox API key | (none) |

Environment variable syntax in config:
- `${VAR}` - Required, errors if not set
- `${VAR:-default}` - Optional with default value

Changes require a backend restart.
