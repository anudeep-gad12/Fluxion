# Reasoner

A local AI chat application with a FastAPI backend, a React + Vite UI, and a pluggable thinking system. It streams tokens in real time, stores full traces in SQLite, and exposes a small REST + SSE API for the UI.

## What It Does

- Runs local or OpenAI-compatible LLMs via HTTP (LM Studio by default)
- Supports multiple reasoning strategies (direct, CoT, auto routing, self-consistency, self-reflection, chain-of-draft)
- Streams answer and thinking tokens over SSE
- Persists conversations, runs, and thinking traces in SQLite
- Provides a UI for chats, streaming, and raw trace inspection

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
  - ThinkingOrchestrator: strategy selection
  - SQLite repositories (conversations, runs, model_calls)
        |
        | OpenAI-compatible HTTP
        v
Local LLM (LM Studio / llama.cpp / vLLM)
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

- **LM Studio** (default): run a model on `http://127.0.0.1:1234`
- **llama.cpp**: use `./scripts/start_models.sh` and update `orchestrator/chat_config.yaml`

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
│   ├── thinking/              # Thinking strategies + orchestrator
│   ├── routes/                # API routes (conversations, runs)
│   ├── storage/               # SQLite schema + repositories
│   ├── reporting/             # Report builder for runs
│   ├── models/                # OpenAI-compatible client (utility)
│   └── utils/                 # Token counting, prompt helpers
├── ui/                        # Frontend (React + Vite)
│   └── src/
│       ├── components/        # Conversation UI, thinking panel, trace panel
│       ├── hooks/             # Zustand store, SSE hook
│       ├── api/               # REST + SSE client
│       └── types/             # Shared TS types
├── ARCHITECTURE.md            # Detailed architecture map
├── Procfile                   # dev process manager
├── justfile                   # dev tasks
└── var/                        # SQLite DB and runtime artifacts
```

## Thinking System (Backend)

The backend supports multiple reasoning strategies under `orchestrator/thinking`:

- `direct`: single model call, no explicit reasoning
- `cot`: chain-of-thought using `[THINK]...[/THINK]` tags
- `auto`: routes by complexity (see `thinking/complexity.py`)
- `self_consistency`: parallel candidates + majority vote
- `self_reflection`: critique + revise loop
- `chain_of_draft`: minimal drafts for faster responses

The `ChatEngine` uses `ThinkingOrchestrator` to select a strategy based on config or a request override.

## Data & Tracing

SQLite stores three core entities:

- `conversations`: chat sessions and summaries
- `runs`: one run per user message
- `model_calls`: each thinking step or model call

Thinking traces are stored in `model_calls` with both internal and UI-friendly metadata. The UI uses `thinking_summary` for display, and detailed thinking steps are available via `/api/runs/{id}/thinking`.

## API Summary

### Conversations

- `POST /api/conversations`
- `GET /api/conversations`
- `GET /api/conversations/{id}`
- `PATCH /api/conversations/{id}`
- `DELETE /api/conversations/{id}`

### Runs

- `POST /api/conversations/{id}/runs`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{id}`
- `GET /api/runs/{id}/stream` (SSE)
- `GET /api/runs/{id}/events`
- `GET /api/runs/{id}/report`
- `GET /api/runs/{id}/thinking`

### System

- `GET /api/health`
- `GET /api/config`

## Configuration

All runtime settings live in `orchestrator/chat_config.yaml` and are loaded by `orchestrator/config.py`. It controls:

- Model endpoint + generation parameters
- Context window limits
- Default thinking strategy and thresholds
- Tracing options

Changes require a backend restart.

## Notes

- `orchestrator/models/openai_compat.py` is an optional reusable client. The current `ChatEngine` calls the OpenAI-compatible endpoint directly via `httpx`.
- Evaluation tables (`eval_runs`, `eval_samples`) exist in `orchestrator/storage/schema.sql` but are not wired to routes yet.
