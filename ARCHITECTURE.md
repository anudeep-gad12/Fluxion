# Reasoner Architecture

This document maps the current system in detail. It is aligned to the current codebase (FastAPI backend + React UI + pluggable thinking strategies + SQLite tracing).

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
│  ┌──────────────┐   ┌────────────────────┐   ┌──────────────────────────┐    │
│  │   Routes     │───│    ChatEngine      │───│      Repositories         │    │
│  │ /api/*       │   │  model + thinking  │   │  conversations/runs/calls │    │
│  └──────────────┘   └─────────┬──────────┘   └─────────────┬────────────┘    │
└──────────────────────────────┼────────────────────────────┼─────────────────┘
                               │                            │
                               ▼                            ▼
┌────────────────────────────────────────┐  ┌─────────────────────────────────┐
│    LLM Server (LM Studio default)      │  │      SQLite (var/traces.sqlite) │
│    OpenAI-compatible API               │  │  conversations | runs | calls    │
└────────────────────────────────────────┘  └─────────────────────────────────┘
```

## Backend Architecture

### Entry Point

- `orchestrator/app.py`: FastAPI app, CORS, routers, health/config endpoints, lifespan hook.

### Core Orchestration

- `orchestrator/engine/chat_engine.py`
  - Builds message history from prior runs.
  - Delegates reasoning to `ThinkingOrchestrator`.
  - Streams tokens by parsing `[THINK]...[/THINK]` blocks into separate thinking/answer streams.
  - Writes traces (`runs`, `model_calls`) and updates `thinking_summary`.

### Thinking System

- `orchestrator/thinking/orchestrator.py`: strategy registry and routing.
- `orchestrator/thinking/base.py`:
  - `ThinkingStrategy` abstract class.
  - `ThinkingResult` and `ThinkingStep` data models.
  - `StreamParser` that separates thinking vs answer tokens.
- Strategies (all under `orchestrator/thinking/strategies/`):
  - `direct`: no explicit reasoning, single model call.
  - `cot`: chain-of-thought with `[THINK]` tags.
  - `auto`: complexity detection routes to strategy.
  - `self_consistency`: N candidates + majority vote.
  - `self_reflection`: critique + revision loop.
  - `chain_of_draft`: minimal reasoning tokens.
- `orchestrator/thinking/complexity.py`: heuristic complexity detection.

### Routes

- `orchestrator/routes/conversations.py`: CRUD for conversations.
- `orchestrator/routes/runs.py`: run creation, SSE streaming, events, report, thinking traces.
  - Runs are streamed via an in-memory queue keyed by `run_id`.
  - SSE events include token streams and completion markers.

### Storage

- `orchestrator/storage/db.py`: SQLite connection and schema init.
- `orchestrator/storage/schema.sql`: tables and indexes.
- `orchestrator/storage/repositories/`:
  - `ConversationRepo`: conversation CRUD + summary updates.
  - `TraceRepo`: run lifecycle, model calls, and thinking traces.

### Reporting

- `orchestrator/reporting/report_builder.py`: builds a basic markdown report and a timeline structure for UI consumption.

### Utilities

- `orchestrator/utils/tokens.py`: token counting using `tiktoken`.
- `orchestrator/utils/prompts.py`: prompt loading helper (not currently wired into `ChatEngine`).

## Frontend Architecture

### App Shell

- `ui/src/App.tsx`: main layout with a collapsible sidebar and a trace panel.

### State & Data Flow

- `ui/src/hooks/useStore.ts`: Zustand store for conversations, runs, events, streaming text, and UI state.
- `ui/src/api/client.ts`: REST + SSE client for the backend.
- `ui/src/hooks/useSSE.ts`: subscribes to `/api/runs/{id}/stream` and updates streaming state.

### UI Components

- `ConversationList`: fetches conversations, selection + deletion.
- `ConversationView`: renders chat turns, triggers new runs, and attaches SSE.
- `ThinkingPanel`: shows streaming thinking tokens and persisted summaries.
- `DetailPanel`: shows raw trace events; acts as a debugging panel.

## Request Lifecycle

### 1) Create a run

`POST /api/conversations/{id}/runs` creates a run and returns a stream URL.

Backend flow:

1. Create run record (`runs` table) with `status=running`.
2. Build messages from conversation history.
3. Call `ChatEngine.chat(...)`.
4. `ChatEngine` selects a thinking strategy and makes model calls.
5. Tokens are streamed back over SSE as they arrive.
6. Final answer and thinking summary are persisted to `runs`.
7. `model_calls` rows store thinking steps and metadata.

### 2) Stream tokens and events

- The backend emits:
  - `THINKING_TOKEN`: tokens inside `[THINK]...[/THINK]` sections.
  - `TOKEN`: tokens for the final answer section.
  - `CHAT_STARTED`, `CHAT_COMPLETED`, `CHAT_FAILED` events.
  - A final SSE `complete` event with final status and answer.

- The frontend:
  - Uses `useSSE` to append streaming tokens to the UI.
  - Stops streaming on `complete` or `error`.

## Data Model

### conversations

- `conversation_id`: primary key
- `title`, `summary`, `status`, `metadata_json`
- `created_at`

### runs

- `run_id`, `conversation_id`, `created_at`
- `user_message`, `system_prompt_snapshot`
- `profile_name`, `mode`, `model_config_snapshot`
- `final_answer`, `thinking_summary`, `status`, `error_message`
- `usage_stats`

### model_calls

- One row per thinking step or model call
- `step_type` + `content`
- `metadata_json` includes both internal and UI-friendly thinking data

### eval tables

`eval_runs` and `eval_samples` are present in `schema.sql` but are not wired to routes yet.

## API Surface

### Conversations

- `POST /api/conversations`
- `GET /api/conversations`
- `GET /api/conversations/{id}`
- `PATCH /api/conversations/{id}`
- `DELETE /api/conversations/{id}`

### Runs

- `POST /api/runs`
- `POST /api/conversations/{id}/runs`
- `GET /api/runs`
- `GET /api/runs/{id}`
- `GET /api/runs/{id}/stream`
- `GET /api/runs/{id}/events`
- `GET /api/runs/{id}/report`
- `GET /api/runs/{id}/thinking`

### System

- `GET /api/health`
- `GET /api/config`

## Configuration

- `orchestrator/chat_config.yaml` is the source of truth for model params, context limits, tracing, and thinking strategy selection.
- `orchestrator/config.py` loads and caches the configuration.

## Streaming & Trace Handling

- `ChatEngine` parses streaming tokens with `StreamParser` to separate thinking vs answer.
- `runs.py` holds an in-memory queue per active run to serve SSE.
- `TraceRepo.add_thinking_step(...)` stores both internal and UI-friendly representations of each step.
- `GET /api/runs/{id}/thinking` returns user-only, internal-only, or full thinking detail.

## UI Trace Inspection

- `DetailPanel` fetches `GET /api/runs/{id}/events` and shows raw trace JSON.
- A toggle filters internal vs user-facing events (based on event metadata).

## Deployment Notes

- The backend runs on `127.0.0.1:9000` by default.
- The UI runs on `127.0.0.1:3000`.
- The LLM endpoint default is `http://127.0.0.1:1234`.

For a visual overview, open `architecture-diagram.html` in a browser.
