# Reasoning Runtime

A local web application for running reasoning tasks with an orchestrated solver loop.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (localhost:3000)                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Vite + React + Zustand                                  │   │
│  │  ConversationList │ ConversationView │ DetailPanel       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP + SSE (real-time tokens)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Backend (localhost:9000)                               │
│  ┌──────────┐ ┌────────────┐ ┌─────────────────────────────┐   │
│  │  Routes  │ │ ChatEngine │ │  Storage                    │   │
│  │ /api/*   │ │ streaming  │ │  SQLite (traces.sqlite)     │   │
│  │          │ │ + tracing  │ │  conversations/runs/calls   │   │
│  └──────────┘ └────────────┘ └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP (OpenAI-compatible)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LM Studio (localhost:1234)                                     │
│  Local LLM inference with streaming support                     │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- pnpm (`npm install -g pnpm`)
- uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- llama.cpp (for local model serving)
- honcho (`pip install honcho`) - optional, for process supervision

## Quick Start

### 1. Install dependencies

```bash
# Python dependencies
uv sync

# UI dependencies
cd ui && pnpm install && cd ..
```

Or using just:
```bash
just install
```

### 2. Start a model server

#### Option A: LM Studio (Recommended)

If you have LM Studio installed with models:

1. Open **LM Studio**
2. Go to **Local Server** tab (left sidebar)
3. Load any model (e.g., Mistral, Llama, Qwen)
4. Click **Start Server** (runs on port 1234)

That's it! The app is pre-configured to use LM Studio.

#### Option B: llama.cpp

```bash
./scripts/start_models.sh ~/path/to/model.gguf
```

Then change the profile in `orchestrator/config.py` from `lmstudio` to `local_single`.

### 3. Start the application

```bash
# Using honcho (starts UI + API)
honcho start

# Or start separately:
# Terminal 1: API
uv run uvicorn orchestrator.app:app --host 127.0.0.1 --port 9000 --reload

# Terminal 2: UI
cd ui && pnpm dev
```

### 4. Open the UI

Visit http://localhost:3000

## Project Structure

```
reasoner/
├── orchestrator/               # Python backend
│   ├── app.py                  # FastAPI entry point
│   ├── config.py               # Configuration loader
│   ├── schemas.py              # Pydantic request/response models
│   ├── chat_config.yaml        # Runtime settings
│   │
│   ├── engine/                 # Core business logic
│   │   └── chat_engine.py      # LLM orchestration + streaming
│   │
│   ├── routes/                 # API route modules
│   │   ├── conversations.py    # Conversation CRUD
│   │   └── runs.py             # Run creation + SSE streaming
│   │
│   ├── models/                 # LLM clients
│   │   ├── base.py             # Abstract interface
│   │   └── openai_compat.py    # OpenAI-compatible client
│   │
│   ├── storage/                # Data layer
│   │   ├── db.py               # SQLite connection manager
│   │   ├── schema.sql          # Table definitions
│   │   └── repositories/
│   │       ├── conversation_repo.py
│   │       └── trace_repo.py
│   │
│   ├── reporting/              # Report generation
│   │   └── report_builder.py
│   │
│   ├── utils/                  # Utilities
│   │   ├── tokens.py           # Token counting
│   │   └── prompts.py          # Prompt helpers
│   │
│   └── prompts/                # Prompt templates
│       └── chat.txt            # Default system prompt
│
├── ui/                         # React frontend
│   └── src/
│       ├── App.tsx             # Main layout
│       ├── api/
│       │   └── client.ts       # API client
│       ├── components/
│       │   ├── ConversationList.tsx
│       │   ├── ConversationView.tsx
│       │   ├── DetailPanel.tsx
│       │   └── ui/             # Reusable UI components
│       ├── hooks/
│       │   ├── useStore.ts     # Zustand store
│       │   └── useSSE.ts       # SSE subscription
│       └── types/
│           └── index.ts
│
├── var/                        # Runtime data (gitignored)
│   └── traces.sqlite           # SQLite database
├── logs/                       # Server logs
├── Procfile                    # Process definitions
├── pyproject.toml              # Python config
└── justfile                    # Dev commands
```

## API Endpoints

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/conversations` | Create new conversation |
| GET | `/api/conversations` | List conversations |
| GET | `/api/conversations/{id}` | Get conversation with runs |
| PATCH | `/api/conversations/{id}` | Update title/status |
| DELETE | `/api/conversations/{id}` | Delete conversation + runs |

### Runs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/conversations/{id}/runs` | Send message to conversation |
| POST | `/api/runs` | Create standalone run |
| GET | `/api/runs` | List all runs |
| GET | `/api/runs/{id}` | Get run details |
| GET | `/api/runs/{id}/stream` | SSE event stream |
| GET | `/api/runs/{id}/events` | Get logged events |
| GET | `/api/runs/{id}/report` | Get markdown report |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/config` | Get current configuration |

## Chat Flow

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│   User      │────▶│  ChatEngine  │────▶│  LM Studio │
│   Message   │     │  (streaming) │     │    LLM     │
└─────────────┘     └──────────────┘     └────────────┘
                           │
                    ┌──────▼──────┐
                    │   SQLite    │
                    │  (traces)   │
                    └─────────────┘
```

1. **Receive Message** - User sends message to conversation
2. **Build Context** - Load conversation history, construct messages array
3. **Stream Response** - Call LLM with streaming, emit tokens via SSE
4. **Log Trace** - Store model call with full messages/response for debugging
5. **Return Result** - Final answer saved to run, UI updates

## Configuration

Settings are defined in `orchestrator/chat_config.yaml`:

```yaml
# LLM endpoint
endpoint: "http://127.0.0.1:1234"

# Model parameters
model:
  temperature: 0.7
  max_tokens: 4096
  seed: null

# Context management
context:
  max_messages: 50
  max_tokens: 6000
  reserve_for_response: 2048
  truncation_strategy: sliding_window

# System prompt
system_prompt: "You are a helpful AI assistant..."

# Tracing
tracing:
  enabled: true
  log_level: info
  log_model_calls: true
```

## Development

```bash
# Run linting
just lint

# Run formatting
just fmt

# Run tests
just test

# Clean generated files
just clean
```