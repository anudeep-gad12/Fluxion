# Reasoner

A local AI chat application with a FastAPI backend, React + Vite UI, and pluggable thinking system. It streams tokens in real time, stores full traces in SQLite, and exposes a REST + SSE API.

## What It Does

- Runs local or OpenAI-compatible LLMs via HTTP (LM Studio, vLLM, Ollama, OpenAI)
- Provider abstraction layer with dual endpoint support (`/v1/responses` + `/v1/chat/completions`)
- Two reasoning strategies: **direct** (single call) and **cot** (chain-of-thought with token budgets)
- Native reasoning support for gpt-oss models via `reasoning_effort` parameter
- Streams answer and thinking tokens over SSE
- Persists conversations, runs, and trace events in SQLite
- Provides a UI for chats, streaming, thinking display, and trace inspection

## Architecture Snapshot

```
Browser (React + Vite)
  - Conversation list, chat view, thinking panel, trace panel
  - Zustand store, SSE hook
        |
        | HTTP + SSE
        v
FastAPI Backend
  - Routes: conversations, runs
  - ChatEngine: model orchestration + streaming
  - ThinkingOrchestrator: strategy selection (direct, cot)
  - Provider abstraction: LLMProvider protocol
  - SQLite repositories (conversations, runs, trace_events)
        |
        | OpenAI-compatible HTTP
        v
LLM Server (LM Studio / vLLM / Ollama / OpenAI)
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

### 2) Start a model server

- **LM Studio** (default): Run a model on `http://127.0.0.1:1234`
- **Ollama**: `ollama serve` on default port
- **vLLM**: Start with OpenAI-compatible API enabled

### 3) Run the app

```bash
# UI + API (Procfile)
honcho start
```

Or separately:

```bash
uv run uvicorn orchestrator.app:app --host 127.0.0.1 --port 9000 --reload
cd ui && pnpm dev
```

Open http://localhost:3000

## Repository Layout

```
reasoner/
├── orchestrator/              # Backend (FastAPI)
│   ├── app.py                 # FastAPI entrypoint, routers, CORS
│   ├── config.py              # ChatConfig + loader for chat_config.yaml
│   ├── chat_config.yaml       # Runtime settings (model, thinking, tracing)
│   ├── schemas.py             # API request/response models
│   ├── engine/
│   │   └── chat_engine.py     # Orchestrates model calls + streaming
│   ├── providers/             # LLM provider abstraction layer
│   │   ├── base.py            # LLMProvider protocol, LLMResponse dataclass
│   │   ├── factory.py         # Provider factory
│   │   ├── openai_compat.py   # OpenAI-compatible client
│   │   ├── request_builders.py
│   │   └── response_parsers.py
│   ├── thinking/              # Thinking strategies + orchestrator
│   │   ├── base.py            # ThinkingStrategy, StreamParser, data models
│   │   ├── orchestrator.py    # Strategy registry and routing
│   │   └── strategies/
│   │       ├── direct.py      # No explicit thinking (fastest)
│   │       └── cot.py         # Chain-of-thought with token budgets
│   ├── routes/                # API routes (conversations, runs)
│   ├── storage/               # SQLite schema + repositories
│   │   ├── db.py
│   │   ├── schema.sql
│   │   └── repositories/
│   │       ├── conversation_repo.py
│   │       └── trace_repo.py
│   ├── reporting/             # Report builder for runs
│   └── utils/                 # Token counting, prompt helpers
├── ui/                        # Frontend (React + Vite)
│   └── src/
│       ├── components/        # Conversation UI, thinking panel, trace panel
│       ├── hooks/             # Zustand store, SSE hook
│       ├── api/               # REST + SSE client
│       └── types/             # Shared TS types
├── ARCHITECTURE.md            # Detailed architecture documentation
├── Procfile                   # Dev process manager
├── justfile                   # Dev tasks
└── var/                       # SQLite DB and runtime artifacts
```

## Thinking System

The backend supports two reasoning strategies under `orchestrator/thinking/strategies/`:

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `direct` | Single model call, no explicit reasoning | Fast responses, gpt-oss with native reasoning |
| `cot` | Chain-of-thought with `[THINK]...[/THINK]` tags | Models without native reasoning support |

**Native Reasoning (gpt-oss)**: When using gpt-oss models, set `reasoning_effort` (low/medium/high) in config. The model's native reasoning is captured and displayed as `thinking_summary`.

**Token Budgeting (TALE-EP)**: The CoT strategy uses token budgets to constrain thinking, achieving 67% token reduction while maintaining accuracy.

The `ChatEngine` uses `ThinkingOrchestrator` to select a strategy based on config mapping:

```yaml
thinking:
  mode_mapping:
    default: "direct"    # Fast path
    thinking: "direct"   # For gpt-oss (native reasoning)
    # Use "cot" for thinking mode with non-gpt-oss models
```

## Provider Abstraction

All LLM interactions go through the provider layer (`orchestrator/providers/`):

- **Dual endpoint support**: Tries `/v1/responses` first, falls back to `/v1/chat/completions`
- **Retry logic**: Exponential backoff with jitter for transient failures
- **Native reasoning**: Captures gpt-oss reasoning via separate callback
- **Tool support**: Structured tool calls with gpt-oss models

## Data & Tracing

SQLite stores three core entities:

| Table | Description |
|-------|-------------|
| `conversations` | Chat sessions with title, summary, status |
| `runs` | One run per user message, stores final answer + thinking summary |
| `trace_events` | Granular timeline of LLM requests/responses/errors/thinking steps |

Thinking steps are stored as trace_events with `event_type="thinking"`. The UI uses `thinking_summary` for display. Detailed traces are available via `/api/runs/{id}/timeline`.

## API Summary

### Conversations

- `POST /api/conversations` - Create conversation
- `GET /api/conversations` - List conversations
- `GET /api/conversations/{id}` - Get conversation + runs
- `PATCH /api/conversations/{id}` - Update (title, summary, status)
- `DELETE /api/conversations/{id}` - Delete conversation

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

### System

- `GET /api/health` - Health check
- `GET /api/config` - Get current configuration

## Configuration

All runtime settings live in `orchestrator/chat_config.yaml`:

```yaml
provider:
  base_url: ${LLM_BASE_URL:-http://127.0.0.1:1234}
  api_key: ${LLM_API_KEY:-}
  endpoint: "responses"       # responses | chat_completions | auto
  fallback_on_404: true

model:
  name: "openai/gpt-oss-20b"
  temperature: 1.0
  max_tokens: 4096
  reasoning_effort: "medium"  # For gpt-oss: low | medium | high

context:
  max_messages: 50
  max_tokens: 6000

thinking:
  mode_mapping:
    default: "direct"
    thinking: "direct"
```

Environment variable syntax:
- `${VAR}` - Required, errors if not set
- `${VAR:-default}` - Optional with default value

Changes require a backend restart.

## Notes

- Evaluation tables (`eval_runs`, `eval_samples`) exist in `schema.sql` but are not wired to routes yet
- The `architecture-diagram.html` file provides a visual overview (open in browser)
