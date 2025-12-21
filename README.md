# Reasoning Runtime

A local web application for running reasoning tasks with an orchestrated solver loop.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (localhost:3000)                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Vite + React UI                                         │   │
│  │  - Run List | Timeline | Step Cards | Artifact Viewer    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP + SSE
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Orchestrator API (localhost:9000)                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │  Routes  │ │  Engine  │ │  Tools   │ │  Storage         │   │
│  │ /api/*   │ │ state_   │ │ python   │ │ SQLite + Artifacts│   │
│  │          │ │ machine  │ │ tests    │ │                  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP (OpenAI-compat)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Model Servers (llama.cpp)                                      │
│  Router:8001 │ Planner:8002 │ Worker-Gen:8003 │                │
│  Worker-Code:8004 │ Critic:8005                                 │
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
reasoning-runtime/
├── orchestrator/           # Python backend
│   ├── app.py             # FastAPI routes
│   ├── config.py          # Configuration
│   ├── engine/            # Solver loop
│   │   ├── state_machine.py
│   │   ├── gates.py
│   │   ├── budgets.py
│   │   └── stuck.py
│   ├── models/            # LLM clients
│   │   ├── base.py
│   │   └── openai_compat.py
│   ├── tools/             # Executable tools
│   │   ├── python_tool.py
│   │   ├── tests_tool.py
│   │   └── file_tool.py
│   ├── storage/           # Persistence
│   │   ├── sqlite.py
│   │   └── artifacts.py
│   └── reporting/         # Report generation
│       └── report_builder.py
├── ui/                    # React frontend
│   └── src/
│       ├── components/
│       ├── hooks/
│       ├── api/
│       └── types/
├── var/                   # Runtime data (gitignored)
├── scripts/               # Helper scripts
├── Procfile              # Process definitions
├── pyproject.toml        # Python config
└── justfile              # Dev commands
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/runs` | Create new run |
| GET | `/api/runs` | List all runs |
| GET | `/api/runs/{id}` | Get run details |
| GET | `/api/runs/{id}/stream` | SSE event stream |
| GET | `/api/runs/{id}/events` | Get run events |
| GET | `/api/runs/{id}/report` | Get human-readable report |
| GET | `/api/artifacts/{ref}` | Get artifact content |
| GET | `/api/profiles` | List available profiles |
| GET | `/api/health` | Health check |

## Solver Loop Stages

Baseline (single-trajectory):

1. **Route** - Analyze task, determine type and required gates
2. **Plan** - Create step-by-step execution plan
3. **Execute** - Worker executes actions, calls tools
4. **Critique** - Critic evaluates the draft answer
5. **Revise** - Worker addresses critique (if needed)
6. **Finalize** - Check gates, accept or reject

Forked (multi-trajectory):

1. **Route** - Analyze task, determine type and required gates
2. **Plan Fork** - Generate multiple diverse candidate plans
3. **Execute Candidates** - Run each plan end-to-end in isolation
4. **Discriminate** - Judge selects the best candidate without rewriting
5. **Verify** - Adversarial verifier attempts to falsify the candidate
6. **Finalize** - Gate checks scoped to the selected candidate

## Configuration

Profiles are defined in `orchestrator/config.py`:

```python
PROFILES = {
    "local_m4": Profile(
        name="local_m4",
        endpoints=ModelEndpoints(
            router="http://127.0.0.1:8001",
            planner="http://127.0.0.1:8002",
            worker_general="http://127.0.0.1:8003",
            worker_code="http://127.0.0.1:8004",
            critic="http://127.0.0.1:8005",
        ),
        budgets=BudgetConfig(
            max_steps=50,
            max_tool_calls=20,
            max_time_seconds=300,
            max_revisions=3,
        ),
        num_candidates=3,
    ),
}
```

## Evaluation

Run the baseline vs forked comparison on a JSONL dataset:

```bash
uv run python -m orchestrator.eval.run_eval --dataset eval/sample.jsonl --profile local_m4
```

Dataset format (one JSON per line):

```json
{\"prompt\": \"Compute 22 + 66 * 88.\", \"expected_number\": 5830}
```

Optional fields:
- `expected` (string substring match)
- `expected_regex` (regex search)
- `expected_number` (numeric match)
- `test_code` (pytest code, evaluated against a Python code block in the answer)

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

## License

MIT
